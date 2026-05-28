"""SellerConnection — vincula una cuenta de Amazon Seller Central con nuestro sistema.

El refresh_token se almacena encriptado con Fernet (AES-128-CBC)
para cumplir con Amazon Data Protection Policy.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SellerConnection(Base):
    __tablename__ = "seller_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Amazon seller info
    seller_id: Mapped[str] = mapped_column(String(20), unique=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marketplace_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # OAuth credentials — ENCRIPTADO con Fernet
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def set_refresh_token(self, plaintext_token: str) -> None:
        """Encripta y guarda el refresh_token."""
        from app.core.encryption import encrypt
        self.refresh_token_encrypted = encrypt(plaintext_token)

    def get_refresh_token(self) -> str:
        """Desencripta y retorna el refresh_token."""
        from app.core.encryption import decrypt
        return decrypt(self.refresh_token_encrypted)
