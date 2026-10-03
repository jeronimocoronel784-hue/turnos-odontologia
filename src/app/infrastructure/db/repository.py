"""BaseRepository[T]: todo acceso a datos de negocio filtra por `tenant_id` (D3).

El `tenant_id` efectivo viene del contexto (JWT en C-03, R4) y se inyecta al
construir el repositorio. Si falta, se levanta error en vez de devolver datos
sin filtro: ver filas del tenant equivocado es bug CRITICAL que bloquea el change.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import AppError


class TenantContextoRequerido(AppError):
    """Se intentó consultar sin tenant: el sistema se niega antes de filtrar mal."""

    def __init__(self) -> None:
        super().__init__("Che, falta el consultorio en el contexto. Probá loguearte de nuevo.", 401)


class BaseRepository[T]:
    """Repositorio genérico con aislamiento por tenant automático."""

    def __init__(self, session: AsyncSession, tenant_id: UUID | None, modelo: type[T]) -> None:
        if tenant_id is None:
            raise TenantContextoRequerido()
        self.session = session
        self.tenant_id = tenant_id
        self.modelo = modelo

    async def agregar(self, entidad: T) -> T:
        """Agrega una entidad del tenant actual (falla si trae otro tenant_id)."""
        actual = getattr(entidad, "tenant_id", None)
        if actual is not None and actual != self.tenant_id:
            raise TenantContextoRequerido()
        setattr(entidad, "tenant_id", self.tenant_id)  # noqa: B010
        self.session.add(entidad)
        await self.session.flush()
        return entidad

    async def obtener(self, entidad_id: object) -> T | None:
        """Obtiene por PK solo si pertenece al tenant actual."""
        stmt = select(self.modelo).where(  # type: ignore[arg-type]
            self.modelo.tenant_id == self.tenant_id,  # type: ignore[attr-defined]
            self.modelo.id == entidad_id,  # type: ignore[attr-defined]
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def listar(self, limite: int = 100) -> list[T]:
        """Lista filas SOLO del tenant actual, con límite defensivo."""
        stmt = (
            select(self.modelo)  # type: ignore[arg-type]
            .where(self.modelo.tenant_id == self.tenant_id)  # type: ignore[attr-defined]
            .limit(limite)
        )
        return list((await self.session.execute(stmt)).scalars().all())
