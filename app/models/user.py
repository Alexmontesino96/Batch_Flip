"""User — tabla propia sincronizada con Supabase Auth.

Supabase Auth maneja registro/login/JWT.
Esta tabla persiste: plan, is_admin, rate limits, stripe_customer_id.
Se crea automáticamente en el primer login/register (upsert).

Basado en FlipIQ users (supabase_id, tier, credits).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Límites por plan
PLAN_LIMITS = {
    "free": 999_999_999,
    "starter": 50_000,
    "pro": 200_000,
    "enterprise": 999_999_999,
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    supabase_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Plan y permisos
    plan: Mapped[str] = mapped_column(String(20), default="free")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Rate limiting
    scans_used_month: Mapped[int] = mapped_column(Integer, default=0)
    scans_limit_month: Mapped[int] = mapped_column(Integer, default=999_999_999)

    # Billing (futuro)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
