"""Casos de uso de Mercado Pago (C-12, US-031).

Reglas implementadas:
- RN-PA-02: la preferencia de pago se ata a la seña (`external_reference = sena.id`) y vence
  junto con ella (`expiration_date_to = sena.vence_at`).
- RN-PA-03: el webhook es idempotente por `mp_payment_id` único; un reenvío no duplica caja.
- RN-PA-05: pagos tardíos o con monto distinto quedan en `discrepancia` sin auto-confirmar el
  turno ni cerrar nada; la conciliación periódica vuelve a comparar contra Mercado Pago.
- RN-SE-04: la firma HMAC se valida en el router; acá sólo se procesa un pago ya autenticado.
- R7: `movimiento_caja` es append-only; la devolución se registra como egreso compensatorio.
- R8: todos los montos se normalizan a `Decimal` con 2 decimales.
- R9: la auditoría nunca guarda PHI ni secretos (sólo ids, estados y motivo).
"""

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_mercadopago import PreferenciaRead
from app.application.auditoria import registrar_auditoria
from app.application.caja import (
    _monto,
    _registrar_egreso,
    _registrar_ingreso,
    obtener_sena,
)
from app.domain.caja import EstadoSena, MedioPago, Sena
from app.domain.mercadopago import CobroMP, EstadoConciliacionMP, EstadoMP
from app.domain.turno import EstadoTurno, Turno
from app.infrastructure.mercadopago.client import MercadoPagoClient
from app.shared.exceptions import EntidadInvalida
from app.shared.settings import Settings, get_settings

CERO = Decimal("0.00")
CONCEPTO_SENA_MP = "Cobro de seña Mercado Pago"
CONCEPTO_DEVOLUCION_SENA_MP = "Devolución de seña Mercado Pago"
TITULO_PREFERENCIA_DEFAULT = "Seña de turno odontológico"
ORIGEN_WEBHOOK = "webhook_mercadopago"
ESTADOS_TURNO_NO_CONFIRMABLES = frozenset({EstadoTurno.CANCELADO.value, EstadoTurno.AUSENTE.value})
ESTADOS_SENA_CON_DINERO = frozenset({EstadoSena.COBRADA.value, EstadoSena.APLICADA.value})


@dataclass(frozen=True)
class PagoMP:
    """Datos mínimos de un pago de MP necesarios para reconciliar la seña."""

    payment_id: str
    estado: EstadoMP
    monto: Decimal
    external_reference: str | None = None
    preference_id: str | None = None


@dataclass(frozen=True)
class ResultadoWebhookMP:
    """Resultado del procesamiento de una notificación (para la respuesta 200 de MP)."""

    cobro: CobroMP | None = None
    duplicado: bool = False
    ignorado: bool = False
    discrepancia: bool = False


def _normalizar_estado(valor: object) -> EstadoMP:
    """Mapea el estado de MP al enum persistible; desconocidos quedan `pending`."""
    try:
        return EstadoMP(str(valor))
    except ValueError:
        return EstadoMP.PENDING


def _a_decimal(valor: object, default: Decimal) -> Decimal:
    """Normaliza un monto externo (float/str/Decimal) a `Decimal` con 2 decimales (R8)."""
    if valor is None or valor == "":
        return default
    try:
        return _monto(valor)
    except (ArithmeticError, TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Preferencias de pago (RN-PA-02)
# ---------------------------------------------------------------------------


async def crear_preferencia_para_sena(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID,
    settings: Settings | None = None,
    cliente: MercadoPagoClient | None = None,
    titulo: str = TITULO_PREFERENCIA_DEFAULT,
    paciente_email: str | None = None,
) -> PreferenciaRead:
    """Genera el link de checkout de una seña `pendiente` con vencimiento sincronizado."""
    sena = await obtener_sena(session, tenant_id=tenant_id, sena_id=sena_id)
    if sena.estado != EstadoSena.PENDIENTE.value:
        raise EntidadInvalida(
            "Che, sólo se puede generar el link de pago de una seña 'pendiente': "
            f"esta está en '{sena.estado}'."
        )
    if sena.vence_at is None:
        raise EntidadInvalida(
            "Che, la seña no tiene fecha de vencimiento: no se puede generar el link de pago."
        )

    cfg = settings if settings is not None else get_settings()
    mp = cliente if cliente is not None else MercadoPagoClient(access_token=cfg.mp_access_token)
    return await mp.crear_preferencia(
        sena_id=sena.id,
        monto=_monto(sena.monto),
        titulo=titulo,
        vence_at=sena.vence_at,
        paciente_email=paciente_email,
    )


# ---------------------------------------------------------------------------
# Resolución de la seña desde el webhook (sin tenant en el request)
# ---------------------------------------------------------------------------


async def resolver_sena_por_external_reference(
    session: AsyncSession,
    external_reference: str | None,
) -> tuple[Sena, Turno] | None:
    """Resuelve seña + turno por `external_reference`; el tenant se deriva de la seña (R4)."""
    if not external_reference:
        return None
    try:
        sena_id = uuid.UUID(str(external_reference))
    except (TypeError, ValueError):
        return None

    sena = (await session.execute(select(Sena).where(Sena.id == sena_id))).scalar_one_or_none()
    if sena is None:
        return None
    turno = (
        await session.execute(select(Turno).where(Turno.id == sena.turno_id))
    ).scalar_one_or_none()
    if turno is None:
        return None
    return sena, turno


async def _obtener_cobro_por_pago(session: AsyncSession, payment_id: str) -> CobroMP | None:
    return (
        await session.execute(select(CobroMP).where(CobroMP.mp_payment_id == payment_id))
    ).scalar_one_or_none()


async def _resolver_pago(
    payment_id: str,
    payload: dict[str, Any],
    cliente: MercadoPagoClient | None,
    monto_default: Decimal,
) -> PagoMP:
    """Toma el detalle del pago del payload y, si falta, lo consulta a MP (design D1)."""
    data = payload.get("data")
    detalle: dict[str, Any] = data if isinstance(data, dict) else {}

    estado_raw = detalle.get("status")
    monto_raw = detalle.get("transaction_amount")
    external = detalle.get("external_reference")
    preference = detalle.get("preference_id") or detalle.get("preference")

    if (estado_raw is None or monto_raw is None or external is None) and cliente is not None:
        consulta = await cliente.obtener_pago(payment_id)
        if estado_raw is None:
            estado_raw = consulta.get("status")
        if monto_raw is None:
            monto_raw = consulta.get("transaction_amount")
        if external is None:
            external = consulta.get("external_reference")
        if preference is None:
            preference = consulta.get("preference_id") or consulta.get("preference")

    return PagoMP(
        payment_id=payment_id,
        estado=_normalizar_estado(estado_raw),
        monto=_a_decimal(monto_raw, monto_default),
        external_reference=str(external) if external else None,
        preference_id=str(preference) if preference else None,
    )


# ---------------------------------------------------------------------------
# Procesamiento del webhook (RN-PA-03 / RN-PA-05)
# ---------------------------------------------------------------------------


def _motivo_discrepancia_aprobado(
    sena: Sena | None,
    turno: Turno | None,
    monto: Decimal,
    payment_id: str,
) -> str | None:
    """Devuelve el motivo por el que un `approved` no puede confirmar la seña (o `None`)."""
    if sena is None:
        return "No se encontró la seña asociada al pago"
    if sena.estado == EstadoSena.VENCIDA.value:
        return "Pago aprobado con la seña vencida"
    if turno is None:
        return "No se encontró el turno asociado a la seña"
    if turno.estado in ESTADOS_TURNO_NO_CONFIRMABLES:
        return f"Pago aprobado con el turno '{turno.estado}'"
    if _monto(monto) != _monto(sena.monto):
        return "El monto pagado no coincide con el monto de la seña"
    if sena.estado in ESTADOS_SENA_CON_DINERO:
        if sena.mp_payment_id and sena.mp_payment_id != payment_id:
            return "La seña ya estaba cobrada con otro pago de Mercado Pago"
        if sena.mp_payment_id is None:
            return "La seña ya estaba cobrada por otro medio de pago"
        return None
    if sena.estado == EstadoSena.DEVUELTA.value:
        return "Pago aprobado sobre una seña ya devuelta"
    if sena.estado != EstadoSena.PENDIENTE.value:
        return f"Pago aprobado sobre una seña en estado '{sena.estado}'"
    return None


def _motivo_discrepancia_refund(sena: Sena | None, turno: Turno | None) -> str | None:
    if sena is None:
        return "No se encontró la seña a devolver"
    if turno is None:
        return "No se encontró el turno asociado a la seña a devolver"
    if sena.estado == EstadoSena.DEVUELTA.value:
        return None
    if sena.estado not in ESTADOS_SENA_CON_DINERO:
        return f"Devolución con la seña en estado '{sena.estado}'"
    return None


async def _marcar_discrepancia(
    session: AsyncSession,
    *,
    cobro: CobroMP,
    motivo: str,
) -> None:
    """Marca el cobro para revisión manual; nunca auto-cierra ni auto-confirma (RN-PA-05)."""
    cobro.estado_conciliacion = EstadoConciliacionMP.DISCREPANCIA.value
    await registrar_auditoria(
        session,
        tenant_id=cobro.tenant_id,
        actor_id=None,
        accion="cobro_mp.discrepancia",
        entidad="cobro_mp",
        entidad_id=str(cobro.id),
        despues={
            "mp_payment_id": cobro.mp_payment_id,
            "estado_mp": cobro.estado_mp,
            "motivo": motivo,
            "origen": ORIGEN_WEBHOOK,
        },
    )
    await session.flush()


async def _confirmar_sena_con_pago(
    session: AsyncSession,
    *,
    cobro: CobroMP,
    sena: Sena,
    turno: Turno,
) -> None:
    """Aplica un pago `approved` consistente sobre la seña y la caja (RN-PA-01/05)."""
    if sena.estado in ESTADOS_SENA_CON_DINERO and sena.mp_payment_id == cobro.mp_payment_id:
        # Reconciliación repetida del mismo pago: no duplica el ingreso.
        cobro.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value
        return

    antes: dict[str, object] = {"estado": sena.estado, "sena_cobrada": turno.sena_cobrada}
    sena.estado = EstadoSena.COBRADA.value
    sena.mp_payment_id = cobro.mp_payment_id
    turno.sena_cobrada = True
    await session.flush()

    movimiento = await _registrar_ingreso(
        session,
        tenant_id=sena.tenant_id,
        concepto=CONCEPTO_SENA_MP,
        medio=MedioPago.MP.value,
        monto=_monto(cobro.monto),
        actor_id=turno.profesional_id,
        turno_id=turno.id,
        sena_id=sena.id,
        cobro_mp_id=cobro.id,
    )
    cobro.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value

    await registrar_auditoria(
        session,
        tenant_id=sena.tenant_id,
        actor_id=None,
        accion="sena.cobrar_mp",
        entidad="sena",
        entidad_id=str(sena.id),
        antes=antes,
        despues={
            "estado": sena.estado,
            "sena_cobrada": turno.sena_cobrada,
            "monto": str(_monto(cobro.monto)),
            "medio": movimiento.medio,
            "movimiento_id": str(movimiento.id),
            "cobro_mp_id": str(cobro.id),
            "origen": ORIGEN_WEBHOOK,
        },
    )


async def _devolver_sena_por_refund(
    session: AsyncSession,
    *,
    cobro: CobroMP,
    sena: Sena,
    turno: Turno,
) -> None:
    """Registra la devolución del pago y el egreso compensatorio (idempotente)."""
    if sena.estado == EstadoSena.DEVUELTA.value:
        cobro.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value
        return

    antes: dict[str, object] = {"estado": sena.estado, "sena_cobrada": turno.sena_cobrada}
    sena.estado = EstadoSena.DEVUELTA.value
    turno.sena_cobrada = False
    await session.flush()

    movimiento = await _registrar_egreso(
        session,
        tenant_id=sena.tenant_id,
        concepto=CONCEPTO_DEVOLUCION_SENA_MP,
        medio=MedioPago.MP.value,
        monto=_monto(cobro.monto),
        actor_id=turno.profesional_id,
        turno_id=turno.id,
        sena_id=sena.id,
        cobro_mp_id=cobro.id,
    )
    cobro.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value

    await registrar_auditoria(
        session,
        tenant_id=sena.tenant_id,
        actor_id=None,
        accion="sena.devolver_mp",
        entidad="sena",
        entidad_id=str(sena.id),
        antes=antes,
        despues={
            "estado": sena.estado,
            "sena_cobrada": turno.sena_cobrada,
            "monto": str(_monto(cobro.monto)),
            "medio": movimiento.medio,
            "movimiento_id": str(movimiento.id),
            "cobro_mp_id": str(cobro.id),
            "origen": ORIGEN_WEBHOOK,
        },
    )


async def _aplicar_estado(
    session: AsyncSession,
    *,
    cobro: CobroMP,
    sena: Sena | None,
    turno: Turno | None,
    pago: PagoMP,
) -> None:
    """Mapea el estado de MP sobre `Sena`, `Turno` y `MovimientoCaja` (RN-PA-05)."""
    if pago.estado is EstadoMP.APPROVED:
        motivo = _motivo_discrepancia_aprobado(sena, turno, pago.monto, cobro.mp_payment_id)
        if motivo is not None or sena is None or turno is None:
            await _marcar_discrepancia(
                session,
                cobro=cobro,
                motivo=motivo or "No se pudo reconciliar el pago con la seña",
            )
            return
        await _confirmar_sena_con_pago(session, cobro=cobro, sena=sena, turno=turno)
        return

    if pago.estado is EstadoMP.REFUNDED:
        motivo = _motivo_discrepancia_refund(sena, turno)
        if motivo is not None or sena is None or turno is None:
            await _marcar_discrepancia(
                session,
                cobro=cobro,
                motivo=motivo or "No se pudo reconciliar la devolución con la seña",
            )
            return
        await _devolver_sena_por_refund(session, cobro=cobro, sena=sena, turno=turno)
        return

    if pago.estado is EstadoMP.PENDING:
        # Todavía no hay dinero: sigue pendiente para la conciliación periódica.
        cobro.estado_conciliacion = EstadoConciliacionMP.PENDIENTE.value
        return

    # `rejected` / `cancelled`: no acredita dinero, no hay nada que conciliar en caja.
    cobro.estado_conciliacion = EstadoConciliacionMP.CONCILIADO.value


async def procesar_webhook_mp(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    settings: Settings | None = None,
    cliente: MercadoPagoClient | None = None,
) -> ResultadoWebhookMP:
    """Procesa una notificación de MP ya autenticada, de forma estrictamente idempotente."""
    data = payload.get("data")
    detalle: dict[str, Any] = data if isinstance(data, dict) else {}
    payment_id = str(detalle.get("id") or "").strip()
    if not payment_id:
        raise EntidadInvalida("Che, la notificación de Mercado Pago no trae el id del pago.")

    externo = detalle.get("external_reference")
    existente = await _obtener_cobro_por_pago(session, payment_id)

    resuelto = await resolver_sena_por_external_reference(
        session, str(externo) if externo else None
    )
    if resuelto is None and existente is not None and existente.sena_id is not None:
        sena_existente = await session.get(Sena, existente.sena_id)
        if sena_existente is not None:
            resuelto = await resolver_sena_por_external_reference(session, str(sena_existente.id))

    sena = resuelto[0] if resuelto is not None else None
    turno = resuelto[1] if resuelto is not None else None
    monto_default = _monto(sena.monto) if sena is not None else CERO

    cfg = settings if settings is not None else None
    mp = cliente
    if mp is None and cfg is not None and cfg.mp_access_token:
        mp = MercadoPagoClient(access_token=cfg.mp_access_token)

    pago = await _resolver_pago(payment_id, payload, mp, monto_default)

    if existente is not None:
        if existente.estado_mp == pago.estado.value:
            return ResultadoWebhookMP(
                cobro=existente,
                duplicado=True,
                discrepancia=(
                    existente.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
                ),
            )
        if existente.estado_mp == EstadoMP.APPROVED.value and pago.estado is EstadoMP.REFUNDED:
            existente.estado_mp = EstadoMP.REFUNDED.value
            await _aplicar_estado(session, cobro=existente, sena=sena, turno=turno, pago=pago)
            await session.flush()
            return ResultadoWebhookMP(
                cobro=existente,
                discrepancia=(
                    existente.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
                ),
            )
        if existente.estado_mp == EstadoMP.PENDING.value:
            existente.estado_mp = pago.estado.value
            if pago.monto > CERO:
                existente.monto = pago.monto
            await _aplicar_estado(session, cobro=existente, sena=sena, turno=turno, pago=pago)
            await session.flush()
            return ResultadoWebhookMP(
                cobro=existente,
                discrepancia=(
                    existente.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value
                ),
            )
        # Transición no soportada (p. ej. approved -> pending): se ignora sin efectos.
        return ResultadoWebhookMP(cobro=existente, duplicado=True)

    # Sin seña resoluble no hay tenant ni datos que persistir (R4): MP recibe 200 igual.
    if resuelto is None or sena is None or turno is None:
        return ResultadoWebhookMP(ignorado=True)

    if pago.monto <= CERO:
        pago = replace(pago, monto=monto_default)

    cobro = CobroMP(
        id=uuid.uuid4(),
        tenant_id=sena.tenant_id,
        turno_id=turno.id,
        sena_id=sena.id,
        mp_payment_id=payment_id,
        mp_preference_id=pago.preference_id,
        monto=pago.monto,
        estado_mp=pago.estado.value,
        estado_conciliacion=EstadoConciliacionMP.PENDIENTE.value,
        payload=payload,
    )
    session.add(cobro)
    try:
        # D3: el payload crudo se persiste antes de evaluar la máquina de estados.
        await session.flush()
    except IntegrityError:
        # Race de reintentos en ráfaga: otro request ganó la unicidad de mp_payment_id.
        await session.rollback()
        existente = await _obtener_cobro_por_pago(session, payment_id)
        return ResultadoWebhookMP(cobro=existente, duplicado=True)

    await _aplicar_estado(session, cobro=cobro, sena=sena, turno=turno, pago=pago)
    await session.flush()
    return ResultadoWebhookMP(
        cobro=cobro,
        discrepancia=(cobro.estado_conciliacion == EstadoConciliacionMP.DISCREPANCIA.value),
    )


# ---------------------------------------------------------------------------
# Conciliación periódica y consultas administrativas (RN-PA-05)
# ---------------------------------------------------------------------------


async def conciliar_cobros(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    cliente: MercadoPagoClient | None = None,
) -> list[CobroMP]:
    """Recorre cobros `pendientes`, consulta MP y marca `conciliado` o `discrepancia`."""
    stmt = select(CobroMP).where(
        CobroMP.estado_conciliacion == EstadoConciliacionMP.PENDIENTE.value
    )
    if tenant_id is not None:
        stmt = stmt.where(CobroMP.tenant_id == tenant_id)
    stmt = stmt.order_by(CobroMP.created_at.asc(), CobroMP.id.asc())
    cobros = list((await session.execute(stmt)).scalars().all())

    for cobro in cobros:
        estado_raw: object = cobro.estado_mp
        monto = _monto(cobro.monto)
        if cliente is not None:
            consulta = await cliente.obtener_pago(cobro.mp_payment_id)
            estado_raw = consulta.get("status", estado_raw)
            monto = _a_decimal(consulta.get("transaction_amount"), monto)

        estado = _normalizar_estado(estado_raw)
        cobro.estado_mp = estado.value
        cobro.monto = _monto(monto)

        sena = await session.get(Sena, cobro.sena_id) if cobro.sena_id else None
        turno = await session.get(Turno, cobro.turno_id) if cobro.turno_id else None
        pago = PagoMP(
            payment_id=cobro.mp_payment_id,
            estado=estado,
            monto=_monto(monto),
            external_reference=str(sena.id) if sena is not None else None,
            preference_id=cobro.mp_preference_id,
        )
        await _aplicar_estado(session, cobro=cobro, sena=sena, turno=turno, pago=pago)

    await session.flush()
    return cobros


async def listar_cobros_mp(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
    estado_mp: EstadoMP | None = None,
    estado_conciliacion: EstadoConciliacionMP | None = None,
    limite: int = 100,
    offset: int = 0,
) -> list[CobroMP]:
    """Lista los cobros MP del tenant con filtros básicos de administración (R4)."""
    stmt = select(CobroMP).where(CobroMP.tenant_id == tenant_id)
    if sena_id is not None:
        stmt = stmt.where(CobroMP.sena_id == sena_id)
    if turno_id is not None:
        stmt = stmt.where(CobroMP.turno_id == turno_id)
    if estado_mp is not None:
        stmt = stmt.where(CobroMP.estado_mp == estado_mp.value)
    if estado_conciliacion is not None:
        stmt = stmt.where(CobroMP.estado_conciliacion == estado_conciliacion.value)
    stmt = stmt.order_by(CobroMP.created_at.desc(), CobroMP.id.asc()).limit(limite).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


def _motivo_actual(cobro: CobroMP, sena: Sena | None, turno: Turno | None) -> str:
    """Motivo visible de una discrepancia según el estado actual del cobro."""
    motivo: str | None = None
    if cobro.estado_mp == EstadoMP.APPROVED.value:
        motivo = _motivo_discrepancia_aprobado(
            sena, turno, _monto(cobro.monto), cobro.mp_payment_id
        )
    elif cobro.estado_mp == EstadoMP.REFUNDED.value:
        motivo = _motivo_discrepancia_refund(sena, turno)
    return motivo or "Discrepancia pendiente de revisión manual de recepción o dueño."


async def listar_discrepancias_mp(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
    limite: int = 100,
    offset: int = 0,
) -> list[tuple[CobroMP, str]]:
    """Lista cobros en `discrepancia` con su motivo derivado del estado actual."""
    cobros = await listar_cobros_mp(
        session,
        tenant_id=tenant_id,
        sena_id=sena_id,
        turno_id=turno_id,
        estado_conciliacion=EstadoConciliacionMP.DISCREPANCIA,
        limite=limite,
        offset=offset,
    )
    resultado: list[tuple[CobroMP, str]] = []
    for cobro in cobros:
        sena = await session.get(Sena, cobro.sena_id) if cobro.sena_id else None
        turno = await session.get(Turno, cobro.turno_id) if cobro.turno_id else None
        resultado.append((cobro, _motivo_actual(cobro, sena, turno)))
    return resultado
