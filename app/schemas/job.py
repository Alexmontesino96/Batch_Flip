"""Schemas Pydantic para Jobs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    scan_mode: str = Field(default="fast", description="'fast' (SP-API only, ~15K/hr) o 'deep' (SP-API + Keepa, ~400/hr)")
    marketplace: str = Field(default="us", description="Amazon marketplace: us, uk, de, fr, es, it, ca, mx, br, au")
    fulfillment_type: str = Field(default="fba", description="fba o mfn")
    prep_cost_per_item: float = Field(default=0.0, ge=0)
    shipping_to_amazon: float = Field(default=0.0, ge=0)
    seller_connection_id: UUID | None = Field(default=None, description="ID de SellerConnection para SP-API")
    check_restrictions: bool = Field(default=True, description="Verificar listing restrictions via SP-API")


class UploadResponse(BaseModel):
    total_items: int
    detected_id_type: str
    detected_id_column: str
    detected_cost_column: str | None
    warnings: list[str] = []


class JobResponse(BaseModel):
    id: UUID
    status: str
    progress_phase: str | None
    scan_mode: str
    marketplace: str
    fulfillment_type: str
    check_restrictions: bool
    file_name: str | None
    total_items: int
    processed_items: int
    matched_items: int
    profitable_items: int
    restricted_items: int
    error_items: int
    processing_speed: float | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobStatsResponse(BaseModel):
    total_items: int
    matched_items: int
    restricted_items: int
    not_found_items: int
    profitable_items: int
    error_items: int
    avg_roi: float | None
    avg_profit: float | None
    total_profit: float | None
    best_roi_asin: str | None
    best_profit_asin: str | None


class JobItemResponse(BaseModel):
    id: UUID
    input_row: int
    input_id: str
    input_id_type: str | None
    cost_price: float | None

    # Amazon data
    asin: str | None
    title: str | None
    brand: str | None
    category: str | None
    sales_rank: int | None
    buy_box_price: float | None
    amazon_is_seller: bool
    seller_count: int
    multipack_qty: int
    is_hazmat: bool
    image_url: str | None
    list_price: float | None

    # Listing Restrictions
    can_sell: bool | None
    restriction_reason: str | None
    restriction_message: str | None

    # Fees (SP-API exactos o Keepa fallback)
    fba_fee: float | None
    referral_fee_pct: float | None
    sp_api_total_fees: float | None
    sp_api_referral_fee: float | None
    sp_api_fba_fee: float | None

    # Profit calculations
    estimated_sale_price: float | None
    profit: float | None
    roi_pct: float | None
    margin_pct: float | None
    marketplace_fees: float | None

    # Velocity & Sales
    velocity_score: int | None
    sales_per_day: float | None
    estimated_days_to_sell: str | None
    monthly_sold: int | None
    sales_rank_drops_30: int | None

    # Reviews
    rating: float | None
    review_count: int | None

    # Competition
    buy_box_is_amazon: bool
    offer_count_new: int | None
    offer_count_used: int | None
    out_of_stock_pct_90: int | None
    trade_in_value: float | None

    # Scores
    risk_score: int | None

    status: str

    model_config = {"from_attributes": True}


class JobResultsResponse(BaseModel):
    items: list[JobItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
