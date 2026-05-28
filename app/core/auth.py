"""Supabase Auth + User ORM sync.

Supabase maneja JWT. Nosotros:
- Validamos JWT con Supabase admin client
- Hacemos upsert en nuestra tabla users (plan, is_admin, rate limits)
- get_current_user retorna User ORM (no dict de Supabase)
"""

import logging
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_supabase_client: Optional[Client] = None
_supabase_admin: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _supabase_client


def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_admin


async def upsert_user(db: AsyncSession, supabase_id: str, email: str) -> "User":
    """Crea o actualiza nuestro User local sincronizado con Supabase Auth."""
    from app.models.user import User, PLAN_LIMITS

    user = await db.get(User, uuid.UUID(supabase_id))
    if user:
        if user.email != email:
            user.email = email
        return user

    user = User(
        id=uuid.UUID(supabase_id),
        supabase_id=supabase_id,
        email=email,
        plan="free",
        scans_limit_month=PLAN_LIMITS["free"],
    )
    db.add(user)
    await db.flush()
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(None),  # Se overridea por el endpoint
) -> "User":
    """Dependency: valida JWT → retorna User ORM de nuestra DB.

    NOTA: Los endpoints deben pasar db explícitamente. Esta función
    se usa como base — ver get_current_user_with_db abajo.
    """
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Use get_current_user_with_db")


async def get_current_user_with_db(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Paso 1: Valida JWT con Supabase y retorna info básica.

    Los endpoints que necesitan el User ORM hacen el upsert + lookup en su propio db session.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        supabase = get_supabase_admin()
        user_response = supabase.auth.get_user(token)
        user = user_response.user

        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")

        return {
            "id": user.id,
            "email": user.email,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error validando token: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")


async def get_authenticated_user(
    supabase_info: dict = Depends(get_current_user_with_db),
) -> dict:
    """Dependency para endpoints que NO necesitan DB (retorna dict básico)."""
    return supabase_info


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict | None:
    if not credentials:
        return None
    try:
        return await get_current_user_with_db(credentials)
    except HTTPException:
        return None
