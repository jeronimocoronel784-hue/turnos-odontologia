"""Tests de conciliación y detección de discrepancias de Mercado Pago (tarea 3.1).

Cubre:
- Pago `approved` con seña `vencida` o turno `cancelado|ausente` -> `discrepancia` sin
  auto-confirmar ni cerrar la seña (RN-PA-05).
- Monto pagado distinto al de la seña -> `discrepancia`.
- `conciliar_cobros(...)`: recorre cobros `pendientes`, consulta MP y marca
  `conciliado` / `discrepancia` (aplicando el pago sólo cuando es consistente).
- Aislamiento por tenant del job de conciliación (R4).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import crear_turno
from app.application.caja import vencer_sena_impaga
from app.application.mercadopago import conciliar_cobros, procesar_webhook_mp
from app.domain.caja import EstadoSena, MovimientoCaja, Sena
from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.domain.usuario import RolUsuario, Usuario

MONTO_SENA = Decimal("10000.00")


async def _preparar_escenario(
    session: AsyncSession,
    tenant: Tenant,
    *,
    etiqueta: str = "a",
    inicio: datetime = datetime(2026, 12, 3, 10, 0, tzinfo=UTC),
) -> SimpleNamespace:
    """Turno con seña `pendiente` para el tenant indicado."""
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-conc-{tenant.slug}-{etiqueta}@test.com",
        nombre="Dr. Conciliación",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-40401",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Paciente Conciliación {etiqueta}",
        dni=f"43{uuid.uuid4().int % 10**7:07d}",
        telefono=f"+54911999{uuid.uuid4().int % 10**6:06d}",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Box Conc {etiqueta}",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre=f"Implante Conc {etiqueta}",
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
        inicio=inicio,
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


def _payload(
    payment_id: str,
    sena: Sena,
    *,
    estado: str = EstadoMP.APPROVED.value,
    monto: Decimal = MONTO_SENA,
) -> dict[str, Any]:
    return {
        "id": 987654321,
        "live_mode": False,
        "type": "payment",
        "action": "payment.updated",
        "data": {
            "id": payment_id,
            "status": estado,
            "transaction_amount": float(monto),
            "external_reference": str(sena.id),
            "preference_id": "pref_conc_001",
        },
    }


def _cobro_pendiente(
    ctx: SimpleNamespace,
    payment_id: str,
    *,
    estado_mp: str = EstadoMP.PENDING.value,
) -> CobroMP:
    return CobroMP(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        turno_id=ctx.turno.id,
        sena_id=ctx.sena.id,
        mp_payment_id=payment_id,
        mp_preference_id="pref_conc_001",
        monto=MONTO_SENA,
        estado_mp=estado_mp,
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload={"data": {"id": payment_id, "status": estado_mp}},
    )


class _ClienteFake:
    """Cliente MP simulado: devuelve la respuesta configurada por payment id."""

    def __init__(self, respuestas: dict[str, dict[str, Any]]) -> None:
        self.respuestas = respuestas
        self.consultados: list[str] = []

    async def obtener_pago(self, payment_id: str) -> dict[str, Any]:
        self.consultados.append(payment_id)
        return self.respuestas[payment_id]


async def test_pago_aprobado_con_sena_vencida_marca_discrepancia_sin_mutar(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-05: seña vencida + turno cancelado -> discrepancia, sin tocar seña/turno/caja."""
    ctx = await _preparar_escenario(session, tenant_a)
    ahora = ctx.sena.vence_at + timedelta(minutes=1)
    await vencer_sena_impaga(
        session,
        tenant_id=tenant_a.id,
        sena_id=ctx.sena.id,
        ahora=ahora,
        actor_id=ctx.odontologo.id,
    )
    await session.refresh(ctx.sena)
    await session.refresh(ctx.turno)
    assert ctx.sena.estado == EstadoSena.VENCIDA.value
    assert ctx.turno.estado == EstadoTurno.CANCELADO.value

    resultado = await procesar_webhook_mp(
        session,
        payload=_payload("mp-conc-vencida-001", ctx.sena),
    )

    assert resultado.cobro is not None
    assert resultado.discrepancia is True
    cobro = resultado.cobro
    assert cobro.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
    assert cobro.estado_mp == EstadoMP.APPROVED.value

    await session.refresh(ctx.sena)
    await session.refresh(ctx.turno)
    assert ctx.sena.estado == EstadoSena.VENCIDA.value
    assert ctx.sena.mp_payment_id is None
    assert ctx.turno.estado == EstadoTurno.CANCELADO.value
    assert ctx.turno.sena_cobrada is False
    movimientos = (
        await session.execute(
            select(MovimientoCaja).where(MovimientoCaja.sena_id == ctx.sena.id)
        )
    ).scalars().all()
    assert movimientos == []


async def test_pago_aprobado_con_monto_distinto_marca_discrepancia(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """R8/RN-PA-05: un monto que no coincide no confirma la seña."""
    ctx = await _preparar_escenario(session, tenant_a)

    resultado = await procesar_webhook_mp(
        session,
        payload=_payload("mp-conc-monto-002", ctx.sena, monto=Decimal("5000.00")),
    )

    assert resultado.discrepancia is True
    assert resultado.cobro is not None
    assert resultado.cobro.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
    await session.refresh(ctx.sena)
    assert ctx.sena.estado == EstadoSena.PENDIENTE.value
    assert ctx.sena.mp_payment_id is None
    movimientos = (
        await session.execute(
            select(MovimientoCaja).where(MovimientoCaja.sena_id == ctx.sena.id)
        )
    ).scalars().all()
    assert movimientos == []


async def test_pago_aprobado_sobre_turno_ausente_marca_discrepancia(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-05: turno marcado `ausente` no se resucita con un pago tardío."""
    ctx = await _preparar_escenario(session, tenant_a)
    ctx.turno.estado = EstadoTurno.AUSENTE.value
    await session.flush()

    resultado = await procesar_webhook_mp(
        session,
        payload=_payload("mp-conc-ausente-003", ctx.sena),
    )

    assert resultado.discrepancia is True
    assert resultado.cobro is not None
    assert resultado.cobro.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
    await session.refresh(ctx.turno)
    assert ctx.turno.estado == EstadoTurno.AUSENTE.value
    assert ctx.turno.sena_cobrada is False


async def test_conciliar_cobros_aplica_pagos_consistentes_y_marca_discrepancias(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """`conciliar_cobros` consulta MP, concilia el pago válido y detecta el tardío."""
    ok = await _preparar_escenario(session, tenant_a, etiqueta="ok")
    tardio = await _preparar_escenario(
        session,
        tenant_a,
        etiqueta="tardio",
        inicio=datetime(2026, 12, 3, 11, 30, tzinfo=UTC),
    )

    cobro_ok = _cobro_pendiente(ok, "mp-conc-job-ok-004")
    session.add(cobro_ok)

    await vencer_sena_impaga(
        session,
        tenant_id=tenant_a.id,
        sena_id=tardio.sena.id,
        ahora=tardio.sena.vence_at + timedelta(minutes=1),
        actor_id=tardio.odontologo.id,
    )
    await session.refresh(tardio.sena)
    await session.refresh(tardio.turno)
    cobro_tardio = _cobro_pendiente(tardio, "mp-conc-job-tardio-005")
    session.add(cobro_tardio)
    await session.flush()

    cliente = _ClienteFake(
        {
            cobro_ok.mp_payment_id: {
                "id": cobro_ok.mp_payment_id,
                "status": EstadoMP.APPROVED.value,
                "transaction_amount": float(MONTO_SENA),
                "external_reference": str(ok.sena.id),
            },
            cobro_tardio.mp_payment_id: {
                "id": cobro_tardio.mp_payment_id,
                "status": EstadoMP.APPROVED.value,
                "transaction_amount": float(MONTO_SENA),
                "external_reference": str(tardio.sena.id),
            },
        }
    )

    cobros = await conciliar_cobros(
        session,
        tenant_id=tenant_a.id,
        cliente=cliente,  # type: ignore[arg-type]
    )

    assert {c.id for c in cobros} == {cobro_ok.id, cobro_tardio.id}
    assert set(cliente.consultados) == {cobro_ok.mp_payment_id, cobro_tardio.mp_payment_id}

    await session.refresh(cobro_ok)
    await session.refresh(ok.sena)
    await session.refresh(ok.turno)
    assert cobro_ok.estado_conciliacion == EstadoConciliacionMP.CONCILIADO.value
    assert ok.sena.estado == EstadoSena.COBRADA.value
    assert ok.sena.mp_payment_id == cobro_ok.mp_payment_id
    assert ok.turno.sena_cobrada is True
    movimientos_ok = (
        await session.execute(
            select(MovimientoCaja).where(MovimientoCaja.sena_id == ok.sena.id)
        )
    ).scalars().all()
    assert len(movimientos_ok) == 1
    assert movimientos_ok[0].cobro_mp_id == cobro_ok.id

    await session.refresh(cobro_tardio)
    await session.refresh(tardio.sena)
    assert cobro_tardio.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
    assert tardio.sena.estado == EstadoSena.VENCIDA.value
    movimientos_tardio = (
        await session.execute(
            select(MovimientoCaja).where(MovimientoCaja.sena_id == tardio.sena.id)
        )
    ).scalars().all()
    assert movimientos_tardio == []


async def test_conciliar_cobros_respeta_el_tenant_del_llamador(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
) -> None:
    """R4: el job de un consultorio nunca toca cobros de otro tenant."""
    propio = await _preparar_escenario(session, tenant_a, etiqueta="propio")
    ajeno = await _preparar_escenario(
        session,
        tenant_b,
        etiqueta="ajeno",
        inicio=datetime(2026, 12, 3, 12, 30, tzinfo=UTC),
    )
    cobro_propio = _cobro_pendiente(propio, "mp-conc-tenant-a-006")
    cobro_ajeno = _cobro_pendiente(ajeno, "mp-conc-tenant-b-007")
    session.add_all([cobro_propio, cobro_ajeno])
    await session.flush()

    cliente = _ClienteFake(
        {
            cobro_propio.mp_payment_id: {
                "id": cobro_propio.mp_payment_id,
                "status": EstadoMP.APPROVED.value,
                "transaction_amount": float(MONTO_SENA),
                "external_reference": str(propio.sena.id),
            },
        }
    )

    cobros = await conciliar_cobros(
        session,
        tenant_id=tenant_a.id,
        cliente=cliente,  # type: ignore[arg-type]
    )

    assert [c.id for c in cobros] == [cobro_propio.id]
    assert cliente.consultados == [cobro_propio.mp_payment_id]
    await session.refresh(cobro_ajeno)
    assert cobro_ajeno.estado_conciliacion == EstadoConciliacionMP.PENDIENTE.value
    await session.refresh(ajeno.sena)
    assert ajeno.sena.estado == EstadoSena.PENDIENTE.value


@pytest.mark.parametrize("estado", [EstadoMP.PENDING.value, EstadoMP.REJECTED.value])
async def test_conciliar_cobros_no_confirma_con_estados_sin_acreditacion(
    session: AsyncSession,
    tenant_a: Tenant,
    estado: str,
) -> None:
    """`pending` sigue pendiente de conciliar; `rejected` se cierra sin acreditar la seña."""
    ctx = await _preparar_escenario(session, tenant_a)
    cobro = _cobro_pendiente(ctx, f"mp-conc-{estado}-008")
    session.add(cobro)
    await session.flush()

    cliente = _ClienteFake(
        {
            cobro.mp_payment_id: {
                "id": cobro.mp_payment_id,
                "status": estado,
                "transaction_amount": float(MONTO_SENA),
                "external_reference": str(ctx.sena.id),
            },
        }
    )

    await conciliar_cobros(
        session,
        tenant_id=tenant_a.id,
        cliente=cliente,  # type: ignore[arg-type]
    )

    await session.refresh(cobro)
    await session.refresh(ctx.sena)
    assert ctx.sena.estado == EstadoSena.PENDIENTE.value
    assert ctx.turno.sena_cobrada is False
    if estado == EstadoMP.PENDING.value:
        assert cobro.estado_conciliacion == EstadoConciliacionMP.PENDIENTE.value
    else:
        assert cobro.estado_conciliacion == EstadoConciliacionMP.CONCILIADO.value


async def test_webhook_race_de_reintentos_captura_integrity_error_y_responde_duplicado(
    session: AsyncSession,
    tenant_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos webhooks en ráfaga: la unicidad de `mp_payment_id` gana y el perdedor es 200."""
    import app.application.mercadopago as modulo

    ctx = await _preparar_escenario(session, tenant_a)
    existente = _cobro_pendiente(
        ctx, "mp-race-integrity-009", estado_mp=EstadoMP.APPROVED.value
    )
    existente.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value
    session.add(existente)
    await session.commit()

    original = modulo._obtener_cobro_por_pago
    llamadas = {"cantidad": 0}

    async def _primera_vez_ninguno(ses: AsyncSession, payment_id: str) -> CobroMP | None:
        llamadas["cantidad"] += 1
        if llamadas["cantidad"] == 1:
            return None
        return await original(ses, payment_id)

    monkeypatch.setattr(modulo, "_obtener_cobro_por_pago", _primera_vez_ninguno)

    resultado = await modulo.procesar_webhook_mp(
        session,
        payload=_payload("mp-race-integrity-009", ctx.sena),
    )

    assert resultado.duplicado is True
    assert resultado.cobro is not None
    assert resultado.cobro.mp_payment_id == "mp-race-integrity-009"

    cobros = (
        await session.execute(
            select(CobroMP).where(CobroMP.mp_payment_id == "mp-race-integrity-009")
        )
    ).scalars().all()
    assert len(cobros) == 1
