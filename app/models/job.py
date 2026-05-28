import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Keepa domain mapping
MARKETPLACE_DOMAINS = {
    "us": 1, "uk": 2, "de": 3, "fr": 4, "jp": 5,
    "ca": 6, "it": 8, "es": 9, "mx": 11, "br": 13, "au": 14,
}


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    progress_phase: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Scan mode
    scan_mode: Mapped[str] = mapped_column(String(10), default="fast")  # fast, deep

    # Marketplace
    marketplace: Mapped[str] = mapped_column(String(5), default="us")
    domain_id: Mapped[int] = mapped_column(SmallInteger, default=1)

    # File info
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_id_column: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_cost_column: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_id_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Seller connection (SP-API)
    seller_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_connections.id"), nullable=True,
    )
    check_restrictions: Mapped[bool] = mapped_column(Boolean, default=True)

    # Counts
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    matched_items: Mapped[int] = mapped_column(Integer, default=0)
    profitable_items: Mapped[int] = mapped_column(Integer, default=0)
    restricted_items: Mapped[int] = mapped_column(Integer, default=0)
    error_items: Mapped[int] = mapped_column(Integer, default=0)

    # Cost profile — dual FBA/MFN
    fulfillment_type: Mapped[str] = mapped_column(String(5), default="fba")  # selected/preferred
    # FBA costs
    fba_prep_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    fba_shipping_to_amazon: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    # MFN costs
    mfn_prep_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    mfn_shipping_to_customer: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    mfn_packaging_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    # Legacy (backward compat)
    prep_cost_per_item: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    shipping_to_amazon: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    # Timing
    processing_speed: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("JobItem", back_populates="job", cascade="all, delete-orphan")
    seller_connection = relationship("SellerConnection", lazy="joined")
