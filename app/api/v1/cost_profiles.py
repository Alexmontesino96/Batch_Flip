"""Endpoints para Cost Profiles — todos protegidos con auth + ownership."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.auth import get_current_user_with_db
from app.models.cost_profile import CostProfile
from app.schemas.cost_profile import CostProfileCreate, CostProfileResponse, CostProfileUpdate

router = APIRouter(prefix="/cost-profiles", tags=["cost-profiles"])


async def get_profile_with_ownership(
    profile_id: uuid.UUID,
    db: AsyncSession,
    user_id: str,
) -> CostProfile:
    """Obtiene un perfil verificando que pertenece al usuario. Raises 404 si no existe o no es suyo."""
    profile = await db.get(CostProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Perfil de costos no encontrado")
    if str(profile.user_id) != user_id:
        raise HTTPException(404, "Perfil de costos no encontrado")
    return profile


@router.post("", response_model=CostProfileResponse, status_code=201)
async def create_cost_profile(
    req: CostProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Crear un nuevo perfil de costos (requiere autenticación)."""
    # Si el nuevo perfil es default, quitar el flag de los demás del usuario
    if req.is_default:
        existing = await db.execute(
            select(CostProfile).where(
                CostProfile.user_id == uuid.UUID(user["id"]),
                CostProfile.is_default == True,  # noqa: E712
            )
        )
        for old_profile in existing.scalars().all():
            old_profile.is_default = False

    profile = CostProfile(
        user_id=uuid.UUID(user["id"]),
        name=req.name,
        marketplace=req.marketplace,
        fulfillment_type=req.fulfillment_type,
        fba_prep_cost=req.fba_prep_cost,
        fba_shipping_to_amazon=req.fba_shipping_to_amazon,
        mfn_prep_cost=req.mfn_prep_cost,
        mfn_shipping_to_customer=req.mfn_shipping_to_customer,
        mfn_packaging_cost=req.mfn_packaging_cost,
        is_default=req.is_default,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("", response_model=list[CostProfileResponse])
async def list_cost_profiles(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Listar perfiles de costos del usuario autenticado."""
    result = await db.execute(
        select(CostProfile)
        .where(CostProfile.user_id == uuid.UUID(user["id"]))
        .order_by(CostProfile.is_default.desc(), CostProfile.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{profile_id}", response_model=CostProfileResponse)
async def get_cost_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Obtener un perfil de costos por ID (requiere auth + ownership)."""
    return await get_profile_with_ownership(profile_id, db, user["id"])


@router.put("/{profile_id}", response_model=CostProfileResponse)
async def update_cost_profile(
    profile_id: uuid.UUID,
    req: CostProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Actualizar un perfil de costos (requiere auth + ownership)."""
    profile = await get_profile_with_ownership(profile_id, db, user["id"])

    # Si se está marcando como default, quitar el flag de los demás del usuario
    if req.is_default:
        existing = await db.execute(
            select(CostProfile).where(
                CostProfile.user_id == uuid.UUID(user["id"]),
                CostProfile.is_default == True,  # noqa: E712
                CostProfile.id != profile_id,
            )
        )
        for old_profile in existing.scalars().all():
            old_profile.is_default = False

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_cost_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Eliminar un perfil de costos (requiere auth + ownership)."""
    profile = await get_profile_with_ownership(profile_id, db, user["id"])
    await db.delete(profile)
    await db.commit()
