"""Product cache — upsert datos de producto compartidos en tabla products.

Datos compartidos (title, BSR, rating, etc.) se guardan en products.
Datos per-seller (can_sell, profit) siguen en job_items.
Cache TTL: 6 horas — si keepa_updated_at < 6h, no re-fetch.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.providers.base import ProductData

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 6


def _is_cache_fresh(product: Product) -> bool:
    """Verifica si los datos de producto están frescos (< 6 horas)."""
    if not product.keepa_updated_at:
        return False
    age = datetime.now(timezone.utc) - product.keepa_updated_at
    return age < timedelta(hours=CACHE_TTL_HOURS)


async def upsert_product(db: AsyncSession, data: ProductData) -> Product:
    """Crea o actualiza un producto en la cache. Retorna el Product ORM."""
    existing = await db.get(Product, data.asin)

    if existing:
        # Actualizar solo si datos nuevos son más completos
        if data.title:
            existing.title = data.title
        if data.brand:
            existing.brand = data.brand
        if data.category:
            existing.category = data.category
        if data.product_type:
            existing.product_type = data.product_type
        if data.buy_box_price is not None:
            existing.buy_box_price = data.buy_box_price
        if data.list_price is not None:
            existing.list_price = data.list_price
        if data.sales_rank is not None:
            existing.sales_rank = data.sales_rank
        if data.monthly_sold is not None:
            existing.monthly_sold = data.monthly_sold
        if data.sales_rank_drops_30 is not None:
            existing.sales_rank_drops_30 = data.sales_rank_drops_30
        if data.rating is not None:
            existing.rating = data.rating
        if data.review_count is not None:
            existing.review_count = data.review_count
        if data.referral_fee_pct is not None:
            existing.referral_fee_pct = data.referral_fee_pct
        if data.fba_fulfillment_fee is not None:
            existing.fba_fulfillment_fee = data.fba_fulfillment_fee
        if data.seller_count:
            existing.seller_count = data.seller_count
        if data.image_url:
            existing.image_url = data.image_url
        if data.parent_asin:
            existing.parent_asin = data.parent_asin
        if data.upc_list:
            existing.upc = data.upc_list[0]

        existing.is_hazmat = data.is_hazmat
        existing.is_adult_product = data.is_adult_product
        existing.analysis_count = (existing.analysis_count or 0) + 1
        existing.keepa_updated_at = datetime.now(timezone.utc)

        return existing

    # Crear nuevo
    product = Product(
        asin=data.asin,
        title=data.title,
        brand=data.brand,
        category=data.category,
        product_type=data.product_type,
        color=data.color,
        size=data.size,
        buy_box_price=data.buy_box_price,
        list_price=data.list_price,
        sales_rank=data.sales_rank,
        monthly_sold=data.monthly_sold,
        sales_rank_drops_30=data.sales_rank_drops_30,
        rating=data.rating,
        review_count=data.review_count,
        referral_fee_pct=data.referral_fee_pct,
        fba_fulfillment_fee=data.fba_fulfillment_fee,
        seller_count=data.seller_count,
        image_url=data.image_url,
        parent_asin=data.parent_asin,
        upc=data.upc_list[0] if data.upc_list else None,
        is_hazmat=data.is_hazmat,
        is_adult_product=data.is_adult_product,
        analysis_count=1,
        keepa_updated_at=datetime.now(timezone.utc),
    )
    db.add(product)
    return product


async def upsert_products_batch(
    db: AsyncSession, products: dict[str, ProductData | None],
) -> dict[str, Product]:
    """Upsert múltiples productos. Retorna {asin: Product}."""
    result = {}
    for asin, data in products.items():
        if data:
            result[asin] = await upsert_product(db, data)
    return result
