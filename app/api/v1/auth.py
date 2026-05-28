"""Endpoints de autenticación con Supabase Auth."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.core.auth import get_current_user, get_supabase

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
    user_metadata: dict


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """Registrar nuevo usuario con email + password."""
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })

        if not response.user:
            raise HTTPException(400, "Error al registrar usuario")

        session = response.session
        if not session:
            # Email confirmation required
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=response.user.id,
                email=response.user.email,
            )

        return AuthResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user_id=response.user.id,
            email=response.user.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error en registro: %s", e)
        raise HTTPException(400, f"Error al registrar: {str(e)}")


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Login con email + password."""
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })

        if not response.user or not response.session:
            raise HTTPException(401, "Credenciales inválidas")

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
async def get_me(user: dict = Depends(get_current_user)):
    """Obtener perfil del usuario autenticado."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        user_metadata=user["user_metadata"],
    )
