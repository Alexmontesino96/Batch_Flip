"""Data Provider abstraction layer.

Permite intercambiar Keepa por SP-API (u otro) sin cambiar el batch processor.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# Keepa domain IDs por marketplace
DOMAIN_MAP = {
    "us": 1, "uk": 2, "de": 3, "fr": 4, "jp": 5,
    "ca": 6, "it": 8, "es": 9, "mx": 11, "br": 13, "au": 14,
}


@dataclass
class ProductData:
    """Datos unificados de producto devueltos por cualquier provider."""

    asin: str
    title: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    part_number: str | None = None
    category: str | None = None
    category_tree: list[dict] | None = None
    product_type: str | None = None
    color: str | None = None
    size: str | None = None

    # Sales Rank
    sales_rank: int | None = None

    # Buy Box
    buy_box_price: float | None = None
    buy_box_seller: str | None = None
    buy_box_is_fba: bool = False
    buy_box_is_amazon: bool = False
    buy_box_stats: dict | None = None  # {seller_id: {percentageWon, avgPrice, isFBA}}

    # Sellers
    amazon_is_seller: bool = False
    seller_count: int = 0
    offer_count_fba: int = 0
    offer_count_fbm: int = 0

    # Pricing
    list_price: float | None = None
    competitive_price_threshold: float | None = None

    # Fees reales del provider
    referral_fee_pct: float | None = None
    fba_fulfillment_fee: float | None = None

    # Velocity — datos reales de Keepa
    sales_per_day: float = 0.0
    monthly_sold: int | None = None  # Dato real de Amazon "X+ bought in past month"
    sales_rank_drops_30: int | None = None  # Drops de rank ≈ ventas en 30 días
    sales_rank_drops_90: int | None = None

    # Stock
    out_of_stock_pct_90: int | None = None  # % tiempo fuera de stock (Amazon)
    amazon_oos_days_30: int | None = None  # Días Amazon OOS en 30d

    # Multipack
    multipack_qty: int = 1
    is_multipack: bool = False
    package_quantity: int = 1

    # Dimensions & Weight
    item_weight_grams: int | None = None
    package_weight_grams: int | None = None
    item_height: int | None = None  # 1/100 inch
    item_length: int | None = None
    item_width: int | None = None

    # Reviews
    rating: float | None = None  # 1.0 - 5.0
    review_count: int | None = None

    # Flags
    is_hazmat: bool = False
    is_adult_product: bool = False
    is_sns: bool = False  # Subscribe & Save
    image_url: str | None = None

    # Identifiers
    upc_list: list[str] | None = None
    ean_list: list[str] | None = None
    parent_asin: str | None = None

    # Listing restrictions (SP-API)
    can_sell: bool | None = None  # None = no verificado
    restriction_reason: str | None = None
    restriction_message: str | None = None

    # FBA Eligibility (SP-API)
    fba_eligible: bool | None = None  # None = no verificado

    # Fees exactos (SP-API)
    sp_api_total_fees: float | None = None
    sp_api_referral_fee: float | None = None
    sp_api_fba_fee: float | None = None

    # Competitive pricing (SP-API)
    offer_count_new: int | None = None
    offer_count_used: int | None = None
    trade_in_value: float | None = None

    # Item Offers detail (SP-API)
    lowest_price_new: float | None = None
    lowest_price_used: float | None = None
    buy_box_eligible_offers_new: int | None = None
    buy_box_eligible_offers_used: int | None = None

    # Raw Keepa product dict (para engines que lo necesiten)
    raw_product: dict = field(default_factory=dict)


# --- SP-API specific result types ---

@dataclass
class RestrictionResult:
    """Resultado de verificar si un seller puede vender un ASIN."""
    can_sell: bool
    reason_code: str | None = None  # NOT_ELIGIBLE, APPROVAL_REQUIRED, ASIN_NOT_FOUND
    message: str | None = None


@dataclass
class FeesResult:
    """Fees exactos de SP-API para un ASIN a un precio dado."""
    total_fees: float
    referral_fee: float
    fba_fee: float
    variable_closing_fee: float = 0.0
    per_item_fee: float = 0.0


@dataclass
class PricingResult:
    """Datos de competitive pricing de SP-API."""
    buy_box_price: float | None = None
    offer_count_new: int = 0
    offer_count_used: int = 0
    trade_in_value: float | None = None
    sales_rank: int | None = None
    sales_rank_category: str | None = None


@dataclass
class OffersResult:
    """Datos detallados de ofertas de SP-API Item Offers endpoint."""
    buy_box_price: float | None = None
    buy_box_shipping: float | None = None
    lowest_price_new: float | None = None
    lowest_price_used: float | None = None
    offer_count_new_fba: int = 0
    offer_count_new_fbm: int = 0
    offer_count_used_fba: int = 0
    offer_count_used_fbm: int = 0
    buy_box_eligible_new: int = 0
    buy_box_eligible_used: int = 0


# Marketplace IDs de Amazon
MARKETPLACE_IDS = {
    "us": "ATVPDKIKX0DER",
    "ca": "A2EUQ1WTGCTBG2",
    "mx": "A1AM78C64UM0Y8",
    "br": "A2Q3Y263D00KWC",
    "uk": "A1F83G8C2ARO7P",
    "de": "A1PA6795UKMFR9",
    "fr": "A13V1IB3VIYZZH",
    "es": "A1RKKUPIHCS9HS",
    "it": "APJ6JRA9NG5V4",
    "au": "A39IBJ37TRP1C6",
    "jp": "A1VC38T7YXB528",
}


class DataProvider(ABC):
    """Interfaz abstracta para fuentes de datos Amazon."""

    @abstractmethod
    async def get_products_batch(
        self, asins: list[str], domain: int = 1,
    ) -> dict[str, ProductData | None]:
        """Fetch datos de producto para múltiples ASINs.

        Returns: {asin: ProductData | None}
        """
        ...

    @abstractmethod
    async def resolve_code_to_asin(
        self, code: str, domain: int = 1,
    ) -> str | None:
        """Resolver UPC/EAN/ISBN a ASIN."""
        ...

    @abstractmethod
    async def search_by_keyword(
        self, keyword: str, domain: int = 1, limit: int = 5,
    ) -> list[str]:
        """Buscar ASINs por keyword. Retorna lista de ASINs."""
        ...
