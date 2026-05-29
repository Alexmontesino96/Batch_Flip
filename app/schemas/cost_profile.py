"""Schemas Pydantic para Cost Profiles."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CostProfileCreate(BaseModel):
    name: str = Field(..., max_length=100, description="Nombre del perfil de costos")
    marketplace: str = Field(default="us", description="Amazon marketplace")
    fulfillment_type: Literal["fba", "mfn", "both"] = Field(default="both", description="Tipo de fulfillment")
    # FBA costs
    fba_prep_cost: float = Field(default=0.0, ge=0, description="Costo de preparación por item para FBA")
    fba_shipping_to_amazon: float = Field(default=0.0, ge=0, description="Envío al almacén FBA por item")
    # MFN costs
    mfn_prep_cost: float = Field(default=0.0, ge=0, description="Costo de preparación por item para MFN")
    mfn_shipping_to_customer: float = Field(default=0.0, ge=0, description="Envío al cliente por item")
    mfn_packaging_cost: float = Field(default=0.0, ge=0, description="Costo de empaque por item para MFN")
    is_default: bool = Field(default=False, description="Si es el perfil por defecto del usuario")


class CostProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    marketplace: str | None = Field(default=None)
    fulfillment_type: Literal["fba", "mfn", "both"] | None = Field(default=None)
    fba_prep_cost: float | None = Field(default=None, ge=0)
    fba_shipping_to_amazon: float | None = Field(default=None, ge=0)
    mfn_prep_cost: float | None = Field(default=None, ge=0)
    mfn_shipping_to_customer: float | None = Field(default=None, ge=0)
    mfn_packaging_cost: float | None = Field(default=None, ge=0)
    is_default: bool | None = Field(default=None)


class CostProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    marketplace: str
    fulfillment_type: str
    fba_prep_cost: float
    fba_shipping_to_amazon: float
    mfn_prep_cost: float
    mfn_shipping_to_customer: float
    mfn_packaging_cost: float
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
