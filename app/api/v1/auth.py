"""Endpoints de autenticación con Supabase Auth."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.audit import log_auth_event
from app.core.auth import get_current_user_with_db, get_supabase, upsert_user
from app.core.security_config import validate_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class UserResponse(BaseModel):
    id: str
    email: str
    plan: str = "free"
    is_admin: bool = False
    scans_used_month: int = 0
    scans_limit_month: int = 500


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, request: Request = None, db: AsyncSession = Depends(get_db)):
    """Registrar nuevo usuario con email + password."""
    validate_password(req.password)
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })

        if not response.user:
            await log_auth_event(db, "register", "failure", email=req.email, request=request, reason="no_user_returned")
            await db.commit()
            raise HTTPException(400, "Error al registrar usuario")

        await log_auth_event(db, "register", "success", email=req.email, user_id=response.user.id, request=request)
        await db.commit()

        session = response.session
        if not session:
            return AuthResponse(access_token="", refresh_token="", user_id=response.user.id, email=response.user.email)

        return AuthResponse(
            access_token=session.access_token, refresh_token=session.refresh_token,
            user_id=response.user.id, email=response.user.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error en registro: %s", e)
        await log_auth_event(db, "register", "failure", email=req.email, request=request, reason=str(e)[:200])
        await db.commit()
        raise HTTPException(400, f"Error al registrar: {str(e)}")


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request = None, db: AsyncSession = Depends(get_db)):
    """Login con email + password."""
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })

        if not response.user or not response.session:
            await log_auth_event(db, "login", "failure", email=req.email, request=request, reason="invalid_credentials")
            await db.commit()
            raise HTTPException(401, "Credenciales inválidas")

        # Upsert en nuestra tabla users (sync con Supabase Auth)
        await upsert_user(db, response.user.id, response.user.email)
        await log_auth_event(db, "login", "success", email=req.email, user_id=response.user.id, request=request)
        await db.commit()

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user_id=response.user.id,
            email=response.user.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error en login: %s", e)
        await log_auth_event(db, "login", "failure", email=req.email, request=request, reason=str(e)[:200])
        await db.commit()
        raise HTTPException(401, f"Credenciales inválidas: {str(e)}")


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(refresh_token: str):
    """Renovar access token con refresh token."""
    try:
        supabase = get_supabase()
        response = supabase.auth.refresh_session(refresh_token)

        if not response.user or not response.session:
            raise HTTPException(401, "Refresh token inválido")

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user_id=response.user.id,
            email=response.user.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"Error al renovar token: {str(e)}")


@router.get("/me", response_model=UserResponse)
async def get_me(
    supabase_info: dict = Depends(get_current_user_with_db),
    db: AsyncSession = Depends(get_db),
):
    """Obtener perfil del usuario autenticado (desde nuestra tabla users)."""
    user = await upsert_user(db, supabase_info["id"], supabase_info["email"])
    await db.commit()
    return UserResponse(
        id=str(user.id),
        email=user.email,
        plan=user.plan,
        is_admin=user.is_admin,
        scans_used_month=user.scans_used_month,
        scans_limit_month=user.scans_limit_month,
    )
