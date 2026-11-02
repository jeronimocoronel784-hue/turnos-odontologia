"""Casos de uso de Señas y Caja diaria (C-11, US-030 / US-031).

Reglas implementadas:
- RN-PA-01: la seña vive atada al turno; el cobro habilita la confirmación del turno.
- RN-PA-02: reservar un turno de una prestación con `requiere_sena` genera la seña `pendiente`;
  el vencimiento impago cancela el turno y libera el slot (Flujo 1 paso 6).
- RN-PA-04: cancelación en término -> `devuelta`; fuera de término o inasistencia -> retenida
  (`aplicada`).
- RN-PA-05: todo cobro genera su `MovimientoCaja` conciliado y el cierre diario calcula
  `total_sistema`, `diferencia` y queda inmutable al cerrarse.
- R7: `movimiento_caja` es append-only y el cierre se reabre (nunca se borra) con auditoría.
- R8: todos los montos se calculan en servidor como `Decimal`; el cobro de seña es idempotente.
- RN-SE-01: la reapertura de caja deja un evento en `Auditoria` con `antes` y `despues`.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_caja import (
    CierreCajaAbrirInput,
    CierreCajaCerrarInput,
    CierreCajaReabrirInput,
    CobrarTurnoInput,
    LiquidacionTurnoRead,
    MovimientoCajaCreate,
    SenaCobrarInput,
    SenaCreate,
    SenaResolverCancelacionInput,
)
from app.application.auditoria import registrar_auditoria
from app.application.presupuestos import calcular_montos_item_presupuesto
from app.domain.caja import (
    CierreCaja,
    EstadoCierreCaja,
    EstadoSena,
    MovimientoCaja,
    Sena,
    TipoMovimientoCaja,
    es_transicion_sena_valida,
)
from app.domain.mixins import asegurar_utc
from app.domain.prestacion import Prestacion
from app.domain.tenant import Tenant
from app.domain.turno import ESTADOS_ACTIVOS_AGENDA, EstadoTurno, Turno
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

CERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")
HORAS_VENCIMIENTO_SENA_DEFAULT = 24
CANCELACION_HS_DEFAULT = 24
CONCEPTO_COBRO_SALDO = "Cobro de saldo de atención"


def _monto(valor: object) -> Decimal:
    """Normaliza cualquier monto persistido a `Decimal` con 2 decimales (R8)."""
    return Decimal(str(valor)).quantize(CENTAVOS)


# ---------------------------------------------------------------------------
# Señas: consulta y alta
# ---------------------------------------------------------------------------


async def listar_senas(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID | None = None,
    estado: EstadoSena | None = None,
) -> list[Sena]:
    """Lista las señas del consultorio filtrables por turno o estado."""
    stmt = select(Sena).where(Sena.tenant_id == tenant_id)
    if turno_id is not None:
        stmt = stmt.where(Sena.turno_id == turno_id)
    if estado is not None:
        stmt = stmt.where(Sena.estado == estado.value)
    stmt = stmt.order_by(Sena.created_at.asc(), Sena.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def obtener_sena(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID,
) -> Sena:
    """Busca una seña del tenant o levanta 404 (R4: nunca filtra datos de otro consultorio)."""
    sena = (
        await session.execute(select(Sena).where(Sena.id == sena_id, Sena.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if sena is None:
        raise NoEncontrado("Che, no encontramos esa seña en el consultorio.")
    return sena


async def _obtener_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
) -> Turno:
    turno = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos ese turno en el consultorio.")
    return turno


async def _obtener_prestacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID,
) -> Prestacion:
    prestacion = (
        await session.execute(
            select(Prestacion).where(
                Prestacion.id == prestacion_id,
                Prestacion.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if prestacion is None:
        raise NoEncontrado("Che, no encontramos la prestación del turno.")
    return prestacion


async def generar_sena_pendiente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno: Turno,
    prestacion: Prestacion,
    actor_id: uuid.UUID | None = None,
    vence_at: datetime | None = None,
) -> Sena:
    """Crea la seña `pendiente` del turno con el monto de la prestación (RN-PA-02, R8)."""
    if not prestacion.requiere_sena or prestacion.monto_sena is None:
        raise EntidadInvalida(
            "Che, esta prestación no exige seña: no hay monto de seña para cobrar."
        )

    existente = (
        await session.execute(select(Sena).where(Sena.turno_id == turno.id))
    ).scalar_one_or_none()
    if existente is not None:
        raise Conflicto("Che, este turno ya tiene una seña registrada.")

    ahora = datetime.now(UTC)
    vencimiento = (
        vence_at
        if vence_at is not None
        else ahora + timedelta(hours=HORAS_VENCIMIENTO_SENA_DEFAULT)
    )

    sena = Sena(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        turno_id=turno.id,
        monto=_monto(prestacion.monto_sena),
        estado=EstadoSena.PENDIENTE.value,
        vence_at=asegurar_utc(vencimiento),
    )
    session.add(sena)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="sena.crear",
        entidad="sena",
        entidad_id=str(sena.id),
        despues={
            "turno_id": str(turno.id),
            "estado": sena.estado,
            "monto": str(_monto(sena.monto)),
            "vence_at": sena.vence_at.isoformat() if sena.vence_at else None,
        },
    )
    return sena


async def crear_sena(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: SenaCreate,
    actor_id: uuid.UUID | None = None,
) -> Sena:
    """Genera la seña `pendiente` de un turno con el monto de la prestación (RN-PA-02, R8)."""
    turno = await _obtener_turno(session, tenant_id=tenant_id, turno_id=datos.turno_id)
    prestacion = await _obtener_prestacion(
        session, tenant_id=tenant_id, prestacion_id=turno.prestacion_id
    )
    return await generar_sena_pendiente(
        session,
        tenant_id=tenant_id,
        turno=turno,
        prestacion=prestacion,
        actor_id=actor_id,
        vence_at=datos.vence_at,
    )


# ---------------------------------------------------------------------------
# Señas: cobro y resolución
# ---------------------------------------------------------------------------


async def _cierre_abierto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> CierreCaja | None:
    """Devuelve el cierre abierto vigente del consultorio (el más reciente por fecha)."""
    return (
        await session.execute(
            select(CierreCaja)
            .where(
                CierreCaja.tenant_id == tenant_id,
                CierreCaja.estado == EstadoCierreCaja.ABIERTO.value,
            )
            .order_by(CierreCaja.fecha.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _registrar_ingreso(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    concepto: str,
    medio: str,
    monto: Decimal,
    actor_id: uuid.UUID,
    turno_id: uuid.UUID | None = None,
    sena_id: uuid.UUID | None = None,
) -> MovimientoCaja:
    """Crea el movimiento de ingreso y lo asocia al cierre abierto vigente (RN-PA-05, D3)."""
    cierre = await _cierre_abierto(session, tenant_id=tenant_id)
    movimiento = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tipo=TipoMovimientoCaja.INGRESO.value,
        concepto=concepto,
        medio=medio,
        monto=_monto(monto),
        turno_id=turno_id,
        sena_id=sena_id,
        cierre_id=cierre.id if cierre is not None else None,
        created_by=actor_id,
    )
    session.add(movimiento)
    await session.flush()
    return movimiento


async def cobrar_sena(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID,
    datos: SenaCobrarInput,
    actor_id: uuid.UUID,
) -> Sena:
    """Cobra la seña, habilita la confirmación del turno y registra el ingreso (RN-PA-01/05)."""
    sena = await obtener_sena(session, tenant_id=tenant_id, sena_id=sena_id)

    # R8: reintentar el cobro de una seña ya cobrada no duplica el movimiento.
    if sena.estado == EstadoSena.COBRADA.value:
        return sena

    if not es_transicion_sena_valida(sena.estado, EstadoSena.COBRADA):
        raise EntidadInvalida(f"Che, no se puede cobrar una seña en estado '{sena.estado}'.")

    turno = await _obtener_turno(session, tenant_id=tenant_id, turno_id=sena.turno_id)

    antes: dict[str, object] = {"estado": sena.estado, "sena_cobrada": turno.sena_cobrada}
    sena.estado = EstadoSena.COBRADA.value
    turno.sena_cobrada = True
    await session.flush()

    movimiento = await _registrar_ingreso(
        session,
        tenant_id=tenant_id,
        concepto="Cobro de seña",
        medio=datos.medio.value,
        monto=_monto(sena.monto),
        actor_id=actor_id,
        turno_id=turno.id,
        sena_id=sena.id,
    )

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="sena.cobrar",
        entidad="sena",
        entidad_id=str(sena.id),
        antes=antes,
        despues={
            "estado": sena.estado,
            "sena_cobrada": turno.sena_cobrada,
            "monto": str(_monto(sena.monto)),
            "medio": movimiento.medio,
            "movimiento_id": str(movimiento.id),
            "cierre_id": str(movimiento.cierre_id) if movimiento.cierre_id else None,
        },
    )
    return sena


async def _cancelacion_hs(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Anticipación mínima de cancelación configurada en el consultorio (RN-AG-05)."""
    tenant = await session.get(Tenant, tenant_id)
    politicas = (tenant.politicas if tenant and isinstance(tenant.politicas, dict) else {}) or {}
    raw_hs = politicas.get("cancelacion_hs", CANCELACION_HS_DEFAULT)
    return raw_hs if isinstance(raw_hs, int) else CANCELACION_HS_DEFAULT


async def resolver_sena_por_cancelacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID,
    datos: SenaResolverCancelacionInput,
    actor_id: uuid.UUID,
    ahora: datetime | None = None,
) -> Sena:
    """Resuelve la seña al cancelar el turno según la política de cancelación (RN-PA-04).

    - Seña impaga (`pendiente`): se libera como `devuelta` (no había dinero a retener).
    - Seña `cobrada` + cancelación en término: se devuelve (`devuelta`).
    - Seña `cobrada` + fuera de término o inasistencia: se retiene (`aplicada`).
    """
    sena = await obtener_sena(session, tenant_id=tenant_id, sena_id=sena_id)
    turno = await _obtener_turno(session, tenant_id=tenant_id, turno_id=sena.turno_id)

    if sena.estado == EstadoSena.PENDIENTE.value:
        destino = EstadoSena.DEVUELTA
    elif sena.estado == EstadoSena.COBRADA.value:
        ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)
        horas_anticipacion = (asegurar_utc(turno.inicio) - ahora_utc).total_seconds() / 3600
        en_termino = not datos.ausente and horas_anticipacion >= await _cancelacion_hs(
            session, tenant_id
        )
        destino = EstadoSena.DEVUELTA if en_termino else EstadoSena.APLICADA
    else:
        raise EntidadInvalida(f"Che, no se puede resolver una seña en estado '{sena.estado}'.")

    if not es_transicion_sena_valida(sena.estado, destino):
        raise EntidadInvalida(
            f"Che, no se puede pasar la seña de '{sena.estado}' a '{destino.value}'."
        )

    antes: dict[str, object] = {"estado": sena.estado, "sena_cobrada": turno.sena_cobrada}
    sena.estado = destino.value
    if destino is EstadoSena.DEVUELTA:
        # La seña devuelta deja de estar acreditada para confirmar el turno (RN-PA-01).
        turno.sena_cobrada = False
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="sena.resolver_cancelacion",
        entidad="sena",
        entidad_id=str(sena.id),
        antes=antes,
        despues={
            "estado": sena.estado,
            "sena_cobrada": turno.sena_cobrada,
            "ausente": datos.ausente,
            "motivo": datos.motivo,
        },
    )
    return sena


async def vencer_sena_impaga(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sena_id: uuid.UUID,
    ahora: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> Sena:
    """Vence la seña impaga y cancela el turno, liberando el slot (Flujo 1 paso 6)."""
    from app.application.agenda import cambiar_estado_turno

    sena = await obtener_sena(session, tenant_id=tenant_id, sena_id=sena_id)
    if sena.estado != EstadoSena.PENDIENTE.value:
        raise EntidadInvalida(
            f"Che, solo vence una seña impaga: esta está en estado '{sena.estado}'."
        )

    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)
    if sena.vence_at is not None and asegurar_utc(sena.vence_at) > ahora_utc:
        raise EntidadInvalida("Che, esta seña todavía no venció: esperá a su vencimiento.")

    if not es_transicion_sena_valida(sena.estado, EstadoSena.VENCIDA):
        raise EntidadInvalida(f"Che, no se puede vencer una seña en estado '{sena.estado}'.")

    turno = await _obtener_turno(session, tenant_id=tenant_id, turno_id=sena.turno_id)

    antes: dict[str, object] = {"estado": sena.estado, "turno_estado": turno.estado}
    sena.estado = EstadoSena.VENCIDA.value
    await session.flush()

    # El turno sólo se cancela si seguía activo; cambiar_estado_turno libera el slot y
    # dispara la oferta a la lista de espera (RN-LE-01).
    if EstadoTurno(turno.estado) in ESTADOS_ACTIVOS_AGENDA:
        await cambiar_estado_turno(
            session,
            tenant_id=tenant_id,
            turno_id=turno.id,
            nuevo_estado=EstadoTurno.CANCELADO,
            motivo_cancelacion="Seña impaga vencida",
            actor_id=actor_id,
        )

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="sena.vencer",
        entidad="sena",
        entidad_id=str(sena.id),
        antes=antes,
        despues={"estado": sena.estado, "turno_estado": turno.estado},
    )
    return sena


# ---------------------------------------------------------------------------
# Liquidación del turno (Flujo 4)
# ---------------------------------------------------------------------------


async def calcular_liquidacion_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    obra_social: str | None = None,
    fecha_referencia: date | None = None,
) -> LiquidacionTurnoRead:
    """Calcula en servidor `saldo = max(0, precio - cobertura_os - sena_cobrada)` (R8)."""
    turno = await _obtener_turno(session, tenant_id=tenant_id, turno_id=turno_id)
    precio_unit, cobertura_os, _ = await calcular_montos_item_presupuesto(
        session,
        tenant_id=tenant_id,
        prestacion_id=turno.prestacion_id,
        cantidad=1,
        obra_social=obra_social,
        fecha_referencia=fecha_referencia,
    )

    sena = (
        await session.execute(
            select(Sena).where(
                Sena.turno_id == turno.id,
                Sena.estado.in_([EstadoSena.COBRADA.value, EstadoSena.APLICADA.value]),
            )
        )
    ).scalar_one_or_none()
    sena_cobrada = _monto(sena.monto) if sena is not None else CERO

    saldo = max(CERO, _monto(precio_unit - cobertura_os - sena_cobrada))
    return LiquidacionTurnoRead(
        turno_id=turno.id,
        precio_particular=_monto(precio_unit),
        cobertura_os=_monto(cobertura_os),
        sena_cobrada=sena_cobrada,
        saldo=saldo,
        obra_social=obra_social,
    )


async def cobrar_saldo_turno(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    datos: CobrarTurnoInput,
    actor_id: uuid.UUID,
    fecha_referencia: date | None = None,
) -> MovimientoCaja:
    """Cobra el saldo de la atención y aplica la seña cobrada (Flujo 4, RN-PA-05)."""
    liquidacion = await calcular_liquidacion_turno(
        session,
        tenant_id=tenant_id,
        turno_id=turno_id,
        obra_social=datos.obra_social,
        fecha_referencia=fecha_referencia,
    )
    if liquidacion.saldo <= CERO:
        raise Conflicto(
            "Che, este turno no tiene saldo pendiente: ya está cubierto por la cobertura y la seña."
        )

    # R8: idempotencia del cobro. El modelo v1 no guarda un flag `saldo_cobrado` en el turno,
    # así que el movimiento de saldo ya registrado es la evidencia de que la atención se cobró.
    ya_cobrado = (
        (
            await session.execute(
                select(MovimientoCaja).where(
                    MovimientoCaja.tenant_id == tenant_id,
                    MovimientoCaja.turno_id == turno_id,
                    MovimientoCaja.tipo == TipoMovimientoCaja.INGRESO.value,
                    MovimientoCaja.concepto == CONCEPTO_COBRO_SALDO,
                )
            )
        )
        .scalars()
        .first()
    )
    if ya_cobrado is not None:
        raise Conflicto(
            "Che, el saldo de este turno ya se cobró. Si necesitás corregirlo, "
            "registrá un ajuste de caja con el dueño."
        )

    movimiento = await _registrar_ingreso(
        session,
        tenant_id=tenant_id,
        concepto=CONCEPTO_COBRO_SALDO,
        medio=datos.medio.value,
        monto=liquidacion.saldo,
        actor_id=actor_id,
        turno_id=turno_id,
    )

    sena = (
        await session.execute(
            select(Sena).where(
                Sena.turno_id == turno_id,
                Sena.tenant_id == tenant_id,
                Sena.estado == EstadoSena.COBRADA.value,
            )
        )
    ).scalar_one_or_none()
    sena_aplicada = False
    if sena is not None and es_transicion_sena_valida(sena.estado, EstadoSena.APLICADA):
        sena.estado = EstadoSena.APLICADA.value
        sena_aplicada = True
        await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="caja.cobrar_saldo_turno",
        entidad="turno",
        entidad_id=str(turno_id),
        despues={
            "precio_particular": str(liquidacion.precio_particular),
            "cobertura_os": str(liquidacion.cobertura_os),
            "sena_cobrada": str(liquidacion.sena_cobrada),
            "saldo": str(liquidacion.saldo),
            "medio": movimiento.medio,
            "movimiento_id": str(movimiento.id),
            "sena_aplicada": sena_aplicada,
        },
    )
    return movimiento


# ---------------------------------------------------------------------------
# Caja diaria: apertura, movimientos, cierre y reapertura
# ---------------------------------------------------------------------------


async def obtener_cierre(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cierre_id: uuid.UUID,
) -> CierreCaja:
    """Busca un cierre de caja del tenant o levanta 404."""
    cierre = (
        await session.execute(
            select(CierreCaja).where(
                CierreCaja.id == cierre_id,
                CierreCaja.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if cierre is None:
        raise NoEncontrado("Che, no encontramos ese cierre de caja.")
    return cierre


async def listar_cierres(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fecha: date | None = None,
    estado: EstadoCierreCaja | None = None,
) -> list[CierreCaja]:
    """Lista los cierres del consultorio, opcionalmente por fecha o estado."""
    stmt = select(CierreCaja).where(CierreCaja.tenant_id == tenant_id)
    if fecha is not None:
        stmt = stmt.where(CierreCaja.fecha == fecha)
    if estado is not None:
        stmt = stmt.where(CierreCaja.estado == estado.value)
    stmt = stmt.order_by(CierreCaja.fecha.desc(), CierreCaja.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def abrir_cierre_caja(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: CierreCajaAbrirInput,
    actor_id: uuid.UUID,
) -> CierreCaja:
    """Abre el cierre diario: uno por fecha y consultorio (D3)."""
    existente = (
        await session.execute(
            select(CierreCaja).where(
                CierreCaja.tenant_id == tenant_id,
                CierreCaja.fecha == datos.fecha,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        raise Conflicto("Che, ya hay un cierre de caja para esa fecha en este consultorio.")

    cierre = CierreCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        fecha=datos.fecha,
        total_sistema=CERO,
        estado=EstadoCierreCaja.ABIERTO.value,
        abierto_por=actor_id,
    )
    session.add(cierre)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="caja.abrir",
        entidad="cierre_caja",
        entidad_id=str(cierre.id),
        despues={"fecha": cierre.fecha.isoformat(), "estado": cierre.estado},
    )
    return cierre


async def registrar_movimiento_caja(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: MovimientoCajaCreate,
    actor_id: uuid.UUID,
) -> MovimientoCaja:
    """Registra un movimiento append-only asociado al cierre abierto vigente (RN-PA-05, R7)."""
    if datos.turno_id is not None:
        await _obtener_turno(session, tenant_id=tenant_id, turno_id=datos.turno_id)
    if datos.sena_id is not None:
        await obtener_sena(session, tenant_id=tenant_id, sena_id=datos.sena_id)

    cierre = await _cierre_abierto(session, tenant_id=tenant_id)
    movimiento = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tipo=datos.tipo.value,
        concepto=datos.concepto,
        medio=datos.medio.value,
        monto=_monto(datos.monto),
        turno_id=datos.turno_id,
        sena_id=datos.sena_id,
        cierre_id=cierre.id if cierre is not None else None,
        created_by=actor_id,
    )
    session.add(movimiento)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="caja.registrar_movimiento",
        entidad="movimiento_caja",
        entidad_id=str(movimiento.id),
        despues={
            "tipo": movimiento.tipo,
            "concepto": movimiento.concepto,
            "medio": movimiento.medio,
            "monto": str(_monto(movimiento.monto)),
            "cierre_id": str(movimiento.cierre_id) if movimiento.cierre_id else None,
        },
    )
    return movimiento


async def listar_movimientos(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cierre_id: uuid.UUID | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> list[MovimientoCaja]:
    """Lista los movimientos del consultorio (append-only) con filtros de conciliación."""
    stmt = select(MovimientoCaja).where(MovimientoCaja.tenant_id == tenant_id)
    if cierre_id is not None:
        stmt = stmt.where(MovimientoCaja.cierre_id == cierre_id)
    if desde is not None:
        stmt = stmt.where(MovimientoCaja.created_at >= asegurar_utc(desde))
    if hasta is not None:
        stmt = stmt.where(MovimientoCaja.created_at <= asegurar_utc(hasta))
    stmt = stmt.order_by(MovimientoCaja.created_at.asc(), MovimientoCaja.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def _total_sistema_cierre(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cierre_id: uuid.UUID,
) -> Decimal:
    """`total_sistema = ingresos - egresos` de los movimientos del cierre (RN-PA-05)."""

    async def _suma(tipo: TipoMovimientoCaja) -> Decimal:
        total = await session.scalar(
            select(func.coalesce(func.sum(MovimientoCaja.monto), 0)).where(
                MovimientoCaja.tenant_id == tenant_id,
                MovimientoCaja.cierre_id == cierre_id,
                MovimientoCaja.tipo == tipo.value,
            )
        )
        return _monto(total if total is not None else 0)

    return _monto(await _suma(TipoMovimientoCaja.INGRESO) - await _suma(TipoMovimientoCaja.EGRESO))


async def cerrar_caja(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cierre_id: uuid.UUID,
    datos: CierreCajaCerrarInput,
    actor_id: uuid.UUID,
) -> CierreCaja:
    """Cierra la caja fijando `total_sistema` y `diferencia = contado - sistema` (RN-PA-05)."""
    cierre = await obtener_cierre(session, tenant_id=tenant_id, cierre_id=cierre_id)
    if cierre.estado == EstadoCierreCaja.CERRADO.value:
        raise Conflicto(
            "Che, este cierre de caja ya está cerrado y es inmutable. "
            "Si necesitás corregirlo, el dueño tiene que reabrirlo con un motivo."
        )

    total_sistema = await _total_sistema_cierre(session, tenant_id=tenant_id, cierre_id=cierre.id)
    total_contado = _monto(datos.total_contado)
    diferencia = _monto(total_contado - total_sistema)

    antes: dict[str, object] = {
        "estado": cierre.estado,
        "total_sistema": str(_monto(cierre.total_sistema)),
    }
    cierre.total_sistema = total_sistema
    cierre.total_contado = total_contado
    cierre.diferencia = diferencia
    cierre.estado = EstadoCierreCaja.CERRADO.value
    cierre.cerrado_por = actor_id
    cierre.cerrado_at = datetime.now(UTC)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="caja.cerrar",
        entidad="cierre_caja",
        entidad_id=str(cierre.id),
        antes=antes,
        despues={
            "estado": cierre.estado,
            "total_sistema": str(total_sistema),
            "total_contado": str(total_contado),
            "diferencia": str(diferencia),
        },
    )
    return cierre


async def reabrir_caja(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cierre_id: uuid.UUID,
    datos: CierreCajaReabrirInput,
    actor_id: uuid.UUID,
) -> CierreCaja:
    """Reabre un cierre cerrado dejando el motivo y el diff en `Auditoria` (RN-SE-01)."""
    cierre = await obtener_cierre(session, tenant_id=tenant_id, cierre_id=cierre_id)
    if cierre.estado != EstadoCierreCaja.CERRADO.value:
        raise EntidadInvalida("Che, solo se puede reabrir un cierre de caja cerrado.")

    antes: dict[str, object] = {
        "estado": cierre.estado,
        "total_sistema": str(_monto(cierre.total_sistema)),
        "total_contado": (
            str(_monto(cierre.total_contado)) if cierre.total_contado is not None else None
        ),
        "diferencia": str(_monto(cierre.diferencia)) if cierre.diferencia is not None else None,
        "cerrado_por": str(cierre.cerrado_por) if cierre.cerrado_por else None,
        "cerrado_at": cierre.cerrado_at.isoformat() if cierre.cerrado_at else None,
    }

    # R7: nunca se borra el cierre; se reabre y el snapshot queda en la auditoría.
    cierre.estado = EstadoCierreCaja.ABIERTO.value
    cierre.reabierto_motivo = datos.motivo
    cierre.cerrado_por = None
    cierre.cerrado_at = None
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="caja.reabrir_cierre",
        entidad="cierre_caja",
        entidad_id=str(cierre.id),
        antes=antes,
        despues={
            "estado": cierre.estado,
            "motivo": datos.motivo,
            "total_sistema": str(_monto(cierre.total_sistema)),
        },
    )
    return cierre
