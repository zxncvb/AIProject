from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
admin_engine = create_async_engine(settings.database_admin_url or settings.database_url, pool_pre_ping=True)
AdminSessionLocal = async_sessionmaker(admin_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_admin_db() -> AsyncIterator[AsyncSession]:
    async with AdminSessionLocal() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Set transaction-local context consumed by the optional PostgreSQL RLS policies."""
    await session.execute(text("select set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
