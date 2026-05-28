"""Dependencies compartidas para endpoints."""

import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_job_with_ownership(
    job_id: uuid.UUID,
    db: AsyncSession,
    user_id: str,
):
    """Obtiene un job verificando que pertenece al usuario. Raises 404 si no existe o no es suyo."""
    from app.models.job import Job
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if str(job.user_id) != user_id:
        raise HTTPException(404, "Job no encontrado")  # 404 en vez de 403 para no revelar existencia
    return job


async def validate_seller_connection_ownership(
    seller_connection_id: uuid.UUID | None,
    user_id: str,
    db: AsyncSession,
) -> None:
    """Verifica que la seller_connection pertenece al usuario. Raises 403 si no."""
    if not seller_connection_id:
        return
    from app.models.seller import SellerConnection
    conn = await db.get(SellerConnection, seller_connection_id)
    if not conn or str(conn.user_id) != user_id:
        raise HTTPException(403, "Seller connection no pertenece a este usuario")
    if not conn.is_active:
        raise HTTPException(400, "Seller connection inactiva")
