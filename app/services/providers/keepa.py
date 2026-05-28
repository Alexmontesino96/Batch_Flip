"""Keepa API provider — adaptado de FlipIQ/app/services/marketplace/amazon.py.

Cambios vs FlipIQ:
- domain parametrizado (no hardcodeado a 1/US)
- httpx.AsyncClient compartido (no uno por request)
- Retorna ProductData en vez de CompsResult
- Soporta batch de ASINs nativamente
"""

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.services.providers.base import DataProvider, ProductData

logger = logging.getLogger(__name__)

KEEPA_BASE = "https://api.keepa.com"
KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
KEEPA_TIMEOUT = 20

# Keepa CSV indices
CSV_AMAZON = 0
CSV_NEW = 1
CSV_USED = 2
CSV_SALES_RANK = 3
CSV_BUY_BOX = 18

MAX_REASONABLE_PRICE = 5000.0

_PACK_RE = re.compile(
    r"(?:"
    r"\bpack\s+of\s+(\d+)"
    r"|\b(\d+)\s*[-\s]?pack\b"
    r"|\btwin\s+pack\b"
    r"|\btriple\s+pack\b"
    r"|\b(\d+)\s*[-\s]?count\b"
    r")",
    re.IGNORECASE,
)


def keepa_time_to_datetime(keepa_minutes: int) -> datetime:
    return KEEPA_EPOCH + timedelta(minutes=keepa_minutes)


def estimate_sales_per_day(sales_rank: int | None) -> float:
    if sales_rank is None or sales_rank <= 0:
        return 0.0
    if sales_rank < 5_000:
        return 10.0
    if sales_rank < 50_000:
        return 3.5
    if sales_rank < 200_000:
        return 0.75
    return 0.15


def _is_multipack(title: str) -> bool:
    m = _PACK_RE.search(title)
    if not m:
        return False
    qty = m.group(1) or m.group(2) or m.group(3)
    if qty:
        return int(qty) > 1
    return True


def _extract_brand_model(product: dict) -> tuple[str | None, str | None]:
    brand = product.get("brand") or None
    model = product.get("model") or product.get("partNumber") or None
    return brand, model


def _extract_buy_box_price(product: dict) -> float | None:
    """Extrae el precio actual del Buy Box del producto."""
    stats = product.get("stats")
    if not stats:
        return None
    current = stats.get("current")
    if not current or len(current) <= CSV_BUY_BOX:
        return None
    bb_cents = current[CSV_BUY_BOX]
    if bb_cents is not None and bb_cents > 0:
        return bb_cents / 100.0
    # Fallback: precio New actual
    new_cents = current[CSV_NEW] if len(current) > CSV_NEW else None
    if new_cents is not None and new_cents > 0:
        return new_cents / 100.0
    return None


def _extract_sales_rank(product: dict) -> int | None:
    stats = product.get("stats")
    if not stats:
        return None
    rank = stats.get("salesRankReference")
    if rank:
        return rank
    current = stats.get("current")
    if current and len(current) > CSV_SALES_RANK:
        r = current[CSV_SALES_RANK]
        return r if r and r > 0 else None
    return None


def _extract_fees(product: dict) -> tuple[float | None, float | None]:
    """Extrae referral fee % y FBA fulfillment fee del producto Keepa."""
    ref_pct = product.get("referralFeePercentage")
    referral = ref_pct / 100.0 if ref_pct is not None and ref_pct > 0 else None

    fba_fees = product.get("fbaFees")
    fulfillment = None
    if fba_fees and isinstance(fba_fees, dict):
        pick_pack = fba_fees.get("pickAndPackFee")
        if pick_pack is not None and pick_pack > 0:
            fulfillment = pick_pack / 100.0

    return referral, fulfillment


def _extract_image_url(product: dict) -> str | None:
    images_csv = product.get("imagesCSV")
    if images_csv:
        first_hash = images_csv.split(",")[0].strip()
        if first_hash:
            return f"https://images-na.ssl-images-amazon.com/images/I/{first_hash}"
    return None


def _extract_seller_count(product: dict) -> int:
    """Cuenta sellers de las ofertas del producto."""
    offers = product.get("offers") or []
    sellers = set()
    for offer in offers:
        sid = offer.get("sellerId")
        if sid:
            sellers.add(sid)
    return len(sellers)


def _check_amazon_is_seller(product: dict) -> bool:
    offers = product.get("offers") or []
    for offer in offers:
        if offer.get("sellerId") == "ATVPDKIKX0DER":  # Amazon US seller ID
            return True
    return False


def _product_to_data(product: dict) -> ProductData:
    """Convierte un dict de producto Keepa a ProductData."""
    title = product.get("title") or ""
    brand, model = _extract_brand_model(product)
    buy_box = _extract_buy_box_price(product)
    rank = _extract_sales_rank(product)
    referral, fulfillment = _extract_fees(product)
    image = _extract_image_url(product)
    is_mp = _is_multipack(title)
    stats = product.get("stats") or {}

    # Category
    category = None
    cat_tree = product.get("categoryTree")
    if cat_tree and isinstance(cat_tree, list) and len(cat_tree) > 0:
        category = cat_tree[-1].get("name")

    # List price (centavos)
    list_price = None
    current = stats.get("current") or []
    if len(current) > 4 and current[4] and current[4] > 0:
        list_price = current[4] / 100.0

    # Monthly sold (dato real de Amazon)
    monthly_sold = product.get("monthlySold")

    # Sales per day: usar monthlySold si disponible, sino salesRankDrops, sino BSR
    if monthly_sold and monthly_sold > 0:
        spd = monthly_sold / 30.0
    elif stats.get("salesRankDrops30"):
        spd = stats["salesRankDrops30"] / 30.0
    else:
        spd = estimate_sales_per_day(rank)

    # Buy Box stats
    bb_stats = stats.get("buyBoxStats")
    bb_seller = stats.get("buyBoxSellerId")
    bb_is_fba = bool(stats.get("buyBoxIsFBA"))
    bb_is_amazon = bool(stats.get("buyBoxIsAmazon"))

    # Reviews
    rating = None
    review_count = None
    if len(current) > 16 and current[16] and current[16] > 0:
        rating = current[16] / 10.0
    if len(current) > 17 and current[17] and current[17] > 0:
        review_count = current[17]

    # Offer counts
    offer_fba = stats.get("offerCountFBA") or 0
    offer_fbm = stats.get("offerCountFBM") or 0

    # Out of stock
    oos_pct_90 = None
    oos_arr = stats.get("outOfStockPercentage90")
    if oos_arr and isinstance(oos_arr, list) and len(oos_arr) > 0:
        oos_pct_90 = oos_arr[0] if oos_arr[0] >= 0 else None

    return ProductData(
        asin=product.get("asin", ""),
        title=title if title else None,
        brand=brand,
        manufacturer=product.get("manufacturer"),
        model=model,
        part_number=product.get("partNumber"),
        category=category,
        category_tree=cat_tree,
        product_type=product.get("type"),
        color=product.get("color"),
        size=product.get("size"),
        sales_rank=rank,
        buy_box_price=buy_box,
        buy_box_seller=bb_seller,
        buy_box_is_fba=bb_is_fba,
        buy_box_is_amazon=bb_is_amazon,
        buy_box_stats=bb_stats,
        amazon_is_seller=_check_amazon_is_seller(product),
        seller_count=_extract_seller_count(product),
        offer_count_fba=offer_fba,
        offer_count_fbm=offer_fbm,
        list_price=list_price,
        competitive_price_threshold=product.get("competitivePriceThreshold", 0) / 100.0 if product.get("competitivePriceThreshold") else None,
        referral_fee_pct=referral,
        fba_fulfillment_fee=fulfillment,
        sales_per_day=round(spd, 4),
        monthly_sold=monthly_sold,
        sales_rank_drops_30=stats.get("salesRankDrops30"),
        sales_rank_drops_90=stats.get("salesRankDrops90"),
        out_of_stock_pct_90=oos_pct_90,
        amazon_oos_days_30=stats.get("outOfStockCountAmazon30"),
        multipack_qty=product.get("packageQuantity") or 1,
        is_multipack=is_mp,
        package_quantity=product.get("packageQuantity") or 1,
        item_weight_grams=product.get("itemWeight"),
        package_weight_grams=product.get("packageWeight"),
        item_height=product.get("itemHeight"),
        item_length=product.get("itemLength"),
        item_width=product.get("itemWidth"),
        rating=rating,
        review_count=review_count,
        is_hazmat=bool(product.get("hazardousMaterials")),
        is_adult_product=bool(product.get("isAdultProduct")),
        is_sns=bool(product.get("isSNS")),
        image_url=image,
        upc_list=product.get("upcList"),
        ean_list=product.get("eanList"),
        parent_asin=product.get("parentAsin"),
        raw_product=product,
    )


class KeepaProvider(DataProvider):
    """Implementación de DataProvider usando Keepa REST API."""

    def __init__(self) -> None:
        self._api_key = settings.keepa_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=KEEPA_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _keepa_get(self, endpoint: str, params: dict) -> dict | None:
        if not self._api_key:
            return None
        params["key"] = self._api_key
        try:
            client = await self._get_client()
            resp = await client.get(f"{KEEPA_BASE}/{endpoint}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Keepa API error %s: %s", e.response.status_code, e)
            return None
        except Exception as e:
            logger.warning("Keepa request failed: %s", e)
            return None

    async def _keepa_product(
        self, asins: list[str], domain: int = 1, stats: int = 30, offers: int = 20,
    ) -> list[dict]:
        if not asins:
            return []
        data = await self._keepa_get("product", {
            "domain": domain,
            "asin": ",".join(asins),
            "stats": stats,
            "buybox": 1,
            "history": 1,
            "days": 90,
            "offers": offers,
        })
        if not data:
            return []
        return data.get("products", [])

    async def _keepa_product_by_code(self, code: str, domain: int = 1) -> list[dict]:
        data = await self._keepa_get("product", {
            "domain": domain,
            "code": code,
            "stats": 30,
            "buybox": 1,
            "history": 1,
            "days": 90,
            "offers": 20,
        })
        if not data:
            return []
        return data.get("products", [])

    async def get_products_batch(
        self, asins: list[str], domain: int = 1,
    ) -> dict[str, ProductData | None]:
        """Fetch datos de múltiples ASINs en un solo request Keepa."""
        if not asins:
            return {}

        products = await self._keepa_product(asins, domain=domain)

        result: dict[str, ProductData | None] = {}
        found_asins = set()

        for product in products:
            asin = product.get("asin", "")
            if not asin:
                continue
            data = _product_to_data(product)
            # Skip multipacks
            if data.is_multipack:
                logger.debug("Skipping multipack: %s", asin)
                result[asin] = None
                found_asins.add(asin)
                continue
            result[asin] = data
            found_asins.add(asin)

        # ASINs no encontrados
        for asin in asins:
            if asin not in found_asins:
                result[asin] = None

        return result

    async def resolve_code_to_asin(
        self, code: str, domain: int = 1,
    ) -> str | None:
        """Resolver UPC/EAN a ASIN via Keepa."""
        products = await self._keepa_product_by_code(code, domain=domain)
        if not products:
            return None
        # Retornar primer ASIN no-multipack
        for p in products:
            title = p.get("title") or ""
            if not _is_multipack(title):
                return p.get("asin")
        # Si todos son multipack, retornar el primero
        return products[0].get("asin") if products else None

    async def search_by_keyword(
        self, keyword: str, domain: int = 1, limit: int = 5,
    ) -> list[str]:
        """Buscar ASINs por keyword."""
        data = await self._keepa_get("search", {
            "domain": domain,
            "type": "product",
            "term": keyword,
        })
        if not data:
            return []
        products = data.get("products", [])
        return [p["asin"] for p in products if p.get("asin")][:limit]
