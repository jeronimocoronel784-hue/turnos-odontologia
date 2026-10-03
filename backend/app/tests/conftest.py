"""Fixtures compartidos: DB real (Postgres en CI/Docker, SQLite file local sin Docker).

R11: la fuente de verdad es Postgres en contenedor (CI + task 4.3). El fallback a
SQLite solo permite desarrollar sin Docker; `dialecto` expone el motor activo para
skipear lo que sea específico de Postgres (GRANTs de auditoría).
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importar modelos para que create_all los vea (SQLAlchemy 2.0 sin registry global).
import app.domain.auditoria  # noqa: F401
import app.domain.tenant  # noqa: F401
import app.domain.usuario  # noqa: F401
from app.domain.tenant import Tenant
from app.infrastructure.db.base import Base
from app.shared.database import create_engine_for


def _test_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    override = os.getenv("DATABASE_URL_TEST", "")
    if override:
        return override
    return f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('db')}/test.db"


@pytest.fixture(scope="session")
def db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _test_db_url(tmp_path_factory)


@pytest.fixture(scope="session")
def dialecto(db_url: str) -> str:
    return "postgresql" if db_url.startswith(("postgresql", "postgres")) else "sqlite"


@pytest_asyncio.fixture()
async def session(db_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Sesión async sobre DB real con esquema creado y limpio por test."""
    engine = create_engine_for(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as ses:
        yield ses
        # Limpieza: borra en orden inverso a las FK.
        for tabla in ("auditoria", "usuario", "tenant"):
            await ses.execute(text(f"DELETE FROM {tabla}"))
        await ses.commit()
    await engine.dispose()


@pytest_asyncio.fixture()
async def tenant_a(session: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(), slug="tenant-a-test", nombre="Tenant A Test", politicas={}, activo=True
    )
    session.add(tenant)
    await session.flush()
    return tenant


@pytest_asyncio.fixture()
async def tenant_b(session: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(), slug="tenant-b-test", nombre="Tenant B Test", politicas={}, activo=True
    )
    session.add(tenant)
    await session.flush()
    return tenant
