"""Lectura del trail de auditor��a (`/api/auditoria`, C-14, D2)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_auditoria import AuditoriaEventoRead, AuditoriaPaginaRead
from app.api.security import ActorAutenticado, requiere
from app.application.auditoria import listar_auditoria
from app.domain.rbac import Accion, Recurso
from app.shared.exceptions import NoEncontrado

router = APIRouter(tags=["auditoria"])


@router.get("/auditoria", response_model=AuditoriaPaginaRead)
async def get_auditoria(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AUDITORIA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    entidad: Annotated[str | None, Query(max_length=60)] = None,
    entidad_id: Annotated[str | None, Query(max_length=60)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    accion: Annotated[str | None, Query(max_length=60)] = None,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
    limite: Annotated[int, Query()] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> AuditoriaPaginaRead:
    """Lee el trail append-only del consultorio con filtros y paginaci��n keyset (D2)."""
    eventos, siguiente = await listar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        entidad=entidad,
        entidad_id=entidad_id,
        actor_id=actor_id,
        accion=accion,
        desde=desde,
        hasta=hasta,
        limite=limite,
        cursor=cursor,
    )
    return AuditoriaPaginaRead(
        eventos=[AuditoriaEventoRead.model_validate(e) for e in eventos],
        siguiente_cursor=siguiente,
    )


@router.get("/auditoria/{evento_id}", response_model=AuditoriaEventoRead)
async def get_auditoria_evento(
    evento_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.AUDITORIA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> AuditoriaEventoRead:
    """El trail es solo de lectura por colección; no hay lectura individual (append-only, R7)."""
    raise NoEncontrado("No encontramos ese evento de auditoría.")
