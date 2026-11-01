"""Endpoints para Presupuestos y Planes de Tratamiento (/api/presupuestos, C-10).

Cumple:
- R1 / R8: Schemas Pydantic v2 estrictos con extra='forbid'; montos calculados en servidor.
- R4: tenant_id proviene exclusivamente del JWT (ActorAutenticado).
- RBAC: Recurso.PRESUPUESTOS (Dueño, Recepción, Odontólogo: CRUD).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_presupuestos import (
    PresupuestoCreate,
    PresupuestoItemInput,
    PresupuestoRead,
    PresupuestoTurnoRead,
    PresupuestoVincularTurnoInput,
)
from app.api.security import ActorAutenticado, requiere
from app.application.presupuestos import (
    aceptar_presupuesto,
    agregar_item_presupuesto,
    cambiar_estado_presupuesto,
    crear_presupuesto,
    listar_presupuestos,
    listar_turnos_presupuesto,
    obtener_presupuesto,
    vincular_turno_a_presupuesto,
)
from app.domain.presupuesto import EstadoPresupuesto, PresupuestoTurno
from app.domain.rbac import Accion, Recurso

router = APIRouter(prefix="/presupuestos", tags=["presupuestos"])


@router.get("", response_model=list[PresupuestoRead])
async def get_presupuestos(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    paciente_id: uuid.UUID | None = None,
    estado: str | None = None,
) -> list[PresupuestoRead]:
    """Lista los presupuestos del consultorio."""
    return await listar_presupuestos(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        estado=estado,
    )


@router.post("", response_model=PresupuestoRead, status_code=status.HTTP_201_CREATED)
async def post_presupuesto(
    datos: PresupuestoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Crea un presupuesto calculando sus items y cobertura OS en servidor (RN-OS-01, R8)."""
    return await crear_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.get("/{presupuesto_id}", response_model=PresupuestoRead)
async def get_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Obtiene el detalle de un presupuesto con sus items y turnos vinculados."""
    return await obtener_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
    )


@router.post(
    "/{presupuesto_id}/items",
    response_model=PresupuestoRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_item_presupuesto(
    presupuesto_id: uuid.UUID,
    datos: PresupuestoItemInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Agrega un item a un presupuesto y recalcula sus totales en servidor."""
    return await agregar_item_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        item_input=datos,
        actor_id=actor.usuario_id,
    )


@router.post("/{presupuesto_id}/presentar", response_model=PresupuestoRead)
async def post_presentar_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Pasa un presupuesto en borrador a estado presentado."""
    return await cambiar_estado_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        nuevo_estado=EstadoPresupuesto.PRESENTADO,
        actor_id=actor.usuario_id,
    )


@router.post("/{presupuesto_id}/aceptar", response_model=PresupuestoRead)
async def post_aceptar_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Acepta un presupuesto verificando consentimiento en prestaciones invasivas (RN-CL-04)."""
    return await aceptar_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        actor_id=actor.usuario_id,
    )


@router.post("/{presupuesto_id}/rechazar", response_model=PresupuestoRead)
async def post_rechazar_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Marca un presupuesto como rechazado."""
    return await cambiar_estado_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        nuevo_estado=EstadoPresupuesto.RECHAZADO,
        actor_id=actor.usuario_id,
    )


@router.post("/{presupuesto_id}/finalizar", response_model=PresupuestoRead)
async def post_finalizar_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoRead:
    """Marca un plan de tratamiento como finalizado."""
    return await cambiar_estado_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        nuevo_estado=EstadoPresupuesto.FINALIZADO,
        actor_id=actor.usuario_id,
    )


@router.get("/{presupuesto_id}/turnos", response_model=list[PresupuestoTurnoRead])
async def get_turnos_presupuesto(
    presupuesto_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[PresupuestoTurno]:
    """Lista los turnos vinculados al plan de tratamiento."""
    return await listar_turnos_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
    )


@router.post(
    "/{presupuesto_id}/turnos",
    response_model=PresupuestoTurnoRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_turno_presupuesto(
    presupuesto_id: uuid.UUID,
    datos: PresupuestoVincularTurnoInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PRESUPUESTOS, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PresupuestoTurno:
    """Vincula un turno al plan de tratamiento y pasa el presupuesto a en_curso (US-022)."""
    return await vincular_turno_a_presupuesto(
        session,
        tenant_id=actor.tenant_id,
        presupuesto_id=presupuesto_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
