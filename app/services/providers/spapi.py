"""Amazon SP-API provider.

Endpoints implementados:
- Catalog Items 2022-04-01
- Listing Restrictions 2021-08-01
- Product Fees v0
- Competitive Pricing v0
- Item Offers v0
- Sellers v1 (marketplace participations)

Rate limits respetados con asyncio.Semaphore por endpoint.
"""

import asyncio
import logging

import httpx

from app.config import settings
from app.services.providers.base import (
    MARKETPLACE_IDS,
    DataProvider,
    FeesResult,
    OffersResult,
    PricingResult,
    ProductData,
    RestrictionResult,
)
from app.services.providers.spapi_auth import SPAPIAuth

logger = logging.getLogger(__name__)

# SP-API base URLs por región
SPAPI_ENDPOINTS = {
    "na": "https://sellingpartnerapi-na.amazon.com",
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}

# Marketplace → región
MARKETPLACE_REGION = {
    "us": "na", "ca": "na", "mx": "na", "br": "na",
    "uk": "eu", "de": "eu", "fr": "eu", "es": "eu", "it": "eu",
    "jp": "fe", "au": "fe",
}

# Rate limit semaphores (requests por segundo)
_RATE_LIMITS = {
    "catalog": 2,
    "restrictions": 5,
    "fees": 1,
    "pricing": 2,
    "offers": 2,
    "fba": 1,
}

SPAPI_TIMEOUT = 15


def _marketplace_to_region(marketplace: str) -> str:
    return MARKETPLACE_REGION.get(marketplace, "na")


def _get_base_url(marketplace: str) -> str:
    region = _marketplace_to_region(marketplace)
    return SPAPI_ENDPOINTS[region]


def _get_marketplace_id(marketplace: str) -> str:
    return MARKETPLACE_IDS.get(marketplace, MARKETPLACE_IDS["us"])


def _weight_to_grams(measure: dict | None) -> int | None:
    """Convierte un peso de SP-API a gramos."""
    if not measure:
        return None

    value = measure.get("value")
    unit = str(measure.get("unit", "")).lower()
    if value is None:
        return None

    if unit in {"grams", "gram", "g"}:
        return int(round(value))
    if unit in {"kilograms", "kilogram", "kg"}:
        return int(round(value * 1000))
    if unit in {"pounds", "pound", "lb", "lbs"}:
        return int(round(value * 453.592))
    if unit in {"ounces", "ounce", "oz"}:
        return int(round(value * 28.3495))
    return None


def _dimension_to_hundredths_inch(measure: dict | None) -> int | None:
    """Convierte una dimensión de SP-API a 1/100 de pulgada.

    Keepa usa esta escala para altura/largo/ancho, así que mantenemos el
    mismo contrato en ProductData para evitar mezclar unidades.
    """
    if not measure:
        return None

    value = measure.get("value")
    unit = str(measure.get("unit", "")).lower()
    if value is None:
        return None

    if unit in {"inches", "inch", "in"}:
        inches = value
    elif unit in {"centimeters", "centimeter", "cm"}:
        inches = value / 2.54
    elif unit in {"millimeters", "millimeter", "mm"}:
        inches = value / 25.4
    else:
        return None

    return int(round(inches * 100))


class SPAPIProvider(DataProvider):
    """Implementación de DataProvider usando Amazon SP-API."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        seller_id: str | None = None,
        marketplace: str = "us",
    ) -> None:
        self._auth = SPAPIAuth(
            client_id=client_id or settings.sp_api_client_id,
            client_secret=client_secret or settings.sp_api_client_secret,
            refresh_token=refresh_token or settings.sp_api_refresh_token,
        )
        self._seller_id = seller_id
        self._marketplace = marketplace
        self._client: httpx.AsyncClient | None = None

        # Rate limit semaphores
        self._semaphores = {
            name: asyncio.Semaphore(rate)
            for name, rate in _RATE_LIMITS.items()
        }

    @property
    def is_configured(self) -> bool:
        return self._auth.is_configured

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=SPAPI_TIMEOUT)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, semaphore_key: str,
        params: dict | None = None, json_body: dict | None = None,
        marketplace: str | None = None,
    ) -> dict | None:
        """Request genérico a SP-API con rate limiting y auth."""
        mkt = marketplace or self._marketplace
        base_url = _get_base_url(mkt)
        client = await self._get_client()

        async with self._semaphores[semaphore_key]:
            headers = await self._auth.get_headers(client)
            try:
                if method == "GET":
                    resp = await client.get(f"{base_url}{path}", headers=headers, params=params)
                else:
                    resp = await client.post(f"{base_url}{path}", headers=headers, params=params, json=json_body)

                if resp.status_code == 429:
                    logger.warning("SP-API rate limited on %s, retrying in 1s", path)
                    await asyncio.sleep(1)
                    return await self._request(method, path, semaphore_key, params, json_body, marketplace)

                if resp.status_code == 403:
                    logger.warning("SP-API 403 on %s: %s", path, resp.text[:200])
                    return None

                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning("SP-API error %s on %s: %s", e.response.status_code, path, e)
                return None
            except Exception as e:
                logger.warning("SP-API request failed on %s: %s", path, e)
                return None

    # ── Marketplace Participations ──

    async def get_seller_info(self) -> dict | None:
        """Obtiene info del seller: seller_id, store_name, marketplaces."""
        data = await self._request("GET", "/sellers/v1/marketplaceParticipations", "catalog")
        if not data or "payload" not in data:
            return None

        participations = data["payload"]
        if not participations:
            return None

        # Extraer seller_id del primer marketplace activo
        result = {
            "marketplaces": [],
            "store_name": None,
        }
        for p in participations:
            mkt = p.get("marketplace", {})
            participation = p.get("participation", {})
            if participation.get("isParticipating"):
                result["marketplaces"].append({
                    "id": mkt.get("id"),
                    "country": mkt.get("countryCode"),
                    "name": mkt.get("name"),
                    "currency": mkt.get("defaultCurrencyCode"),
                })
            if not result["store_name"]:
                result["store_name"] = p.get("storeName")

        return result

    # ── Catalog Items ──

    async def get_catalog_item(self, asin: str, marketplace: str | None = None) -> ProductData | None:
        """Obtiene datos de catálogo de un ASIN."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("GET", f"/catalog/2022-04-01/items/{asin}", "catalog",
            params={
                "marketplaceIds": mkt_id,
                "includedData": "summaries,salesRanks,productTypes,identifiers,dimensions",
            }, marketplace=mkt)

        if not data or "asin" not in data:
            return None

        # Parse summaries
        summary = {}
        for s in data.get("summaries", []):
            if s.get("marketplaceId") == mkt_id:
                summary = s
                break

        # Parse dimensions
        dims = {}
        for d in data.get("dimensions", []):
            if d.get("marketplaceId") == mkt_id:
                dims = d
                break

        # Parse sales ranks
        sales_rank = None
        for sr in data.get("salesRanks", []):
            if sr.get("marketplaceId") == mkt_id:
                display_ranks = sr.get("displayGroupRanks", [])
                if display_ranks:
                    sales_rank = display_ranks[0].get("rank")
                break

        # Parse identifiers
        upc_list, ean_list = [], []
        for ids in data.get("identifiers", []):
            if ids.get("marketplaceId") == mkt_id:
                for ident in ids.get("identifiers", []):
                    if ident["identifierType"] == "UPC":
                        upc_list.append(ident["identifier"])
                    elif ident["identifierType"] == "EAN":
                        ean_list.append(ident["identifier"])

        item_dims = dims.get("item", {})
        pkg_dims = dims.get("package", {})
        item_weight_grams = _weight_to_grams(item_dims.get("weight"))
        pkg_weight_grams = _weight_to_grams(pkg_dims.get("weight"))
        item_height = _dimension_to_hundredths_inch(item_dims.get("height"))
        item_length = _dimension_to_hundredths_inch(item_dims.get("length"))
        item_width = _dimension_to_hundredths_inch(item_dims.get("width"))

        return ProductData(
            asin=data["asin"],
            title=summary.get("itemName"),
            brand=summary.get("brand"),
            manufacturer=summary.get("manufacturer"),
            model=summary.get("modelNumber"),
            part_number=summary.get("partNumber"),
            category=summary.get("browseClassification", {}).get("displayName"),
            product_type=data.get("productTypes", [{}])[0].get("productType") if data.get("productTypes") else None,
            color=summary.get("color"),
            size=summary.get("size"),
            sales_rank=sales_rank,
            is_adult_product=summary.get("adultProduct", False),
            package_quantity=summary.get("packageQuantity", 1),
            upc_list=upc_list or None,
            ean_list=ean_list or None,
            item_weight_grams=item_weight_grams,
            package_weight_grams=pkg_weight_grams,
            item_height=item_height,
            item_length=item_length,
            item_width=item_width,
        )

    # ── Listing Restrictions ──

    async def check_listing_restrictions(
        self, asin: str, seller_id: str | None = None,
        marketplace: str | None = None, condition: str = "new_new",
    ) -> RestrictionResult:
        """Verifica si un seller puede vender un ASIN."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)
        sid = seller_id or self._seller_id

        if not sid:
            return RestrictionResult(can_sell=None, reason_code="NO_SELLER_ID", message="Seller ID no configurado")

        data = await self._request("GET", "/listings/2021-08-01/restrictions", "restrictions",
            params={
                "asin": asin,
                "sellerId": sid,
                "marketplaceIds": mkt_id,
                "conditionType": condition,
            }, marketplace=mkt)

        if data is None:
            return RestrictionResult(can_sell=None, reason_code="API_ERROR", message="Error consultando SP-API")

        restrictions = data.get("restrictions", [])
        if not restrictions:
            return RestrictionResult(can_sell=True)

        # Verificar si hay razones de restricción
        for restriction in restrictions:
            reasons = restriction.get("reasons", [])
            if not reasons:
                return RestrictionResult(can_sell=True)

            # Si hay razones, está restringido
            first_reason = reasons[0]
            reason_code = first_reason.get("reasonCode", "UNKNOWN")

            # ASIN_NOT_FOUND no es una restricción real
            if reason_code == "ASIN_NOT_FOUND":
                return RestrictionResult(can_sell=None, reason_code="ASIN_NOT_FOUND", message="ASIN no existe en este marketplace")

            messages = [r.get("message", "") for r in reasons]
            return RestrictionResult(
                can_sell=False,
                reason_code=reason_code,
                message=" | ".join(m for m in messages if m),
            )

        return RestrictionResult(can_sell=True)

    async def check_listing_restrictions_batch(
        self, asins: list[str], seller_id: str | None = None,
        marketplace: str | None = None,
    ) -> dict[str, RestrictionResult]:
        """Verifica restrictions para múltiples ASINs concurrentemente."""
        tasks = [
            self.check_listing_restrictions(asin, seller_id, marketplace)
            for asin in asins
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, RestrictionResult] = {}
        for asin, result in zip(asins, results):
            if isinstance(result, Exception):
                logger.warning("Error checking restrictions for %s: %s", asin, result)
                output[asin] = RestrictionResult(can_sell=None, reason_code="ERROR", message=str(result))
            else:
                output[asin] = result

        return output

    # ── Fees Estimate ──

    async def get_fees_estimate(
        self, asin: str, price: float,
        marketplace: str | None = None, is_fba: bool = True,
    ) -> FeesResult | None:
        """Obtiene fees exactos para un ASIN a un precio dado."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("POST",
            f"/products/fees/v0/items/{asin}/feesEstimate", "fees",
            json_body={
                "FeesEstimateRequest": {
                    "MarketplaceId": mkt_id,
                    "IsAmazonFulfilled": is_fba,
                    "PriceToEstimateFees": {
                        "ListingPrice": {"CurrencyCode": "USD", "Amount": price},
                    },
                    "Identifier": f"req_{asin}",
                },
            }, marketplace=mkt)

        if not data:
            return None

        result = data.get("payload", {}).get("FeesEstimateResult", {})
        if result.get("Status") != "Success":
            return None

        fees = result.get("FeesEstimate", {})
        fee_list = fees.get("FeeDetailList", [])

        referral = 0.0
        fba = 0.0
        closing = 0.0
        per_item = 0.0

        for fee in fee_list:
            amount = fee.get("FinalFee", {}).get("Amount", 0.0)
            fee_type = fee.get("FeeType", "")
            if fee_type == "ReferralFee":
                referral = amount
            elif fee_type == "FBAFees":
                fba = amount
            elif fee_type == "VariableClosingFee":
                closing = amount
            elif fee_type == "PerItemFee":
                per_item = amount

        total = fees.get("TotalFeesEstimate", {}).get("Amount", 0.0)

        return FeesResult(
            total_fees=total,
            referral_fee=referral,
            fba_fee=fba,
            variable_closing_fee=closing,
            per_item_fee=per_item,
        )

    async def get_fees_estimate_batch(
        self, items: list[tuple[str, float]],
        marketplace: str | None = None, is_fba: bool = True,
    ) -> dict[str, FeesResult | None]:
        """Batch fees via getMyFeesEstimates — 20 ASINs en 1 request."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)
        output: dict[str, FeesResult | None] = {}

        # Chunks de 20
        for i in range(0, len(items), 20):
            chunk = items[i:i + 20]

            body = [
                {
                    "FeesEstimateRequest": {
                        "MarketplaceId": mkt_id,
                        "IsAmazonFulfilled": is_fba,
                        "PriceToEstimateFees": {
                            "ListingPrice": {"CurrencyCode": "USD", "Amount": price},
                        },
                        "Identifier": asin,
                    },
                    "IdType": "ASIN",
                    "IdValue": asin,
                }
                for asin, price in chunk
            ]

            data = await self._request("POST",
                "/products/fees/v0/feesEstimate", "fees",
                json_body=body, marketplace=mkt)

            if not data or not isinstance(data, list):
                for asin, _ in chunk:
                    output[asin] = None
                continue

            for item in data:
                status = item.get("Status", "")
                fe = item.get("FeesEstimateIdentifier", {})
                asin = fe.get("IdValue") or fe.get("SellerInputIdentifier", "")
                fees = item.get("FeesEstimate", {})

                if status != "Success" or not asin:
                    continue

                fee_list = fees.get("FeeDetailList", [])
                referral = next((f["FinalFee"]["Amount"] for f in fee_list if f["FeeType"] == "ReferralFee"), 0.0)
                fba_fee = next((f["FinalFee"]["Amount"] for f in fee_list if f["FeeType"] == "FBAFees"), 0.0)
                closing = next((f["FinalFee"]["Amount"] for f in fee_list if f["FeeType"] == "VariableClosingFee"), 0.0)
                per_item = next((f["FinalFee"]["Amount"] for f in fee_list if f["FeeType"] == "PerItemFee"), 0.0)
                total = fees.get("TotalFeesEstimate", {}).get("Amount", 0.0)

                output[asin] = FeesResult(
                    total_fees=total,
                    referral_fee=referral,
                    fba_fee=fba_fee,
                    variable_closing_fee=closing,
                    per_item_fee=per_item,
                )

        # ASINs sin resultado
        for asin, _ in items:
            if asin not in output:
                output[asin] = None

        return output

    # ── Item Offers (detalle de ofertas) ──

    async def get_item_offers(
        self, asin: str, marketplace: str | None = None, condition: str = "New",
    ) -> OffersResult | None:
        """Obtiene detalle de ofertas: Buy Box price, lowest prices, offer counts por fulfillment."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("GET",
            f"/products/pricing/v0/items/{asin}/offers", "offers",
            params={"MarketplaceId": mkt_id, "ItemCondition": condition},
            marketplace=mkt)

        if not data or "payload" not in data:
            return None

        payload = data["payload"]
        summary = payload.get("Summary", {})

        # Buy Box prices
        bb_price = None
        bb_shipping = None
        for bb in summary.get("BuyBoxPrices", []):
            if bb.get("condition") == "New":
                bb_price = bb.get("LandedPrice", {}).get("Amount")
                bb_shipping = bb.get("Shipping", {}).get("Amount", 0)
                break

        # Lowest prices
        lowest_new = None
        lowest_used = None
        for lp in summary.get("LowestPrices", []):
            price = lp.get("LandedPrice", {}).get("Amount")
            if lp.get("condition") == "new" and (lowest_new is None or price < lowest_new):
                lowest_new = price
            elif lp.get("condition") == "used" and (lowest_used is None or price < lowest_used):
                lowest_used = price

        # Offer counts por fulfillment channel
        new_fba, new_fbm, used_fba, used_fbm = 0, 0, 0, 0
        for offer in summary.get("NumberOfOffers", []):
            count = offer.get("OfferCount", 0)
            cond = offer.get("condition", "")
            channel = offer.get("fulfillmentChannel", "")
            if cond == "new" and channel == "Amazon":
                new_fba = count
            elif cond == "new" and channel == "Merchant":
                new_fbm = count
            elif cond == "used" and channel == "Amazon":
                used_fba = count
            elif cond == "used" and channel == "Merchant":
                used_fbm = count

        # Buy Box eligible offers
        bb_new, bb_used = 0, 0
        for bbe in summary.get("BuyBoxEligibleOffers", []):
            count = bbe.get("OfferCount", 0)
            if bbe.get("condition") == "new":
                bb_new = count
            elif bbe.get("condition") == "used":
                bb_used = count

        return OffersResult(
            buy_box_price=bb_price,
            buy_box_shipping=bb_shipping,
            lowest_price_new=lowest_new,
            lowest_price_used=lowest_used,
            offer_count_new_fba=new_fba,
            offer_count_new_fbm=new_fbm,
            offer_count_used_fba=used_fba,
            offer_count_used_fbm=used_fbm,
            buy_box_eligible_new=bb_new,
            buy_box_eligible_used=bb_used,
        )

    # ── Competitive Pricing ──

    async def get_competitive_pricing(
        self, asins: list[str], marketplace: str | None = None,
    ) -> dict[str, PricingResult | None]:
        """Competitive pricing para múltiples ASINs (max 20 por request)."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("GET", "/products/pricing/v0/competitivePrice", "pricing",
            params={
                "MarketplaceId": mkt_id,
                "Asins": ",".join(asins),
                "ItemType": "Asin",
            }, marketplace=mkt)

        if not data or "payload" not in data:
            return {asin: None for asin in asins}

        output: dict[str, PricingResult | None] = {}
        for item in data["payload"]:
            asin = item.get("ASIN", "")
            if item.get("status") != "Success":
                output[asin] = None
                continue

            product = item.get("Product", {})
            comp = product.get("CompetitivePricing", {})

            # Offer counts
            offer_new = 0
            offer_used = 0
            for listing in comp.get("NumberOfOfferListings", []):
                cond = listing.get("condition", "")
                count = listing.get("Count", 0)
                if cond == "New":
                    offer_new = count
                elif cond == "Used":
                    offer_used = count

            # Trade-in value
            trade_in = comp.get("TradeInValue", {}).get("Amount")

            # Sales rank
            rank = None
            rank_cat = None
            rankings = product.get("SalesRankings", [])
            if rankings:
                rank = rankings[0].get("Rank")
                rank_cat = rankings[0].get("ProductCategoryId")

            output[asin] = PricingResult(
                offer_count_new=offer_new,
                offer_count_used=offer_used,
                trade_in_value=trade_in,
                sales_rank=rank,
                sales_rank_category=rank_cat,
            )

        # ASINs sin resultado
        for asin in asins:
            if asin not in output:
                output[asin] = None

        return output

    # ── Catalog Search by Identifier (UPC/EAN → ASIN) ──

    async def search_by_identifier(
        self, code: str, identifier_type: str = "UPC",
        marketplace: str | None = None,
    ) -> list[str]:
        """Busca ASINs por UPC, EAN, ISBN o GTIN via SP-API Catalog."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("GET", "/catalog/2022-04-01/items", "catalog",
            params={
                "marketplaceIds": mkt_id,
                "identifiers": code,
                "identifiersType": identifier_type,
                "includedData": "summaries",
                "pageSize": 10,
            }, marketplace=mkt)

        if not data or "items" not in data:
            return []

        return [item["asin"] for item in data["items"] if "asin" in item]

    # ── FBA Inbound Eligibility ──

    async def check_fba_eligibility(
        self, asin: str, marketplace: str | None = None,
    ) -> bool | None:
        """Verifica si un ASIN es elegible para envío FBA Inbound."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        data = await self._request("GET",
            "/fba/inbound/v1/eligibility/itemPreview", "fba",
            params={
                "asin": asin,
                "program": "INBOUND",
                "marketplaceIds": mkt_id,
            }, marketplace=mkt)

        if not data or "payload" not in data:
            return None

        return data["payload"].get("isEligibleForProgram")

    async def check_fba_eligibility_batch(
        self, asins: list[str], marketplace: str | None = None,
    ) -> dict[str, bool | None]:
        """FBA eligibility para múltiples ASINs (1 por request, concurrente)."""
        tasks = [self.check_fba_eligibility(asin, marketplace) for asin in asins]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, bool | None] = {}
        for asin, result in zip(asins, results):
            if isinstance(result, Exception):
                logger.warning("Error checking FBA eligibility for %s: %s", asin, result)
                output[asin] = None
            else:
                output[asin] = result

        return output

    # ── Batch Item Offers ──

    async def get_item_offers_batch(
        self, asins: list[str], marketplace: str | None = None,
        condition: str = "New", max_per_request: int = 20,
    ) -> dict[str, OffersResult | None]:
        """Batch de Item Offers — múltiples ASINs en 1 request (max 20)."""
        mkt = marketplace or self._marketplace
        mkt_id = _get_marketplace_id(mkt)

        all_results: dict[str, OffersResult | None] = {}

        # Chunked en grupos de max_per_request
        for i in range(0, len(asins), max_per_request):
            chunk = asins[i:i + max_per_request]

            requests_body = [
                {
                    "uri": f"/products/pricing/v0/items/{asin}/offers",
                    "method": "GET",
                    "MarketplaceId": mkt_id,
                    "ItemCondition": condition,
                }
                for asin in chunk
            ]

            data = await self._request("POST",
                "/batches/products/pricing/v0/itemOffers", "offers",
                json_body={"requests": requests_body},
                marketplace=mkt)

            if not data or "responses" not in data:
                for asin in chunk:
                    all_results[asin] = None
                continue

            for resp in data["responses"]:
                body = resp.get("body", {})
                status_code = resp.get("status", {}).get("statusCode", 0)
                payload = body.get("payload", {})
                asin = payload.get("ASIN", "")

                if status_code != 200 or not asin:
                    continue

                summary = payload.get("Summary", {})

                # Buy Box
                bb_price, bb_shipping = None, None
                for bb in summary.get("BuyBoxPrices", []):
                    if bb.get("condition") == "New":
                        bb_price = bb.get("LandedPrice", {}).get("Amount")
                        bb_shipping = bb.get("Shipping", {}).get("Amount", 0)
                        break

                # Lowest prices
                lowest_new, lowest_used = None, None
                for lp in summary.get("LowestPrices", []):
                    price = lp.get("LandedPrice", {}).get("Amount")
                    if lp.get("condition") == "new" and (lowest_new is None or price < lowest_new):
                        lowest_new = price
                    elif lp.get("condition") == "used" and (lowest_used is None or price < lowest_used):
                        lowest_used = price

                # Offer counts
                new_fba, new_fbm, used_fba, used_fbm = 0, 0, 0, 0
                for offer in summary.get("NumberOfOffers", []):
                    count = offer.get("OfferCount", 0)
                    cond = offer.get("condition", "")
                    channel = offer.get("fulfillmentChannel", "")
                    if cond == "new" and channel == "Amazon":
                        new_fba = count
                    elif cond == "new" and channel == "Merchant":
                        new_fbm = count
                    elif cond == "used" and channel == "Amazon":
                        used_fba = count
                    elif cond == "used" and channel == "Merchant":
                        used_fbm = count

                # BB eligible
                bb_new, bb_used = 0, 0
                for bbe in summary.get("BuyBoxEligibleOffers", []):
                    count = bbe.get("OfferCount", 0)
                    if bbe.get("condition") == "new":
                        bb_new = count
                    elif bbe.get("condition") == "used":
                        bb_used = count

                all_results[asin] = OffersResult(
                    buy_box_price=bb_price,
                    buy_box_shipping=bb_shipping,
                    lowest_price_new=lowest_new,
                    lowest_price_used=lowest_used,
                    offer_count_new_fba=new_fba,
                    offer_count_new_fbm=new_fbm,
                    offer_count_used_fba=used_fba,
                    offer_count_used_fbm=used_fbm,
                    buy_box_eligible_new=bb_new,
                    buy_box_eligible_used=bb_used,
                )

        # ASINs sin resultado
        for asin in asins:
            if asin not in all_results:
                all_results[asin] = None

        return all_results

    # ── DataProvider ABC implementation ──

    async def get_products_batch(
        self, asins: list[str], domain: int = 1,
    ) -> dict[str, ProductData | None]:
        """Fetch product data via SP-API catalog items (1 por 1 debido a rate limit)."""
        tasks = [self.get_catalog_item(asin) for asin in asins]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, ProductData | None] = {}
        for asin, result in zip(asins, results):
            if isinstance(result, Exception):
                logger.warning("Error fetching catalog for %s: %s", asin, result)
                output[asin] = None
            else:
                output[asin] = result

        return output

    async def resolve_code_to_asin(self, code: str, domain: int = 1) -> str | None:
        """Resolver UPC/EAN → ASIN via SP-API Catalog Search."""
        # Detectar tipo de identificador
        code = code.strip()
        if len(code) == 12 and code.isdigit():
            id_type = "UPC"
        elif len(code) == 13 and code.isdigit():
            id_type = "EAN"
        elif len(code) == 10 and (code.isdigit() or code[-1] == "X"):
            id_type = "ISBN"
        else:
            id_type = "UPC"  # fallback

        asins = await self.search_by_identifier(code, identifier_type=id_type)
        return asins[0] if asins else None

    async def search_by_keyword(self, keyword: str, domain: int = 1, limit: int = 5) -> list[str]:
        """SP-API Catalog search by keyword."""
        mkt_id = _get_marketplace_id(self._marketplace)
        data = await self._request("GET", "/catalog/2022-04-01/items", "catalog",
            params={
                "marketplaceIds": mkt_id,
                "keywords": keyword,
                "pageSize": limit,
                "includedData": "summaries",
            })
        if not data or "items" not in data:
            return []
        return [item["asin"] for item in data["items"] if "asin" in item]
