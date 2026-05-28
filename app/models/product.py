"""Product — cache compartida de datos de producto por ASIN.

Datos de Keepa y SP-API se guardan aquí para evitar duplicación.
job_items referencia a products.asin para datos compartidos.
Datos per-seller (can_sell, profit, fees) siguen en job_items.

Basado en FlipIQ products pero con ASIN como PK (no barcode).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    # ASIN como primary key
    asin: Mapped[str] = mapped_column(String(10), primary_key=True)

    # Datos básicos
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Pricing
    buy_box_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    list_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Velocity
    sales_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_rank_drops_30: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reviews
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Fees
    referral_fee_pct: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    fba_fulfillment_fee: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Competition
    seller_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Media
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Identifiers
    parent_asin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    upc: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)

    # Flags
    is_hazmat: Mapped[bool] = mapped_column(Boolean, default=False)
    is_adult_product: Mapped[bool] = mapped_column(Boolean, default=False)

    # Analytics
    analysis_count: Mapped[int] = mapped_column(Integer, default=0)

    # Cache timestamps
    keepa_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    spapi_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
