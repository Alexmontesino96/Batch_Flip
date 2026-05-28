"""Audit Log — registro de eventos de seguridad.

Amazon requiere:
- Logs de seguridad retenidos 12 meses mínimo
- Capturar: success/failure, timestamps, user IDs, access attempts, data changes
- Revisión bi-semanal o monitoreo en tiempo real
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)  # auth.login, auth.register, amazon.connect, job.create, etc.
    resource: Mapped[str | None] = mapped_column(String(100), nullable=True)  # job_id, seller_id, asin
    status: Mapped[str] = mapped_column(String(10))  # success, failure
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON con detalles extras
