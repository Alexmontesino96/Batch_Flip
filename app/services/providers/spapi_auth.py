"""SP-API OAuth token lifecycle.

Maneja obtención y auto-refresh del access token.
El access token expira en 3600s — se cachea en memoria
y se renueva automáticamente cuando queda < 60s.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
TOKEN_MARGIN_SECONDS = 60  # Renovar cuando quedan menos de 60s


class SPAPIAuth:
    """Maneja el OAuth token para SP-API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret and self._refresh_token)

    def _is_expired(self) -> bool:
        return time.time() >= (self._expires_at - TOKEN_MARGIN_SECONDS)

    async def get_access_token(self, http_client: httpx.AsyncClient) -> str:
        """Obtiene un access token válido. Renueva si está expirado."""
        if self._access_token and not self._is_expired():
            return self._access_token

        logger.debug("SP-API: Renovando access token")
        resp = await http_client.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        })
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)

        logger.info("SP-API: Token renovado, expira en %ds", data.get("expires_in", 3600))
        return self._access_token

    async def get_headers(self, http_client: httpx.AsyncClient) -> dict[str, str]:
        """Retorna headers con access token para SP-API requests."""
        token = await self.get_access_token(http_client)
        return {
            "x-amz-access-token": token,
            "User-Agent": "FlipIQ/1.0 (Language=Python)",
            "Content-Type": "application/json",
        }

    def invalidate(self) -> None:
        """Fuerza renovación del token en la próxima llamada."""
        self._access_token = None
        self._expires_at = 0.0
