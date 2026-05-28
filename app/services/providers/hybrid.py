"""Hybrid Provider — combina Keepa + SP-API.

Keepa aporta:  monthlySold, salesRankDrops, Buy Box stats por seller,
               rating, reviews, outOfStock%, historial de precios
SP-API aporta: listing restrictions (can_sell), fees EXACTOS,
               competitive pricing real-time, catalog oficial

Estrategia:
1. Keepa batch (rápido, datos históricos ricos)
2. SP-API restrictions (can_sell por seller)
3. SP-API fees (solo para items vendibles, fees exactos)
4. Merge: SP-API sobrescribe fees/pricing, Keepa mantiene históricos
"""

import asyncio
import logging

from app.services.providers.base import (
    DOMAIN_MAP,
    MARKETPLACE_IDS,
    FeesResult,
    ProductData,
    RestrictionResult,
)
from app.services.providers.keepa import KeepaProvider
from app.services.providers.spapi import SPAPIProvider

logger = logging.getLogger(__name__)


class HybridProvider:
    """Combina datos de Keepa y SP-API en un solo ProductData enriquecido."""

    def __init__(
        self,
        keepa: KeepaProvider,
        spapi: SPAPIProvider | None = None,
        seller_id: str | None = None,
        marketplace: str = "us",
    ) -> None:
        self._keepa = keepa
        self._spapi = spapi
        self._seller_id = seller_id
        self._marketplace = marketplace

    async def close(self) -> None:
        await self._keepa.close()
        if self._spapi:
            await self._spapi.close()

    @property
    def has_spapi(self) -> bool:
        return self._spapi is not None and self._spapi.is_configured

    async def resolve_code_to_asin(self, code: str, domain: int = 1) -> str | None:
        """Resolver UPC/EAN → ASIN. Intenta SP-API primero (más confiable), Keepa como fallback."""
        # SP-API Catalog Search (más confiable, datos oficiales de Amazon)
        if self.has_spapi:
            asin = await self._spapi.resolve_code_to_asin(code, domain=domain)
            if asin:
                logger.debug("Resolved %s → %s via SP-API", code, asin)
                return asin

        # Keepa fallback
        asin = await self._keepa.resolve_code_to_asin(code, domain=domain)
        if asin:
            logger.debug("Resolved %s → %s via Keepa", code, asin)
        return asin

    async def get_products_enriched(
        self,
        asins: list[str],
        domain: int = 1,
        check_restrictions: bool = True,
        fetch_fees: bool = True,
    ) -> dict[str, ProductData | None]:
        """Pipeline completo: Keepa → SP-API restrictions → SP-API fees → merge.

        Args:
            asins: Lista de ASINs a procesar
            domain: Keepa domain ID
            check_restrictions: Si verificar listing restrictions (requiere SP-API)
            fetch_fees: Si obtener fees exactos de SP-API
        """
        if not asins:
            return {}

        # ── Paso 1: Keepa batch (datos históricos + velocity + Buy Box) ──
        keepa_data = await self._keepa.get_products_batch(asins, domain=domain)

        # Si no hay SP-API, retornar solo Keepa
        if not self.has_spapi:
            logger.info("Hybrid: sin SP-API, retornando solo Keepa para %d ASINs", len(asins))
            return keepa_data

        # ASINs con datos de Keepa
        found_asins = [asin for asin, data in keepa_data.items() if data is not None]

        if not found_asins:
            return keepa_data

        # ── Paso 2: SP-API listing restrictions (concurrente) ──
        restrictions: dict[str, RestrictionResult] = {}
        if check_restrictions and self._seller_id:
            logger.info("Hybrid: verificando restrictions para %d ASINs", len(found_asins))
            restrictions = await self._spapi.check_listing_restrictions_batch(
                found_asins, seller_id=self._seller_id, marketplace=self._marketplace,
            )

        # ── Paso 2b: SP-API FBA Eligibility (concurrente) ──
        fba_eligibility: dict[str, bool | None] = {}
        if check_restrictions and found_asins:
            # Solo verificar items que pueden venderse (o no verificados)
            eligible_to_check = [
                a for a in found_asins
                if restrictions.get(a) is None or restrictions.get(a).can_sell is not False
            ]
            if eligible_to_check:
                logger.info("Hybrid: verificando FBA eligibility para %d ASINs", len(eligible_to_check))
                fba_eligibility = await self._spapi.check_fba_eligibility_batch(
                    eligible_to_check, marketplace=self._marketplace,
                )

        # ── Paso 3: SP-API fees (solo para items vendibles) ──
        fees: dict[str, FeesResult | None] = {}
        if fetch_fees:
            # Determinar items para fees: vendibles + con Buy Box price
            fee_requests: list[tuple[str, float]] = []
            for asin in found_asins:
                product = keepa_data[asin]
                restriction = restrictions.get(asin)

                # Skip si explícitamente no puede vender
                if restriction and restriction.can_sell is False:
                    continue

                # Necesitamos un precio para estimar fees
                price = product.buy_box_price
                if price and price > 0:
                    fee_requests.append((asin, price))

            if fee_requests:
                logger.info("Hybrid: obteniendo fees para %d ASINs vendibles", len(fee_requests))
                fees = await self._spapi.get_fees_estimate_batch(
                    fee_requests, marketplace=self._marketplace,
                )

        # ── Paso 4: SP-API competitive pricing ──
        pricing_data = {}
        if found_asins:
            # Competitive pricing acepta hasta 20 ASINs por request
            chunks = [found_asins[i:i + 20] for i in range(0, len(found_asins), 20)]
            for chunk in chunks:
                chunk_pricing = await self._spapi.get_competitive_pricing(
                    chunk, marketplace=self._marketplace,
                )
                pricing_data.update(chunk_pricing)

        # ── Paso 5: SP-API Batch Item Offers (Buy Box real-time + lowest prices) ──
        offers_data = {}
        sellable_asins = [
            a for a in found_asins
            if keepa_data.get(a) and (
                restrictions.get(a) is None or restrictions.get(a).can_sell is not False
            )
        ]
        if sellable_asins:
            logger.info("Hybrid: obteniendo batch item offers para %d ASINs", len(sellable_asins))
            # Batch endpoint — 20 ASINs por request en vez de 1-por-1
            offers_data = await self._spapi.get_item_offers_batch(
                sellable_asins, marketplace=self._marketplace,
            )
            # Limpiar errores
            for asin, result in list(offers_data.items()):
                if isinstance(result, Exception):
                    logger.warning("Error getting offers for %s: %s", asin, result)
                else:
                    offers_data[asin] = result

        # ── Paso 6: Merge ──
        for asin in found_asins:
            product = keepa_data[asin]
            if product is None:
                continue

            # Merge restrictions
            restriction = restrictions.get(asin)
            if restriction:
                product.can_sell = restriction.can_sell
                product.restriction_reason = restriction.reason_code
                product.restriction_message = restriction.message

            # Merge FBA eligibility
            fba_elig = fba_eligibility.get(asin)
            if fba_elig is not None:
                product.fba_eligible = fba_elig

            # Merge fees (SP-API sobrescribe Keepa si disponible)
            fee = fees.get(asin)
            if fee:
                product.sp_api_total_fees = fee.total_fees
                product.sp_api_referral_fee = fee.referral_fee
                product.sp_api_fba_fee = fee.fba_fee
                if fee.referral_fee > 0 and product.buy_box_price:
                    product.referral_fee_pct = fee.referral_fee / product.buy_box_price
                if fee.fba_fee > 0:
                    product.fba_fulfillment_fee = fee.fba_fee

            # Merge competitive pricing
            pricing = pricing_data.get(asin)
            if pricing:
                product.offer_count_new = pricing.offer_count_new
                product.offer_count_used = pricing.offer_count_used
                if pricing.trade_in_value:
                    product.trade_in_value = pricing.trade_in_value
                if pricing.sales_rank:
                    product.sales_rank = pricing.sales_rank

            # Merge item offers (datos más detallados)
            offers = offers_data.get(asin)
            if offers:
                # Buy Box price en tiempo real (más actual que Keepa)
                if offers.buy_box_price and offers.buy_box_price > 0:
                    product.buy_box_price = offers.buy_box_price
                product.lowest_price_new = offers.lowest_price_new
                product.lowest_price_used = offers.lowest_price_used
                product.buy_box_eligible_offers_new = offers.buy_box_eligible_new
                product.buy_box_eligible_offers_used = offers.buy_box_eligible_used
                # Offer counts más detallados (FBA vs FBM)
                if offers.offer_count_new_fba or offers.offer_count_new_fbm:
                    product.offer_count_fba = offers.offer_count_new_fba
                    product.offer_count_fbm = offers.offer_count_new_fbm

        logger.info(
            "Hybrid: %d ASINs procesados (%d restrictions, %d fees, %d offers)",
            len(found_asins), len(restrictions), len(fees), len(offers_data),
        )

        return keepa_data
