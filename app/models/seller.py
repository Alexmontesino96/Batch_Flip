"""SellerConnection — vincula una cuenta de Amazon Seller Central con nuestro sistema.

Para MVP: una sola conexión con refresh_token del .env.
Para SaaS: cada usuario conecta su cuenta via OAuth, se almacena el refresh_token
encriptado y se usa para llamar SP-API en nombre del seller.
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

    # OAuth credentials (encriptadas en producción)
    refresh_token: Mapped[str] = mapped_column(Text)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
