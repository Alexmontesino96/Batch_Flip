"""Schemas para análisis single-item."""

from pydantic import BaseModel, Field


class SingleAnalysisRequest(BaseModel):
    product_id: str = Field(description="ASIN, UPC, EAN o ISBN")
    cost_price: float = Field(gt=0, description="Costo del producto")
    marketplace: str = Field(default="us")
    fulfillment_type: str = Field(default="fba")
    prep_cost: float = Field(default=0.0, ge=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    check_restrictions: bool = Field(default=True, description="Verificar si puedes vender este producto")


class SingleAnalysisResponse(BaseModel):
    asin: str | None
    title: str | None
    brand: str | None
    category: str | None
    image_url: str | None

    # Listing Restrictions
    can_sell: bool | None
    restriction_reason: str | None
    restriction_message: str | None

    # Pricing
    sales_rank: int | None
    buy_box_price: float | None
    list_price: float | None

    # Physical attributes
    item_weight_grams: int | None
    package_weight_grams: int | None
    item_height: int | None
    item_length: int | None
    item_width: int | None

    # Profit
    estimated_sale_price: float | None
    profit: float | None
    roi_pct: float | None
    margin_pct: float | None
    marketplace_fees: float | None

    # Fees
    referral_fee_pct: float | None
    fba_fulfillment_fee: float | None
    sp_api_total_fees: float | None
    sp_api_referral_fee: float | None
    sp_api_fba_fee: float | None

    # Velocity
    velocity_score: int | None
    sales_per_day: float | None
    estimated_days_to_sell: str | None
    monthly_sold: int | None
    sales_rank_drops_30: int | None

    # Competition
    seller_count: int
    amazon_is_seller: bool
    buy_box_is_amazon: bool
    offer_count_new: int | None
    offer_count_used: int | None
    out_of_stock_pct_90: int | None

    # Reviews
    rating: float | None
    review_count: int | None
    trade_in_value: float | None
