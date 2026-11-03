"""Endpoints de cobertura de obra social y liquidaciones (`/api/os/*`, `/api/liquidaciones`, C-13).

Cumple:
- R1 / R8: schemas Pydantic v2 estrictos (`extra='forbid'`) y montos calculados en servidor.
- R4: `tenant_id` proviene exclusivamente del JWT (`ActorAutenticado`), nunca del body/query.
- RBAC (`D8`): `Recurso.LIQUIDACIONES` — Dueño y Recepción con CRUD + exportación; el
  Odontólogo queda en sólo lectura (puede consultar la cobertura de sus turnos).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_liquidaciones import CoberturaLookupRead
from app.api.security import ActorAutenticado, requiere
from app.application.cobertura import consultar_cobertura
from app.domain.rbac import Accion, Recurso

router = APIRouter(tags=["liquidaciones"])


@router.get("/os/cobertura", response_model=CoberturaLookupRead)
async def get_cobertura(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    prestacion_id: Annotated[uuid.UUID | None, Query()] = None,
    turno_id: Annotated[uuid.UUID | None, Query()] = None,
    obra_social: Annotated[str | None, Query(max_length=160)] = None,
    fecha: Annotated[date | None, Query()] = None,
    cantidad: Annotated[int, Query(ge=1, le=99)] = 1,
) -> CoberturaLookupRead:
    """Resuelve la cobertura vigente de una prestación o de un turno (US-040, RN-OS-01)."""
    consulta = await consultar_cobertura(
        session,
        tenant_id=actor.tenant_id,
        prestacion_id=prestacion_id,
        turno_id=turno_id,
        obra_social=obra_social,
        fecha=fecha,
        cantidad=cantidad,
    )
    resolucion = consulta.resolucion
    return CoberturaLookupRead(
        prestacion_id=consulta.prestacion_id,
        obra_social=consulta.obra_social,
        cobertura_id=resolucion.cobertura_id,
        precio_particular=resolucion.precio_particular,
        cobertura=resolucion.cobertura,
        monto_a_cargo=resolucion.monto_a_cargo,
        estado_arancel=resolucion.estado_arancel,
        vigencia_desde=resolucion.vigencia_desde,
        vigencia_hasta=resolucion.vigencia_hasta,
        arancel_vencido=resolucion.arancel_vencido,
        advertencia=resolucion.advertencia,
    )
