"""Casos de uso de liquidaciones mensuales a obras sociales (C-13, US-041).

Reglas implementadas:
- RN-OS-02: un turno se reclama una sola vez por obra social y período mientras la
  liquidación no esté `anulada` (D9); el índice parcial de `liquidacion_detalle` es la
  última garantía y el caso de uso excluye los turnos ya reclamados.
- US-041: los débitos se informan por turno con motivo y los totales se recalculan en servidor.
- R7: la baja de un borrador es lógica (`anulada`); nunca se borra una liquidación ni su detalle.
- R8: todos los montos son `Decimal` calculados acá; ningún total llega desde el cliente.
- R9 / RN-SE-01: la auditoría guarda IDs y montos, nunca datos personales del paciente.
- D2/D4/D5/D6: cobertura con arancel vencido congelado por turno, grafo cerrado de estados,
  membresía derivada del período y complementarias avisadas.
- D9/D10/D11 (Bloque E): reclamo único por OS/período, resultado todo-o-nada con total
  recalculado desde el detalle persistido, lock pesimista de cabecera e `IntegrityError`
  traducido a `409`.

Notas de diseño:
- La cobertura se resuelve por día de atención (D1): `resolver_coberturas_lote` se invoca una
  vez por fecha distinta del período, así un arancel cargado a mitad de mes no se aplica
  retroactivamente y no hay N+1 por turno.
- `turnos_sin_cobertura` y `advertencias` son resultado del alta; al releer se derivan del
  snapshot `arancel_vencido` del detalle y del valor persistido en la cabecera (D12).
"""

import csv
import io
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_liquidaciones import (
    LiquidacionOSAnularInput,
    LiquidacionOSCerrarInput,
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleRead,
    LiquidacionOSExportacionRead,
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
from app.domain.textos_libres import exigir_texto_sin_phi
from app.domain.turno import EstadoTurno, Turno
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado
from app.shared.montos import CERO, monto_2dp

ADVERTENCIA_COMPLEMENTARIA = (
    "El período ya tiene una liquidación pagada para esta obra social: "
    "esta liquidación se tratará como complementaria."
)
ADVERTENCIA_ARANCEL_VENCIDO = (
    "Hay turnos liquidados con arancel vencido: revisalos con la obra social antes de presentar."
)
ADVERTENCIA_TURNOS_YA_RECLAMADOS = (
    "Estos turnos ya se liquidaron en otra liquidación de esta obra social y período, "
    "así que quedan fuera de esta: {turnos}."
)
MENSAJE_SIN_TURNOS_NUEVOS = "no hay turnos nuevos para liquidar en ese período"


def _agregar_advertencia(advertencias: list[str], mensaje: str | None) -> None:
    """Agrega una advertencia sin repetirla, conservando el orden de aparición."""
    if mensaje and mensaje not in advertencias:
        advertencias.append(mensaje)


def _ids(turno_ids: list[uuid.UUID] | set[uuid.UUID]) -> str:
    """Lista de `turno_id` para los mensajes de error (sin PHI, R9)."""
    return ", ".join(str(turno_id) for turno_id in sorted(turno_ids, key=str))


def _expunge(session: AsyncSession, *objetos: object) -> None:
    """Saca del session los objetos de un savepoint fallido (evita un INSERT colgado)."""
    for objeto in objetos:
        try:
            session.expunge(objeto)
        except InvalidRequestError:  # pragma: no cover - el objeto puede ya no estar attached
            continue


async def obtener_liquidacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    bloquear: bool = False,
) -> LiquidacionOS:
    """Busca una liquidación del tenant o levanta 404 (R4).

    `bloquear=True` agrega `SELECT ... FOR UPDATE` (D11): Postgres serializa las
    mutaciones de una misma liquidación y SQLite lo ignora.
    """
    consulta = select(LiquidacionOS).where(
        LiquidacionOS.id == liquidacion_id,
        LiquidacionOS.tenant_id == tenant_id,
    )
    if bloquear:
        consulta = consulta.with_for_update()
    liquidacion = (await session.execute(consulta)).scalar_one_or_none()
    if liquidacion is None:
        raise NoEncontrado("Che, no encontramos esa liquidación en el consultorio.")
    return liquidacion


async def _detalles_de(
    session: AsyncSession, liquidacion: LiquidacionOS, *, actualizar: bool = False
) -> list[LiquidacionOSDetalle]:
    """Detalle de la liquidación dentro del tenant, en orden estable (R4).

    `actualizar=True` refresca los objetos ya cargados (identity map) con el estado real
    de la base: sin eso, una mutación concurrente podría partir de montos viejos (D11).
    """
    consulta = (
        select(LiquidacionOSDetalle)
        .where(
            LiquidacionOSDetalle.tenant_id == liquidacion.tenant_id,
            LiquidacionOSDetalle.liquidacion_id == liquidacion.id,
        )
        .order_by(LiquidacionOSDetalle.created_at.asc(), LiquidacionOSDetalle.id.asc())
    )
    if actualizar:
        filas = (
            (await session.execute(consulta, execution_options={"populate_existing": True}))
            .scalars()
            .all()
        )
    else:
        filas = (await session.execute(consulta)).scalars().all()
    return list(filas)


async def _detalles_por_turno(
    session: AsyncSession, liquidacion: LiquidacionOS
) -> dict[uuid.UUID, tuple[Decimal | None, str | None, datetime]]:
    """Foto cruda del detalle (lectura de columnas, sin identity map) para D11."""
    filas = (
        await session.execute(
            select(
                LiquidacionOSDetalle.turno_id,
                LiquidacionOSDetalle.monto_reconocido,
                LiquidacionOSDetalle.debito_motivo,
                LiquidacionOSDetalle.updated_at,
            ).where(
                LiquidacionOSDetalle.tenant_id == liquidacion.tenant_id,
                LiquidacionOSDetalle.liquidacion_id == liquidacion.id,
            )
        )
    ).all()
    return {fila[0]: (fila[1], fila[2], fila[3]) for fila in filas}


async def _cargar_para_mutar(
    session: AsyncSession, *, tenant_id: uuid.UUID, liquidacion_id: uuid.UUID
) -> tuple[LiquidacionOS, list[LiquidacionOSDetalle]]:
    """Carga la liquidación con lock pesimista y detecta mutaciones concurrentes (D11).

    El lock de cabecera serializa las mutaciones de una misma liquidación; la comparación
    del detalle antes y después del lock hace que la perdedora de una carrera reciba `409`
    y no pise los montos ya calculados por la que entró.
    """
    inicial = await obtener_liquidacion(session, tenant_id=tenant_id, liquidacion_id=liquidacion_id)
    previa = await _detalles_por_turno(session, inicial)
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id, bloquear=True
    )
    await session.refresh(liquidacion, with_for_update=True)
    if await _detalles_por_turno(session, liquidacion) != previa:
        raise Conflicto(
            "Che, otra operación modificó esta liquidación al mismo tiempo. "
            "Recargala y volvé a intentarlo."
        )
    return liquidacion, await _detalles_de(session, liquidacion, actualizar=True)


@dataclass(frozen=True)
class _DatosDetalle:
    """Detalle de una liquidación (o de un lote) ya cargado en memoria (N1)."""

    detalles: list[LiquidacionOSDetalle]
    turnos: dict[uuid.UUID, Turno]
    prestaciones: dict[uuid.UUID, Prestacion]


async def _cargar_turnos_y_prestaciones(
    session: AsyncSession, tenant_id: uuid.UUID, detalles: Sequence[LiquidacionOSDetalle]
) -> tuple[dict[uuid.UUID, Turno], dict[uuid.UUID, Prestacion]]:
    """Carga los turnos y las prestaciones del detalle con 2 queries (N1, sin N+1)."""
    if not detalles:
        return {}, {}
    turnos = {
        turno.id: turno
        for turno in (
            (
                await session.execute(
                    select(Turno).where(
                        Turno.tenant_id == tenant_id,
                        Turno.id.in_({detalle.turno_id for detalle in detalles}),
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    if not turnos:
        return turnos, {}
    prestaciones = {
        prestacion.id: prestacion
        for prestacion in (
            (
                await session.execute(
                    select(Prestacion).where(
                        Prestacion.tenant_id == tenant_id,
                        Prestacion.id.in_({turno.prestacion_id for turno in turnos.values()}),
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    return turnos, prestaciones


async def _cargar_detalle(session: AsyncSession, liquidacion: LiquidacionOS) -> _DatosDetalle:
    """Detalle de una liquidación suelta (detalle + turnos + prestaciones)."""
    detalles = await _detalles_de(session, liquidacion)
    turnos, prestaciones = await _cargar_turnos_y_prestaciones(
        session, liquidacion.tenant_id, detalles
    )
    return _DatosDetalle(detalles=detalles, turnos=turnos, prestaciones=prestaciones)


async def _cargar_detalle_lote(
    session: AsyncSession, liquidaciones: Sequence[LiquidacionOS]
) -> dict[uuid.UUID, _DatosDetalle]:
    """Detalle del lote con 3 queries en total (N1: el listado no escala por liquidación).

    Antes, `_armar_read` se llamaba por liquidación y hacía 3 queries cada una (N+1).
    """
    if not liquidaciones:
        return {}
    tenant_id = liquidaciones[0].tenant_id
    detalles = list(
        (
            await session.execute(
                select(LiquidacionOSDetalle)
                .where(
                    LiquidacionOSDetalle.tenant_id == tenant_id,
                    LiquidacionOSDetalle.liquidacion_id.in_(
                        [liquidacion.id for liquidacion in liquidaciones]
                    ),
                )
                .order_by(LiquidacionOSDetalle.created_at.asc(), LiquidacionOSDetalle.id.asc())
            )
        )
        .scalars()
        .all()
    )
    turnos, prestaciones = await _cargar_turnos_y_prestaciones(session, tenant_id, detalles)
    por_liquidacion: dict[uuid.UUID, list[LiquidacionOSDetalle]] = {}
    for detalle in detalles:
        por_liquidacion.setdefault(detalle.liquidacion_id, []).append(detalle)
    return {
        liquidacion.id: _DatosDetalle(
            detalles=por_liquidacion.get(liquidacion.id, []),
            turnos=turnos,
            prestaciones=prestaciones,
        )
        for liquidacion in liquidaciones
    }


async def _armar_read(
    session: AsyncSession,
    liquidacion: LiquidacionOS,
    *,
    turnos_sin_cobertura: int = 0,
    advertencias: list[str] | None = None,
) -> LiquidacionOSRead:
    """Arma la respuesta con cabecera, detalle por turno y totales persistidos (R1, R8)."""
    datos = await _cargar_detalle(session, liquidacion)
    return _armar_read_desde_datos(
        liquidacion,
        datos,
        turnos_sin_cobertura=turnos_sin_cobertura,
        advertencias=advertencias,
    )


def _armar_read_desde_datos(
    liquidacion: LiquidacionOS,
    datos: _DatosDetalle,
    *,
    turnos_sin_cobertura: int = 0,
    advertencias: list[str] | None = None,
) -> LiquidacionOSRead:
    """Arma la respuesta con el detalle ya cargado en memoria (N1: sin queries)."""
    filas: list[LiquidacionOSDetalleRead] = []
    for detalle in datos.detalles:
        turno = datos.turnos.get(detalle.turno_id)
        if turno is None:  # pragma: no cover - la FK RESTRICT garantiza el turno
            continue
        prestacion = datos.prestaciones.get(turno.prestacion_id)
        filas.append(
            LiquidacionOSDetalleRead(
                id=detalle.id,
                turno_id=detalle.turno_id,
                fecha_turno=asegurar_utc(turno.inicio),
                prestacion=prestacion.nombre if prestacion is not None else "Sin prestación",
                monto_reclamado=monto_2dp(detalle.monto_reclamado),
                monto_reconocido=(
                    monto_2dp(detalle.monto_reconocido)
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

    # D12: el conteo de turnos sin cobertura vive en la cabecera (migración `013`).
    sin_cobertura = int(liquidacion.turnos_sin_cobertura)

    return LiquidacionOSRead(
        id=liquidacion.id,
        tenant_id=liquidacion.tenant_id,
        obra_social=liquidacion.obra_social,
        periodo=liquidacion.periodo,
        estado=EstadoLiquidacionOS(liquidacion.estado),
        total=monto_2dp(liquidacion.total),
        total_reconocido=(
            monto_2dp(liquidacion.total_reconocido)
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
        turnos_sin_cobertura=sin_cobertura,
        advertencias=advertencias,
        detalles=filas,
    )


async def obtener_liquidacion_read(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Detalle completo de una liquidación del tenant (404 si es de otro consultorio, R4)."""
    liquidacion = await obtener_liquidacion(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    return await _armar_read(session, liquidacion)


async def listar_liquidaciones(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    obra_social: str | None = None,
    periodo: str | None = None,
    estado: EstadoLiquidacionOS | None = None,
) -> list[LiquidacionOSRead]:
    """Lista las liquidaciones del tenant con filtros de OS, período y estado (R4)."""
    consulta = select(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant_id)
    if obra_social is not None and obra_social.strip():
        consulta = consulta.where(
            func.lower(LiquidacionOS.obra_social) == obra_social.strip().lower()
        )
    if periodo is not None:
        consulta = consulta.where(LiquidacionOS.periodo == periodo)
    if estado is not None:
        consulta = consulta.where(LiquidacionOS.estado == estado.value)
    consulta = consulta.order_by(
        LiquidacionOS.periodo.desc(),
        LiquidacionOS.obra_social.asc(),
        LiquidacionOS.created_at.desc(),
    )
    liquidaciones = list((await session.execute(consulta)).scalars().all())
    # N1: el detalle del lote se carga en 3 queries y las respuestas se arman con mapas.
    datos_por_liquidacion = await _cargar_detalle_lote(session, liquidaciones)
    return [
        _armar_read_desde_datos(liquidacion, datos_por_liquidacion[liquidacion.id])
        for liquidacion in liquidaciones
    ]


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


async def _turnos_ya_reclamados(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    obra_social: str,
    periodo: str,
    turno_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    """Turnos con detalle en cualquier liquidación **no anulada** de esa OS/período (D9).

    `vigente` ya no es la señal de "ya reclamado" (D3 enmendado): el reclamo es un hecho
    económico que sólo la anulación libera.
    """
    if not turno_ids:
        return set()
    filas = (
        (
            await session.execute(
                select(LiquidacionOSDetalle.turno_id)
                .join(LiquidacionOS, LiquidacionOSDetalle.liquidacion_id == LiquidacionOS.id)
                .where(
                    LiquidacionOSDetalle.tenant_id == tenant_id,
                    func.lower(LiquidacionOSDetalle.obra_social) == obra_social.lower(),
                    LiquidacionOSDetalle.periodo == periodo,
                    LiquidacionOS.estado != EstadoLiquidacionOS.ANULADA.value,
                    LiquidacionOSDetalle.turno_id.in_(turno_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(filas)


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

    # D9: un turno se reclama una sola vez por obra social y período mientras la liquidación
    # que lo contiene no esté anulada. Los turnos ya reclamados quedan fuera del borrador y
    # se informan en las advertencias; si no queda ninguno, el alta se rechaza con 422.
    ya_reclamados = await _turnos_ya_reclamados(
        session,
        tenant_id=tenant_id,
        obra_social=obra_social,
        periodo=datos.periodo,
        turno_ids=[turno.id for turno, _ in incluidos],
    )
    if ya_reclamados:
        incluidos = [
            (turno, resolucion) for turno, resolucion in incluidos if turno.id not in ya_reclamados
        ]
        if not incluidos:
            raise EntidadInvalida(
                f"Che, {MENSAJE_SIN_TURNOS_NUEVOS} ({datos.periodo}) para {obra_social}: "
                "todos los turnos finalizados ya fueron liquidados."
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
    if ya_reclamados:
        _agregar_advertencia(
            advertencias,
            ADVERTENCIA_TURNOS_YA_RECLAMADOS.format(turnos=_ids(ya_reclamados)),
        )

    total = monto_2dp(sum((resolucion.cobertura for _, resolucion in incluidos), CERO))
    liquidacion = LiquidacionOS(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        obra_social=obra_social,
        periodo=datos.periodo,
        estado=EstadoLiquidacionOS.BORRADOR.value,
        total=total,
        created_by=actor_id,
    )
    detalles = [
        LiquidacionOSDetalle(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            liquidacion_id=liquidacion.id,
            turno_id=turno.id,
            obra_social=obra_social,
            periodo=datos.periodo,
            monto_reclamado=monto_2dp(resolucion.cobertura),
            arancel_vencido=resolucion.arancel_vencido,
            vigente=True,
        )
        for turno, resolucion in incluidos
    ]
    liquidacion.turnos_sin_cobertura = sin_cobertura

    # D11: el alta va dentro de un SAVEPOINT para que una carrera contra el índice único
    # se traduzca a 409 sin abortar la transacción del request (nunca `session.rollback()`).
    try:
        async with session.begin_nested():
            session.add(liquidacion)
            await session.flush()
            session.add_all(detalles)
            await session.flush()
    except IntegrityError as exc:
        _expunge(session, liquidacion, *detalles)
        raise Conflicto(
            "Che, no se pudo crear la liquidación porque choca con otra liquidación "
            "de esa obra social y período. Intentá de nuevo en un momento."
        ) from exc

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
    """Foto mínima para la auditoría: estado, totales y montos por `turno_id` (R9).

    N4: las `observaciones` también quedan en el snapshot (append-only) para que el
    texto libre que escribió el usuario quede rastreado. El guard de `R9` garantiza
    que ese texto no arrastre PHI.
    """
    return {
        "estado": liquidacion.estado,
        "total": str(monto_2dp(liquidacion.total)),
        "total_reconocido": (
            str(monto_2dp(liquidacion.total_reconocido))
            if liquidacion.total_reconocido is not None
            else None
        ),
        "observaciones": liquidacion.observaciones,
        "detalles": {
            str(detalle.turno_id): {
                "monto_reclamado": str(monto_2dp(detalle.monto_reclamado)),
                "monto_reconocido": (
                    str(monto_2dp(detalle.monto_reconocido))
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
    total = monto_2dp(sum((monto_2dp(detalle.monto_reclamado) for detalle in detalles), CERO))
    reconocidos = [
        monto_2dp(detalle.monto_reconocido)
        for detalle in detalles
        if detalle.monto_reconocido is not None
    ]
    liquidacion.total = total
    liquidacion.total_reconocido = monto_2dp(sum(reconocidos, CERO)) if reconocidos else None
    await session.flush()


def _rechazar_turnos_repetidos(turno_ids: list[uuid.UUID]) -> None:
    """D10: defensa en profundidad ante un `turno_id` repetido (422, nunca doble suma)."""
    vistos: set[uuid.UUID] = set()
    repetidos: set[uuid.UUID] = set()
    for turno_id in turno_ids:
        if turno_id in vistos:
            repetidos.add(turno_id)
        vistos.add(turno_id)
    if repetidos:
        raise EntidadInvalida(
            f"Che, no podés informar el mismo turno más de una vez. Se repiten: {_ids(repetidos)}."
        )


async def registrar_debitos(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    datos: LiquidacionOSDebitosInput,
    actor_id: uuid.UUID,
) -> LiquidacionOSRead:
    """Registra los reconocidos por turno sobre un borrador y recalcula totales (US-041)."""
    liquidacion, detalles = await _cargar_para_mutar(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    if liquidacion.estado != EstadoLiquidacionOS.BORRADOR.value:
        raise Conflicto(
            f"Che, sólo se editan débitos de un borrador: esta liquidación está en "
            f"estado '{liquidacion.estado}'."
        )

    _rechazar_turnos_repetidos([item.turno_id for item in datos.detalles])
    por_turno = {detalle.turno_id: detalle for detalle in detalles}
    antes = _snapshot_liquidacion(liquidacion, detalles)

    # E.11 / R9: los textos libres no pueden arrastrar PHI (DNI o teléfono).
    exigir_texto_sin_phi(datos.observaciones, campo="las observaciones")

    # Validar todo antes de mutar: un 422 no deja el detalle a medio actualizar.
    propuesta: list[tuple[LiquidacionOSDetalle, Decimal, str | None]] = []
    for item in datos.detalles:
        detalle = por_turno.get(item.turno_id)
        if detalle is None:
            raise EntidadInvalida(
                "Che, uno de los turnos indicados no forma parte de esta liquidación."
            )
        reconocido = monto_2dp(item.monto_reconocido)
        reclamado = monto_2dp(detalle.monto_reclamado)
        if reconocido > reclamado:
            raise EntidadInvalida(
                "Che, el monto reconocido de un turno no puede superar el monto reclamado."
            )
        motivo = (item.debito_motivo or "").strip() or None
        exigir_texto_sin_phi(motivo, campo="el motivo del débito")
        if reconocido < reclamado and motivo is None:
            raise EntidadInvalida(
                "Che, si la obra social reconoce menos de lo reclamado tenés que "
                "indicar el motivo del débito."
            )
        propuesta.append((detalle, reconocido, motivo))

    for detalle, reconocido, motivo in propuesta:
        reclamado = monto_2dp(detalle.monto_reclamado)
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
    liquidacion, detalles = await _cargar_para_mutar(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    if not es_transicion_liquidacion_valida(liquidacion.estado, EstadoLiquidacionOS.PRESENTADA):
        raise Conflicto(
            f"Che, no se puede presentar una liquidación en estado '{liquidacion.estado}'."
        )

    if not any(monto_2dp(detalle.monto_reclamado) > CERO for detalle in detalles):
        raise EntidadInvalida(
            "Che, la liquidación no tiene turnos con monto a reclamar: no se puede presentar."
        )

    # E.11 / R9: las observaciones son texto libre y no pueden arrastrar PHI.
    if datos is not None:
        exigir_texto_sin_phi(datos.observaciones, campo="las observaciones")

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
    liquidacion, detalles = await _cargar_para_mutar(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    estado_actual = EstadoLiquidacionOS(liquidacion.estado)
    nuevo_estado = EstadoLiquidacionOS(datos.resultado)
    if not es_transicion_liquidacion_valida(liquidacion.estado, nuevo_estado):
        raise Conflicto(
            f"Che, no se puede pasar la liquidación de '{liquidacion.estado}' "
            f"a '{nuevo_estado.value}'."
        )

    if not detalles:
        raise EntidadInvalida(
            "Che, la liquidación no tiene turnos para registrar el resultado de la obra social."
        )

    # D10: el schema ya rechaza repetidos; acá se repite la comprobación por si el caso de
    # uso se invoca desde otro camino (defensa en profundidad).
    _rechazar_turnos_repetidos([item.turno_id for item in datos.detalles])

    por_turno = {detalle.turno_id: detalle for detalle in detalles}
    informados = {item.turno_id for item in datos.detalles}
    faltantes = [turno_id for turno_id in por_turno if turno_id not in informados]
    sobrantes = [turno_id for turno_id in informados if turno_id not in por_turno]
    if faltantes:
        raise EntidadInvalida(
            f"Che, el resultado tiene que informar todos los turnos de la liquidación: "
            f"faltan {len(faltantes)} ({_ids(faltantes)})."
        )
    if sobrantes:
        raise EntidadInvalida(
            f"Che, el resultado informó {len(sobrantes)} turnos que no forman parte de la "
            f"liquidación ({_ids(sobrantes)})."
        )

    antes = _snapshot_liquidacion(liquidacion, detalles)

    # E.11 / R9: los textos libres no pueden arrastrar PHI (DNI o teléfono).
    exigir_texto_sin_phi(datos.observaciones, campo="las observaciones")

    # Validar todo antes de mutar: un 422 no deja montos ni estados a medio aplicar.
    propuesta: list[tuple[LiquidacionOSDetalle, Decimal, str | None]] = []
    for item in datos.detalles:
        detalle = por_turno[item.turno_id]
        reconocido = monto_2dp(item.monto_reconocido)
        reclamado = monto_2dp(detalle.monto_reclamado)
        if reconocido > reclamado:
            raise EntidadInvalida(
                "Che, el monto reconocido de un turno no puede superar el monto reclamado."
            )
        motivo = (item.debito_motivo or "").strip() or None
        exigir_texto_sin_phi(motivo, campo="el motivo del débito")
        if motivo is None and estado_actual is EstadoLiquidacionOS.CON_DEBITOS:
            # D4 (enmienda): al pasar de `con_debitos` a `pagada` se conserva el débito ya
            # cargado; el payload no tiene por qué volver a mandar el motivo.
            motivo = detalle.debito_motivo
        if reconocido < reclamado and motivo is None:
            raise EntidadInvalida(
                "Che, si la obra social reconoce menos de lo reclamado tenés que "
                "indicar el motivo del débito."
            )
        propuesta.append((detalle, reconocido, motivo))

    total = monto_2dp(liquidacion.total)
    reconocido_previsto = monto_2dp(sum((reconocido for _, reconocido, _ in propuesta), CERO))

    # D4 (enmienda): la coherencia se valida por transición, no por estado destino.
    if estado_actual is EstadoLiquidacionOS.PRESENTADA:
        if nuevo_estado is EstadoLiquidacionOS.PAGADA and reconocido_previsto != total:
            raise EntidadInvalida(
                "Che, un resultado 'pagada' tiene que reconocer el total reclamado. "
                "Si la obra social reconoce menos, registralo como 'con_debitos'."
            )
        if nuevo_estado is EstadoLiquidacionOS.CON_DEBITOS and reconocido_previsto >= total:
            raise EntidadInvalida(
                "Che, un resultado 'con_debitos' tiene que reconocer menos que el total reclamado."
            )
    else:  # `con_debitos → pagada`: la OS paga el saldo reconocido, no el total.
        reconocido_previo = monto_2dp(liquidacion.total_reconocido or CERO)
        if reconocido_previsto < reconocido_previo:
            raise EntidadInvalida(
                "Che, el monto reconocido no puede ser menor al que ya estaba reconocido "
                f"({reconocido_previo})."
            )

    for detalle, reconocido, motivo in propuesta:
        reclamado = monto_2dp(detalle.monto_reclamado)
        detalle.monto_reconocido = reconocido
        detalle.debito_motivo = None if reconocido == reclamado else motivo
        if nuevo_estado is EstadoLiquidacionOS.PAGADA:
            # D3: al pagarse, la liquidación queda cerrada (ya no es "abierta").
            detalle.vigente = False

    if datos.observaciones is not None:
        liquidacion.observaciones = datos.observaciones
    # Primero se persiste el detalle...
    await session.flush()
    # ...y recién después se recalculan los totales desde el detalle persistido (D10/R8:
    # el total reconocido nunca sale de sumar el payload).
    await _recalcular_totales(session, liquidacion)

    liquidacion.estado = nuevo_estado.value
    liquidacion.resuelta_por = actor_id
    liquidacion.resuelta_at = datetime.now(UTC)
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
    liquidacion, detalles = await _cargar_para_mutar(
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
    # E.11 / R9: el motivo de anulación es texto libre y no puede arrastrar PHI.
    exigir_texto_sin_phi(motivo, campo="el motivo de la anulación")

    antes = _snapshot_liquidacion(liquidacion, detalles)

    # R7: baja lógica, sin DELETE. El detalle se conserva y sólo deja de estar vigente.
    liquidacion.estado = EstadoLiquidacionOS.ANULADA.value
    liquidacion.anulada_motivo = motivo
    for detalle in detalles:
        detalle.vigente = False
        # D9/D12: la anulación es la única baja que libera el reclamo; si el detalle
        # siguiera `reclamado = true`, el índice único parcial impediría re-liquidar
        # el turno anulado.
        detalle.reclamado = False
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


# ---------------------------------------------------------------------------
# Exportación (D7, RN-OS-03)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportacionLiquidacion:
    """Archivo de exportación ya armado en memoria (R3): contenido, tipo MIME y nombre.

    `nombre_archivo` es ASCII (el header HTTP se codifica en latin-1) y `nombre_legible`
    conserva el nombre con acentos, que viaja percent-encoded en `filename*` (RFC 5987).
    """

    contenido: bytes
    media_type: str
    nombre_archivo: str
    nombre_legible: str

    def cabeceras(self) -> dict[str, str]:
        """Headers HTTP de la descarga, sin datos sensibles en la URL (R9)."""
        extendido = quote(self.nombre_legible, safe="")
        return {
            "Content-Disposition": (
                f"attachment; filename=\"{self.nombre_archivo}\"; filename*=UTF-8''{extendido}"
            ),
            "Cache-Control": "no-store",
        }


FORMATOS_EXPORTACION = frozenset({"csv", "json"})

# D7: una fila por turno, sin datos del paciente (R9).
COLUMNAS_EXPORTACION = (
    "periodo",
    "obra_social",
    "estado",
    "estado_arancel",
    "turno_id",
    "fecha_turno",
    "prestacion",
    "monto_reclamado",
    "monto_reconocido",
    "debito_motivo",
    "saldo_debito",
)


def _slug(obra_social: str, *, ascii_only: bool) -> str:
    """Slug del nombre de la obra social: sin espacios, comillas ni saltos de línea (R9).

    Cada carácter que no es alfanumérico (o que no es ASCII, si `ascii_only`) se
    reemplaza por `-`; las rachas de guiones se colapsan en una sola.
    """
    normalizado = " ".join(obra_social.split())
    limpio = "".join(
        caracter if _se_guarda(caracter, ascii_only=ascii_only) else "-" for caracter in normalizado
    )
    colapsado = "-".join(parte for parte in limpio.split("-") if parte)
    return colapsado.strip("-") or "os"


def _se_guarda(caracter: str, *, ascii_only: bool) -> bool:
    """True si el carácter puede quedar literal en el slug (alfanumérico o `-`/`_`)."""
    if caracter in "-_":
        return True
    if not caracter.isalnum():
        return False
    return not ascii_only or caracter.isascii()


def _slug_archivo(obra_social: str) -> str:
    """Slug ASCII del nombre de la obra social (N3: el header HTTP es latin-1)."""
    return _slug(obra_social, ascii_only=True)


def _nombre_legible(obra_social: str) -> str:
    """Slug legible del nombre de la obra social (conserva los acentos, RFC 5987)."""
    return _slug(obra_social, ascii_only=False)


def _texto_monto(monto: Decimal | None) -> str:
    """Monto con punto decimal y dos decimales; vacío si la OS todavía no informó (D7)."""
    return "" if monto is None else str(monto_2dp(monto))


def _fila_csv(liquidacion: LiquidacionOSRead, detalle: LiquidacionOSDetalleRead) -> list[str]:
    """Fila del export: cabecera repetida por turno para que el archivo se lea solo."""
    return [
        liquidacion.periodo,
        liquidacion.obra_social,
        liquidacion.estado.value,
        "vencido" if detalle.arancel_vencido else "vigente",
        str(detalle.turno_id),
        detalle.fecha_turno.date().isoformat(),
        detalle.prestacion,
        _texto_monto(detalle.monto_reclamado),
        _texto_monto(detalle.monto_reconocido),
        detalle.debito_motivo or "",
        _texto_monto(liquidacion.saldo_debito),
    ]


def _exportar_csv(liquidacion: LiquidacionOSRead) -> bytes:
    """CSV UTF-8 con BOM, separador `,` y quoting/CRLF de RFC 4180 (D7)."""
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=",", quotechar='"', lineterminator="\r\n")
    escritor.writerow(COLUMNAS_EXPORTACION)
    escritor.writerows(_fila_csv(liquidacion, detalle) for detalle in liquidacion.detalles)
    # El BOM ayuda a Excel a detectar UTF-8 con acentos sin configuración extra.
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _exportar_json(liquidacion: LiquidacionOSRead) -> bytes:
    """JSON con cabecera + detalle; `Decimal` viaja como string para no perder centavos (R8)."""
    exportacion = LiquidacionOSExportacionRead(
        obra_social=liquidacion.obra_social,
        periodo=liquidacion.periodo,
        estado=liquidacion.estado,
        total=liquidacion.total,
        total_reconocido=liquidacion.total_reconocido,
        detalles=liquidacion.detalles,
    )
    return json.dumps(exportacion.model_dump(mode="json"), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )


async def exportar_liquidacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    liquidacion_id: uuid.UUID,
    formato: str = "csv",
) -> ExportacionLiquidacion:
    """Exporta la liquidación del tenant (D7). El contenido se arma en servidor (R8)."""
    formato_limpio = formato.strip().lower()
    if formato_limpio not in FORMATOS_EXPORTACION:
        raise EntidadInvalida("Che, el formato de la exportación tiene que ser 'csv' o 'json'.")

    liquidacion = await obtener_liquidacion_read(
        session, tenant_id=tenant_id, liquidacion_id=liquidacion_id
    )
    contenido = (
        _exportar_csv(liquidacion) if formato_limpio == "csv" else _exportar_json(liquidacion)
    )
    # N3: el `filename` del header es ASCII y el nombre legible (con acentos) viaja
    # percent-encoded en `filename*` (RFC 5987).
    return ExportacionLiquidacion(
        contenido=contenido,
        media_type="text/csv" if formato_limpio == "csv" else "application/json",
        nombre_archivo=(
            f"liquidacion-{_slug_archivo(liquidacion.obra_social)}-"
            f"{liquidacion.periodo}.{formato_limpio}"
        ),
        nombre_legible=(
            f"liquidacion-{_nombre_legible(liquidacion.obra_social)}-"
            f"{liquidacion.periodo}.{formato_limpio}"
        ),
    )
