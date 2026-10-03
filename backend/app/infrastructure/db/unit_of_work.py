"""UnitOfWork: agrupa la transacción de un request (D1/D3)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import BaseRepository


class UnitOfWork:
    """Contexto transaccional: commit al salir bien, rollback si algo falla."""

    def __init__(self, session: AsyncSession, tenant_id: UUID | None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    def repos[T](self, modelo: type[T]) -> BaseRepository[T]:
        """Repositorio del tenant actual para el modelo dado."""
        return BaseRepository(self.session, self.tenant_id, modelo)


@asynccontextmanager
async def usar_uow(
    session: AsyncSession, tenant_id: UUID | None
) -> AsyncGenerator[UnitOfWork, None]:
    """Helper: `async with usar_uow(session, tenant) as uow:` con commit/rollback automático."""
    uow = UnitOfWork(session, tenant_id)
    try:
        yield uow
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise
