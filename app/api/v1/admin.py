"""Admin endpoints — key rotation, audit, system health."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.auth import get_current_user
from app.core.encryption import generate_new_key, rotate_token
from app.models.seller import SellerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/rotate-encryption-key")
async def rotate_encryption_key(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Rotar encryption key: re-encripta todos los tokens con la key actual.

    Proceso de rotation:
    1. Generar nueva key → ENCRYPTION_KEY_NEW
    2. En .env: mover ENCRYPTION_KEY → ENCRYPTION_KEY_PREVIOUS, poner nueva en ENCRYPTION_KEY
    3. Restart app (carga nuevas keys)
    4. Llamar este endpoint → re-encripta todos los tokens con key nueva
    5. Cuando todo OK, quitar ENCRYPTION_KEY_PREVIOUS del .env
    """
    result = await db.execute(
        select(SellerConnection).where(SellerConnection.is_active == True)
    )
    connections = result.scalars().all()

    rotated = 0
    errors = 0

    for conn in connections:
        try:
            new_encrypted = rotate_token(conn.refresh_token_encrypted)
            conn.refresh_token_encrypted = new_encrypted
            rotated += 1
        except Exception as e:
            logger.error("Error rotating token for seller %s: %s", conn.seller_id, e)
            errors += 1

    await db.commit()

    logger.info("Key rotation: %d rotated, %d errors", rotated, errors)

    return {
        "message": "Key rotation complete",
        "rotated": rotated,
        "errors": errors,
        "next_step": "Remove ENCRYPTION_KEY_PREVIOUS from .env after verifying all tokens work",
    }


@router.get("/generate-key")
async def gen_key(user: dict = Depends(get_current_user)):
    """Genera una nueva Fernet key (para planificar rotation)."""
    return {"new_key": generate_new_key()}
