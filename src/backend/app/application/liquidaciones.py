"""Casos de uso de liquidaciones mensuales a obras sociales (C-13, US-041).

Reglas implementadas:
- RN-OS-02: un turno vive en una sola liquidación abierta por OS/período; el índice parcial
  de `liquidacion_detalle` es la última garantía y el caso de uso rechaza antes con 409.
- US-041: los débitos se informan por turno con motivo y los totales se recalculan en servidor.
- R7: la baja de un borrador es lógica (`anulada`); nunca se borra una liquidación ni su detalle.
- R8: todos los montos son `Decimal` calculados acá; ningún total llega desde el cliente.
- R9 / RN-SE-01: la auditoría guarda IDs y montos, nunca datos personales del paciente.
- D2/D4/D5/D6: cobertura con arancel vencido congelado por turno, grafo cerrado de estados,
  membresía derivada del período y complementarias avisadas.

Notas de diseño:
- La cobertura se resuelve por día de atención (D1): `resolver_coberturas_lote` se invoca una
  vez por fecha distinta del período, así un arancel cargado a mitad de mes no se aplica
  retroactivamente y no hay N+1 por turno.
- `turnos_sin_cobertura` y `advertencias` son resultado del alta (no columnas del modelo, por
  diseño §Modelo de datos); al releer se derivan del snapshot `arancel_vencido` del detalle.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_liquidaciones import (
    LiquidacionOSAnularInput,
    LiquidacionOSCerrarInput,
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleRead,
    LiquidacionOSRead,
    ResultadoOSInput,
)
from app.application.auditoria import registrar_auditoria
from app.application.cobertura import resolver_coberturas_lote
from app.domain.cobertura_os import EstadoArancel, ResolucionCobertura
from app.domain.liquidacion_os import (
    EstadoLiquidacionOS,
    LiquidacionOS,
    LiquidacionOSDetalle,
    es_transicion_liquidacion_valida,
    rango_periodo,
)
from app.domain.mixins import asegurar_utc
from app.domain.prestacion import Prestacion
from app.domain.turno import EstadoTurno, Turno
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

CERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")

ADVERTENCIA_COMPLEMENTARIA = (
    "El período ya tiene una liquidación pagada para esta obra social: "
    "esta liquidación se tratará como complementaria."
)
ADVERTENCIA_ARANCEL_VENCIDO = (
    "Hay turnos liquidados con arancel vencido: revisalos con la obra social antes de presentar."
)


def _monto(valor: object) -> Decimal:
    """Normaliza cualquier monto a `Decimal` con 2 decimales (R8: nunca float)."""
    return Decimal(str(valor)).quantize(CENTAVOS)


def _agregar_advertencia(advertencias: list[str], mensaje: str | None) -> None:
    """Agrega una advertencia sin repetirla, conservando el orden de aparición."""
    if mensaje and mensaje not in advertencias:
        advertencias.append(mensaje)


async def obtener_liquidacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
) -> LiquidacionOS:
    """Busca una liquidación del tenant o levanta 404 (R4)."""
    liquidacion = (
        await session.execute(
            select(LiquidacionOS).where(
                LiquidacionOS.id == liquidacion_id,
                LiquidacionOS.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if liquidacion is None:
        raise NoEncontrado("Che, no encontramos esa liquidación en el consultorio.")
    return liquidacion


async def _detalles_de(
    session: AsyncSession, liquidacion: LiquidacionOS
) -> list[LiquidacionOSDetalle]:
    """Detalle de la liquidación dentro del tenant, en orden estable (R4)."""
    filas = (
        (
            await session.execute(
                select(LiquidacionOSDetalle)
                .where(
                    LiquidacionOSDetalle.tenant_id == liquidacion.tenant_id,
                    LiquidacionOSDetalle.liquidacion_id == liquidacion.id,
                )
                .order_by(LiquidacionOSDetalle.created_at.asc(), LiquidacionOSDetalle.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(filas)


async def _armar_read(
    session: AsyncSession,
    liquidacion: LiquidacionOS,
    *,
    turnos_sin_cobertura: int = 0,
    advertencias: list[str] | None = None,
) -> LiquidacionOSRead:
    """Arma la respuesta con cabecera, detalle por turno y totales persistidos (R1, R8)."""
    detalles = await _detalles_de(session, liquidacion)

    turnos: dict[uuid.UUID, Turno] = {}
    prestaciones: dict[uuid.UUID, Prestacion] = {}
    if detalles:
        turnos = {
            turno.id: turno
            for turno in (
                (
                    await session.execute(
                        select(Turno).where(
                            Turno.tenant_id == liquidacion.tenant_id,
                            Turno.id.in_([detalle.turno_id for detalle in detalles]),
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        if turnos:
            prestaciones = {
                prestacion.id: prestacion
                for prestacion in (
                    (
                        await session.execute(
                            select(Prestacion).where(
                                Prestacion.tenant_id == liquidacion.tenant_id,
                                Prestacion.id.in_(
                                    {turno.prestacion_id for turno in turnos.values()}
                                ),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            }

    filas: list[LiquidacionOSDetalleRead] = []
    for detalle in detalles:
        turno = turnos.get(detalle.turno_id)
        if turno is None:  # pragma: no cover - la FK RESTRICT garantiza el turno
            continue
        prestacion = prestaciones.get(turno.prestacion_id)
        filas.append(
            LiquidacionOSDetalleRead(
                id=detalle.id,
                turno_id=detalle.turno_id,
                fecha_turno=asegurar_utc(turno.inicio),
                prestacion=prestacion.nombre if prestacion is not None else "Sin prestación",
                monto_reclamado=_monto(detalle.monto_reclamado),
                monto_reconocido=(
                    _monto(detalle.monto_reconocido)
                    if detalle.monto_reconocido is not None
                    else None
                ),
                debito_motivo=detalle.debito_motivo,
                arancel_vencido=detalle.arancel_vencido,
                vigente=detalle.vigente,
            )
        )
    filas.sort(key=lambda fila: (fila.fecha_turno, str(fila.id)))

    if advertencias is None:
        advertencias = []
        if any(fila.arancel_vencido for fila in filas):
            _agregar_advertencia(advertencias, ADVERTENCIA_ARANCEL_VENCIDO)

    return LiquidacionOSRead(
        id=liquidacion.id,
        tenant_id=liquidacion.tenant_id,
        obra_social=liquidacion.obra_social,
        periodo=liquidacion.periodo,
        estado=EstadoLiquidacionOS(liquidacion.estado),
        total=_monto(liquidacion.total),
        total_reconocido=(
            _monto(liquidacion.total_reconocido)
            if liquidacion.total_reconocido is not None
            else None
        ),
        observaciones=liquidacion.observaciones,
        presentada_por=liquidacion.presentada_por,
        presentada_at=liquidacion.presentada_at,
        resuelta_por=liquidacion.resuelta_por,
        resuelta_at=liquidacion.resuelta_at,
        anulada_motivo=liquidacion.anulada_motivo,
        created_by=liquidacion.created_by,
        created_at=liquidacion.created_at,
        updated_at=liquidacion.updated_at,
        turnos_sin_cobertura=turnos_sin_cobertura,
        advertencias=advertencias,
        detalles=filas,
    )


async def _resolver_coberturas_por_dia(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turnos: list[Turno],
    obra_social: str,
) -> dict[tuple[uuid.UUID, date], ResolucionCobertura]:
    """Resuelve la cobertura de cada prestación por el día de atención (D1, D2)."""
    por_dia: dict[date, set[uuid.UUID]] = {}
    for turno in turnos:
        por_dia.setdefault(asegurar_utc(turno.inicio).date(), set()).add(turno.prestacion_id)

    resoluciones: dict[tuple[uuid.UUID, date], ResolucionCobertura] = {}
    for fecha, prestacion_ids in por_dia.items():
        lote = await resolver_coberturas_lote(
            session,
            tenant_id=tenant_id,
            prestacion_ids=prestacion_ids,
            obra_social=obra_social,
            fecha_referencia=fecha,
        )
        for prestacion_id, resolucion in lote.items():
            resoluciones[(prestacion_id, fecha)] = resolucion
    return resoluciones


async def generar_borrador(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: LiquidacionOSCreate,
    actor_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Alta del borrador con los turnos `finalizado` del período (D5, RN-OS-02)."""
    obra_social = datos.obra_social.strip()
    if not obra_social:
        raise EntidadInvalida("Che, la liquidación tiene que indicar la obra social.")

    # 422 si el período no es `yyyymm`; el schema ya lo valida y el dominio lo reafirma.
    desde, hasta = rango_periodo(datos.periodo)

    borrador_existente = (
        await session.execute(
            select(LiquidacionOS).where(
                LiquidacionOS.tenant_id == tenant_id,
                func.lower(LiquidacionOS.obra_social) == obra_social.lower(),
                LiquidacionOS.periodo == datos.periodo,
                LiquidacionOS.estado == EstadoLiquidacionOS.BORRADOR.value,
            )
        )
    ).scalar_one_or_none()
    if borrador_existente is not None:
        raise Conflicto(
            "Che, ya hay un borrador de esa obra social para ese período. "
            "Anulá ese borrador si necesitás regenerarlo."
        )

    turnos = list(
        (
            await session.execute(
                select(Turno)
                .where(
                    Turno.tenant_id == tenant_id,
                    Turno.estado == EstadoTurno.FINALIZADO.value,
                    Turno.inicio >= desde,
                    Turno.inicio < hasta,
                )
                .order_by(Turno.inicio.asc(), Turno.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not turnos:
        raise EntidadInvalida(
            f"Che, no hay turnos finalizados en el período {datos.periodo} "
            "para liquidar a la obra social."
        )

    coberturas = await _resolver_coberturas_por_dia(
        session, tenant_id=tenant_id, turnos=turnos, obra_social=obra_social
    )

    advertencias: list[str] = []
    sin_cobertura = 0
    incluidos: list[tuple[Turno, ResolucionCobertura]] = []
    for turno in turnos:
        fecha = asegurar_utc(turno.inicio).date()
        resolucion = coberturas.get((turno.prestacion_id, fecha))
        if resolucion is None or resolucion.estado_arancel is EstadoArancel.SIN_COBERTURA:
            sin_cobertura += 1
            if resolucion is not None:
                _agregar_advertencia(advertencias, resolucion.advertencia)
            continue
        incluidos.append((turno, resolucion))
        _agregar_advertencia(advertencias, resolucion.advertencia)

    if not incluidos:
        raise EntidadInvalida(
            f"Che, no hay turnos finalizados con convenio de {obra_social} "
            f"en el período {datos.periodo}."
        )

    ya_liquidados = list(
        (
            await session.execute(
                select(LiquidacionOSDetalle.turno_id).where(
                    LiquidacionOSDetalle.tenant_id == tenant_id,
                    LiquidacionOSDetalle.turno_id.in_([turno.id for turno, _ in incluidos]),
                    func.lower(LiquidacionOSDetalle.obra_social) == obra_social.lower(),
                    LiquidacionOSDetalle.periodo == datos.periodo,
                    LiquidacionOSDetalle.vigente.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if ya_liquidados:
        raise Conflicto(
            "Che, hay turnos que ya están en otra liquidación abierta de esa obra social "
            "para ese período."
        )

    periodo_pagado = (
        await session.execute(
            select(LiquidacionOS.id)
            .where(
                LiquidacionOS.tenant_id == tenant_id,
                func.lower(LiquidacionOS.obra_social) == obra_social.lower(),
                LiquidacionOS.periodo == datos.periodo,
                LiquidacionOS.estado == EstadoLiquidacionOS.PAGADA.value,
            )
            .limit(1)
        )
    ).first()
    if periodo_pagado is not None:
        advertencias.insert(0, ADVERTENCIA_COMPLEMENTARIA)

    total = _monto(sum((resolucion.cobertura for _, resolucion in incluidos), CERO))
    liquidacion = LiquidacionOS(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        obra_social=obra_social,
        periodo=datos.periodo,
        estado=EstadoLiquidacionOS.BORRADOR.value,
        total=total,
        created_by=actor_id,
    )
    session.add(liquidacion)
    await session.flush()

    session.add_all(
        [
            LiquidacionOSDetalle(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                liquidacion_id=liquidacion.id,
                turno_id=turno.id,
                obra_social=obra_social,
                periodo=datos.periodo,
                monto_reclamado=_monto(resolucion.cobertura),
                arancel_vencido=resolucion.arancel_vencido,
                vigente=True,
            )
            for turno, resolucion in incluidos
        ]
    )
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="liquidacion.crear",
        entidad="liquidacion_os",
        entidad_id=str(liquidacion.id),
        despues={
            "estado": liquidacion.estado,
            "obra_social": obra_social,
            "periodo": datos.periodo,
            "total": str(total),
            "turnos": len(incluidos),
            "turnos_sin_cobertura": sin_cobertura,
        },
    )
    return await _armar_read(
        session,
        liquidacion,
        turnos_sin_cobertura=sin_cobertura,
        advertencias=advertencias,
    )


def _snapshot_liquidacion(
    liquidacion: LiquidacionOS, detalles: list[LiquidacionOSDetalle]
) -> dict[str, object]:
    """Foto mínima para la auditoría: estado, totales y montos por `turno_id` (R9)."""
    return {
        "estado": liquidacion.estado,
        "total": str(_monto(liquidacion.total)),
        "total_reconocido": (
            str(_monto(liquidacion.total_reconocido))
            if liquidacion.total_reconocido is not None
            else None
        ),
        "detalles": {
            str(detalle.turno_id): {
                "monto_reclamado": str(_monto(detalle.monto_reclamado)),
                "monto_reconocido": (
                    str(_monto(detalle.monto_reconocido))
                    if detalle.monto_reconocido is not None
                    else None
                ),
                "debito_motivo": detalle.debito_motivo,
            }
            for detalle in detalles
        },
    }


async def _recalcular_totales(session: AsyncSession, liquidacion: LiquidacionOS) -> None:
    """Recalcula en servidor `total` y `total_reconocido` desde el detalle persistido (R8)."""
    detalles = await _detalles_de(session, liquidacion)
    total = _monto(sum((_monto(detalle.monto_reclamado) for detalle in detalles), CERO))
    reconocidos = [
        _monto(detalle.monto_reconocido)
        for detalle in detalles
        if detalle.monto_reconocido is not None
    ]
    liquidacion.total = total
    liquidacion.total_reconocido = _monto(sum(reconocidos, CERO)) if reconocidos else None
    await session.flush()


async def registrar_debitos(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    datos: LiquidacionOSDebitosInput,
    actor_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Registra los reconocidos por turno sobre un borrador y recalcula totales (US-041)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    if liquidacion.estado != EstadoLiquidacionOS.BORRADOR.value:
        raise Conflicto(
            f"Che, sólo se editan débitos de un borrador: esta liquidación está en "
            f"estado '{liquidacion.estado}'."
        )

    detalles = await _detalles_de(session, liquidacion)
    por_turno = {detalle.turno_id: detalle for detalle in detalles}
    antes = _snapshot_liquidacion(liquidacion, detalles)

    # Validar todo antes de mutar: un 422 no deja el detalle a medio actualizar.
    propuesta: list[tuple[LiquidacionOSDetalle, Decimal, str | None]] = []
    for item in datos.detalles:
        detalle = por_turno.get(item.turno_id)
        if detalle is None:
            raise EntidadInvalida(
                "Che, uno de los turnos indicados no forma parte de esta liquidación."
            )
        reconocido = _monto(item.monto_reconocido)
        reclamado = _monto(detalle.monto_reclamado)
        if reconocido > reclamado:
            raise EntidadInvalida(
                "Che, el monto reconocido de un turno no puede superar el monto reclamado."
            )
        motivo = (item.debito_motivo or "").strip() or None
        if reconocido < reclamado and motivo is None:
            raise EntidadInvalida(
                "Che, si la obra social reconoce menos de lo reclamado tenés que "
                "indicar el motivo del débito."
            )
        propuesta.append((detalle, reconocido, motivo))

    for detalle, reconocido, motivo in propuesta:
        reclamado = _monto(detalle.monto_reclamado)
        detalle.monto_reconocido = reconocido
        detalle.debito_motivo = None if reconocido == reclamado else motivo
    if datos.observaciones is not None:
        liquidacion.observaciones = datos.observaciones
    await session.flush()
    await _recalcular_totales(session, liquidacion)

    despues = _snapshot_liquidacion(liquidacion, await _detalles_de(session, liquidacion))
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="liquidacion.debitos",
        entidad="liquidacion_os",
        entidad_id=str(liquidacion.id),
        antes=antes,
        despues=despues,
    )
    return await _armar_read(session, liquidacion)


async def presentar_liquidacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    actor_id: uuid.UUID,
    datos: LiquidacionOSCerrarInput | None = None,
) -> LiquidacionOSRead:
    """Presenta el borrador a la obra social fijando actor y fecha (D4)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    if not es_transicion_liquidacion_valida(liquidacion.estado, EstadoLiquidacionOS.PRESENTADA):
        raise Conflicto(
            f"Che, no se puede presentar una liquidación en estado '{liquidacion.estado}'."
        )

    detalles = await _detalles_de(session, liquidacion)
    if not any(_monto(detalle.monto_reclamado) > CERO for detalle in detalles):
        raise EntidadInvalida(
            "Che, la liquidación no tiene turnos con monto a reclamar: no se puede presentar."
        )

    antes: dict[str, object] = {"estado": liquidacion.estado}
    liquidacion.estado = EstadoLiquidacionOS.PRESENTADA.value
    liquidacion.presentada_por = actor_id
    liquidacion.presentada_at = datetime.now(UTC)
    if datos is not None and datos.observaciones is not None:
        liquidacion.observaciones = datos.observaciones
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="liquidacion.presentar",
        entidad="liquidacion_os",
        entidad_id=str(liquidacion.id),
        antes=antes,
        despues={"estado": liquidacion.estado},
    )
    return await _armar_read(session, liquidacion)


async def registrar_resultado(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    datos: ResultadoOSInput,
    actor_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Registra la respuesta de la OS: `pagada` o `con_debitos` (US-041, D4)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    nuevo_estado = EstadoLiquidacionOS(datos.resultado)
    if not es_transicion_liquidacion_valida(liquidacion.estado, nuevo_estado):
        raise Conflicto(
            f"Che, no se puede pasar la liquidación de '{liquidacion.estado}' "
            f"a '{nuevo_estado.value}'."
        )

    detalles = await _detalles_de(session, liquidacion)
    if not detalles:
        raise EntidadInvalida(
            "Che, la liquidación no tiene turnos para registrar el resultado de la obra social."
        )
    por_turno = {detalle.turno_id: detalle for detalle in detalles}
    if {item.turno_id for item in datos.detalles} != set(por_turno):
        raise EntidadInvalida(
            "Che, el resultado tiene que informar todos los turnos de la liquidación."
        )

    antes = _snapshot_liquidacion(liquidacion, detalles)

    # Validar todo antes de mutar: un 422 no deja montos ni estados a medio aplicar.
    propuesta: list[tuple[LiquidacionOSDetalle, Decimal, str | None]] = []
    for item in datos.detalles:
        detalle = por_turno[item.turno_id]
        reconocido = _monto(item.monto_reconocido)
        reclamado = _monto(detalle.monto_reclamado)
        if reconocido > reclamado:
            raise EntidadInvalida(
                "Che, el monto reconocido de un turno no puede superar el monto reclamado."
            )
        motivo = (item.debito_motivo or "").strip() or None
        if reconocido < reclamado and motivo is None:
            raise EntidadInvalida(
                "Che, si la obra social reconoce menos de lo reclamado tenés que "
                "indicar el motivo del débito."
            )
        propuesta.append((detalle, reconocido, motivo))

    total = _monto(liquidacion.total)
    total_reconocido = _monto(sum((reconocido for _, reconocido, _ in propuesta), CERO))
    if nuevo_estado is EstadoLiquidacionOS.PAGADA and total_reconocido != total:
        raise EntidadInvalida(
            "Che, un resultado 'pagada' tiene que reconocer el total reclamado. "
            "Si la obra social reconoce menos, registralo como 'con_debitos'."
        )
    if nuevo_estado is EstadoLiquidacionOS.CON_DEBITOS and total_reconocido >= total:
        raise EntidadInvalida(
            "Che, un resultado 'con_debitos' tiene que reconocer menos que el total reclamado."
        )

    for detalle, reconocido, motivo in propuesta:
        reclamado = _monto(detalle.monto_reclamado)
        detalle.monto_reconocido = reconocido
        detalle.debito_motivo = None if reconocido == reclamado else motivo
        if nuevo_estado is EstadoLiquidacionOS.PAGADA:
            # D3: al pagarse, los turnos quedan liberados para una liquidación posterior.
            detalle.vigente = False

    liquidacion.estado = nuevo_estado.value
    liquidacion.total_reconocido = total_reconocido
    liquidacion.resuelta_por = actor_id
    liquidacion.resuelta_at = datetime.now(UTC)
    if datos.observaciones is not None:
        liquidacion.observaciones = datos.observaciones
    await session.flush()

    despues = _snapshot_liquidacion(liquidacion, await _detalles_de(session, liquidacion))
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="liquidacion.resultado",
        entidad="liquidacion_os",
        entidad_id=str(liquidacion.id),
        antes=antes,
        despues=despues,
    )
    return await _armar_read(session, liquidacion)


async def anular_liquidacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    datos: LiquidacionOSAnularInput,
    actor_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Baja lógica del borrador liberando sus turnos (R7, D3)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    if not es_transicion_liquidacion_valida(liquidacion.estado, EstadoLiquidacionOS.ANULADA):
        raise Conflicto(
            f"Che, sólo se anula un borrador: esta liquidación está en estado "
            f"'{liquidacion.estado}'."
        )

    motivo = datos.motivo.strip()
    if not motivo:
        raise EntidadInvalida("Che, la anulación exige un motivo.")

    detalles = await _detalles_de(session, liquidacion)
    antes = _snapshot_liquidacion(liquidacion, detalles)

    # R7: baja lógica, sin DELETE. El detalle se conserva y sólo deja de estar vigente.
    liquidacion.estado = EstadoLiquidacionOS.ANULADA.value
    liquidacion.anulada_motivo = motivo
    for detalle in detalles:
        detalle.vigente = False
    await session.flush()

    despues = {
        **_snapshot_liquidacion(liquidacion, detalles),
        "motivo": motivo,
        "detalles_liberados": len(detalles),
    }
    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="liquidacion.anular",
        entidad="liquidacion_os",
        entidad_id=str(liquidacion.id),
        antes=antes,
        despues=despues,
    )
    return await _armar_read(session, liquidacion)
