"""Endpoint para análisis single-item — requiere autenticación.

Usa HybridProvider con credenciales del seller conectado del usuario,
NO credenciales globales del servidor.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.config import settings
from app.core.auth import get_current_user_with_db
from app.models.seller import SellerConnection
from app.schemas.analyze import SingleAnalysisRequest, SingleAnalysisResponse
from app.services.engines.profit_engine import compute_profit
from app.services.engines.velocity_engine import compute_velocity_from_sales_per_day
from app.services.file_parser import detect_id_type
from app.services.providers.base import DOMAIN_MAP
from app.services.providers.hybrid import HybridProvider
from app.services.providers.keepa import KeepaProvider
from app.services.providers.spapi import SPAPIProvider

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _resolve_profit_marketplace(fulfillment_type: str) -> str:
    return "amazon_mfn" if fulfillment_type.lower() == "mfn" else "amazon_fba"


async def _get_user_spapi(user: dict, db: AsyncSession, marketplace: str) -> tuple[SPAPIProvider | None, str | None]:
    """Obtiene SPAPIProvider con credenciales del seller conectado del user."""
    import uuid
    result = await db.execute(
        select(SellerConnection).where(
            SellerConnection.user_id == uuid.UUID(user["id"]),
            SellerConnection.is_active == True,
        ).limit(1)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return None, None
    return (
        SPAPIProvider(refresh_token=conn.get_refresh_token(), seller_id=conn.seller_id, marketplace=marketplace),
        conn.seller_id,
    )


@router.post("", response_model=SingleAnalysisResponse)
async def analyze_single(
    req: SingleAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Analizar un solo producto (requiere autenticación)."""
    if not settings.keepa_api_key:
        raise HTTPException(503, "Keepa API key no configurada")

    domain = DOMAIN_MAP.get(req.marketplace, 1)

    # Crear providers con credenciales del USER, no globales
    keepa = KeepaProvider()
    spapi, seller_id = None, None
    if req.check_restrictions:
        spapi, seller_id = await _get_user_spapi(user, db, req.marketplace)

    hybrid = HybridProvider(
        keepa=keepa, spapi=spapi,
        seller_id=seller_id,
        marketplace=req.marketplace,
    )

    try:
        id_type = detect_id_type(req.product_id)
        asin = req.product_id if id_type == "asin" else None

        if not asin:
            asin = await hybrid.resolve_code_to_asin(req.product_id, domain=domain)

        if not asin:
            raise HTTPException(404, f"No se encontró ASIN para '{req.product_id}'")

        products = await hybrid.get_products_enriched(
            [asin], domain=domain,
            check_restrictions=req.check_restrictions,
            fetch_fees=True,
        )
        product = products.get(asin)

        if not product:
            raise HTTPException(404, f"No se encontraron datos para ASIN {asin}")

        # Profit
        sale_price = product.buy_box_price
        profit_result = None
        marketplace = _resolve_profit_marketplace(req.fulfillment_type)
        fee_fixed = product.fba_fulfillment_fee if marketplace == "amazon_fba" else None

        if sale_price and req.cost_price > 0:
            profit_result = compute_profit(
                sale_price=sale_price, cost_price=req.cost_price,
                marketplace=marketplace, shipping_cost=req.shipping_cost,
                prep_cost=req.prep_cost,
                fee_rate_override=product.referral_fee_pct,
                fee_fixed_override=fee_fixed,
            )

        # Velocity
        velocity_score, days_to_sell = None, None
        if product.sales_per_day and product.sales_per_day > 0:
            vel = compute_velocity_from_sales_per_day(product.sales_per_day)
            velocity_score = vel.score
            days_to_sell = vel.estimated_days_to_sell

        return SingleAnalysisResponse(
            asin=product.asin, title=product.title, brand=product.brand,
            category=product.category, image_url=product.image_url,
            can_sell=product.can_sell, restriction_reason=product.restriction_reason,
            restriction_message=product.restriction_message,
            sales_rank=product.sales_rank, buy_box_price=product.buy_box_price,
            list_price=product.list_price,
            item_weight_grams=product.item_weight_grams,
            package_weight_grams=product.package_weight_grams,
            item_height=product.item_height,
            item_length=product.item_length,
            item_width=product.item_width,
            estimated_sale_price=sale_price,
            profit=round(profit_result.profit, 2) if profit_result else None,
            roi_pct=round(profit_result.roi * 100, 2) if profit_result else None,
            margin_pct=round(profit_result.margin * 100, 2) if profit_result else None,
            marketplace_fees=round(profit_result.marketplace_fees, 2) if profit_result else None,
            referral_fee_pct=product.referral_fee_pct,
            fba_fulfillment_fee=product.fba_fulfillment_fee,
            sp_api_total_fees=product.sp_api_total_fees,
            sp_api_referral_fee=product.sp_api_referral_fee,
            sp_api_fba_fee=product.sp_api_fba_fee,
            velocity_score=velocity_score,
            sales_per_day=round(product.sales_per_day, 2) if product.sales_per_day else None,
            estimated_days_to_sell=days_to_sell,
            monthly_sold=product.monthly_sold,
            sales_rank_drops_30=product.sales_rank_drops_30,
            seller_count=product.seller_count,
            amazon_is_seller=product.amazon_is_seller,
            buy_box_is_amazon=product.buy_box_is_amazon,
            offer_count_new=product.offer_count_new,
            offer_count_used=product.offer_count_used,
            out_of_stock_pct_90=product.out_of_stock_pct_90,
            rating=product.rating, review_count=product.review_count,
            trade_in_value=product.trade_in_value,
        )
    finally:
        await hybrid.close()
