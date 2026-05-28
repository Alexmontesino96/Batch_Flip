from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _get_db_url() -> str:
    """Normaliza la DATABASE_URL para asyncpg."""
    url = settings.database_url
    # Render/Supabase pueden dar postgresql:// — asyncpg necesita postgresql+asyncpg://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(
    _get_db_url(),
    echo=settings.debug,
    pool_size=5,       # Render/Supabase tienen limits bajos
    max_overflow=5,
    pool_recycle=300,   # Reciclar conexiones cada 5 min
    pool_pre_ping=True, # Verificar conexión antes de usar
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session
