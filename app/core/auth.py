"""Supabase Auth — registro, login, y validación de JWT.

Supabase maneja:
- Registro/login (email + password)
- JWT tokens (access + refresh)
- Social login (Google, etc.)
- Email verification, password reset

Nosotros:
- Validamos el JWT en cada request protegido
- Extraemos user_id del token
- Usamos service_role para operaciones admin
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)

# Supabase clients (lazy init)
_supabase_client: Optional[Client] = None
_supabase_admin: Optional[Client] = None


def get_supabase() -> Client:
    """Supabase client con anon key (para operaciones de usuario)."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _supabase_client


def get_supabase_admin() -> Client:
    """Supabase client con service_role key (para operaciones admin)."""
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_admin


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Dependency: valida JWT y retorna user data de Supabase.

    Retorna dict con: id, email, user_metadata, etc.
    Raises 401 si no hay token o es inválido.
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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado",
            )

        return {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
            "created_at": str(user.created_at) if user.created_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error validando token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict | None:
    """Dependency: igual que get_current_user pero retorna None si no hay token."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
