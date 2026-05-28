"""Batch processor — pipeline de 6 fases con HybridProvider (Keepa + SP-API).

Fases:
1. ID Resolution (UPC/EAN → ASIN via Keepa)
2. Keepa Batch Lookup (datos históricos, velocity, Buy Box stats)
3. SP-API Listing Restrictions (can_sell por seller)
4. SP-API Fees Estimate (fees exactos para items vendibles)
5. Analysis (profit, velocity, risk por item)
6. Persist (update JobItems + Job counts)
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
from app.services.engines.velocity_engine import compute_velocity_from_sales_per_day
from app.services.providers.base import ProductData
from app.services.providers.keepa import KeepaProvider
from app.services.providers.spapi import SPAPIProvider

logger = logging.getLogger(__name__)


def _resolve_profit_marketplace(fulfillment_type: str) -> str:
    return "amazon_mfn" if fulfillment_type.lower() == "mfn" else "amazon_fba"


def _populate_item_from_product(item: JobItem, product: ProductData) -> None:
    """Copia datos de ProductData a JobItem."""
    item.title = product.title
    item.brand = product.brand
    item.category = product.category
    item.sales_rank = product.sales_rank
    item.buy_box_price = product.buy_box_price
    item.amazon_is_seller = product.amazon_is_seller
    item.seller_count = product.seller_count
    item.fba_fee = product.fba_fulfillment_fee
    item.referral_fee_pct = product.referral_fee_pct
    item.multipack_qty = product.multipack_qty
    item.is_hazmat = product.is_hazmat
    item.image_url = product.image_url
    item.sales_per_day = product.sales_per_day
    item.list_price = product.list_price

    # Campos Keepa enriquecidos
    item.monthly_sold = product.monthly_sold
    item.sales_rank_drops_30 = product.sales_rank_drops_30
    item.rating = product.rating
    item.review_count = product.review_count
    item.buy_box_is_amazon = product.buy_box_is_amazon
    item.out_of_stock_pct_90 = product.out_of_stock_pct_90

    # Campos SP-API (si disponibles del HybridProvider)
    item.can_sell = product.can_sell
    item.restriction_reason = product.restriction_reason
    item.restriction_message = product.restriction_message
    item.sp_api_total_fees = product.sp_api_total_fees
    item.sp_api_referral_fee = product.sp_api_referral_fee
    item.sp_api_fba_fee = product.sp_api_fba_fee
    item.offer_count_new = product.offer_count_new
    item.offer_count_used = product.offer_count_used
    item.trade_in_value = product.trade_in_value


def _compute_velocity(item: JobItem, product: ProductData) -> None:
    """Calcula velocity score y días estimados para vender."""
    if product.sales_per_day and product.sales_per_day > 0:
        vel = compute_velocity_from_sales_per_day(product.sales_per_day)
        item.velocity_score = vel.score
        item.estimated_days_to_sell = vel.estimated_days_to_sell


def _compute_item_profit(
    item: JobItem, product: ProductData, marketplace: str,
    shipping_cost: float, prep_cost: float,
) -> None:
    """Calcula profit/ROI para un item."""
    sale_price = product.buy_box_price
    item.estimated_sale_price = sale_price

    if not sale_price or not item.cost_price or float(item.cost_price) <= 0:
        return

    # Usar SP-API fees si disponibles, sino Keepa
    fee_rate = product.referral_fee_pct
    fee_fixed = product.fba_fulfillment_fee if marketplace == "amazon_fba" else None

    try:
        pr = compute_profit(
            sale_price=sale_price,
            cost_price=float(item.cost_price),
            marketplace=marketplace,
            shipping_cost=shipping_cost,
            prep_cost=prep_cost,
            fee_rate_override=fee_rate,
            fee_fixed_override=fee_fixed,
        )
        item.profit = round(pr.profit, 2)
        item.roi_pct = round(pr.roi * 100, 4) if pr.roi else 0
        item.margin_pct = round(pr.margin * 100, 4) if pr.margin else 0
        item.marketplace_fees = round(pr.marketplace_fees, 2)
        item.shipping_cost = round(pr.shipping_cost, 2)
        item.prep_cost = round(pr.prep_cost, 2)
        item.return_reserve = round(pr.return_reserve, 2)
    except Exception as e:
        logger.warning("Error calculando profit para %s: %s", item.asin, e)


async def process_job(job_id: str, db: AsyncSession) -> None:
    """Procesa un batch job completo con pipeline de 6 fases."""
    job = await db.get(Job, UUID(job_id))
    if not job:
        logger.error("Job %s no encontrado", job_id)
        return

    started_at = datetime.now(timezone.utc)
    job.started_at = started_at
    job.status = "processing"
    await db.commit()

    # Crear providers
    keepa = KeepaProvider()
    spapi = None
    seller_id = None

    # Si hay seller_connection, crear SP-API provider con su refresh token
    if job.check_restrictions and job.seller_connection_id:
        from app.models.seller import SellerConnection
        conn = await db.get(SellerConnection, job.seller_connection_id)
        if conn and conn.is_active:
            spapi = SPAPIProvider(
                refresh_token=conn.get_refresh_token(),
                seller_id=conn.seller_id,
                marketplace=job.marketplace,
            )
            seller_id = conn.seller_id
    elif job.check_restrictions and settings.sp_api_refresh_token:
        # Fallback: usar credenciales del .env (MVP)
        spapi = SPAPIProvider(
            seller_id=settings.sp_api_seller_id,
            marketplace=job.marketplace,
        )
        seller_id = settings.sp_api_seller_id

    domain = job.domain_id

    try:
        # Cargar items del job
        result = await db.execute(
            select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.input_row)
        )
        items = list(result.scalars().all())

        if not items:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # ════════════════════════════════════════════
        # FASE 1: ID Resolution (UPC/EAN → ASIN)
        # ════════════════════════════════════════════
        job.progress_phase = "resolving_ids"
        await db.commit()

        resolve_items = []
        for item in items:
            if item.input_id_type == "asin":
                item.asin = item.input_id
            else:
                resolve_items.append(item)

        if resolve_items:
            sem = asyncio.Semaphore(settings.resolve_concurrency)

            async def resolve_one(item: JobItem):
                async with sem:
                    try:
                        asin = await keepa.resolve_code_to_asin(item.input_id, domain=domain)
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

        # ════════════════════════════════════════════
        # FASE 2: Keepa Batch Lookup
        # ════════════════════════════════════════════
        job.progress_phase = "fetching_keepa"
        await db.commit()

        items_with_asin = [i for i in items if i.asin and i.status == "pending"]
        asin_to_items: dict[str, list[JobItem]] = {}
        for item in items_with_asin:
            asin_to_items.setdefault(item.asin, []).append(item)

        unique_asins = list(asin_to_items.keys())
        all_product_data: dict[str, ProductData | None] = {}

        # Keepa batch fetch
        chunk_size = settings.keepa_batch_size
        sem = asyncio.Semaphore(settings.keepa_concurrency)

        async def fetch_chunk(chunk: list[str]):
            async with sem:
                return await keepa.get_products_batch(chunk, domain=domain)

        chunks = [unique_asins[i:i + chunk_size] for i in range(0, len(unique_asins), chunk_size)]
        chunk_results = await asyncio.gather(
            *[fetch_chunk(c) for c in chunks], return_exceptions=True,
        )
        for res in chunk_results:
            if isinstance(res, Exception):
                logger.warning("Error en batch Keepa: %s", res)
                continue
            all_product_data.update(res)

        # ════════════════════════════════════════════
        # FASE 3: SP-API Listing Restrictions
        # ════════════════════════════════════════════
        if spapi and seller_id:
            job.progress_phase = "checking_restrictions"
            await db.commit()

            # Solo verificar ASINs que Keepa encontró
            found_asins = [a for a in unique_asins if all_product_data.get(a)]

            if found_asins:
                logger.info("Fase 3: verificando restrictions para %d ASINs", len(found_asins))
                restrictions = await spapi.check_listing_restrictions_batch(
                    found_asins, seller_id=seller_id, marketplace=job.marketplace,
                )
                for asin, restriction in restrictions.items():
                    product = all_product_data.get(asin)
                    if product:
                        product.can_sell = restriction.can_sell
                        product.restriction_reason = restriction.reason_code
                        product.restriction_message = restriction.message

        # ════════════════════════════════════════════
        # FASE 4: SP-API Fees Estimate
        # ════════════════════════════════════════════
        if spapi:
            job.progress_phase = "fetching_fees"
            await db.commit()

            is_fba = job.fulfillment_type.lower() == "fba"

            # Solo pedir fees para items vendibles con Buy Box price
            fee_requests: list[tuple[str, float]] = []
            for asin, product in all_product_data.items():
                if not product:
                    continue
                # Skip items explícitamente restringidos
                if product.can_sell is False:
                    continue
                if product.buy_box_price and product.buy_box_price > 0:
                    fee_requests.append((asin, product.buy_box_price))

            if fee_requests:
                logger.info("Fase 4: obteniendo fees para %d ASINs vendibles", len(fee_requests))
                fees = await spapi.get_fees_estimate_batch(
                    fee_requests, marketplace=job.marketplace, is_fba=is_fba,
                )
                for asin, fee in fees.items():
                    product = all_product_data.get(asin)
                    if product and fee:
                        product.sp_api_total_fees = fee.total_fees
                        product.sp_api_referral_fee = fee.referral_fee
                        product.sp_api_fba_fee = fee.fba_fee
                        # SP-API fees son más precisos — override Keepa
                        if fee.referral_fee > 0 and product.buy_box_price:
                            product.referral_fee_pct = fee.referral_fee / product.buy_box_price
                        if fee.fba_fee > 0:
                            product.fba_fulfillment_fee = fee.fba_fee

        # ════════════════════════════════════════════
        # FASE 5: Analysis
        # ════════════════════════════════════════════
        job.progress_phase = "analyzing"
        await db.commit()

        marketplace = _resolve_profit_marketplace(job.fulfillment_type)
        shipping = float(job.shipping_to_amazon)
        prep = float(job.prep_cost_per_item)

        for asin, item_list in asin_to_items.items():
            product = all_product_data.get(asin)

            for item in item_list:
                if not product:
                    item.status = "not_found"
                    continue

                # Poblar todos los datos
                _populate_item_from_product(item, product)

                # Velocity
                _compute_velocity(item, product)

                # Determinar status
                if product.can_sell is False:
                    item.status = "restricted"
                    # Aún calcular profit para informar al seller
                    _compute_item_profit(item, product, marketplace, shipping, prep)
                    continue

                # Profit
                _compute_item_profit(item, product, marketplace, shipping, prep)
                item.status = "matched"

        # ════════════════════════════════════════════
        # FASE 6: Persist
        # ════════════════════════════════════════════
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

        has_issues = bool(not_found or errors)
        job.status = "completed_with_errors" if has_issues else "completed"
        job.completed_at = datetime.now(timezone.utc)

        elapsed_hours = (job.completed_at - started_at).total_seconds() / 3600
        if elapsed_hours > 0:
            job.processing_speed = round(job.total_items / elapsed_hours, 2)

        await db.commit()

        logger.info(
            "Job %s completado: %d total, %d matched, %d restricted, %d profitable, "
            "%d not_found, %d errors, %.0f items/hr",
            job_id, job.total_items, len(matched), len(restricted),
            len(profitable), len(not_found), len(errors),
            job.processing_speed or 0,
        )

    except Exception:
        logger.exception("Error procesando job %s", job_id)
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise

    finally:
        await keepa.close()
        if spapi:
            await spapi.close()
