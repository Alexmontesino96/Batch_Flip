"""Fernet encryption for Amazon tokens at rest.

Cumple con Amazon Data Protection Policy:
- Datos sensibles encriptados en DB (AES-128-CBC via Fernet)
- Key almacenada en variable de entorno, no en código
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY not configured")
        _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encripta un string. Retorna texto base64 encriptado."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Desencripta un string encriptado con encrypt()."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Token de encriptación inválido o datos corruptos")
