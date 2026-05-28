"""Endpoint para análisis single-item — requiere autenticación.

Usa HybridProvider con credenciales del seller conectado del usuario,
NO credenciales globales del servidor.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.config import settings
from app.core.auth import get_current_user_with_db
from app.models.seller import SellerConnection
from app.schemas.analyze import (
    FulfillmentScenarioResponse,
    ProfitScenariosResponse,
    SingleAnalysisRequest,
    SingleAnalysisResponse,
)
from app.services.engines.profit_engine import compute_profit
from app.services.engines.velocity_engine import compute_velocity_from_sales_per_day
from app.services.file_parser import detect_id_type
from app.services.providers.base import DOMAIN_MAP, FeesResult, ProductData
from app.services.providers.hybrid import HybridProvider
from app.services.providers.keepa import KeepaProvider
from app.services.providers.spapi import SPAPIProvider

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _resolve_profit_marketplace(fulfillment_type: str) -> str:
    return "amazon_mfn" if fulfillment_type.lower() == "mfn" else "amazon_fba"


def _resolve_scenario_costs(req: SingleAnalysisRequest, fulfillment_type: str) -> tuple[float, float, float]:
    """Resuelve costos por escenario con fallback a campos legacy."""
    if fulfillment_type == "fba":
        shipping = req.shipping_to_amazon if req.shipping_to_amazon is not None else req.shipping_cost
        prep = req.fba_prep_cost if req.fba_prep_cost is not None else req.prep_cost
        packaging = 0.0
    else:
        shipping = req.shipping_to_customer if req.shipping_to_customer is not None else req.shipping_cost
        prep = req.mfn_prep_cost if req.mfn_prep_cost is not None else req.prep_cost
        packaging = req.mfn_packaging_cost
    return float(shipping), float(prep), float(packaging)


def _resolve_eligibility(product: ProductData, fulfillment_type: str) -> tuple[bool | None, str | None]:
    """Resuelve elegibilidad por escenario."""
    if product.can_sell is False:
        return False, product.restriction_reason or product.restriction_message

    if fulfillment_type == "fba":
        if product.fba_eligible is False:
            return False, "NOT_FBA_ELIGIBLE"
        if product.can_sell is True and product.fba_eligible is True:
            return True, None
        return None, None

    if product.can_sell is True:
        return True, None
    return product.can_sell, product.restriction_reason if product.can_sell is False else None


def _build_scenario_response(
    product: ProductData,
    cost_price: float,
    fulfillment_type: str,
    shipping_cost: float,
    prep_cost: float,
    packaging_cost: float,
    exact_fee: FeesResult | None,
) -> FulfillmentScenarioResponse:
    """Construye el resultado de profit para un escenario concreto."""
    sale_price = product.buy_box_price
    marketplace = _resolve_profit_marketplace(fulfillment_type)
    eligible_to_sell, eligibility_reason = _resolve_eligibility(product, fulfillment_type)

    referral_fee_pct = product.referral_fee_pct
    fee_fixed_override = product.fba_fulfillment_fee if marketplace == "amazon_fba" else None
    uses_exact_fees = exact_fee is not None

    if exact_fee and sale_price:
        if exact_fee.referral_fee > 0:
            referral_fee_pct = exact_fee.referral_fee / sale_price
        fee_fixed_override = exact_fee.fba_fee if fulfillment_type == "fba" else 0.0

    profit_result = None
    if sale_price and cost_price > 0:
        profit_result = compute_profit(
            sale_price=sale_price,
            cost_price=cost_price,
            marketplace=marketplace,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            prep_cost=prep_cost,
            fee_rate_override=referral_fee_pct,
            fee_fixed_override=fee_fixed_override,
        )

    return FulfillmentScenarioResponse(
        fulfillment_type=fulfillment_type,
        eligible_to_sell=eligible_to_sell,
        eligibility_reason=eligibility_reason,
        uses_exact_fees=uses_exact_fees,
        estimated_sale_price=sale_price,
        shipping_cost=shipping_cost,
        prep_cost=prep_cost,
        packaging_cost=packaging_cost,
        return_reserve=round(profit_result.return_reserve, 2) if profit_result else None,
        marketplace_fees=round(profit_result.marketplace_fees, 2) if profit_result else None,
        referral_fee_pct=referral_fee_pct,
        sp_api_total_fees=exact_fee.total_fees if exact_fee else (product.sp_api_total_fees if fulfillment_type == "fba" else None),
        sp_api_referral_fee=exact_fee.referral_fee if exact_fee else (product.sp_api_referral_fee if fulfillment_type == "fba" else None),
        sp_api_fba_fee=exact_fee.fba_fee if exact_fee else (product.sp_api_fba_fee if fulfillment_type == "fba" else None),
        profit=round(profit_result.profit, 2) if profit_result else None,
        roi_pct=round(profit_result.roi * 100, 2) if profit_result else None,
        margin_pct=round(profit_result.margin * 100, 2) if profit_result else None,
    )


async def _get_scenario_fees(
    spapi: SPAPIProvider | None,
    asin: str,
    sale_price: float | None,
    marketplace: str,
    compare_fulfillment: bool,
    selected_fulfillment: str,
) -> dict[str, FeesResult | None]:
    """Obtiene fees exactos por escenario cuando hay SP-API disponible."""
    if not spapi or not sale_price or sale_price <= 0:
        return {}

    scenarios = ["fba", "mfn"] if compare_fulfillment else [selected_fulfillment]
    tasks = [
        spapi.get_fees_estimate(
            asin,
            sale_price,
            marketplace=marketplace,
            is_fba=(scenario == "fba"),
        )
        for scenario in scenarios
    ]
    results = await asyncio.gather(*tasks)
    return dict(zip(scenarios, results))


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
    selected_fulfillment = "mfn" if req.fulfillment_type.lower() == "mfn" else "fba"
    effective_restrictions = req.check_restrictions or req.compare_fulfillment

    # Crear providers con credenciales del USER, no globales
    keepa = KeepaProvider()
    spapi, seller_id = None, None
    if effective_restrictions:
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
            check_restrictions=effective_restrictions,
            fetch_fees=True,
        )
        product = products.get(asin)

        if not product:
            raise HTTPException(404, f"No se encontraron datos para ASIN {asin}")

        sale_price = product.buy_box_price
        scenario_fees = await _get_scenario_fees(
            spapi=spapi,
            asin=asin,
            sale_price=sale_price,
            marketplace=req.marketplace,
            compare_fulfillment=req.compare_fulfillment,
            selected_fulfillment=selected_fulfillment,
        )

        fba_shipping, fba_prep, fba_packaging = _resolve_scenario_costs(req, "fba")
        mfn_shipping, mfn_prep, mfn_packaging = _resolve_scenario_costs(req, "mfn")

        fba_scenario = _build_scenario_response(
            product=product,
            cost_price=req.cost_price,
            fulfillment_type="fba",
            shipping_cost=fba_shipping,
            prep_cost=fba_prep,
            packaging_cost=fba_packaging,
            exact_fee=scenario_fees.get("fba"),
        )
        mfn_scenario = _build_scenario_response(
            product=product,
            cost_price=req.cost_price,
            fulfillment_type="mfn",
            shipping_cost=mfn_shipping,
            prep_cost=mfn_prep,
            packaging_cost=mfn_packaging,
            exact_fee=scenario_fees.get("mfn"),
        )
        selected_scenario = mfn_scenario if selected_fulfillment == "mfn" else fba_scenario

        # Velocity
        velocity_score, days_to_sell = None, None
        if product.sales_per_day and product.sales_per_day > 0:
            vel = compute_velocity_from_sales_per_day(product.sales_per_day)
            velocity_score = vel.score
            days_to_sell = vel.estimated_days_to_sell

        return SingleAnalysisResponse(
            asin=product.asin, title=product.title, brand=product.brand,
            category=product.category, image_url=product.image_url,
            selected_fulfillment_type=selected_fulfillment,
            can_sell=product.can_sell, fba_eligible=product.fba_eligible,
            restriction_reason=product.restriction_reason,
            restriction_message=product.restriction_message,
            sales_rank=product.sales_rank, buy_box_price=product.buy_box_price,
            list_price=product.list_price,
            item_weight_grams=product.item_weight_grams,
            package_weight_grams=product.package_weight_grams,
            item_height=product.item_height,
            item_length=product.item_length,
            item_width=product.item_width,
            estimated_sale_price=selected_scenario.estimated_sale_price,
            profit=selected_scenario.profit,
            roi_pct=selected_scenario.roi_pct,
            margin_pct=selected_scenario.margin_pct,
            marketplace_fees=selected_scenario.marketplace_fees,
            referral_fee_pct=selected_scenario.referral_fee_pct,
            fba_fulfillment_fee=product.fba_fulfillment_fee,
            sp_api_total_fees=selected_scenario.sp_api_total_fees,
            sp_api_referral_fee=selected_scenario.sp_api_referral_fee,
            sp_api_fba_fee=selected_scenario.sp_api_fba_fee,
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
            profit_scenarios=(
                ProfitScenariosResponse(fba=fba_scenario, mfn=mfn_scenario)
                if req.compare_fulfillment else None
            ),
            pricing_assumption=f"Both scenarios use current Buy Box price ${product.buy_box_price:.2f}. Actual MFN prices may be lower to compete without Prime." if product.buy_box_price else "Connect your Amazon account for exact pricing and eligibility data.",
        )
    finally:
        await hybrid.close()
