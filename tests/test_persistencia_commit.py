"""Persistencia cross-sesión de los endpoints mutantes (C-19, spec `persistencia-sesiones`).

Guard de commit: toda respuesta `2xx` de pacientes, clínica, caja y presupuestos debe
quedar confirmada y visible desde una sesión de base de datos distinta a la de la request.

Replica el patrón de `tests/test_liquidaciones_api.py:741`: cada aserción abre un
**engine y sesión nuevos** con `create_engine_for(db_url)` y consulta filtrando SIEMPRE
por el `tenant_id` del token usado en la request (R4).

Por qué hace falta este guard: `conftest._app_de_prueba` cede la misma sesión compartida
a todos los requests, así que un `flush()` sin `commit()` se "ve" igual en la suite
(ceguera del bug, design D3). Con la sesión real por request, el cierre sin commit
revertía todo lo escrito.

R11: DB real (`DATABASE_URL_TEST` → PostgreSQL; SQLite file como fallback local).
Fixtures 100% sintéticas (R13), sin PHI (R9).
"""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import deps
from app.api.routers import pacientes
from app.domain.auditoria import Auditoria
from app.domain.caja import CierreCaja, EstadoCierreCaja, EstadoSena, MovimientoCaja, Sena
from app.domain.clinica import Evolucion, PiezaEvento
from app.domain.ficha_clinica import FichaClinica
from app.domain.lista_espera import CanalAviso, EstadoListaEspera, ListaEspera
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import EstadoPresupuesto, Presupuesto
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.base import Base
from app.shared.database import create_engine_for

# ---------------------------------------------------------------------------
# Helpers: verificación desde una sesión NUEVA (patrón liquidaciones:741)
# ---------------------------------------------------------------------------


async def _fila_desde_sesion_nueva(
    modelo: type[Base],
    db_url: str,
    *,
    tenant_id: uuid.UUID,
    **filtros: object,
) -> Any | None:
    """Lee desde un engine y sesión NUEVOS: solo lo que quedó commiteado (R4: por tenant)."""
    engine = create_engine_for(db_url)
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as ses:
            stmt = select(modelo).where(modelo.tenant_id == tenant_id)
            for campo, valor in filtros.items():
                stmt = stmt.where(getattr(modelo, campo) == valor)
            return (await ses.execute(stmt)).scalars().first()
    finally:
        await engine.dispose()


async def _contar_desde_sesion_nueva(
    modelo: type[Base],
    db_url: str,
    *,
    tenant_id: uuid.UUID,
    **filtros: object,
) -> int:
    """Cuenta filas confirmadas desde un engine y sesión NUEVOS (R4: por tenant)."""
    engine = create_engine_for(db_url)
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as ses:
            stmt = select(func.count()).select_from(modelo).where(modelo.tenant_id == tenant_id)
            for campo, valor in filtros.items():
                stmt = stmt.where(getattr(modelo, campo) == valor)
            return int((await ses.execute(stmt)).scalar_one())
    finally:
        await engine.dispose()


@pytest.fixture()
def assert_persistido(db_url: str) -> Callable[..., Awaitable[Any]]:
    """Aserción cross-sesión: la fila existe confirmada en una sesión NUEVA (siempre por tenant)."""

    async def _verificar(modelo: type[Base], *, tenant_id: uuid.UUID, **filtros: object) -> Any:
        fila = await _fila_desde_sesion_nueva(modelo, db_url, tenant_id=tenant_id, **filtros)
        assert fila is not None, (
            f"no se persistió: la fila de `{modelo.__tablename__}` no está confirmada en una "
            "sesión nueva (el endpoint no hizo commit de su transacción)"
        )
        return fila

    return _verificar


@pytest.fixture()
def assert_no_persistido(db_url: str) -> Callable[..., Awaitable[None]]:
    """Aserción cross-sesión negativa: la fila NO quedó confirmada (R4: por tenant)."""

    async def _verificar(modelo: type[Base], *, tenant_id: uuid.UUID, **filtros: object) -> None:
        fila = await _fila_desde_sesion_nueva(modelo, db_url, tenant_id=tenant_id, **filtros)
        assert fila is None, (
            f"no debería persistirse: una fila de `{modelo.__tablename__}` quedó confirmada "
            "en una sesión nueva pese a que la operación no debía escribirla"
        )

    return _verificar


@pytest.fixture()
def contar_filas(db_url: str) -> Callable[..., Awaitable[int]]:
    """Cuenta filas confirmadas en una sesión NUEVA (R4: por tenant)."""

    async def _contar(modelo: type[Base], *, tenant_id: uuid.UUID, **filtros: object) -> int:
        return await _contar_desde_sesion_nueva(modelo, db_url, tenant_id=tenant_id, **filtros)

    return _contar


@pytest_asyncio.fixture()
async def api_real(
    app_factory: Callable[..., FastAPI],
    db_url: str,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Cliente HTTP con sesión POR REQUEST real (una sesión nueva en cada request).

    A diferencia del fixture `api` (que comparte la sesión del test), acá cada request
    abre una sesión distinta sobre la misma `db_url`: es la lectura posterior real que
    exige el spec (tarea 6.2).
    """
    app = app_factory(pacientes.router)
    engine = create_engine_for(db_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _sesion_por_request() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as ses:
            yield ses

    app.dependency_overrides[deps.sesion_db] = _sesion_por_request
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as cliente:
        yield cliente
    await engine.dispose()


# ---------------------------------------------------------------------------
# Seeds sintéticos (R13)
# ---------------------------------------------------------------------------


async def _paciente_de_prueba(session: AsyncSession, tenant: Tenant, *, dni: str) -> Paciente:
    """Paciente + ficha clínica 1:1 sembrados con solo flush (los commitea el endpoint)."""
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente Sintético C19",
        dni=dni,
        telefono="+5491100000001",
        optin_wa=False,
        activo=True,
    )
    session.add(paciente)
    await session.flush()
    ficha = FichaClinica(id=uuid.uuid4(), tenant_id=tenant.id, paciente_id=paciente.id)
    session.add(ficha)
    await session.flush()
    return paciente


async def _consultorio_de_prueba(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    *,
    dni: str,
    con_sena: bool,
) -> tuple[Usuario, Paciente, Sillon, Prestacion]:
    """Profesional + paciente + sillón + prestación (con o sin seña) para caja/agenda."""
    odontologo = await crear_usuario(
        tenant=tenant,
        email=f"odonto-c19-{dni}@consultorio.test",
        rol=RolUsuario.ODONTOLOGO,
        nombre="Dr. Sintético C19",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente Caja C19",
        dni=dni,
        telefono="+5491100000002",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Box C19 {dni}",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Prestación C19 {dni}",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=con_sena,
        monto_sena=Decimal("10000.00") if con_sena else None,
        invasiva=False,
        activa=True,
    )
    session.add_all([paciente, sillon, prestacion])
    await session.flush()
    return odontologo, paciente, sillon, prestacion


async def _turno_por_api(
    api: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    paciente: Paciente,
    odontologo: Usuario,
    sillon: Sillon,
    prestacion: Prestacion,
) -> uuid.UUID:
    """Alta de turno por la API real (el router de agenda ya confirma su transacción)."""
    inicio = datetime.now(UTC) + timedelta(days=3)
    resp = await api.post(
        "/api/turnos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prestacion.id),
            "inicio": inicio.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


# ---------------------------------------------------------------------------
# 1.1 Guard del helper
# ---------------------------------------------------------------------------


async def test_helper_consulta_en_sesion_nueva_y_filtra_por_tenant(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    assert_persistido: Callable[..., Awaitable[Any]],
    assert_no_persistido: Callable[..., Awaitable[None]],
) -> None:
    """1.1: el helper abre engine/sesión nuevos, consulta sin errores y filtra por tenant (R4)."""
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Helper Smoke C19",
        dni="30000111",
        telefono="+5491100000003",
        optin_wa=False,
        activo=True,
    )
    session.add(paciente)
    await session.flush()
    # El smoke confirma él mismo su fila: sin commit no hay nada que el helper pueda ver.
    await session.commit()

    fila = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente.id)
    assert fila.dni == "30000111"
    # R4: la misma fila es invisible consultada con el tenant_id de otro consultorio.
    await assert_no_persistido(Paciente, tenant_id=tenant_b.id, id=paciente.id)


# ---------------------------------------------------------------------------
# 1.2 Pacientes: alta y edición
# ---------------------------------------------------------------------------


async def test_alta_de_paciente_y_ficha_visibles_desde_sesion_nueva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.2 / spec: POST 201 → paciente y ficha clínica 1:1 confirmados en una sesión nueva."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-alta-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))

    resp = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Alta Sintética C19", "dni": "30555111", "telefono": "+5491100000011"},
    )
    assert resp.status_code == 201, resp.text
    paciente_id = uuid.UUID(resp.json()["id"])

    paciente = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert paciente.activo is True
    assert paciente.dni == "30555111"
    ficha = await assert_persistido(FichaClinica, tenant_id=tenant_a.id, paciente_id=paciente_id)
    assert ficha.paciente_id == paciente_id


async def test_edicion_de_paciente_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.2 / spec: PATCH 200 → los campos actualizados se leen desde una sesión nueva."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-edit-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    alta = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Edición Sintética C19", "dni": "30555222", "telefono": "+5491100000012"},
    )
    assert alta.status_code == 201, alta.text
    paciente_id = uuid.UUID(alta.json()["id"])

    edicion = await api.patch(
        f"/api/pacientes/{paciente_id}",
        headers=headers,
        json={"telefono": "+5491100000099", "observaciones": "Editado por C19"},
    )
    assert edicion.status_code == 200, edicion.text

    paciente = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert paciente.telefono == "+5491100000099"
    assert paciente.observaciones == "Editado por C19"


# ---------------------------------------------------------------------------
# 1.3 Clínica: evolución y evento de odontograma
# ---------------------------------------------------------------------------


async def test_evolucion_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.3 / spec: POST evoluciones 201 → el registro clínico queda confirmado en sesión nueva."""
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30666111")
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-evo-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    headers = autorizacion(token_para(odontologo))

    resp = await api.post(
        f"/api/pacientes/{paciente.id}/evoluciones",
        headers=headers,
        json={"nota": "Control sintético C19"},
    )
    assert resp.status_code == 201, resp.text

    evolucion = await assert_persistido(
        Evolucion, tenant_id=tenant_a.id, id=uuid.UUID(resp.json()["id"])
    )
    assert evolucion.nota == "Control sintético C19"
    assert evolucion.paciente_id == paciente.id


async def test_evento_de_odontograma_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.3 / spec: POST eventos 201 → el evento FDI queda confirmado en una sesión nueva."""
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30666222")
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-odo-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    headers = autorizacion(token_para(odontologo))

    resp = await api.post(
        f"/api/odontograma/{paciente.id}/eventos",
        headers=headers,
        json={"pieza_fdi": 16, "superficie": "oclusal", "evento": "caries"},
    )
    assert resp.status_code == 201, resp.text

    evento = await assert_persistido(
        PiezaEvento, tenant_id=tenant_a.id, id=uuid.UUID(resp.json()["id"])
    )
    assert evento.pieza_fdi == 16
    assert evento.evento == "caries"


# ---------------------------------------------------------------------------
# 1.4 Caja: seña manual y movimiento
# ---------------------------------------------------------------------------


async def test_creacion_de_sena_manual_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.4 / spec: POST /api/senas 201 → la seña queda confirmada en una sesión nueva."""
    odontologo, paciente, sillon, prestacion = await _consultorio_de_prueba(
        session, tenant_a, crear_usuario, dni="30777111", con_sena=True
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recep-sena-c19@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))
    inicio = datetime.now(UTC) + timedelta(days=4)
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=60),
    )
    session.add(turno)
    await session.flush()

    resp = await api.post("/api/senas", headers=headers, json={"turno_id": str(turno.id)})
    assert resp.status_code == 201, resp.text

    sena = await assert_persistido(Sena, tenant_id=tenant_a.id, turno_id=turno.id)
    assert sena.estado == EstadoSena.PENDIENTE.value
    assert sena.monto == Decimal("10000.00")


async def test_movimiento_de_caja_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.4 / spec: POST /api/caja/movimientos 201 → el movimiento se lee desde sesión nueva."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recep-mov-c19@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    cierre = await api.post("/api/caja/cierre", headers=headers, json={"fecha": "2026-12-10"})
    assert cierre.status_code == 201, cierre.text
    cierre_id = uuid.UUID(cierre.json()["id"])

    resp = await api.post(
        "/api/caja/movimientos",
        headers=headers,
        json={
            "tipo": "ingreso",
            "concepto": "Cobro sintético C19",
            "medio": "efectivo",
            "monto": "15000.00",
        },
    )
    assert resp.status_code == 201, resp.text

    movimiento = await assert_persistido(
        MovimientoCaja, tenant_id=tenant_a.id, concepto="Cobro sintético C19"
    )
    assert movimiento.cierre_id == cierre_id
    assert movimiento.monto == Decimal("15000.00")


# ---------------------------------------------------------------------------
# 1.5 Presupuestos: alta y transición
# ---------------------------------------------------------------------------


async def test_presupuesto_creado_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.5 / spec: POST /api/presupuestos 201 → el presupuesto queda confirmado en sesión nueva."""
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-pres-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30888111")
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Resina Sintética C19",
        duracion_min=45,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add(prestacion)
    await session.flush()
    headers = autorizacion(token_para(odontologo))

    resp = await api.post(
        "/api/presupuestos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "items": [{"prestacion_id": str(prestacion.id), "pieza_fdi": 14, "cantidad": 1}],
        },
    )
    assert resp.status_code == 201, resp.text

    presupuesto = await assert_persistido(
        Presupuesto, tenant_id=tenant_a.id, id=uuid.UUID(resp.json()["id"])
    )
    assert presupuesto.estado == EstadoPresupuesto.BORRADOR.value


async def test_presupuesto_presentado_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.5 / spec: POST presentar 200 → el estado nuevo se lee desde una sesión nueva."""
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-pres2-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30888222")
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Corona Sintética C19",
        duracion_min=60,
        precio_particular=Decimal("80000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add(prestacion)
    await session.flush()
    headers = autorizacion(token_para(odontologo))

    alta = await api.post(
        "/api/presupuestos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "items": [{"prestacion_id": str(prestacion.id), "pieza_fdi": 46, "cantidad": 1}],
        },
    )
    assert alta.status_code == 201, alta.text
    presupuesto_id = uuid.UUID(alta.json()["id"])

    presentar = await api.post(f"/api/presupuestos/{presupuesto_id}/presentar", headers=headers)
    assert presentar.status_code == 200, presentar.text

    presupuesto = await assert_persistido(Presupuesto, tenant_id=tenant_a.id, id=presupuesto_id)
    assert presupuesto.estado == EstadoPresupuesto.PRESENTADO.value


# ---------------------------------------------------------------------------
# 1.6 Baja lógica y opt-in de pacientes
# ---------------------------------------------------------------------------


async def test_baja_logica_de_paciente_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.6 / spec: DELETE 200 → la fila existe con `activo=false` (R7, sin hard delete)."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-baja-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    alta = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Baja Lógica C19", "dni": "30555333", "telefono": "+5491100000013"},
    )
    assert alta.status_code == 201, alta.text
    paciente_id = uuid.UUID(alta.json()["id"])

    baja = await api.delete(f"/api/pacientes/{paciente_id}", headers=headers)
    assert baja.status_code == 200, baja.text
    assert baja.json()["activo"] is False

    paciente = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert paciente.activo is False


async def test_optin_wa_ultimo_valor_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.6 / spec (RN-CO-01): opt-in true y luego false → el último valor queda confirmado."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-optin-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    alta = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Optin Sintético C19", "dni": "30555444", "telefono": "+5491100000014"},
    )
    assert alta.status_code == 201, alta.text
    paciente_id = uuid.UUID(alta.json()["id"])

    alza = await api.patch(
        f"/api/pacientes/{paciente_id}/optin", headers=headers, json={"optin_wa": True}
    )
    assert alza.status_code == 200, alza.text
    persistido = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert persistido.optin_wa is True

    stop = await api.patch(
        f"/api/pacientes/{paciente_id}/optin", headers=headers, json={"optin_wa": False}
    )
    assert stop.status_code == 200, stop.text
    persistido = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert persistido.optin_wa is False


# ---------------------------------------------------------------------------
# 1.7 Cadena de vencimiento de seña y cobro de seña
# ---------------------------------------------------------------------------


async def test_cadena_de_vencimiento_de_sena_visible_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.7 / spec: vencer 2xx → seña `vencida` + turno `cancelado` (RN-AG-07) + lista de
    espera `avisada` (RN-LE-01) + auditoría (RN-PA-01) visibles JUNTOS desde sesión nueva."""
    odontologo, paciente, sillon, prestacion = await _consultorio_de_prueba(
        session, tenant_a, crear_usuario, dni="30777222", con_sena=True
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recep-vencer-c19@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))
    turno_id = await _turno_por_api(
        api, headers, paciente=paciente, odontologo=odontologo, sillon=sillon, prestacion=prestacion
    )
    senas = await api.get(f"/api/senas?turno_id={turno_id}", headers=headers)
    assert senas.status_code == 200, senas.text
    sena_id = uuid.UUID(senas.json()[0]["id"])

    # Vencimiento forzado + candidata a la lista de espera (solo flush: el commit es del endpoint).
    sena = await session.get(Sena, sena_id)
    assert sena is not None
    sena.vence_at = datetime.now(UTC) - timedelta(hours=1)
    espera = ListaEspera(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        prestacion_id=prestacion.id,
        profesional_id=odontologo.id,
        prioridad=1,
        estado=EstadoListaEspera.ACTIVA.value,
        canal_aviso=CanalAviso.WA.value,
    )
    session.add(espera)
    await session.flush()

    vencer = await api.post(f"/api/senas/{sena_id}/vencer", headers=headers)
    assert vencer.status_code == 200, vencer.text

    sena_persistida = await assert_persistido(Sena, tenant_id=tenant_a.id, id=sena_id)
    assert sena_persistida.estado == EstadoSena.VENCIDA.value
    turno_persistido = await assert_persistido(Turno, tenant_id=tenant_a.id, id=turno_id)
    assert turno_persistido.estado == EstadoTurno.CANCELADO.value
    espera_persistida = await assert_persistido(ListaEspera, tenant_id=tenant_a.id, id=espera.id)
    assert espera_persistida.estado == EstadoListaEspera.AVISADA.value
    evento = await assert_persistido(
        Auditoria, tenant_id=tenant_a.id, accion="sena.vencer", entidad_id=str(sena_id)
    )
    assert evento.entidad == "sena"


async def test_cobro_de_sena_y_movimiento_visibles_desde_sesion_nueva(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """1.7 / spec: cobro de seña 200 → seña `cobrada` + movimiento de ingreso en sesión nueva."""
    odontologo, paciente, sillon, prestacion = await _consultorio_de_prueba(
        session, tenant_a, crear_usuario, dni="30777333", con_sena=True
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recep-cobrar-c19@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))
    turno_id = await _turno_por_api(
        api, headers, paciente=paciente, odontologo=odontologo, sillon=sillon, prestacion=prestacion
    )
    senas = await api.get(f"/api/senas?turno_id={turno_id}", headers=headers)
    assert senas.status_code == 200, senas.text
    sena_id = uuid.UUID(senas.json()[0]["id"])

    cobro = await api.post(
        f"/api/senas/{sena_id}/cobrar", headers=headers, json={"medio": "efectivo"}
    )
    assert cobro.status_code == 200, cobro.text

    sena = await assert_persistido(Sena, tenant_id=tenant_a.id, id=sena_id)
    assert sena.estado == EstadoSena.COBRADA.value
    movimiento = await assert_persistido(MovimientoCaja, tenant_id=tenant_a.id, sena_id=sena_id)
    assert movimiento.tipo == "ingreso"
    assert movimiento.monto == Decimal("10000.00")


# ---------------------------------------------------------------------------
# 1.8 / 6.3 Aislamiento multi-tenant del helper (R4)
# ---------------------------------------------------------------------------


async def test_escritura_de_un_tenant_visible_para_su_tenant_e_invisible_para_otro(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
    assert_no_persistido: Callable[..., Awaitable[None]],
) -> None:
    """1.8/6.3 / spec: lo creado con el token de A se ve con el tenant_id de A y NO con el de B."""
    dueno_a = await crear_usuario(
        tenant=tenant_a, email="dueno-iso-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno_a))

    resp = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Aislado Tenant A C19", "dni": "30555555", "telefono": "+5491100000015"},
    )
    assert resp.status_code == 201, resp.text
    paciente_id = uuid.UUID(resp.json()["id"])

    # Caso positivo: visible para el propio tenant del token.
    visible = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    assert visible.tenant_id == tenant_a.id
    # Caso negativo: invisible con el tenant_id de otro consultorio.
    await assert_no_persistido(Paciente, tenant_id=tenant_b.id, id=paciente_id)


# ---------------------------------------------------------------------------
# 2.2 / 3.2 / 4.2 / 5.2 Triangulación: operación fallida no deja escrituras
# ---------------------------------------------------------------------------


async def test_alta_con_dni_duplicado_no_deja_paciente_nuevo(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """2.2: el 409 por DNI duplicado no deja un segundo paciente visible desde sesión nueva."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-dup-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    payload = {"nombre": "Duplicado Sintético C19", "dni": "30555666", "telefono": "+5491100000016"}

    ok = await api.post("/api/pacientes", headers=headers, json=payload)
    assert ok.status_code == 201, ok.text
    conflicto = await api.post("/api/pacientes", headers=headers, json=payload)
    assert conflicto.status_code == 409, conflicto.text

    assert await contar_filas(Paciente, tenant_id=tenant_a.id, dni="30555666") == 1


async def test_evolucion_rechazada_no_deja_registro_ni_auditoria(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """3.2: el 404 por paciente inexistente no deja evolución ni auditoría en sesión nueva."""
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30666333")
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-rech-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    headers = autorizacion(token_para(odontologo))

    ok = await api.post(
        f"/api/pacientes/{paciente.id}/evoluciones",
        headers=headers,
        json={"nota": "Evolución válida C19"},
    )
    assert ok.status_code == 201, ok.text
    paciente_falso = uuid.uuid4()
    rechazada = await api.post(
        f"/api/pacientes/{paciente_falso}/evoluciones",
        headers=headers,
        json={"nota": "Evolución huérfana C19"},
    )
    assert rechazada.status_code == 404, rechazada.text

    assert await contar_filas(Evolucion, tenant_id=tenant_a.id, paciente_id=paciente_falso) == 0
    assert await contar_filas(Auditoria, tenant_id=tenant_a.id, accion="evolucion.crear") == 1


async def test_cierre_ya_cerrado_no_deja_cambios_ni_auditoria_extra(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """4.2: cerrar dos veces responde 409 sin dejar cambios ni auditoría extra en sesión nueva."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recep-cierre-c19@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    abrir = await api.post("/api/caja/cierre", headers=headers, json={"fecha": "2026-12-11"})
    assert abrir.status_code == 201, abrir.text
    cierre_id = uuid.UUID(abrir.json()["id"])
    cerrar = await api.post(
        f"/api/caja/cierre/{cierre_id}/cerrar",
        headers=headers,
        json={"total_contado": "10000.00"},
    )
    assert cerrar.status_code == 200, cerrar.text
    recerrar = await api.post(
        f"/api/caja/cierre/{cierre_id}/cerrar",
        headers=headers,
        json={"total_contado": "99999.00"},
    )
    assert recerrar.status_code == 409, recerrar.text

    cierre = await assert_persistido(CierreCaja, tenant_id=tenant_a.id, id=cierre_id)
    assert cierre.estado == EstadoCierreCaja.CERRADO.value
    assert cierre.total_contado == Decimal("10000.00")
    assert await contar_filas(Auditoria, tenant_id=tenant_a.id, accion="caja.cerrar") == 1


async def test_aceptar_invasiva_sin_consentimiento_no_deja_cambio_de_estado(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """5.2: el 409 de RN-CL-04 no deja el estado `aceptado` ni auditoría extra en sesión nueva."""
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-rncl04-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    paciente = await _paciente_de_prueba(session, tenant_a, dni="30888333")
    prestacion_inv = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Exodoncia Sintética C19",
        duracion_min=45,
        precio_particular=Decimal("90000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    session.add(prestacion_inv)
    await session.flush()
    headers = autorizacion(token_para(odontologo))

    alta = await api.post(
        "/api/presupuestos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "items": [{"prestacion_id": str(prestacion_inv.id), "pieza_fdi": 48, "cantidad": 1}],
        },
    )
    assert alta.status_code == 201, alta.text
    presupuesto_id = uuid.UUID(alta.json()["id"])
    presentar = await api.post(f"/api/presupuestos/{presupuesto_id}/presentar", headers=headers)
    assert presentar.status_code == 200, presentar.text

    aceptar = await api.post(f"/api/presupuestos/{presupuesto_id}/aceptar", headers=headers)
    assert aceptar.status_code == 409, aceptar.text

    presupuesto = await assert_persistido(Presupuesto, tenant_id=tenant_a.id, id=presupuesto_id)
    assert presupuesto.estado == EstadoPresupuesto.PRESENTADO.value
    assert (
        await contar_filas(Auditoria, tenant_id=tenant_a.id, accion="presupuesto.cambiar_estado")
        == 1
    )


# ---------------------------------------------------------------------------
# 6.1 Auditoría en la misma transacción
# ---------------------------------------------------------------------------


async def test_auditoria_de_alta_confirmada_junto_con_el_hecho(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    assert_persistido: Callable[..., Awaitable[Any]],
) -> None:
    """6.1 / spec: alta 201 → paciente y su entrada en `auditoria` se ven juntos en sesión nueva."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-audit-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))

    resp = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Auditado Sintético C19", "dni": "30555777", "telefono": "+5491100000017"},
    )
    assert resp.status_code == 201, resp.text
    paciente_id = uuid.UUID(resp.json()["id"])

    paciente = await assert_persistido(Paciente, tenant_id=tenant_a.id, id=paciente_id)
    evento = await assert_persistido(
        Auditoria, tenant_id=tenant_a.id, accion="paciente.crear", entidad_id=str(paciente_id)
    )
    assert paciente.activo is True
    assert evento.entidad == "paciente"
    assert evento.actor_id == dueno.id


async def test_operacion_fallida_no_deja_auditoria_huerfana(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """6.1 / spec: la alta fallida (409) no deja una entrada de auditoría sin su hecho."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-huerfana-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))
    payload = {
        "nombre": "Sin Auditoría Huérfana C19",
        "dni": "30555888",
        "telefono": "+5491100000018",
    }

    ok = await api.post("/api/pacientes", headers=headers, json=payload)
    assert ok.status_code == 201, ok.text
    conflicto = await api.post("/api/pacientes", headers=headers, json=payload)
    assert conflicto.status_code == 409, conflicto.text

    # Solo la alta exitosa audita: la fallida no deja evento huérfano (RN-PA-01).
    assert await contar_filas(Auditoria, tenant_id=tenant_a.id, accion="paciente.crear") == 1


# ---------------------------------------------------------------------------
# 6.2 Coherencia de lectura posterior (request nueva con sesión nueva)
# ---------------------------------------------------------------------------


async def test_lectura_posterior_en_request_nueva_devuelve_lo_escrito(
    api: httpx.AsyncClient,
    api_real: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """6.2 / spec: GET en una request nueva (con sesión nueva) devuelve lo escrito por el 2xx."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-get-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    # Baseline commiteado (como tras un login real): tenant y usuario visibles en toda sesión.
    await session.commit()
    headers = autorizacion(token_para(dueno))

    alta = await api.post(
        "/api/pacientes",
        headers=headers,
        json={"nombre": "Lectura Posterior C19", "dni": "30555999", "telefono": "+5491100000019"},
    )
    assert alta.status_code == 201, alta.text
    paciente_id = uuid.UUID(alta.json()["id"])

    lectura = await api_real.get(f"/api/pacientes/{paciente_id}", headers=headers)
    assert lectura.status_code == 200, lectura.text
    assert lectura.json()["dni"] == "30555999"


async def test_alta_fallida_no_deja_recurso_para_get_posterior(
    api: httpx.AsyncClient,
    api_real: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    contar_filas: Callable[..., Awaitable[int]],
) -> None:
    """6.2 / spec: tras un alta fallida el GET no muestra rastro del intento fallido."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-404-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    await session.commit()
    headers = autorizacion(token_para(dueno))
    payload = {"nombre": "Alta Fallida C19", "dni": "30556001", "telefono": "+5491100000020"}

    ok = await api.post("/api/pacientes", headers=headers, json=payload)
    assert ok.status_code == 201, ok.text
    conflicto = await api.post("/api/pacientes", headers=headers, json=payload)
    assert conflicto.status_code == 409, conflicto.text

    listado = await api_real.get("/api/pacientes?dni=30556001", headers=headers)
    assert listado.status_code == 200, listado.text
    assert len(listado.json()) == 1  # solo la alta exitosa; sin rastro del intento fallido
    inexistente = await api_real.get(f"/api/pacientes/{uuid.uuid4()}", headers=headers)
    assert inexistente.status_code == 404
    assert await contar_filas(Paciente, tenant_id=tenant_a.id, dni="30556001") == 1


async def test_edicion_fallida_conserva_el_estado_anterior_en_get_posterior(
    api: httpx.AsyncClient,
    api_real: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """6.2 / spec: tras una edición fallida (403 por rol) el GET devuelve el estado anterior."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-prev-c19@consultorio.test", rol=RolUsuario.DUENO
    )
    odontologo = await crear_usuario(
        tenant=tenant_a, email="odonto-prev-c19@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    await session.commit()
    headers_dueno = autorizacion(token_para(dueno))
    headers_odonto = autorizacion(token_para(odontologo))

    telefono_original = "+5491100000021"
    alta = await api.post(
        "/api/pacientes",
        headers=headers_dueno,
        json={"nombre": "Estado Anterior C19", "dni": "30556002", "telefono": telefono_original},
    )
    assert alta.status_code == 201, alta.text
    paciente_id = uuid.UUID(alta.json()["id"])

    edicion_fallida = await api.patch(
        f"/api/pacientes/{paciente_id}",
        headers=headers_odonto,
        json={"telefono": "+5491100000022"},
    )
    assert edicion_fallida.status_code == 403, edicion_fallida.text

    lectura = await api_real.get(f"/api/pacientes/{paciente_id}", headers=headers_dueno)
    assert lectura.status_code == 200, lectura.text
    assert lectura.json()["telefono"] == telefono_original
