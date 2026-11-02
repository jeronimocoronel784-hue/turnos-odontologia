"""Tests de API / E2E de Señas y Caja diaria (tarea 3.1).

Verifica:
1. Recepción opera la caja (apertura, movimientos, cierre) y obtiene `diferencia` visible.
2. Recepción recibe `403` al intentar reabrir un cierre; el Dueño reabre con `200` + auditoría.
3. Flujo completo por API: turno con `requiere_sena` -> seña `pendiente` -> cobro -> liquidación
   del saldo -> cobro del saldo (Flujo 4, R8).
4. RBAC de lectura para el odontólogo y rechazo `403` al operar caja.
5. R4: un `tenant_id` en el body se rechaza con `422` (nunca pisa el del token).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.caja import EstadoCierreCaja, EstadoSena, MedioPago, MovimientoCaja, Sena
from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import Turno
from app.domain.usuario import RolUsuario, Usuario

CERO = Decimal("0.00")


def _dec(valor: object) -> Decimal:
    """Normaliza montos de la respuesta JSON a `Decimal` con 2 decimales."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


async def _preparar_consultorio(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> tuple[Usuario, Paciente, Sillon, Prestacion]:
    """Profesional + paciente + sillón + prestación de 50000 con seña de 10000 y OSDE 20000."""
    odontologo = await crear_usuario(
        tenant=tenant,
        rol=RolUsuario.ODONTOLOGO,
        email="odonto-api-caja@consultorio.test",
        nombre="Dr. Caja API",
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Lucía Caja API",
        dni="41222333",
        telefono="+5491177778888",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Box Caja API",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Corona con seña",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=Decimal("10000.00"),
        invasiva=False,
        activa=True,
    )
    cobertura = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        obra_social="OSDE",
        prestacion_id=prestacion.id,
        arancel=Decimal("20000.00"),
        copago=Decimal("30000.00"),
        vigencia_desde=date(2020, 1, 1),
        vigencia_hasta=None,
        activa=True,
    )
    session.add_all([paciente, sillon, prestacion, cobertura])
    await session.flush()
    return odontologo, paciente, sillon, prestacion


async def test_recepcion_opera_caja_cierra_con_diferencia_y_no_puede_reabrir(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    """RN-PA-05 / US-030: recepción abre, registra movimientos y cierra; 403 al reabrir."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-caja@consultorio.test", rol=RolUsuario.RECEPCION
    )
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-caja@consultorio.test", rol=RolUsuario.DUENO
    )
    headers_recepcion = autorizacion(token_para(recepcion))
    headers_dueno = autorizacion(token_para(dueno))

    # 1. Abrir el cierre del día
    r_abrir = await api.post(
        "/api/caja/cierre",
        headers=headers_recepcion,
        json={"fecha": "2026-12-15"},
    )
    assert r_abrir.status_code == 201, r_abrir.text
    cierre_id = r_abrir.json()["id"]
    assert r_abrir.json()["estado"] == EstadoCierreCaja.ABIERTO.value

    # 2. Registrar ingresos y egresos (se asocian al cierre abierto)
    r_ingreso = await api.post(
        "/api/caja/movimientos",
        headers=headers_recepcion,
        json={
            "tipo": "ingreso",
            "concepto": "Cobro de atención",
            "medio": "efectivo",
            "monto": "30000.00",
        },
    )
    assert r_ingreso.status_code == 201, r_ingreso.text
    assert r_ingreso.json()["cierre_id"] == cierre_id

    r_egreso = await api.post(
        "/api/caja/movimientos",
        headers=headers_recepcion,
        json={
            "tipo": "egreso",
            "concepto": "Insumos",
            "medio": "efectivo",
            "monto": "5000.00",
        },
    )
    assert r_egreso.status_code == 201, r_egreso.text

    r_lista = await api.get(
        f"/api/caja/movimientos?cierre_id={cierre_id}", headers=headers_recepcion
    )
    assert r_lista.status_code == 200
    assert len(r_lista.json()) == 2

    # 3. Cerrar declarando 24500 contados -> total sistema 25000, diferencia -500
    r_cerrar = await api.post(
        f"/api/caja/cierre/{cierre_id}/cerrar",
        headers=headers_recepcion,
        json={"total_contado": "24500.00"},
    )
    assert r_cerrar.status_code == 200, r_cerrar.text
    cerrado = r_cerrar.json()
    assert cerrado["estado"] == EstadoCierreCaja.CERRADO.value
    assert _dec(cerrado["total_sistema"]) == Decimal("25000.00")
    assert _dec(cerrado["total_contado"]) == Decimal("24500.00")
    assert _dec(cerrado["diferencia"]) == Decimal("-500.00")

    # 4. El cierre cerrado es inmutable: un segundo cierre choca con 409
    r_recerrar = await api.post(
        f"/api/caja/cierre/{cierre_id}/cerrar",
        headers=headers_recepcion,
        json={"total_contado": "24500.00"},
    )
    assert r_recerrar.status_code == 409, r_recerrar.text

    # 5. Recepción NO puede reabrir (Accion.REABRIR_CIERRE es exclusiva del Dueño)
    r_403 = await api.post(
        f"/api/caja/cierre/{cierre_id}/reabrir",
        headers=headers_recepcion,
        json={"motivo": "Faltó un movimiento"},
    )
    assert r_403.status_code == 403, r_403.text
    assert "permiso" in r_403.json()["detail"].lower()

    # 6. El Dueño reabre con 200 y deja el evento en Auditoria
    r_reabrir = await api.post(
        f"/api/caja/cierre/{cierre_id}/reabrir",
        headers=headers_dueno,
        json={"motivo": "Faltó un movimiento de insumos"},
    )
    assert r_reabrir.status_code == 200, r_reabrir.text
    reabierto = r_reabrir.json()
    assert reabierto["estado"] == EstadoCierreCaja.ABIERTO.value
    assert reabierto["reabierto_motivo"] == "Faltó un movimiento de insumos"

    eventos = await auditoria_de("caja.reabrir_cierre")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == cierre_id
    assert eventos[0].actor_id == dueno.id
    assert eventos[0].antes is not None
    assert eventos[0].antes["estado"] == EstadoCierreCaja.CERRADO.value
    assert eventos[0].despues is not None
    assert eventos[0].despues["estado"] == EstadoCierreCaja.ABIERTO.value


async def test_flujo_completo_sena_cobro_y_cobro_de_saldo_por_api(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Flujo 1+4 / R8: turno con seña -> cobro -> liquidación 20000 -> cobro del saldo."""
    odontologo, paciente, sillon, prestacion = await _preparar_consultorio(
        session, tenant_a, crear_usuario
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-flujo@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    inicio = datetime.now(UTC) + timedelta(days=7)
    r_turno = await api.post(
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
    assert r_turno.status_code == 201, r_turno.text
    turno_id = r_turno.json()["id"]

    # 1. RN-PA-02: el alta del turno generó la seña pendiente por el monto de la prestación
    r_senas = await api.get(f"/api/senas?turno_id={turno_id}", headers=headers)
    assert r_senas.status_code == 200, r_senas.text
    senas = r_senas.json()
    assert len(senas) == 1
    sena = senas[0]
    assert sena["estado"] == EstadoSena.PENDIENTE.value
    assert _dec(sena["monto"]) == Decimal("10000.00")

    # 2. RN-PA-01: el turno no confirma hasta cobrar la seña
    r_conflicto = await api.patch(
        f"/api/turnos/{turno_id}/estado", headers=headers, json={"estado": "confirmado"}
    )
    assert r_conflicto.status_code == 409, r_conflicto.text

    # 3. Cobro de la seña
    r_cobrar = await api.post(
        f"/api/senas/{sena['id']}/cobrar", headers=headers, json={"medio": "efectivo"}
    )
    assert r_cobrar.status_code == 200, r_cobrar.text
    assert r_cobrar.json()["estado"] == EstadoSena.COBRADA.value

    r_confirmar = await api.patch(
        f"/api/turnos/{turno_id}/estado", headers=headers, json={"estado": "confirmado"}
    )
    assert r_confirmar.status_code == 200, r_confirmar.text
    assert r_confirmar.json()["sena_cobrada"] is True

    # 4. Liquidación: 50000 - 20000 (OSDE) - 10000 (seña) = 20000
    r_liq = await api.get(
        f"/api/caja/turnos/{turno_id}/liquidacion?obra_social=OSDE", headers=headers
    )
    assert r_liq.status_code == 200, r_liq.text
    liquidacion = r_liq.json()
    assert _dec(liquidacion["precio_particular"]) == Decimal("50000.00")
    assert _dec(liquidacion["cobertura_os"]) == Decimal("20000.00")
    assert _dec(liquidacion["sena_cobrada"]) == Decimal("10000.00")
    assert _dec(liquidacion["saldo"]) == Decimal("20000.00")

    # 5. Cobro del saldo: movimiento de ingreso por 20000 y seña aplicada
    r_cobro_saldo = await api.post(
        f"/api/caja/turnos/{turno_id}/cobrar",
        headers=headers,
        json={"medio": "transferencia", "obra_social": "OSDE"},
    )
    assert r_cobro_saldo.status_code == 201, r_cobro_saldo.text
    movimiento = r_cobro_saldo.json()
    assert movimiento["tipo"] == "ingreso"
    assert movimiento["medio"] == MedioPago.TRANSFERENCIA.value
    assert _dec(movimiento["monto"]) == Decimal("20000.00")
    assert movimiento["turno_id"] == turno_id

    sena_bd = await session.get(Sena, uuid.UUID(sena["id"]))
    assert sena_bd is not None
    assert sena_bd.estado == EstadoSena.APLICADA.value

    # 6. R8: un segundo cobro del saldo choca con 409 (no duplica la plata)
    r_dup = await api.post(
        f"/api/caja/turnos/{turno_id}/cobrar",
        headers=headers,
        json={"medio": "transferencia", "obra_social": "OSDE"},
    )
    assert r_dup.status_code == 409, r_dup.text

    movimientos = [m for m in (await _movimientos(session)) if m.turno_id is not None]
    assert len(movimientos) == 2  # seña + saldo
    assert {_dec(m.monto) for m in movimientos} == {
        Decimal("10000.00"),
        Decimal("20000.00"),
    }


async def _movimientos(session: AsyncSession) -> list[MovimientoCaja]:
    from sqlalchemy import select

    return list((await session.execute(select(MovimientoCaja))).scalars().all())


async def test_odontologo_lee_caja_pero_no_puede_operarla(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RBAC §03: odontólogo tiene solo lectura de caja (403 al crear movimientos)."""
    odontologo, _, _, _ = await _preparar_consultorio(session, tenant_a, crear_usuario)
    headers = autorizacion(token_para(odontologo))

    r_lectura = await api.get("/api/caja/movimientos", headers=headers)
    assert r_lectura.status_code == 200
    assert r_lectura.json() == []

    r_escritura = await api.post(
        "/api/caja/movimientos",
        headers=headers,
        json={
            "tipo": "ingreso",
            "concepto": "Intento de odontólogo",
            "medio": "efectivo",
            "monto": "1000.00",
        },
    )
    assert r_escritura.status_code == 403, r_escritura.text


async def test_tenant_id_en_el_body_se_rechaza_con_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: el `tenant_id` sale del token; mandarlo en el body rompe el schema (422)."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-tenant@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    r_abrir = await api.post(
        "/api/caja/cierre",
        headers=headers,
        json={"fecha": "2026-12-20", "tenant_id": str(tenant_b.id)},
    )
    assert r_abrir.status_code == 422, r_abrir.text

    # Sin `tenant_id` el alta funciona y el cierre queda en el tenant del token.
    r_ok = await api.post("/api/caja/cierre", headers=headers, json={"fecha": "2026-12-20"})
    assert r_ok.status_code == 201, r_ok.text
    assert r_ok.json()["tenant_id"] == str(tenant_a.id)


async def test_seña_de_otro_tenant_no_es_visible_por_api(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: una seña de otro consultorio responde 404, nunca 200."""
    odontologo, paciente, sillon, prestacion = await _preparar_consultorio(
        session, tenant_a, crear_usuario
    )
    recepcion_a = await crear_usuario(
        tenant=tenant_a, email="recepcion-iso-a@consultorio.test", rol=RolUsuario.RECEPCION
    )
    recepcion_b = await crear_usuario(
        tenant=tenant_b, email="recepcion-iso-b@consultorio.test", rol=RolUsuario.RECEPCION
    )

    r_turno = await api.post(
        "/api/turnos",
        headers=autorizacion(token_para(recepcion_a)),
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prestacion.id),
            "inicio": (datetime.now(UTC) + timedelta(days=9)).isoformat(),
        },
    )
    assert r_turno.status_code == 201, r_turno.text
    turno_id = r_turno.json()["id"]

    r_senas = await api.get(
        f"/api/senas?turno_id={turno_id}",
        headers=autorizacion(token_para(recepcion_a)),
    )
    sena_id = r_senas.json()[0]["id"]

    r_ajena = await api.get(f"/api/senas/{sena_id}", headers=autorizacion(token_para(recepcion_b)))
    assert r_ajena.status_code == 404, r_ajena.text

    turno_bd = await session.get(Turno, uuid.UUID(turno_id))
    assert turno_bd is not None and turno_bd.tenant_id == tenant_a.id


# ---------------------------------------------------------------------------
# Triangulación: validación en el borde y códigos de error de la caja
# ---------------------------------------------------------------------------


async def test_reabrir_sin_motivo_se_rechaza_con_422_antes_de_tocar_la_caja(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-SE-01: la reapertura sin motivo no llega al caso de uso (422 del schema)."""
    dueno = await crear_usuario(
        tenant=tenant_a, email="dueno-sin-motivo@consultorio.test", rol=RolUsuario.DUENO
    )
    headers = autorizacion(token_para(dueno))

    r_abrir = await api.post("/api/caja/cierre", headers=headers, json={"fecha": "2026-12-21"})
    assert r_abrir.status_code == 201, r_abrir.text
    cierre_id = r_abrir.json()["id"]
    r_cerrar = await api.post(
        f"/api/caja/cierre/{cierre_id}/cerrar",
        headers=headers,
        json={"total_contado": "0.00"},
    )
    assert r_cerrar.status_code == 200, r_cerrar.text

    r_sin_motivo = await api.post(
        f"/api/caja/cierre/{cierre_id}/reabrir", headers=headers, json={"motivo": "   "}
    )
    assert r_sin_motivo.status_code == 422, r_sin_motivo.text


async def test_cerrar_un_cierre_inexistente_responde_404(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """R4: un cierre de otro consultorio (o inexistente) responde 404, nunca 200."""
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-404@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    r_cerrar = await api.post(
        f"/api/caja/cierre/{uuid.uuid4()}/cerrar",
        headers=headers,
        json={"total_contado": "100.00"},
    )
    assert r_cerrar.status_code == 404, r_cerrar.text


async def test_resolver_cancelacion_por_api_devuelve_la_sena_impaga(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RN-PA-04: la cancelación por API libera la seña impaga como `devuelta`."""
    odontologo, paciente, sillon, prestacion = await _preparar_consultorio(
        session, tenant_a, crear_usuario
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-cancela@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    r_turno = await api.post(
        "/api/turnos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prestacion.id),
            "inicio": (datetime.now(UTC) + timedelta(days=12)).isoformat(),
        },
    )
    assert r_turno.status_code == 201, r_turno.text
    turno_id = r_turno.json()["id"]

    r_senas = await api.get(f"/api/senas?turno_id={turno_id}", headers=headers)
    sena_id = r_senas.json()[0]["id"]

    r_resolver = await api.post(
        f"/api/senas/{sena_id}/cancelacion",
        headers=headers,
        json={"ausente": False, "motivo": "Canceló antes de pagar"},
    )
    assert r_resolver.status_code == 200, r_resolver.text
    assert r_resolver.json()["estado"] == EstadoSena.DEVUELTA.value


async def test_vencer_sena_antes_del_vencimiento_rechaza_422(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """Flujo 1 paso 6: no se vence una seña cuyo plazo de 24 h sigue corriendo."""
    odontologo, paciente, sillon, prestacion = await _preparar_consultorio(
        session, tenant_a, crear_usuario
    )
    recepcion = await crear_usuario(
        tenant=tenant_a, email="recepcion-vence@consultorio.test", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    r_turno = await api.post(
        "/api/turnos",
        headers=headers,
        json={
            "paciente_id": str(paciente.id),
            "profesional_id": str(odontologo.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prestacion.id),
            "inicio": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
        },
    )
    assert r_turno.status_code == 201, r_turno.text
    turno_id = r_turno.json()["id"]
    sena_id = (await api.get(f"/api/senas?turno_id={turno_id}", headers=headers)).json()[0]["id"]

    r_vencer = await api.post(f"/api/senas/{sena_id}/vencer", headers=headers)
    assert r_vencer.status_code == 422, r_vencer.text

    turno_bd = await session.get(Turno, uuid.UUID(turno_id))
    assert turno_bd is not None
    assert turno_bd.estado != "cancelado"
