"""Fast Scan Processor — pipeline solo SP-API, ~15K ASINs/hora.

Usa batch endpoints (20 ASINs/req) y burst buckets para máximo throughput.
No usa Keepa — pierde monthlySold, reviews, rating pero gana velocidad.

Pipeline por batch de 20 ASINs (paralelo):
1. ID Resolution: Catalog Search (UPC→ASIN) — 2/s burst ~10/s
2. Batch Fees: getMyFeesEstimates — 20/req
3. Batch Offers: getBatchItemOffers — 20/req, Buy Box + lowest prices
4. Competitive Pricing: 20/req, offer counts
5. Restrictions: 5/s paralelo
6. FBA Eligibility: 1/s (solo vendibles)
7. Profit calculation + persist
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job import Job
from app.models.job_item import JobItem
from app.services.engines.profit_engine import compute_profit
from app.services.providers.base import FeesResult, OffersResult, PricingResult, RestrictionResult
from app.services.providers.spapi import SPAPIProvider

logger = logging.getLogger(__name__)


def _resolve_profit_marketplace(fulfillment_type: str) -> str:
    return "amazon_mfn" if fulfillment_type.lower() == "mfn" else "amazon_fba"


async def fast_scan_process(job: Job, items: list[JobItem], db: AsyncSession) -> None:
    """Procesa items usando solo SP-API con batch endpoints."""
    started_at = datetime.now(timezone.utc)

    # Crear SP-API provider
    seller_id = settings.sp_api_seller_id
    if job.seller_connection_id:
        from app.models.seller import SellerConnection
        conn = await db.get(SellerConnection, job.seller_connection_id)
        if conn and conn.is_active:
            spapi = SPAPIProvider(
                refresh_token=conn.get_refresh_token(),
                seller_id=conn.seller_id,
                marketplace=job.marketplace,
            )
            seller_id = conn.seller_id
        else:
            spapi = SPAPIProvider(seller_id=seller_id, marketplace=job.marketplace)
    else:
        spapi = SPAPIProvider(seller_id=seller_id, marketplace=job.marketplace)

    try:
        # ══════════════════════════════════════
        # FASE 1: ID Resolution (UPC/EAN → ASIN)
        # ══════════════════════════════════════
        job.progress_phase = "resolving_ids"
        await db.commit()

        resolve_items = []
        for item in items:
            if item.input_id_type == "asin":
                item.asin = item.input_id
            else:
                resolve_items.append(item)

        if resolve_items:
            # SP-API Catalog Search: 2/s rate, burst ~40
            sem = asyncio.Semaphore(8)  # burst paralelo

            async def resolve_one(item: JobItem):
                async with sem:
                    try:
                        asin = await spapi.resolve_code_to_asin(item.input_id)
                        if asin:
                            item.asin = asin
                        else:
                            item.status = "not_found"
                    except Exception as e:
                        logger.warning("Error resolviendo %s: %s", item.input_id, e)
                        item.status = "error"
                        item.error_message = str(e)[:500]

            await asyncio.gather(*[resolve_one(i) for i in resolve_items])

        job.processed_items = len([i for i in items if i.asin or i.status != "pending"])
        await db.commit()

        # Agrupar por ASIN
        items_with_asin = [i for i in items if i.asin and i.status == "pending"]
        asin_to_items: dict[str, list[JobItem]] = {}
        for item in items_with_asin:
            asin_to_items.setdefault(item.asin, []).append(item)
        unique_asins = list(asin_to_items.keys())

        if not unique_asins:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # ══════════════════════════════════════
        # FASE 2: Batch Data Fetch (todo en paralelo)
        # ══════════════════════════════════════
        job.progress_phase = "fetching_data"
        await db.commit()

        # Necesitamos Buy Box prices primero para calcular fees
        # Paso 2a: Batch Offers (Buy Box price + lowest prices)
        logger.info("Fast scan: batch offers para %d ASINs", len(unique_asins))
        offers_task = spapi.get_item_offers_batch(unique_asins, marketplace=job.marketplace)

        # Paso 2b: Catalog data (title, brand, dimensiones/peso) — en paralelo
        logger.info("Fast scan: catálogo para %d ASINs", len(unique_asins))
        catalog_task = spapi.get_products_batch(unique_asins)

        # Paso 2c: Competitive Pricing (offer counts, trade-in, BSR) — en paralelo
        # Chunks de 20
        async def get_all_pricing():
            all_pricing: dict[str, PricingResult | None] = {}
            chunks = [unique_asins[i:i + 20] for i in range(0, len(unique_asins), 20)]
            for chunk in chunks:
                result = await spapi.get_competitive_pricing(chunk, marketplace=job.marketplace)
                all_pricing.update(result)
            return all_pricing

        pricing_task = get_all_pricing()

        # Paso 2d: Restrictions (5/s) — en paralelo
        restrictions_task = None
        if job.check_restrictions and seller_id:
            logger.info("Fast scan: restrictions para %d ASINs", len(unique_asins))
            restrictions_task = spapi.check_listing_restrictions_batch(
                unique_asins, seller_id=seller_id, marketplace=job.marketplace,
            )

        # Ejecutar en paralelo
        if restrictions_task:
            offers_data, catalog_data, pricing_data, restrictions = await asyncio.gather(
                offers_task, catalog_task, pricing_task, restrictions_task,
            )
        else:
            offers_data, catalog_data, pricing_data = await asyncio.gather(
                offers_task, catalog_task, pricing_task,
            )
            restrictions = {}

        # ══════════════════════════════════════
        # FASE 3: Batch Fees (necesita Buy Box price)
        # ══════════════════════════════════════
        job.progress_phase = "fetching_fees"
        await db.commit()

        # Construir fee requests: solo vendibles con Buy Box price
        fee_requests: list[tuple[str, float]] = []
        for asin in unique_asins:
            restriction = restrictions.get(asin)
            if restriction and restriction.can_sell is False:
                continue
            offer = offers_data.get(asin)
            if offer and offer.buy_box_price and offer.buy_box_price > 0:
                fee_requests.append((asin, offer.buy_box_price))

        # Dual fees: FBA y MFN en paralelo (1 batch extra = ~5-10% más lento)
        fba_fees: dict[str, FeesResult | None] = {}
        mfn_fees: dict[str, FeesResult | None] = {}
        if fee_requests:
            logger.info("Fast scan: dual batch fees (FBA+MFN) para %d ASINs", len(fee_requests))
            fba_task = spapi.get_fees_estimate_batch(fee_requests, marketplace=job.marketplace, is_fba=True)
            mfn_task = spapi.get_fees_estimate_batch(fee_requests, marketplace=job.marketplace, is_fba=False)
            fba_fees, mfn_fees = await asyncio.gather(fba_task, mfn_task)

        # ══════════════════════════════════════
        # FASE 4: FBA Eligibility (solo vendibles)
        # ══════════════════════════════════════
        fba_eligibility: dict[str, bool | None] = {}
        if job.check_restrictions:
            sellable = [a for a in unique_asins
                        if not restrictions.get(a) or restrictions[a].can_sell is not False]
            if sellable:
                job.progress_phase = "checking_fba"
                await db.commit()
                logger.info("Fast scan: FBA eligibility para %d ASINs", len(sellable))
                fba_eligibility = await spapi.check_fba_eligibility_batch(
                    sellable, marketplace=job.marketplace,
                )

        # ══════════════════════════════════════
        # FASE 5: Analysis + Populate Items
        # ══════════════════════════════════════
        job.progress_phase = "analyzing"
        await db.commit()

        marketplace = _resolve_profit_marketplace(job.fulfillment_type)
        shipping = float(job.shipping_to_amazon)
        prep = float(job.prep_cost_per_item)

        # Upsert products con datos parciales de SP-API
        from app.models.product import Product
        for asin in unique_asins:
            existing = await db.get(Product, asin)
            if not existing:
                offer = offers_data.get(asin)
                pricing = pricing_data.get(asin)
                db.add(Product(
                    asin=asin,
                    buy_box_price=offer.buy_box_price if offer else None,
                    sales_rank=pricing.sales_rank if pricing else None,
                    seller_count=(
                        (offer.offer_count_new_fba or 0) + (offer.offer_count_new_fbm or 0)
                        + (offer.offer_count_used_fba or 0) + (offer.offer_count_used_fbm or 0)
                    ) if offer else None,
                    spapi_updated_at=datetime.now(timezone.utc),
                    analysis_count=1,
                ))
            else:
                existing.analysis_count = (existing.analysis_count or 0) + 1

        for asin, item_list in asin_to_items.items():
            offer = offers_data.get(asin)
            catalog = catalog_data.get(asin)
            pricing = pricing_data.get(asin)
            restriction = restrictions.get(asin)
            fee = fees.get(asin)
            fba_elig = fba_eligibility.get(asin)

            for item in item_list:
                item.product_asin = asin
                if catalog:
                    item.title = catalog.title
                    item.brand = catalog.brand
                    item.category = catalog.category
                    item.sales_rank = catalog.sales_rank
                    item.item_weight_grams = catalog.item_weight_grams
                    item.package_weight_grams = catalog.package_weight_grams
                    item.item_height = catalog.item_height
                    item.item_length = catalog.item_length
                    item.item_width = catalog.item_width
                    item.is_hazmat = catalog.is_hazmat

                # Buy Box + offers data
                if offer:
                    item.buy_box_price = offer.buy_box_price
                    item.offer_count_new = (offer.offer_count_new_fba or 0) + (offer.offer_count_new_fbm or 0)
                    item.offer_count_used = (offer.offer_count_used_fba or 0) + (offer.offer_count_used_fbm or 0)
                    item.seller_count = item.offer_count_new + item.offer_count_used

                # Competitive pricing
                if pricing:
                    item.sales_rank = pricing.sales_rank or (catalog.sales_rank if catalog else None)
                    item.trade_in_value = pricing.trade_in_value
                    if not item.offer_count_new:
                        item.offer_count_new = pricing.offer_count_new
                    if not item.offer_count_used:
                        item.offer_count_used = pricing.offer_count_used

                # Restrictions
                if restriction:
                    item.can_sell = restriction.can_sell
                    item.restriction_reason = restriction.reason_code
                    item.restriction_message = restriction.message

                # FBA eligibility
                if fba_elig is not None:
                    item.fba_eligible = fba_elig

                # Dual Profit: FBA + MFN en 1 pasada
                from app.services.dual_profit import compute_dual_profit
                sale_price = float(item.buy_box_price) if item.buy_box_price else None
                compute_dual_profit(
                    item=item, job=job, sale_price=sale_price,
                    fba_fees=fba_fees.get(asin), mfn_fees=mfn_fees.get(asin),
                )

                # Status
                if restriction and restriction.can_sell is False:
                    item.status = "restricted"
                elif item.buy_box_price:
                    item.status = "matched"
                else:
                    item.status = "not_found"

        # ══════════════════════════════════════
        # FASE 6: Persist
        # ══════════════════════════════════════
        job.progress_phase = "persisting"

        matched = [i for i in items if i.status == "matched"]
        restricted = [i for i in items if i.status == "restricted"]
        not_found = [i for i in items if i.status == "not_found"]
        errors = [i for i in items if i.status == "error"]
        profitable = [i for i in matched if i.profit is not None and float(i.profit) > 0]

        job.matched_items = len(matched)
        job.restricted_items = len(restricted)
        job.profitable_items = len(profitable)
        job.error_items = len(not_found) + len(errors)
        job.processed_items = len(matched) + len(restricted) + len(not_found) + len(errors)
        job.status = "completed_with_errors" if (not_found or errors) else "completed"
        job.completed_at = datetime.now(timezone.utc)

        elapsed_hours = (job.completed_at - started_at).total_seconds() / 3600
        if elapsed_hours > 0:
            job.processing_speed = round(job.total_items / elapsed_hours, 2)

        await db.commit()

        logger.info(
            "Fast scan job completado: %d total, %d matched, %d restricted, "
            "%d profitable, %.0f items/hr",
            job.total_items, len(matched), len(restricted),
            len(profitable), job.processing_speed or 0,
        )

    finally:
        await spapi.close()
