"""Router interno de Agenda, Turnos y Bloqueos (C-06).

Protegido por RBAC (`Recurso.AGENDA` y `Recurso.BLOQUEOS`) y aislado estrictamente
por el `tenant_id` del token JWT (R4).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_agenda import (
    AgendaVistaRead,
    BloqueoCreate,
    BloqueoRead,
    TurnoCreate,
    TurnoEstadoUpdate,
    TurnoRead,
    TurnoReprogramarRequest,
)
from app.api.security import ActorAutenticado, requiere
from app.application.agenda import (
    cambiar_estado_turno,
    crear_bloqueo,
    crear_turno,
    reprogramar_turno,
)
from app.application.auditoria import registrar_auditoria
from app.domain.bloqueo import Bloqueo
from app.domain.mixins import asegurar_utc
from app.domain.rbac import Accion, Recurso
from app.domain.turno import EstadoTurno, Turno
from app.shared.exceptions import EntidadInvalida, NoEncontrado

router = APIRouter(tags=["agenda"])


def _serializar_turno(turno: Turno, token_gestion: str | None = None) -> TurnoRead:
    return TurnoRead(
        id=turno.id,
        tenant_id=turno.tenant_id,
        paciente_id=turno.paciente_id,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
        prestacion_id=turno.prestacion_id,
        inicio=turno.inicio,
        fin=turno.fin,
        estado=EstadoTurno(turno.estado),
        origen=turno.origen,  # type: ignore[arg-type]
        sobreturno=turno.sobreturno,
        observaciones=turno.observaciones,
        motivo_cancelacion=turno.motivo_cancelacion,
        turno_origen_id=turno.turno_origen_id,
        sena_cobrada=turno.sena_cobrada,
        created_at=turno.created_at,
        updated_at=turno.updated_at,
        token_gestion=token_gestion,
    )


@router.get("/agenda", response_model=AgendaVistaRead)
async def consultar_agenda(
    desde: datetime,
    hasta: datetime,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AGENDA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    profesional_id: Annotated[uuid.UUID | None, Query()] = None,
    sillon_id: Annotated[uuid.UUID | None, Query()] = None,
    estado: Annotated[EstadoTurno | None, Query()] = None,
) -> AgendaVistaRead:
    desde_utc = asegurar_utc(desde)
    hasta_utc = asegurar_utc(hasta)
    if hasta_utc <= desde_utc:
        raise EntidadInvalida(
            "El parámetro 'hasta' de la agenda tiene que ser posterior a 'desde'."
        )

    stmt_turnos = select(Turno).where(
        Turno.tenant_id == actor.tenant_id,
        Turno.inicio < hasta_utc,
        Turno.fin > desde_utc,
    )
    if profesional_id is not None:
        stmt_turnos = stmt_turnos.where(Turno.profesional_id == profesional_id)
    if sillon_id is not None:
        stmt_turnos = stmt_turnos.where(Turno.sillon_id == sillon_id)
    if estado is not None:
        stmt_turnos = stmt_turnos.where(Turno.estado == estado.value)
    stmt_turnos = stmt_turnos.order_by(Turno.inicio)

    stmt_bloqueos = select(Bloqueo).where(
        Bloqueo.tenant_id == actor.tenant_id,
        Bloqueo.desde < hasta_utc,
        Bloqueo.hasta > desde_utc,
    )
    if profesional_id is not None:
        stmt_bloqueos = stmt_bloqueos.where(Bloqueo.profesional_id == profesional_id)
    if sillon_id is not None:
        stmt_bloqueos = stmt_bloqueos.where(Bloqueo.sillon_id == sillon_id)
    stmt_bloqueos = stmt_bloqueos.order_by(Bloqueo.desde)

    turnos = (await session.execute(stmt_turnos)).scalars().all()
    bloqueos = (await session.execute(stmt_bloqueos)).scalars().all()

    return AgendaVistaRead(
        desde=desde_utc,
        hasta=hasta_utc,
        turnos=[_serializar_turno(t) for t in turnos],
        bloqueos=[BloqueoRead.model_validate(b) for b in bloqueos],
    )


@router.post("/turnos", response_model=TurnoRead, status_code=status.HTTP_201_CREATED)
async def crear_turno_endpoint(
    payload: TurnoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AGENDA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> TurnoRead:
    turno, token = await crear_turno(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=payload.paciente_id,
        profesional_id=payload.profesional_id,
        sillon_id=payload.sillon_id,
        prestacion_id=payload.prestacion_id,
        inicio=payload.inicio,
        fin=payload.fin,
        origen=payload.origen,
        sobreturno=payload.sobreturno,
        observaciones=payload.observaciones,
        sena_cobrada=payload.sena_cobrada,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return _serializar_turno(turno, token_gestion=token)


@router.get("/turnos/{turno_id}", response_model=TurnoRead)
async def obtener_turno_endpoint(
    turno_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AGENDA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> TurnoRead:
    turno = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == actor.tenant_id)
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos ese turno en el consultorio.")
    return _serializar_turno(turno)


@router.patch("/turnos/{turno_id}/estado", response_model=TurnoRead)
async def actualizar_estado_turno_endpoint(
    turno_id: uuid.UUID,
    payload: TurnoEstadoUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AGENDA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> TurnoRead:
    turno = await cambiar_estado_turno(
        session,
        tenant_id=actor.tenant_id,
        turno_id=turno_id,
        nuevo_estado=payload.estado,
        motivo_cancelacion=payload.motivo_cancelacion,
        sena_cobrada=payload.sena_cobrada,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return _serializar_turno(turno)


@router.post(
    "/turnos/{turno_id}/reprogramar",
    response_model=TurnoRead,
    status_code=status.HTTP_201_CREATED,
)
async def reprogramar_turno_endpoint(
    turno_id: uuid.UUID,
    payload: TurnoReprogramarRequest,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AGENDA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> TurnoRead:
    nuevo_turno, nuevo_token = await reprogramar_turno(
        session,
        tenant_id=actor.tenant_id,
        turno_id=turno_id,
        nuevo_inicio=payload.nuevo_inicio,
        profesional_id=payload.profesional_id,
        sillon_id=payload.sillon_id,
        motivo=payload.motivo,
        actor_id=actor.usuario_id,
        validar_anticipacion=False,
    )
    await session.commit()
    return _serializar_turno(nuevo_turno, token_gestion=nuevo_token)


@router.get("/bloqueos", response_model=list[BloqueoRead])
async def listar_bloqueos_endpoint(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.BLOQUEOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    profesional_id: Annotated[uuid.UUID | None, Query()] = None,
    sillon_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[BloqueoRead]:
    stmt = select(Bloqueo).where(Bloqueo.tenant_id == actor.tenant_id)
    if profesional_id is not None:
        stmt = stmt.where(Bloqueo.profesional_id == profesional_id)
    if sillon_id is not None:
        stmt = stmt.where(Bloqueo.sillon_id == sillon_id)
    stmt = stmt.order_by(Bloqueo.desde)
    filas = (await session.execute(stmt)).scalars().all()
    return [BloqueoRead.model_validate(b) for b in filas]


@router.post("/bloqueos", response_model=BloqueoRead, status_code=status.HTTP_201_CREATED)
async def crear_bloqueo_endpoint(
    payload: BloqueoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.BLOQUEOS, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> BloqueoRead:
    bloqueo = await crear_bloqueo(
        session,
        tenant_id=actor.tenant_id,
        profesional_id=payload.profesional_id,
        sillon_id=payload.sillon_id,
        desde=payload.desde,
        hasta=payload.hasta,
        motivo=payload.motivo,
        descripcion=payload.descripcion,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return BloqueoRead.model_validate(bloqueo)


@router.delete("/bloqueos/{bloqueo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_bloqueo_endpoint(
    bloqueo_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.BLOQUEOS, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Response:
    bloqueo = (
        await session.execute(
            select(Bloqueo).where(Bloqueo.id == bloqueo_id, Bloqueo.tenant_id == actor.tenant_id)
        )
    ).scalar_one_or_none()
    if bloqueo is None:
        raise NoEncontrado("Che, ese bloqueo no existe en el consultorio.")

    antes: dict[str, object] = {
        "profesional_id": str(bloqueo.profesional_id) if bloqueo.profesional_id else None,
        "sillon_id": str(bloqueo.sillon_id) if bloqueo.sillon_id else None,
        "desde": asegurar_utc(bloqueo.desde).isoformat(),
        "hasta": asegurar_utc(bloqueo.hasta).isoformat(),
        "motivo": bloqueo.motivo,
    }
    await session.delete(bloqueo)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="bloqueo.eliminar",
        entidad="bloqueo",
        entidad_id=str(bloqueo_id),
        antes=antes,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
