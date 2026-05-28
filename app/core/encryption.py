"""Fernet encryption for Amazon tokens at rest.

Cumple con Amazon Data Protection Policy:
- AES-128-CBC via Fernet (aprobado por Amazon)
- Key rotation anual con soporte dual-key durante migración
- Key almacenada en env var, nunca en código ni DB
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None
_multi_fernet: MultiFernet | None = None


def _get_fernet() -> Fernet:
    """Fernet con key actual (para encriptar)."""
    global _fernet
    if _fernet is None:
        if not settings.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY not configured")
        _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def _get_multi_fernet() -> MultiFernet:
    """MultiFernet con key actual + previous (para desencriptar durante rotation).

    MultiFernet intenta desencriptar con cada key en orden.
    La primera key es la actual (se usa para encriptar).
    La segunda es la anterior (solo para desencriptar tokens viejos).
    """
    global _multi_fernet
    if _multi_fernet is None:
        keys = [Fernet(settings.encryption_key.encode())]
        if settings.encryption_key_previous:
            keys.append(Fernet(settings.encryption_key_previous.encode()))
        _multi_fernet = MultiFernet(keys)
    return _multi_fernet


def encrypt(plaintext: str) -> str:
    """Encripta un string con la key actual."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Desencripta con key actual o previous (para rotation)."""
    try:
        return _get_multi_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Token de encriptación inválido o datos corruptos")


def rotate_token(ciphertext: str) -> str:
    """Re-encripta un token con la key actual.

    Usado durante key rotation: lee con key vieja, escribe con key nueva.
    """
    mf = _get_multi_fernet()
    try:
        return mf.rotate(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("No se pudo rotar — token inválido con ambas keys")


def generate_new_key() -> str:
    """Genera una nueva Fernet key para rotation."""
    return Fernet.generate_key().decode()
