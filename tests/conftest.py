"""Fixtures compartidos: DB real (Postgres en CI/Docker, SQLite file local sin Docker).

R11: la fuente de verdad es Postgres en contenedor (CI + task 4.3). El fallback a
SQLite solo permite desarrollar sin Docker; `dialecto` expone el motor activo para
skipear lo que sea específico de Postgres (GRANTs de auditoría).
"""

import os
import sys
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path

# El package `app` vive en src/backend/ (layout src/backend/ + src/frontend/ + tests/).
# Esto permite `pytest tests` desde la raíz sin instalación editable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importar modelos para que create_all los vea (SQLAlchemy 2.0 sin registry global).
import app.domain.auditoria  # noqa: F401
import app.domain.refresh_token  # noqa: F401
import app.domain.tenant  # noqa: F401
import app.domain.token_gestion  # noqa: F401
import app.domain.usuario  # noqa: F401
from app.api import deps
from app.api.routers import auth, usuarios
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.base import Base
from app.infrastructure.security.passwords import hashear_password
from app.shared.database import create_engine_for
from app.shared.exceptions import register_handlers
from app.shared.settings import Settings


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
        for tabla in ("auditoria", "refresh_token", "token_gestion", "usuario", "tenant"):
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


@pytest.fixture()
def settings_test() -> Settings:
    """Settings de test: bcrypt barato, cookie sin `Secure` (http) y rate limit 5/60 s."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/9",
        jwt_secret="secreto-de-test-con-mas-de-32-caracteres-ok",
        jwt_access_min=15,
        jwt_refresh_days=30,
        cookie_secure=False,
        bcrypt_rounds=4,
        login_rate_limit=5,
        login_rate_window_s=60,
    )


@pytest_asyncio.fixture()
async def redis_fake() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Redis en memoria: el limiter se prueba sin servidor (CI usa Redis real)."""
    cliente = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield cliente
    await cliente.flushall()
    await cliente.aclose()


def _app_de_prueba(
    session: AsyncSession,
    settings: Settings,
    redis: object,
    *routers: object,
) -> FastAPI:
    """App mínima con las dependencias apuntadas a la DB/Redis de test."""
    app = FastAPI()
    register_handlers(app)
    for router in routers:
        app.include_router(router, prefix="/api")  # type: ignore[arg-type]

    async def _sesion() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[deps.sesion_db] = _sesion
    app.dependency_overrides[deps.settings_cacheados] = lambda: settings
    app.dependency_overrides[deps.cliente_redis] = lambda: redis
    return app


@pytest.fixture()
def app_factory(
    session: AsyncSession, settings_test: Settings, redis_fake: fakeredis.aioredis.FakeRedis
) -> Callable[..., FastAPI]:
    """Permite montar apps con routers extra (probes de RBAC) sobre la misma DB."""

    def _crear(*routers: object) -> FastAPI:
        return _app_de_prueba(session, settings_test, redis_fake, *routers)

    return _crear


@pytest_asyncio.fixture()
async def api(
    app_factory: Callable[..., FastAPI],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Cliente HTTP contra los routers reales de auth y usuarios."""
    app = app_factory(auth.router, usuarios.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as cliente:
        yield cliente


@pytest_asyncio.fixture()
async def crear_usuario(
    session: AsyncSession, settings_test: Settings
) -> Callable[..., Awaitable[Usuario]]:
    """Factory de usuarios de staff con password ya hasheado (bcrypt barato)."""

    async def _crear(
        tenant: Tenant,
        *,
        email: str,
        password: str = "secreto-de-prueba",
        rol: RolUsuario = RolUsuario.RECEPCION,
        activo: bool = True,
        nombre: str = "Persona Test",
    ) -> Usuario:
        usuario = Usuario(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=email,
            nombre=nombre,
            rol=rol,
            matricula="MP-1234" if rol == RolUsuario.ODONTOLOGO else None,
            password_hash=hashear_password(password, settings_test.bcrypt_rounds),
            activo=activo,
        )
        session.add(usuario)
        await session.flush()
        return usuario

    return _crear
