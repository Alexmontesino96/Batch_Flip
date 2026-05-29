"""Modelo SQLAlchemy para Cost Profiles."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CostProfile(Base):
    __tablename__ = "cost_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(5), default="us")
    fulfillment_type: Mapped[str] = mapped_column(String(5), default="both")  # fba, mfn, both

    # FBA costs
    fba_prep_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    fba_shipping_to_amazon: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    # MFN costs
    mfn_prep_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    mfn_shipping_to_customer: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    mfn_packaging_cost: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
