"""API de lookup de cobertura `GET /api/os/cobertura` (C-13, tarea 1.3, US-040).

Verifica:
1. Cobertura vigente: montos calculados en servidor y `estado_arancel = vigente` (RN-OS-01).
2. Modo particular cuando la obra social no tiene convenio (R8).
3. Arancel vencido: `arancel_vencido = true` y advertencia para recepción (D2, Flujo 5).
4. `turno_id` deriva la prestación y la fecha de referencia desde el turno.
5. `404` para prestación de otro tenant y `422` si `turno_id` y `prestacion_id` se contradicen.
6. RBAC: sin token `401`; Odontólogo (sólo lectura) recibe la cobertura.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario

URL = "/api/os/cobertura"


async def _consultorio(
    session: AsyncSession, tenant: Tenant
) -> tuple[Usuario, Paciente, Sillon, Prestacion]:
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="odonto-cobertura-api@consultorio.test",
        nombre="Dra. Cobertura",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-30301",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Ana Cobertura",
        dni="30999888",
        telefono="+5491144445555",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box Cobertura", activo=True)
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Limpieza dental",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()
    return odontologo, paciente, sillon, prestacion


async def _convenio(
    session: AsyncSession,
    tenant: Tenant,
    prestacion: Prestacion,
    *,
    obra_social: str = "OSDE",
    arancel: str = "30000.00",
    vigencia_desde: date = date(2026, 1, 1),
    vigencia_hasta: date | None = None,
) -> CoberturaOS:
    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        obra_social=obra_social,
        prestacion_id=prestacion.id,
        arancel=Decimal(arancel),
        copago=Decimal("0.00"),
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        activa=True,
    )
    session.add(cobertura)
    await session.flush()
    return cobertura


async def _turno(
    session: AsyncSession,
    tenant: Tenant,
    *,
    odontologo: Usuario,
    paciente: Paciente,
    sillon: Sillon,
    prestacion: Prestacion,
    inicio: datetime,
) -> Turno:
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=inicio,
        fin=inicio + timedelta(hours=1),
        estado=EstadoTurno.CONFIRMADO.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno


async def test_lookup_vigente_devuelve_montos_calculados_en_servidor(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-OS-01 / R8: 50000 de precio con arancel vigente de 30000 deja 20000 a cargo."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-cobertura@consultorio.test", rol=RolUsuario.RECEPCION
    )
    _, _, _, prestacion = await _consultorio(session, tenant_a)
    await _convenio(session, tenant_a, prestacion)

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(recepcion)),
        params={
            "prestacion_id": str(prestacion.id),
            "obra_social": "osde",
            "fecha": "2026-11-15",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["prestacion_id"] == str(prestacion.id)
    assert cuerpo["obra_social"] == "osde"
    assert Decimal(cuerpo["precio_particular"]) == Decimal("50000.00")
    assert Decimal(cuerpo["cobertura"]) == Decimal("30000.00")
    assert Decimal(cuerpo["monto_a_cargo"]) == Decimal("20000.00")
    assert cuerpo["estado_arancel"] == "vigente"
    assert cuerpo["arancel_vencido"] is False
    assert cuerpo["advertencia"] is None
    assert cuerpo["vigencia_desde"] == "2026-01-01"
    assert cuerpo["vigencia_hasta"] is None
    assert cuerpo["cobertura_id"] is not None


async def test_lookup_sin_convenio_responde_modo_particular(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-OS-01: sin convenio la respuesta es particular con `cobertura = 0`."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-cobertura@consultorio.test", rol=RolUsuario.DUENO
    )
    _, _, _, prestacion = await _consultorio(session, tenant_a)

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(dueno)),
        params={"prestacion_id": str(prestacion.id), "obra_social": "SWISS MEDICAL"},
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_arancel"] == "sin_cobertura"
    assert Decimal(cuerpo["cobertura"]) == Decimal("0.00")
    assert Decimal(cuerpo["monto_a_cargo"]) == Decimal("50000.00")
    assert cuerpo["cobertura_id"] is None
    assert cuerpo["arancel_vencido"] is False


async def test_lookup_con_arancel_vencido_marca_alerta_y_advertencia(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """D2 / Flujo 5: el convenio vencido se usa igual y la respuesta trae la advertencia."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-vencido@consultorio.test", rol=RolUsuario.RECEPCION
    )
    _, _, _, prestacion = await _consultorio(session, tenant_a)
    await _convenio(
        session,
        tenant_a,
        prestacion,
        vigencia_desde=date(2025, 1, 1),
        vigencia_hasta=date(2026, 10, 31),
    )

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(recepcion)),
        params={
            "prestacion_id": str(prestacion.id),
            "obra_social": "OSDE",
            "fecha": "2026-11-15",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_arancel"] == "vencido"
    assert cuerpo["arancel_vencido"] is True
    assert Decimal(cuerpo["cobertura"]) == Decimal("30000.00")
    assert cuerpo["vigencia_hasta"] == "2026-10-31"
    assert "31/10/2026" in cuerpo["advertencia"]


async def test_lookup_por_turno_deriva_la_prestacion_y_la_fecha(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """El turno aporta prestación y fecha: el arancel vence en octubre, el turno es de noviembre."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-turno@consultorio.test", rol=RolUsuario.RECEPCION
    )
    odontologo, paciente, sillon, prestacion = await _consultorio(session, tenant_a)
    await _convenio(
        session,
        tenant_a,
        prestacion,
        vigencia_hasta=date(2026, 10, 31),
        vigencia_desde=date(2026, 1, 1),
    )
    turno = await _turno(
        session,
        tenant_a,
        odontologo=odontologo,
        paciente=paciente,
        sillon=sillon,
        prestacion=prestacion,
        inicio=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(recepcion)),
        params={"turno_id": str(turno.id), "obra_social": "OSDE", "cantidad": 2},
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["prestacion_id"] == str(prestacion.id)
    assert cuerpo["estado_arancel"] == "vencido"
    assert Decimal(cuerpo["cobertura"]) == Decimal("60000.00")
    assert Decimal(cuerpo["monto_a_cargo"]) == Decimal("40000.00")


async def test_lookup_de_prestacion_de_otro_tenant_responde_404(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: la prestación de otro consultorio no se filtra ni se resuelve."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-aislado@consultorio.test", rol=RolUsuario.DUENO
    )
    _, _, _, prestacion_ajena = await _consultorio(session, tenant_b)

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(dueno)),
        params={"prestacion_id": str(prestacion_ajena.id), "obra_social": "OSDE"},
    )

    assert respuesta.status_code == 404, respuesta.text
    assert str(prestacion_ajena.id) not in respuesta.text


async def test_lookup_con_turno_y_prestacion_contradictorios_responde_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Contrato 1.3: el turno y la prestación tienen que coincidir."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-cruce@consultorio.test", rol=RolUsuario.RECEPCION
    )
    odontologo, paciente, sillon, prestacion = await _consultorio(session, tenant_a)
    otra = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Otra prestación",
        duracion_min=30,
        precio_particular=Decimal("10000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add(otra)
    await session.flush()
    turno = await _turno(
        session,
        tenant_a,
        odontologo=odontologo,
        paciente=paciente,
        sillon=sillon,
        prestacion=prestacion,
        inicio=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
    )

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(recepcion)),
        params={"turno_id": str(turno.id), "prestacion_id": str(otra.id)},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_lookup_sin_token_responde_401(
    api: httpx.AsyncClient, session: AsyncSession, tenant_a: Tenant
) -> None:
    """R4: sin token no hay consulta de cobertura (401, sin default de tenant)."""
    _, _, _, prestacion = await _consultorio(session, tenant_a)

    respuesta = await api.get(URL, params={"prestacion_id": str(prestacion.id)})

    assert respuesta.status_code == 401, respuesta.text


async def test_lookup_sin_identificador_responde_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Contrato 1.3: hace falta `prestacion_id` o `turno_id`, no ninguno de los dos."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-sin-id@consultorio.test", rol=RolUsuario.RECEPCION
    )

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(recepcion)),
        params={"obra_social": "OSDE"},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_odontologo_puede_consultar_la_cobertura_de_una_prestacion(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RBAC: el Odontólogo tiene sólo lectura sobre liquidaciones y puede consultar cobertura."""
    odontologo_usuario = await crear_usuario(
        tenant=tenant_a, email="odonto-rbac-cobertura@consultorio.test", rol=RolUsuario.ODONTOLOGO
    )
    _, _, _, prestacion = await _consultorio(session, tenant_a)
    await _convenio(session, tenant_a, prestacion)

    respuesta = await api.get(
        URL,
        headers=autorizacion(token_para(odontologo_usuario)),
        params={"prestacion_id": str(prestacion.id), "obra_social": "OSDE"},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert Decimal(respuesta.json()["cobertura"]) == Decimal("30000.00")
