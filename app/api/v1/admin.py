"""Admin endpoints — solo accesibles con rol admin.

Protegido: solo usuarios con is_admin en user_metadata de Supabase.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.auth import get_current_user_with_db, upsert_user
from app.core.encryption import generate_new_key, rotate_token
from app.models.seller import SellerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(
    supabase_info: dict = Depends(get_current_user_with_db),
    db: AsyncSession = Depends(get_db),
) -> "User":
    """Dependency: requiere is_admin=True en nuestra tabla users (no Supabase metadata)."""
    user = await upsert_user(db, supabase_info["id"], supabase_info["email"])
    if not user.is_admin:
        raise HTTPException(403, "Acceso denegado: se requiere rol admin")
    return user


@router.post("/rotate-encryption-key")
async def rotate_encryption_key(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Rotar encryption key: re-encripta todos los tokens con la key actual.

    Proceso:
    1. Generar nueva key con GET /admin/generate-key
    2. En .env: ENCRYPTION_KEY=nueva, ENCRYPTION_KEY_PREVIOUS=vieja
    3. Restart app
    4. POST este endpoint → re-encripta todos los tokens
    5. Quitar ENCRYPTION_KEY_PREVIOUS
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
    logger.info("Key rotation by admin %s: %d rotated, %d errors", user["id"], rotated, errors)

    return {"message": "Key rotation complete", "rotated": rotated, "errors": errors}


@router.get("/generate-key")
async def gen_key(user: dict = Depends(require_admin)):
    """Genera una nueva Fernet key (solo admin)."""
    return {"new_key": generate_new_key()}
