"""Auditoría append-only: INSERT+SELECT ok; UPDATE/DELETE los rechaza la DB (spec 2.4, D4).

El rechazo por permiso (GRANT/REVOKE de la migración 001) solo existe en
PostgreSQL con el rol app restringido y la URL `APP_ROLE_URL_TEST` apuntando a
esa conexión. Sin Docker esas variables no existen y los 2 casos se skipean,
reportándose como verificación pendiente; en CI (Postgres real) corren siempre.
"""

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.shared.database import create_engine_for


async def _registrar(
    session: AsyncSession, tenant_id: uuid.UUID, actor: uuid.UUID | None = None
) -> Auditoria:
    evento = Auditoria(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=actor,
        accion="usuario.crear",
        entidad="usuario",
        entidad_id="usuario-1",
        antes=None,
        despues={"email": "nueva@example.com"},
    )
    session.add(evento)
    await session.flush()
    return evento


async def test_cambio_critico_deja_rastro_auditable(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    actor = uuid.uuid4()
    evento = await _registrar(session, tenant_a.id, actor)
    leido = (await session.execute(select(Auditoria).where(Auditoria.id == evento.id))).scalar_one()
    assert leido.actor_id == actor
    assert leido.accion == "usuario.crear"
    assert leido.despues == {"email": "nueva@example.com"}
    assert leido.created_at is not None


def _sesion_rol_app() -> AsyncSession:
    """Sesión con el rol app restringido (conecta a Postgres; falla si no hay URL)."""
    url = os.getenv("APP_ROLE_URL_TEST", "")
    if not url:
        pytest.skip(
            "Falta APP_ROLE_URL_TEST (rol app restringido en Postgres); pendiente sin Docker."
        )
    factory = async_sessionmaker(
        create_engine_for(url), class_=AsyncSession, expire_on_commit=False
    )
    return factory()


async def test_update_sobre_auditoria_lo_rechaza_la_db(
    session: AsyncSession, dialecto: str, tenant_a: Tenant
) -> None:
    if dialecto != "postgresql":
        pytest.skip(
            "Requiere Postgres con rol app restringido (migración 001); pendiente sin Docker."
        )
    evento = await _registrar(session, tenant_a.id)
    await session.commit()
    restringida = _sesion_rol_app()
    try:
        with pytest.raises(DBAPIError, match="(?i)(permission|denied|insufficient)"):
            await restringida.execute(
                text("UPDATE auditoria SET accion = 'hack' WHERE id = :id"),
                {"id": evento.id.hex},
            )
            await restringida.commit()
        await restringida.rollback()
    finally:
        await restringida.close()


async def test_delete_sobre_auditoria_lo_rechaza_la_db(
    session: AsyncSession, dialecto: str, tenant_a: Tenant
) -> None:
    if dialecto != "postgresql":
        pytest.skip(
            "Requiere Postgres con rol app restringido (migración 001); pendiente sin Docker."
        )
    evento = await _registrar(session, tenant_a.id)
    await session.commit()
    restringida = _sesion_rol_app()
    try:
        with pytest.raises(DBAPIError, match="(?i)(permission|denied|insufficient)"):
            await restringida.execute(
                text("DELETE FROM auditoria WHERE id = :id"), {"id": evento.id.hex}
            )
            await restringida.commit()
        await restringida.rollback()
    finally:
        await restringida.close()
