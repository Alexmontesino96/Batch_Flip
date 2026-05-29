"""Fast Scan Processor — pipeline solo SP-API, chunk-based con commits parciales.

Procesa en chunks de CHUNK_SIZE ASINs para:
- No exceder rate limits de SP-API
- Commitear progreso parcial (Render puede reciclar instancias)
- No acumular demasiado en memoria

Pipeline por chunk:
1. Batch Offers (Buy Box + lowest prices)
2. Catalog data (title, brand, dimensions)
3. Competitive Pricing (BSR, sellers, trade-in)
4. Restrictions (can_sell per seller)
5. Dual Fees (FBA + MFN en paralelo)
6. FBA Eligibility
7. Dual Profit calculation
8. Commit chunk to DB
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job import Job
from app.models.job_item import JobItem
from app.models.product import Product
from app.services.dual_profit import compute_dual_profit
from app.services.providers.base import FeesResult, OffersResult, PricingResult, RestrictionResult
from app.services.providers.spapi import SPAPIProvider

logger = logging.getLogger(__name__)

CHUNK_SIZE = 20  # ASINs por chunk (= 1 batch request de SP-API)


async def fast_scan_process(job: Job, items: list[JobItem], db: AsyncSession) -> None:
    """Procesa items en chunks con commits parciales."""
    started_at = datetime.now(timezone.utc)
    job.started_at = started_at

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
        # ── FASE 1: Resolve IDs ──
        job.progress_phase = "resolving_ids"
        await db.commit()

        for item in items:
            if item.input_id_type == "asin":
                item.asin = item.input_id
            else:
                try:
                    asin = await spapi.resolve_code_to_asin(item.input_id)
                    item.asin = asin if asin else None
                    if not asin:
                        item.status = "not_found"
                except Exception as e:
                    logger.warning("Error resolviendo %s: %s", item.input_id, e)
                    item.status = "error"
                    item.error_message = str(e)[:500]

        await db.commit()
        logger.info("Fast scan: IDs resolved for %d items", len(items))

        # Agrupar por ASIN único
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

        # ── FASE 2-7: Procesar en chunks ──
        job.progress_phase = "fetching_data"
        await db.commit()

        total_matched = 0
        total_restricted = 0
        total_profitable = 0
        total_not_found = 0
        total_errors = 0

        chunks = [unique_asins[i:i + CHUNK_SIZE] for i in range(0, len(unique_asins), CHUNK_SIZE)]
        logger.info("Fast scan: %d unique ASINs in %d chunks", len(unique_asins), len(chunks))

        for chunk_idx, chunk_asins in enumerate(chunks):
            try:
                await _process_chunk(
                    chunk_asins=chunk_asins,
                    asin_to_items=asin_to_items,
                    job=job,
                    spapi=spapi,
                    seller_id=seller_id,
                    db=db,
                )
            except Exception as e:
                logger.error("Error processing chunk %d: %s", chunk_idx, e)
                # Mark chunk items as error
                for asin in chunk_asins:
                    for item in asin_to_items.get(asin, []):
                        if item.status == "pending":
                            item.status = "error"
                            item.error_message = f"Chunk error: {str(e)[:200]}"

            # Commit chunk + update progress
            for asin in chunk_asins:
                for item in asin_to_items.get(asin, []):
                    if item.status == "matched":
                        total_matched += 1
                        if item.profit is not None and float(item.profit) > 0:
                            total_profitable += 1
                    elif item.status == "restricted":
                        total_restricted += 1
                    elif item.status == "not_found":
                        total_not_found += 1
                    elif item.status == "error":
                        total_errors += 1

            job.processed_items = (chunk_idx + 1) * CHUNK_SIZE
            job.matched_items = total_matched
            job.restricted_items = total_restricted
            job.profitable_items = total_profitable
            job.error_items = total_not_found + total_errors
            await db.commit()

            logger.info(
                "Fast scan chunk %d/%d done: %d matched, %d restricted",
                chunk_idx + 1, len(chunks), total_matched, total_restricted,
            )

        # ── Finalizar ──
        job.progress_phase = "persisting"
        job.processed_items = len(items)
        job.status = "completed_with_errors" if (total_not_found or total_errors) else "completed"
        job.completed_at = datetime.now(timezone.utc)

        elapsed_hours = (job.completed_at - started_at).total_seconds() / 3600
        if elapsed_hours > 0:
            job.processing_speed = round(job.total_items / elapsed_hours, 2)

        await db.commit()

        logger.info(
            "Fast scan completado: %d total, %d matched, %d restricted, %d profitable, %.0f items/hr",
            job.total_items, total_matched, total_restricted, total_profitable,
            job.processing_speed or 0,
        )

    except Exception as e:
        logger.exception("Fast scan failed for job %s: %s", job.id, e)
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    finally:
        await spapi.close()


async def _process_chunk(
    chunk_asins: list[str],
    asin_to_items: dict[str, list[JobItem]],
    job: Job,
    spapi: SPAPIProvider,
    seller_id: str,
    db: AsyncSession,
) -> None:
    """Procesa un chunk de ASINs: fetch data + analyze + populate items."""

    # Fetch todo en paralelo
    tasks = [
        spapi.get_item_offers_batch(chunk_asins, marketplace=job.marketplace),
        spapi.get_products_batch(chunk_asins),
        spapi.get_competitive_pricing(chunk_asins, marketplace=job.marketplace),
    ]
    if job.check_restrictions and seller_id:
        tasks.append(spapi.check_listing_restrictions_batch(
            chunk_asins, seller_id=seller_id, marketplace=job.marketplace,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    offers_data = results[0] if not isinstance(results[0], Exception) else {}
    catalog_data = results[1] if not isinstance(results[1], Exception) else {}
    pricing_data = results[2] if not isinstance(results[2], Exception) else {}
    restrictions = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else {}

    # Dual fees: solo para vendibles con Buy Box
    fee_requests = []
    for asin in chunk_asins:
        r = restrictions.get(asin)
        if r and r.can_sell is False:
            continue
        o = offers_data.get(asin)
        if o and o.buy_box_price and o.buy_box_price > 0:
            fee_requests.append((asin, o.buy_box_price))

    fba_fees: dict[str, FeesResult | None] = {}
    mfn_fees: dict[str, FeesResult | None] = {}
    if fee_requests:
        fba_task = spapi.get_fees_estimate_batch(fee_requests, marketplace=job.marketplace, is_fba=True)
        mfn_task = spapi.get_fees_estimate_batch(fee_requests, marketplace=job.marketplace, is_fba=False)
        fba_fees, mfn_fees = await asyncio.gather(fba_task, mfn_task)

    # FBA eligibility
    fba_eligibility: dict[str, bool | None] = {}
    if job.check_restrictions:
        sellable = [a for a in chunk_asins if not restrictions.get(a) or restrictions[a].can_sell is not False]
        if sellable:
            fba_eligibility = await spapi.check_fba_eligibility_batch(sellable, marketplace=job.marketplace)

    # Upsert products
    for asin in chunk_asins:
        existing = await db.get(Product, asin)
        offer = offers_data.get(asin)
        catalog = catalog_data.get(asin)
        pricing = pricing_data.get(asin)
        if not existing:
            db.add(Product(
                asin=asin,
                title=catalog.title if catalog else None,
                brand=catalog.brand if catalog else None,
                buy_box_price=offer.buy_box_price if offer else None,
                sales_rank=pricing.sales_rank if pricing else None,
                spapi_updated_at=datetime.now(timezone.utc),
                analysis_count=1,
            ))
        else:
            existing.analysis_count = (existing.analysis_count or 0) + 1

    # Populate items
    for asin in chunk_asins:
        offer = offers_data.get(asin)
        catalog = catalog_data.get(asin)
        pricing = pricing_data.get(asin)
        restriction = restrictions.get(asin)
        fba_elig = fba_eligibility.get(asin)

        for item in asin_to_items.get(asin, []):
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

            if offer:
                item.buy_box_price = offer.buy_box_price
                item.offer_count_new = (offer.offer_count_new_fba or 0) + (offer.offer_count_new_fbm or 0)
                item.offer_count_used = (offer.offer_count_used_fba or 0) + (offer.offer_count_used_fbm or 0)
                item.seller_count = (item.offer_count_new or 0) + (item.offer_count_used or 0)

            if pricing:
                item.sales_rank = pricing.sales_rank or (item.sales_rank)
                item.trade_in_value = pricing.trade_in_value
                if not item.offer_count_new:
                    item.offer_count_new = pricing.offer_count_new
                if not item.offer_count_used:
                    item.offer_count_used = pricing.offer_count_used

            if restriction:
                item.can_sell = restriction.can_sell
                item.restriction_reason = restriction.reason_code
                item.restriction_message = restriction.message

            if fba_elig is not None:
                item.fba_eligible = fba_elig

            # Dual profit
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
