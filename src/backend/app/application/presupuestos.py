"""Casos de uso de Presupuestos y Planes de Tratamiento (C-10, US-022).

Reglas implementadas:
- RN-OS-01 / R8: cálculo en servidor de `precio_unit`, `cobertura_os` y `a_cargo` por item según
  cobertura activa y vigente de la obra social o arancel particular.
- RN-CL-04: aceptar un presupuesto que contiene prestaciones invasivas exige consentimiento firmado
  vigente para cada prestación invasiva incluida.
- US-022: vínculo N–N entre presupuesto y turnos; al vincular el primer turno un presupuesto
  `aceptado` pasa automáticamente a `en_curso`.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_presupuestos import (
    PresupuestoCreate,
    PresupuestoItemInput,
    PresupuestoItemRead,
    PresupuestoRead,
    PresupuestoTurnoRead,
    PresupuestoVincularTurnoInput,
)
from app.application.auditoria import registrar_auditoria
from app.application.clinica import tiene_consentimiento_vigente
from app.domain.cobertura_os import CoberturaOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import (
    EstadoPresupuesto,
    Presupuesto,
    PresupuestoItem,
    PresupuestoTurno,
    es_transicion_presupuesto_valida,
)
from app.domain.turno import Turno
from app.shared.exceptions import Conflicto, EntidadInvalida, NoEncontrado

CERO = Decimal("0.00")


async def calcular_montos_item_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    cantidad: int,
    obra_social: str | None = None,
    fecha_referencia: date | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Calcula `(precio_unit, cobertura_os_total, a_cargo_total)` en servidor (RN-OS-01, R8)."""
    prestacion = (
        await session.execute(
            select(Prestacion).where(
                Prestacion.id == prestacion_id,
                Prestacion.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if prestacion is None:
        raise NoEncontrado("Che, no encontramos la prestación indicada para el presupuesto.")

    precio_unit = Decimal(str(prestacion.precio_particular)).quantize(Decimal("0.01"))
    subtotal = (precio_unit * Decimal(cantidad)).quantize(Decimal("0.01"))

    if not obra_social or not obra_social.strip():
        return precio_unit, CERO, subtotal

    hoy = fecha_referencia or datetime.now(UTC).date()
    os_limpia = obra_social.strip().lower()

    cobertura = (
        await session.execute(
            select(CoberturaOS)
            .where(
                CoberturaOS.tenant_id == tenant_id,
                CoberturaOS.prestacion_id == prestacion_id,
                CoberturaOS.activa.is_(True),
                func.lower(CoberturaOS.obra_social) == os_limpia,
                CoberturaOS.vigencia_desde <= hoy,
                or_(CoberturaOS.vigencia_hasta.is_(None), CoberturaOS.vigencia_hasta >= hoy),
            )
            .order_by(CoberturaOS.vigencia_desde.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if cobertura is None:
        return precio_unit, CERO, subtotal

    arancel_unit = Decimal(str(cobertura.arancel)).quantize(Decimal("0.01"))
    cobertura_unit = min(precio_unit, arancel_unit)
    cobertura_total = (cobertura_unit * Decimal(cantidad)).quantize(Decimal("0.01"))
    a_cargo_total = max(CERO, subtotal - cobertura_total).quantize(Decimal("0.01"))
    return precio_unit, cobertura_total, a_cargo_total


async def _armar_presupuesto_read(
    session: AsyncSession,
    presupuesto: Presupuesto,
) -> PresupuestoRead:
    items = (
        (
            await session.execute(
                select(PresupuestoItem)
                .where(
                    PresupuestoItem.tenant_id == presupuesto.tenant_id,
                    PresupuestoItem.presupuesto_id == presupuesto.id,
                )
                .order_by(PresupuestoItem.created_at.asc(), PresupuestoItem.id.asc())
            )
        )
        .scalars()
        .all()
    )
    vinculos = (
        (
            await session.execute(
                select(PresupuestoTurno)
                .where(
                    PresupuestoTurno.tenant_id == presupuesto.tenant_id,
                    PresupuestoTurno.presupuesto_id == presupuesto.id,
                )
                .order_by(PresupuestoTurno.created_at.asc(), PresupuestoTurno.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return PresupuestoRead(
        id=presupuesto.id,
        tenant_id=presupuesto.tenant_id,
        paciente_id=presupuesto.paciente_id,
        obra_social=presupuesto.obra_social,
        estado=presupuesto.estado,
        total=Decimal(str(presupuesto.total)).quantize(Decimal("0.01")),
        total_cobertura_os=Decimal(str(presupuesto.total_cobertura_os)).quantize(Decimal("0.01")),
        total_a_cargo=Decimal(str(presupuesto.total_a_cargo)).quantize(Decimal("0.01")),
        validez_hasta=presupuesto.validez_hasta,
        observaciones=presupuesto.observaciones,
        created_by=presupuesto.created_by,
        items=[PresupuestoItemRead.model_validate(i) for i in items],
        turnos_vinculados=[PresupuestoTurnoRead.model_validate(v) for v in vinculos],
        created_at=presupuesto.created_at,
        updated_at=presupuesto.updated_at,
    )


async def _recalcular_totales_presupuesto(
    session: AsyncSession,
    presupuesto: Presupuesto,
) -> None:
    items = (
        (
            await session.execute(
                select(PresupuestoItem).where(
                    PresupuestoItem.tenant_id == presupuesto.tenant_id,
                    PresupuestoItem.presupuesto_id == presupuesto.id,
                )
            )
        )
        .scalars()
        .all()
    )
    total = CERO
    total_os = CERO
    total_a_cargo = CERO
    for it in items:
        subtotal = (Decimal(str(it.precio_unit)) * Decimal(it.cantidad)).quantize(Decimal("0.01"))
        total += subtotal
        total_os += Decimal(str(it.cobertura_os)).quantize(Decimal("0.01"))
        total_a_cargo += Decimal(str(it.a_cargo)).quantize(Decimal("0.01"))

    presupuesto.total = total
    presupuesto.total_cobertura_os = total_os
    presupuesto.total_a_cargo = total_a_cargo
    presupuesto.updated_at = datetime.now(UTC)
    await session.flush()


async def crear_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    datos: PresupuestoCreate,
    actor_id: uuid.UUID,
    fecha_referencia: date | None = None,
) -> PresupuestoRead:
    """Crea un presupuesto en estado `borrador` calculando todos sus items en servidor."""
    paciente = (
        await session.execute(
            select(Paciente).where(
                Paciente.id == datos.paciente_id,
                Paciente.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente para crear el presupuesto.")

    presupuesto = Presupuesto(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=datos.paciente_id,
        obra_social=datos.obra_social,
        estado=EstadoPresupuesto.BORRADOR.value,
        total=CERO,
        total_cobertura_os=CERO,
        total_a_cargo=CERO,
        validez_hasta=datos.validez_hasta,
        observaciones=datos.observaciones,
        created_by=actor_id,
    )
    session.add(presupuesto)
    await session.flush()

    for item_in in datos.items:
        precio_unit, cobertura_os, a_cargo = await calcular_montos_item_presupuesto(
            session,
            tenant_id=tenant_id,
            prestacion_id=item_in.prestacion_id,
            cantidad=item_in.cantidad,
            obra_social=datos.obra_social,
            fecha_referencia=fecha_referencia,
        )
        session.add(
            PresupuestoItem(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                presupuesto_id=presupuesto.id,
                prestacion_id=item_in.prestacion_id,
                pieza_fdi=item_in.pieza_fdi,
                cantidad=item_in.cantidad,
                precio_unit=precio_unit,
                cobertura_os=cobertura_os,
                a_cargo=a_cargo,
            )
        )
    await session.flush()
    await _recalcular_totales_presupuesto(session, presupuesto)

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="presupuesto.crear",
        entidad="presupuesto",
        entidad_id=str(presupuesto.id),
        despues={
            "estado": presupuesto.estado,
            "total": str(presupuesto.total),
            "total_cobertura_os": str(presupuesto.total_cobertura_os),
            "total_a_cargo": str(presupuesto.total_a_cargo),
        },
    )
    return await _armar_presupuesto_read(session, presupuesto)


async def agregar_item_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    item_input: PresupuestoItemInput,
    actor_id: uuid.UUID,
    fecha_referencia: date | None = None,
) -> PresupuestoRead:
    """Agrega un item a un presupuesto en borrador/presentado y recalcula totales."""
    presupuesto = (
        await session.execute(
            select(Presupuesto).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if presupuesto is None:
        raise NoEncontrado("Che, no encontramos el presupuesto.")

    if presupuesto.estado not in (
        EstadoPresupuesto.BORRADOR.value,
        EstadoPresupuesto.PRESENTADO.value,
    ):
        raise Conflicto(
            "Che, solo podés agregar items a un presupuesto en estado 'borrador' o 'presentado'."
        )

    precio_unit, cobertura_os, a_cargo = await calcular_montos_item_presupuesto(
        session,
        tenant_id=tenant_id,
        prestacion_id=item_input.prestacion_id,
        cantidad=item_input.cantidad,
        obra_social=presupuesto.obra_social,
        fecha_referencia=fecha_referencia,
    )
    session.add(
        PresupuestoItem(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            presupuesto_id=presupuesto.id,
            prestacion_id=item_input.prestacion_id,
            pieza_fdi=item_input.pieza_fdi,
            cantidad=item_input.cantidad,
            precio_unit=precio_unit,
            cobertura_os=cobertura_os,
            a_cargo=a_cargo,
        )
    )
    await session.flush()
    await _recalcular_totales_presupuesto(session, presupuesto)

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="presupuesto.agregar_item",
        entidad="presupuesto",
        entidad_id=str(presupuesto.id),
        despues={
            "total": str(presupuesto.total),
            "total_a_cargo": str(presupuesto.total_a_cargo),
        },
    )
    return await _armar_presupuesto_read(session, presupuesto)


async def obtener_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
) -> PresupuestoRead:
    """Obtiene el detalle completo de un presupuesto con sus items y turnos vinculados."""
    presupuesto = (
        await session.execute(
            select(Presupuesto).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if presupuesto is None:
        raise NoEncontrado("Che, no encontramos el presupuesto solicitado.")
    return await _armar_presupuesto_read(session, presupuesto)


async def listar_presupuestos(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID | None = None,
    estado: str | None = None,
) -> list[PresupuestoRead]:
    """Lista los presupuestos del consultorio filtrables por paciente o estado."""
    stmt = select(Presupuesto).where(Presupuesto.tenant_id == tenant_id)
    if paciente_id is not None:
        stmt = stmt.where(Presupuesto.paciente_id == paciente_id)
    if estado is not None:
        stmt = stmt.where(Presupuesto.estado == estado)
    stmt = stmt.order_by(Presupuesto.created_at.desc())
    filas = (await session.execute(stmt)).scalars().all()
    return [await _armar_presupuesto_read(session, p) for p in filas]


async def cambiar_estado_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    nuevo_estado: EstadoPresupuesto,
    actor_id: uuid.UUID,
) -> PresupuestoRead:
    """Transiciona el estado del presupuesto verificando el grafo y RN-CL-04 al aceptar."""
    presupuesto = (
        await session.execute(
            select(Presupuesto).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if presupuesto is None:
        raise NoEncontrado("Che, no encontramos el presupuesto.")

    if not es_transicion_presupuesto_valida(presupuesto.estado, nuevo_estado):
        raise EntidadInvalida(
            f"Che, no se puede pasar el presupuesto de "
            f"'{presupuesto.estado}' a '{nuevo_estado.value}'."
        )

    if nuevo_estado == EstadoPresupuesto.ACEPTADO:
        items = (
            (
                await session.execute(
                    select(PresupuestoItem).where(
                        PresupuestoItem.tenant_id == tenant_id,
                        PresupuestoItem.presupuesto_id == presupuesto.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for it in items:
            prestacion = await session.get(Prestacion, it.prestacion_id)
            if prestacion is not None and prestacion.invasiva:
                vigente = await tiene_consentimiento_vigente(
                    session,
                    tenant_id=tenant_id,
                    paciente_id=presupuesto.paciente_id,
                    prestacion_id=prestacion.id,
                )
                if not vigente:
                    raise Conflicto(
                        "Che, este presupuesto incluye una prestación invasiva y requiere "
                        "consentimiento informado firmado antes de poder aceptarlo."
                    )

    antes: dict[str, object] = {"estado": presupuesto.estado}
    presupuesto.estado = nuevo_estado.value
    presupuesto.updated_at = datetime.now(UTC)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="presupuesto.cambiar_estado",
        entidad="presupuesto",
        entidad_id=str(presupuesto.id),
        antes=antes,
        despues={"estado": presupuesto.estado},
    )
    return await _armar_presupuesto_read(session, presupuesto)


async def aceptar_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> PresupuestoRead:
    """Atajo semántico para aceptar un presupuesto verificando consentimiento (RN-CL-04)."""
    return await cambiar_estado_presupuesto(
        session,
        tenant_id=tenant_id,
        presupuesto_id=presupuesto_id,
        nuevo_estado=EstadoPresupuesto.ACEPTADO,
        actor_id=actor_id,
    )


async def vincular_turno_a_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    datos: PresupuestoVincularTurnoInput,
    actor_id: uuid.UUID,
) -> PresupuestoTurno:
    """Vincula un turno del paciente al plan y pasa el presupuesto de `aceptado` a `en_curso`."""
    presupuesto = (
        await session.execute(
            select(Presupuesto).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if presupuesto is None:
        raise NoEncontrado("Che, no encontramos el presupuesto.")

    if presupuesto.estado not in (
        EstadoPresupuesto.ACEPTADO.value,
        EstadoPresupuesto.EN_CURSO.value,
    ):
        raise Conflicto("Che, solo podés vincular turnos a un presupuesto aceptado o en curso.")

    turno = (
        await session.execute(
            select(Turno).where(
                Turno.id == datos.turno_id,
                Turno.tenant_id == tenant_id,
                Turno.paciente_id == presupuesto.paciente_id,
            )
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, el turno indicado no pertenece al paciente de este presupuesto.")

    existente = (
        await session.execute(
            select(PresupuestoTurno).where(
                PresupuestoTurno.presupuesto_id == presupuesto.id,
                PresupuestoTurno.turno_id == turno.id,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    vinculo = PresupuestoTurno(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        presupuesto_id=presupuesto.id,
        turno_id=turno.id,
        presupuesto_item_id=datos.presupuesto_item_id,
    )
    session.add(vinculo)

    if presupuesto.estado == EstadoPresupuesto.ACEPTADO.value:
        presupuesto.estado = EstadoPresupuesto.EN_CURSO.value
        presupuesto.updated_at = datetime.now(UTC)

    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="presupuesto.vincular_turno",
        entidad="presupuesto",
        entidad_id=str(presupuesto.id),
        despues={
            "turno_id": str(turno.id),
            "estado": presupuesto.estado,
        },
    )
    return vinculo


async def listar_turnos_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
) -> list[PresupuestoTurno]:
    """Lista las citas (PresupuestoTurno) vinculadas a un presupuesto."""
    presupuesto = (
        await session.execute(
            select(Presupuesto).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if presupuesto is None:
        raise NoEncontrado("Che, no encontramos el presupuesto.")

    filas = (
        (
            await session.execute(
                select(PresupuestoTurno)
                .where(
                    PresupuestoTurno.tenant_id == tenant_id,
                    PresupuestoTurno.presupuesto_id == presupuesto_id,
                )
                .order_by(PresupuestoTurno.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(filas)
