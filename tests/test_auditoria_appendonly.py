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
from app.domain.usuario import RolUsuario
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


def _assert_permiso_denegado(exc: DBAPIError) -> None:
    """Verifica el rechazo por SQLSTATE 42501 (insufficient_privilege).

    Se mira el código y no el mensaje porque el texto del error depende del
    `lc_messages` del servidor ("permission denied" vs "permiso denegado").
    """
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    assert sqlstate == "42501", f"Se esperaba rechazo por permiso (42501); llegó: {exc.orig}"


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
        with pytest.raises(DBAPIError) as exc_info:
            await restringida.execute(
                text("UPDATE auditoria SET accion = 'hack' WHERE id = :id"),
                {"id": evento.id.hex},
            )
            await restringida.commit()
        _assert_permiso_denegado(exc_info.value)
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
        with pytest.raises(DBAPIError) as exc_info:
            await restringida.execute(
                text("DELETE FROM auditoria WHERE id = :id"), {"id": evento.id.hex}
            )
            await restringida.commit()
        _assert_permiso_denegado(exc_info.value)
        await restringida.rollback()
    finally:
        await restringida.close()


# ---------------------------------------------------------------------------
# 3.1 / 3.2 Inmutabilidad expuesta por la API (HTTP 405 + matriz RBAC + OpenAPI)
# ---------------------------------------------------------------------------


AUDITORIA_URL = "/api/auditoria"


async def _evento_api(session, tenant) -> Auditoria:
    import uuid as _uuid

    evento = Auditoria(
        id=_uuid.uuid4(),
        tenant_id=tenant.id,
        actor_id=None,
        accion="usuario.crear",
        entidad="usuario",
        entidad_id="usuario-1",
        antes=None,
        despues={"email": "nueva@example.com"},
    )
    session.add(evento)
    await session.flush()
    await session.commit()
    return evento


async def test_metodos_de_escritura_sobre_auditoria_responden_405(
    api, session, tenant_a, crear_usuario, token_para, autorizacion
) -> None:
    usuario = await crear_usuario(tenant_a, email="dueno-appendonly@test", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(usuario))
    evento = await _evento_api(session, tenant_a)

    for path in (AUDITORIA_URL, f"{AUDITORIA_URL}/{evento.id}"):
        for metodo in ("delete", "put", "patch"):
            respuesta = await getattr(api, metodo)(path, headers=headers)
            assert respuesta.status_code == 405, (
                metodo,
                path,
                respuesta.status_code,
                respuesta.text,
            )

    # El evento sigue existiendo tras el intento.
    listado = await api.get(AUDITORIA_URL, headers=headers)
    assert listado.status_code == 200, listado.text
    ids = [e["id"] for e in listado.json()["eventos"]]
    assert str(evento.id) in ids


async def test_borrar_sobre_auditoria_denegado_para_todos_los_roles() -> None:
    from app.domain.rbac import MATRIZ, Accion, Recurso, permite

    for rol in ("dueno", "recepcion", "odontologo"):
        assert permite([rol], Recurso.AUDITORIA, Accion.BORRAR) is False
        assert Accion.BORRAR not in MATRIZ[Recurso.AUDITORIA][rol]


def test_router_no_declara_rutas_de_escritura_en_openapi() -> None:
    from app.main import app

    paths = app.openapi().get("paths", {})
    metodos_escritura = {"post", "put", "patch", "delete"}
    for path, operaciones in paths.items():
        if path == AUDITORIA_URL or path.startswith(AUDITORIA_URL + "/"):
            solapados = metodos_escritura & set(operaciones)
            assert not solapados, (path, solapados)
