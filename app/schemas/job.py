"""Schemas Pydantic para Jobs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    scan_mode: str = Field(default="fast", description="'fast' (SP-API only) o 'deep' (SP-API + Keepa)")
    marketplace: str = Field(default="us", description="Amazon marketplace")
    fulfillment_type: Literal["fba", "mfn"] = Field(default="fba", description="Preferred/selected fulfillment")
    # FBA costs
    fba_prep_cost: float = Field(default=0.0, ge=0, description="Prep cost per item for FBA")
    fba_shipping_to_amazon: float = Field(default=0.0, ge=0, description="Shipping to FBA warehouse per item")
    # MFN costs
    mfn_prep_cost: float = Field(default=0.0, ge=0, description="Prep cost per item for MFN")
    mfn_shipping_to_customer: float = Field(default=0.0, ge=0, description="Shipping to customer per item")
    mfn_packaging_cost: float = Field(default=0.0, ge=0, description="Packaging cost per item for MFN")
    # Legacy (backward compat)
    prep_cost_per_item: float = Field(default=0.0, ge=0, description="Legacy: maps to fba_prep_cost")
    shipping_to_amazon: float = Field(default=0.0, ge=0, description="Legacy: maps to fba_shipping_to_amazon")
    # Cost profile (opcional — si se provee, sobreescribe los campos de costo inline)
    cost_profile_id: UUID | None = Field(default=None, description="ID de un CostProfile guardado")
    # SP-API
    seller_connection_id: UUID | None = Field(default=None)
    check_restrictions: bool = Field(default=True)


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
    item_weight_grams: int | None
    package_weight_grams: int | None
    item_height: int | None
    item_length: int | None
    item_width: int | None

    # Analysis
    analysis_bucket: str | None  # sellable_profitable, approval_candidate, restricted_hard, etc.

    # Listing Restrictions
    can_sell: bool | None
    fba_eligible: bool | None
    restriction_reason: str | None
    restriction_kind: str | None  # approval_required, not_eligible, asin_not_found
    restriction_message: str | None

    # Fees (SP-API exactos o Keepa fallback)
    fba_fee: float | None
    referral_fee_pct: float | None
    sp_api_total_fees: float | None
    sp_api_referral_fee: float | None
    sp_api_fba_fee: float | None

    # Profit — selected scenario
    estimated_sale_price: float | None
    profit: float | None
    roi_pct: float | None
    margin_pct: float | None
    marketplace_fees: float | None

    # Profit — FBA scenario
    fba_profit: float | None
    fba_roi_pct: float | None
    fba_margin_pct: float | None
    fba_total_fees: float | None

    # Profit — MFN scenario
    mfn_profit: float | None
    mfn_roi_pct: float | None
    mfn_margin_pct: float | None
    mfn_total_fees: float | None

    # Best scenario
    best_scenario: str | None  # fba, mfn, neither

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


class BucketSummaryResponse(BaseModel):
    buckets: dict[str, int]
    total: int
