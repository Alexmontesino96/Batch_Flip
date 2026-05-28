"""Audit logging service.

Registra eventos de seguridad en la tabla audit_logs.
Amazon requiere retención de 12 meses y revisión bi-semanal.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("audit")


async def log_event(
    db: AsyncSession,
    action: str,
    status: str = "success",
    user_id: str | None = None,
    resource: str | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Registra un evento de seguridad en audit_logs."""
    ip = None
    ua = None
    if request:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:255]

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        status=status,
        ip_address=ip,
        user_agent=ua,
        details=json.dumps(details) if details else None,
    )

    db.add(entry)
    # No hacemos commit aquí — se commitea con la transacción del endpoint

    # También log a stdout para monitoreo en tiempo real
    logger.info(
        "AUDIT | %s | %s | user=%s | resource=%s | ip=%s | %s",
        action, status, user_id or "anon", resource or "-", ip or "-",
        json.dumps(details)[:200] if details else "",
    )


async def log_auth_event(
    db: AsyncSession, action: str, status: str,
    email: str | None = None, user_id: str | None = None,
    request: Request | None = None, reason: str | None = None,
) -> None:
    """Shortcut para eventos de autenticación."""
    await log_event(
        db, action=f"auth.{action}", status=status,
        user_id=user_id, resource=email,
        details={"reason": reason} if reason else None,
        request=request,
    )


async def log_amazon_event(
    db: AsyncSession, action: str, status: str,
    user_id: str, seller_id: str | None = None,
    request: Request | None = None, details: dict | None = None,
) -> None:
    """Shortcut para eventos de Amazon OAuth/data access."""
    await log_event(
        db, action=f"amazon.{action}", status=status,
        user_id=user_id, resource=seller_id,
        details=details, request=request,
    )


async def log_data_access(
    db: AsyncSession, user_id: str, resource_type: str,
    resource_id: str, action: str = "read",
    request: Request | None = None,
) -> None:
    """Shortcut para accesos a Amazon data."""
    await log_event(
        db, action=f"data.{action}", status="success",
        user_id=user_id, resource=f"{resource_type}:{resource_id}",
        request=request,
    )
