"""Amazon OAuth — conectar cuenta de Seller Central.

Flujo:
1. GET /authorize → genera URL de autorización de Amazon
2. GET /callback  → Amazon redirige aquí con auth_code
3. Backend exchange auth_code → refresh_token → guarda SellerConnection
"""

import logging
import secrets
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.config import settings
from app.core.auth import get_current_user_with_db
from app.models.seller import SellerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/amazon", tags=["amazon"])

# OAuth state store con TTL (10 min)
import time as _time

_OAUTH_STATE_TTL = 600  # 10 minutos
_oauth_states: dict[str, tuple[str, float]] = {}  # {state: (user_id, created_at)}
_MAX_PENDING_STATES = 100  # Prevenir memory abuse


def _set_oauth_state(state: str, user_id: str) -> None:
    """Guarda state con timestamp. Limpia estados expirados."""
    now = _time.time()
    # Limpiar expirados
    expired = [k for k, (_, t) in _oauth_states.items() if now - t > _OAUTH_STATE_TTL]
    for k in expired:
        del _oauth_states[k]
    # Limitar cantidad
    if len(_oauth_states) >= _MAX_PENDING_STATES:
        oldest = min(_oauth_states, key=lambda k: _oauth_states[k][1])
        del _oauth_states[oldest]
    _oauth_states[state] = (user_id, now)


def _pop_oauth_state(state: str) -> str | None:
    """Extrae y valida state. Retorna user_id o None si expirado/inválido."""
    entry = _oauth_states.pop(state, None)
    if not entry:
        return None
    user_id, created_at = entry
    if _time.time() - created_at > _OAUTH_STATE_TTL:
        return None
    return user_id


AMAZON_AUTH_URL = "https://sellercentral.amazon.com/apps/authorize/consent"
AMAZON_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"


class AuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class ConnectionResponse(BaseModel):
    id: str
    seller_id: str
    store_name: str | None
    marketplace_ids: list[str] | None
    is_active: bool
    connected_at: str | None


class ManualConnectRequest(BaseModel):
    refresh_token: str
    seller_id: str | None = None


@router.get("/authorize", response_model=AuthorizeResponse)
async def authorize(
    redirect_uri: str = Query(default="https://flipiqbatch.com/dashboard/connect/callback"),
    user: dict = Depends(get_current_user_with_db),
):
    """Genera URL de autorización de Amazon Seller Central."""
    state = secrets.token_urlsafe(32)
    _set_oauth_state(state, user["id"])

    params = {
        "application_id": settings.sp_api_app_id,
        "state": state,
        "redirect_uri": redirect_uri,
        # Required while app is in Draft state. Remove after Amazon approves.
        "version": "beta",
    }
    url = f"{AMAZON_AUTH_URL}?{urlencode(params)}"

    return AuthorizeResponse(authorize_url=url, state=state)


@router.get("/callback")
async def callback(
    spapi_oauth_code: str = Query(...),
    state: str = Query(...),
    selling_partner_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Callback de Amazon OAuth — exchange code por refresh_token."""
    # Verificar state con TTL
    user_id = _pop_oauth_state(state)
    if not user_id:
        raise HTTPException(400, "State inválido o expirado")

    # Exchange auth_code → tokens
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(AMAZON_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": spapi_oauth_code,
            "client_id": settings.sp_api_client_id,
            "client_secret": settings.sp_api_client_secret,
        })

        if token_resp.status_code != 200:
            logger.error("Amazon token exchange failed: %s", token_resp.text)
            raise HTTPException(400, "Error al obtener token de Amazon")

        token_data = token_resp.json()
        refresh_token = token_data.get("refresh_token")
        access_token = token_data.get("access_token")

        if not refresh_token:
            raise HTTPException(400, "No se recibió refresh_token de Amazon")

        # Obtener info del seller
        headers = {"x-amz-access-token": access_token, "User-Agent": "FlipIQ/1.0"}
        seller_resp = await client.get(
            f"{SP_API_BASE}/sellers/v1/marketplaceParticipations",
            headers=headers,
        )

    store_name = None
    marketplace_ids = []

    if seller_resp.status_code == 200:
        for p in seller_resp.json().get("payload", []):
            mkt = p.get("marketplace", {})
            participation = p.get("participation", {})
            if participation.get("isParticipating"):
                marketplace_ids.append(mkt.get("id", ""))
            if not store_name:
                store_name = p.get("storeName")

    # Verificar si ya existe conexión para este seller
    existing = await db.execute(
        select(SellerConnection).where(SellerConnection.seller_id == selling_partner_id)
    )
    conn = existing.scalar_one_or_none()

    if conn:
        conn.set_refresh_token(refresh_token)
        conn.store_name = store_name
        conn.marketplace_ids = marketplace_ids
        conn.is_active = True
        conn.user_id = uuid.UUID(user_id)
        conn.set_refresh_token(refresh_token)
    else:
        conn = SellerConnection(
            user_id=uuid.UUID(user_id),
            seller_id=selling_partner_id,
            store_name=store_name,
            marketplace_ids=marketplace_ids,
            refresh_token_encrypted="",
        )
        conn.set_refresh_token(refresh_token)
        db.add(conn)

    await db.commit()
    await db.refresh(conn)

    logger.info("Amazon connected: %s (%s) for user %s", store_name, selling_partner_id, user_id)

    return {
        "message": "Amazon account connected",
        "seller_id": selling_partner_id,
        "store_name": store_name,
        "marketplaces": marketplace_ids,
        "connection_id": str(conn.id),
    }


@router.post("/connect-manual", response_model=ConnectionResponse)
async def connect_manual(
    req: ManualConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Conectar manualmente con refresh_token (solo para desarrollo)."""
    # Obtener seller info usando el refresh_token
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(AMAZON_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": req.refresh_token,
            "client_id": settings.sp_api_client_id,
            "client_secret": settings.sp_api_client_secret,
        })

        if token_resp.status_code != 200:
            raise HTTPException(400, "Refresh token inválido")

        access_token = token_resp.json()["access_token"]

        headers = {"x-amz-access-token": access_token, "User-Agent": "FlipIQ/1.0"}
        seller_resp = await client.get(
            f"{SP_API_BASE}/sellers/v1/marketplaceParticipations",
            headers=headers,
        )

    seller_id = req.seller_id
    store_name = None
    marketplace_ids = []

    if seller_resp.status_code == 200:
        payload = seller_resp.json().get("payload", [])
        for p in payload:
            mkt = p.get("marketplace", {})
            participation = p.get("participation", {})
            if participation.get("isParticipating"):
                marketplace_ids.append(mkt.get("id", ""))
            if not store_name:
                store_name = p.get("storeName")

        # Extraer seller_id del fees response si no fue proporcionado
        if not seller_id:
            # Hacemos una llamada a fees para obtener el seller_id
            fees_resp = await httpx.AsyncClient(timeout=15).post(
                f"{SP_API_BASE}/products/fees/v0/items/B0113UZJE2/feesEstimate",
                headers={**headers, "Content-Type": "application/json"},
                json={"FeesEstimateRequest": {
                    "MarketplaceId": "ATVPDKIKX0DER", "IsAmazonFulfilled": True,
                    "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": 10.0}},
                    "Identifier": "detect",
                }},
            )
            if fees_resp.status_code == 200:
                seller_id = (fees_resp.json().get("payload", {})
                             .get("FeesEstimateResult", {})
                             .get("FeesEstimateIdentifier", {})
                             .get("SellerId"))

    if not seller_id:
        raise HTTPException(400, "No se pudo determinar el Seller ID")

    conn = SellerConnection(
        user_id=uuid.UUID(user["id"]),
        seller_id=seller_id,
        store_name=store_name,
        marketplace_ids=marketplace_ids,
        refresh_token_encrypted="",  # Se encripta abajo
    )
    conn.set_refresh_token(req.refresh_token)
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    return ConnectionResponse(
        id=str(conn.id),
        seller_id=conn.seller_id,
        store_name=conn.store_name,
        marketplace_ids=conn.marketplace_ids,
        is_active=conn.is_active,
        connected_at=str(conn.connected_at),
    )


@router.get("/connections", response_model=list[ConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Lista todas las conexiones de Amazon del usuario."""
    result = await db.execute(
        select(SellerConnection).where(
            SellerConnection.user_id == uuid.UUID(user["id"]),
            SellerConnection.is_active == True,
        )
    )
    connections = result.scalars().all()

    return [
        ConnectionResponse(
            id=str(c.id),
            seller_id=c.seller_id,
            store_name=c.store_name,
            marketplace_ids=c.marketplace_ids,
            is_active=c.is_active,
            connected_at=str(c.connected_at),
        )
        for c in connections
    ]


@router.delete("/connections/{connection_id}")
async def disconnect(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Desconectar una cuenta de Amazon."""
    conn = await db.get(SellerConnection, connection_id)
    if not conn or str(conn.user_id) != user["id"]:
        raise HTTPException(404, "Conexión no encontrada")

    conn.is_active = False
    await db.commit()

    return {"message": "Amazon account disconnected"}
