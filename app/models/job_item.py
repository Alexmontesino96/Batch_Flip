import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobItem(Base):
    __tablename__ = "job_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    input_row: Mapped[int] = mapped_column(Integer)
    input_id: Mapped[str] = mapped_column(String(50))
    input_id_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Resolved Amazon data
    asin: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buy_box_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    buy_box_seller: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amazon_is_seller: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_count: Mapped[int] = mapped_column(Integer, default=0)
    fba_fee: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    referral_fee_pct: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    multipack_qty: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_hazmat: Mapped[bool] = mapped_column(Boolean, default=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Profit calculations
    estimated_sale_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    profit: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    roi_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    marketplace_fees: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    shipping_cost: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    prep_cost: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    return_reserve: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Listing Restrictions (SP-API)
    can_sell: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    restriction_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    restriction_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fees exactos (SP-API)
    sp_api_total_fees: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    sp_api_referral_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    sp_api_fba_fee: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Velocity datos reales
    monthly_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_rank_drops_30: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reviews
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Buy Box detail
    buy_box_is_amazon: Mapped[bool] = mapped_column(Boolean, default=False)

    # Offer counts (SP-API competitive pricing)
    offer_count_new: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    offer_count_used: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Extra
    trade_in_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    out_of_stock_pct_90: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Scores (FlipIQ engines)
    velocity_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    competition_hhi: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    sales_per_day: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    estimated_days_to_sell: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status: pending, matched, restricted, not_found, error
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("Job", back_populates="items")
