"""Tests E2E del webhook de Mercado Pago (tarea 2.2).

Cubre:
- Firma HMAC `x-signature` válida (RN-SE-04) y rechazo `401` de firmas alteradas.
- Persistencia cruda del payload en `cobro_mp` antes de mutar el dominio (design D3).
- Pago `approved`: seña `cobrada`, `turno.sena_cobrada`, `MovimientoCaja` ingreso `mp` y
  auditoría sin actor humano (`origen = webhook_mercadopago`).
- Idempotencia estricta por `mp_payment_id` (RN-PA-03): reenvío `200` sin duplicar nada.
- Pago `refunded`: seña `devuelta` + egreso compensatorio, idempotente.
- `external_reference` desconocida: `200` ignorado, sin persistir datos de terceros (R4).
"""

import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import crear_turno
from app.domain.auditoria import Auditoria
from app.domain.caja import EstadoSena, MedioPago, MovimientoCaja, Sena, TipoMovimientoCaja
from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.mercadopago.client import calcular_firma_mp

SECRETO = "secreto-mp-test"
REQUEST_ID = "req-mp-test-001"
MONTO_SENA = Decimal("10000.00")


async def _preparar_escenario(session: AsyncSession, tenant: Tenant) -> SimpleNamespace:
    """Profesional, paciente, sillón, prestación con seña y turno con seña `pendiente`."""
    sufijo = tenant.slug.replace("-", "")
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-mp-{sufijo}@test.com",
        nombre="Dra. MP Webhook",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-30301",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente MP Webhook",
        dni=f"42{sufijo[:6]}",
        telefono=f"+54911888{sufijo[:6]}",
        email=f"paciente-{sufijo}@test.com",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Box MP",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Implante con seña MP",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=MONTO_SENA,
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()

    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 12, 2, 10, 0, tzinfo=UTC),
        actor_id=odontologo.id,
    )
    await session.flush()
    sena = (await session.execute(select(Sena).where(Sena.turno_id == turno.id))).scalar_one()
    return SimpleNamespace(
        tenant=tenant,
        odontologo=odontologo,
        paciente=paciente,
        turno=turno,
        sena=sena,
    )


def _firma(data_id: str, request_id: str = REQUEST_ID) -> str:
    """Arma el header `x-signature` válido (ts + v1) para el `data.id` indicado."""
    ts = int(time.time())
    v1 = calcular_firma_mp(data_id=data_id, request_id=request_id, ts=ts, secret=SECRETO)
    return f"ts={ts},v1={v1}"


def _payload(
    payment_id: str,
    sena: Sena,
    *,
    estado: str = EstadoMP.APPROVED.value,
    monto: Decimal = MONTO_SENA,
    external_reference: str | None = None,
) -> dict[str, object]:
    """Notificación de MP con el detalle del pago (permite tests offline deterministas)."""
    return {
        "id": 123456789,
        "live_mode": False,
        "type": "payment",
        "action": "payment.updated",
        "data": {
            "id": payment_id,
            "status": estado,
            "transaction_amount": float(monto),
            "external_reference": external_reference or str(sena.id),
            "preference_id": "pref_mp_001",
        },
    }


async def _post_webhook(
    api: httpx.AsyncClient,
    payload: dict[str, object],
    *,
    firma: str | None = None,
) -> httpx.Response:
    data_id = str(payload["data"]["id"])  # type: ignore[index]
    return await api.post(
        "/webhooks/mercadopago",
        content=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-signature": firma or _firma(data_id),
            "x-request-id": REQUEST_ID,
        },
    )


async def test_webhook_approved_confirma_sena_caja_y_persiste_payload_crudo(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    auditoria_de,
) -> None:
    """RN-PA-01/03/05: `approved` cobra la seña, registra ingreso `mp` y persiste el payload."""
    ctx = await _preparar_escenario(session, tenant_a)
    payment_id = "mp-pay-approved-001"

    resp = await _post_webhook(api, _payload(payment_id, ctx.sena))
    assert resp.status_code == 200, resp.text
    assert resp.json()["procesados"] == 1

    await session.refresh(ctx.sena)
    await session.refresh(ctx.turno)
    assert ctx.sena.estado == EstadoSena.COBRADA.value
    assert ctx.sena.mp_payment_id == payment_id
    assert ctx.turno.sena_cobrada is True

    cobro = (
        await session.execute(select(CobroMP).where(CobroMP.mp_payment_id == payment_id))
    ).scalar_one()
    assert cobro.tenant_id == tenant_a.id
    assert cobro.sena_id == ctx.sena.id
    assert cobro.turno_id == ctx.turno.id
    assert cobro.estado_mp == EstadoMP.APPROVED.value
    assert cobro.estado_conciliacion == EstadoConciliacionMP.CONCILIADO.value
    assert Decimal(str(cobro.monto)) == MONTO_SENA
    # D3: se guarda el JSON completo, no un resumen.
    assert cobro.payload["data"]["id"] == payment_id  # type: ignore[index]
    assert cobro.payload["action"] == "payment.updated"

    movimiento = (
        await session.execute(select(MovimientoCaja).where(MovimientoCaja.sena_id == ctx.sena.id))
    ).scalar_one()
    assert movimiento.tipo == TipoMovimientoCaja.INGRESO.value
    assert movimiento.medio == MedioPago.MP.value
    assert Decimal(str(movimiento.monto)) == MONTO_SENA
    assert movimiento.cobro_mp_id == cobro.id
    assert movimiento.created_by == ctx.odontologo.id

    eventos = await auditoria_de("sena.cobrar_mp")
    assert len(eventos) == 1
    assert eventos[0].actor_id is None
    assert eventos[0].despues is not None
    assert eventos[0].despues["origen"] == "webhook_mercadopago"


async def test_webhook_duplicado_responde_200_sin_duplicar_movimientos_ni_estado(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-03: el mismo `mp_payment_id` dos veces no duplica caja, seña ni cobro."""
    ctx = await _preparar_escenario(session, tenant_a)
    payment_id = "mp-pay-duplicado-002"
    payload = _payload(payment_id, ctx.sena)

    primero = await _post_webhook(api, payload)
    assert primero.status_code == 200
    assert primero.json()["procesados"] == 1

    segundo = await _post_webhook(api, payload)
    assert segundo.status_code == 200
    assert segundo.json()["duplicados"] == 1
    assert segundo.json()["procesados"] == 0

    await session.refresh(ctx.sena)
    assert ctx.sena.estado == EstadoSena.COBRADA.value

    cobros = (
        (await session.execute(select(CobroMP).where(CobroMP.mp_payment_id == payment_id)))
        .scalars()
        .all()
    )
    assert len(cobros) == 1

    movimientos = (
        (await session.execute(select(MovimientoCaja).where(MovimientoCaja.sena_id == ctx.sena.id)))
        .scalars()
        .all()
    )
    assert len(movimientos) == 1


async def test_webhook_firma_invalida_rechaza_401_sin_persistir(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-SE-04: una firma alterada no toca datos del consultorio."""
    ctx = await _preparar_escenario(session, tenant_a)
    payload = _payload("mp-pay-firma-mala-003", ctx.sena)

    resp = await _post_webhook(api, payload, firma="ts=1,v1=firma-trucha")

    assert resp.status_code == 401
    await session.refresh(ctx.sena)
    assert ctx.sena.estado == EstadoSena.PENDIENTE.value
    assert ctx.sena.mp_payment_id is None
    assert (await session.execute(select(CobroMP))).scalars().all() == []


async def test_webhook_refunded_devuelve_sena_y_registra_egreso_idempotente(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """`refunded`: la seña vuelve a `devuelta` y el reintegro queda en caja una sola vez."""
    ctx = await _preparar_escenario(session, tenant_a)
    payment_id = "mp-pay-refund-004"

    aprobado = await _post_webhook(api, _payload(payment_id, ctx.sena))
    assert aprobado.status_code == 200, aprobado.text

    devuelto = await _post_webhook(
        api, _payload(payment_id, ctx.sena, estado=EstadoMP.REFUNDED.value)
    )
    assert devuelto.status_code == 200, devuelto.text
    assert devuelto.json()["procesados"] == 1

    await session.refresh(ctx.sena)
    await session.refresh(ctx.turno)
    assert ctx.sena.estado == EstadoSena.DEVUELTA.value
    assert ctx.turno.sena_cobrada is False

    cobro = (
        await session.execute(select(CobroMP).where(CobroMP.mp_payment_id == payment_id))
    ).scalar_one()
    assert cobro.estado_mp == EstadoMP.REFUNDED.value

    egresos = (
        (
            await session.execute(
                select(MovimientoCaja).where(
                    MovimientoCaja.sena_id == ctx.sena.id,
                    MovimientoCaja.tipo == TipoMovimientoCaja.EGRESO.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(egresos) == 1
    assert egresos[0].medio == MedioPago.MP.value
    assert egresos[0].cobro_mp_id == cobro.id
    assert Decimal(str(egresos[0].monto)) == MONTO_SENA

    # Reenvío del mismo refund: idempotente, no crea un segundo egreso.
    repetido = await _post_webhook(
        api, _payload(payment_id, ctx.sena, estado=EstadoMP.REFUNDED.value)
    )
    assert repetido.status_code == 200
    assert repetido.json()["duplicados"] == 1
    egresos_tras_reintento = (
        (
            await session.execute(
                select(MovimientoCaja).where(
                    MovimientoCaja.sena_id == ctx.sena.id,
                    MovimientoCaja.tipo == TipoMovimientoCaja.EGRESO.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(egresos_tras_reintento) == 1


async def test_webhook_external_reference_desconocida_se_ignora_sin_persistir(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R4: sin seña resoluble no hay tenant ni datos que persistir; MP recibe `200`."""
    ctx = await _preparar_escenario(session, tenant_a)
    payload = _payload(
        "mp-pay-huerfano-005",
        ctx.sena,
        external_reference=str(uuid.uuid4()),
    )

    resp = await _post_webhook(api, payload)

    assert resp.status_code == 200
    assert resp.json()["ignorados"] == 1
    assert (await session.execute(select(CobroMP))).scalars().all() == []
    await session.refresh(ctx.sena)
    assert ctx.sena.estado == EstadoSena.PENDIENTE.value


async def test_webhook_pago_aprobado_sobre_turno_cancelado_marca_discrepancia(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-05: pago tardío no resucita el turno; queda como discrepancia revisable."""
    ctx = await _preparar_escenario(session, tenant_a)
    ctx.turno.estado = EstadoTurno.CANCELADO.value
    ctx.sena.estado = EstadoSena.VENCIDA.value
    await session.flush()

    resp = await _post_webhook(api, _payload("mp-pay-tardio-006", ctx.sena))

    assert resp.status_code == 200
    assert resp.json()["discrepancias"] == 1

    cobro = (
        await session.execute(select(CobroMP).where(CobroMP.mp_payment_id == "mp-pay-tardio-006"))
    ).scalar_one()
    assert cobro.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value

    await session.refresh(ctx.sena)
    await session.refresh(ctx.turno)
    assert ctx.sena.estado == EstadoSena.VENCIDA.value
    assert ctx.turno.estado == EstadoTurno.CANCELADO.value
    assert ctx.turno.sena_cobrada is False
    movimientos = (
        (await session.execute(select(MovimientoCaja).where(MovimientoCaja.sena_id == ctx.sena.id)))
        .scalars()
        .all()
    )
    assert movimientos == []

    eventos = await session.execute(
        select(Auditoria).where(Auditoria.accion == "cobro_mp.discrepancia")
    )
    evento = eventos.scalars().one()
    assert evento.actor_id is None
    assert evento.despues is not None
    assert evento.despues["origen"] == "webhook_mercadopago"
