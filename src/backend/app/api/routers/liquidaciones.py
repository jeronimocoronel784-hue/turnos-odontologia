"""Endpoints de cobertura de obra social y liquidaciones (`/api/os/*`, `/api/liquidaciones`, C-13).

Cumple:
- R1 / R8: schemas Pydantic v2 estrictos (`extra='forbid'`) y montos calculados en servidor.
- R4: `tenant_id` proviene exclusivamente del JWT (`ActorAutenticado`), nunca del body/query.
- R7: la baja de un borrador es lógica (`DELETE` cambia el estado a `anulada`).
- N8/R3: cada mutación cierra su transacción con un `commit` explícito: sin eso la
  liquidación no se persistía fuera del contexto de pruebas.
- RBAC (`D8`): `Recurso.LIQUIDACIONES` — Dueño y Recepción con CRUD + exportación; el
  Odontólogo queda en sólo lectura (puede consultar la cobertura de sus turnos).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_liquidaciones import (
    CoberturaLookupRead,
    LiquidacionOSAnularInput,
    LiquidacionOSCerrarInput,
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSRead,
    ResultadoOSInput,
)
from app.api.security import ActorAutenticado, requiere
from app.application.cobertura import consultar_cobertura
from app.application.liquidaciones import (
    anular_liquidacion,
    exportar_liquidacion,
    generar_borrador,
    listar_liquidaciones,
    obtener_liquidacion_read,
    presentar_liquidacion,
    registrar_debitos,
    registrar_resultado,
)
from app.domain.liquidacion_os import EstadoLiquidacionOS
from app.domain.rbac import Accion, Recurso

router = APIRouter(tags=["liquidaciones"])


# ---------------------------------------------------------------------------
# Cobertura de obra social (US-040, RN-OS-01)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Liquidaciones mensuales (US-041, RN-OS-02)
# ---------------------------------------------------------------------------


@router.get("/liquidaciones", response_model=list[LiquidacionOSRead])
async def get_liquidaciones(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    obra_social: Annotated[str | None, Query(max_length=160)] = None,
    periodo: Annotated[str | None, Query(min_length=6, max_length=6)] = None,
    estado: Annotated[EstadoLiquidacionOS | None, Query()] = None,
) -> list[LiquidacionOSRead]:
    """Lista las liquidaciones del consultorio filtrables por OS, período y estado."""
    return await listar_liquidaciones(
        session,
        tenant_id=actor.tenant_id,
        obra_social=obra_social,
        periodo=periodo,
        estado=estado,
    )


@router.post(
    "/liquidaciones",
    response_model=LiquidacionOSRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_liquidacion(
    datos: LiquidacionOSCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> LiquidacionOSRead:
    """Genera el borrador con los turnos finalizados del período y su cobertura (D5)."""
    liquidacion = await generar_borrador(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return liquidacion


@router.get("/liquidaciones/{liquidacion_id}", response_model=LiquidacionOSRead)
async def get_liquidacion(
    liquidacion_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> LiquidacionOSRead:
    """Consulta una liquidación con su detalle por turno (404 si es de otro tenant, R4)."""
    return await obtener_liquidacion_read(
        session, tenant_id=actor.tenant_id, liquidacion_id=liquidacion_id
    )


@router.patch("/liquidaciones/{liquidacion_id}", response_model=LiquidacionOSRead)
async def patch_liquidacion(
    liquidacion_id: uuid.UUID,
    datos: LiquidacionOSDebitosInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> LiquidacionOSRead:
    """Registra los débitos de la OS sobre el borrador y recalcula totales (US-041, R8)."""
    liquidacion = await registrar_debitos(
        session,
        tenant_id=actor.tenant_id,
        liquidacion_id=liquidacion_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return liquidacion


@router.post("/liquidaciones/{liquidacion_id}/cerrar", response_model=LiquidacionOSRead)
async def post_cerrar_liquidacion(
    liquidacion_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    datos: LiquidacionOSCerrarInput | None = None,
) -> LiquidacionOSRead:
    """Presenta el borrador a la obra social fijando actor y fecha (D4)."""
    liquidacion = await presentar_liquidacion(
        session,
        tenant_id=actor.tenant_id,
        liquidacion_id=liquidacion_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return liquidacion


@router.post("/liquidaciones/{liquidacion_id}/resultado", response_model=LiquidacionOSRead)
async def post_resultado_liquidacion(
    liquidacion_id: uuid.UUID,
    datos: ResultadoOSInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> LiquidacionOSRead:
    """Registra la respuesta de la OS: `pagada` o `con_debitos` (US-041, D4)."""
    liquidacion = await registrar_resultado(
        session,
        tenant_id=actor.tenant_id,
        liquidacion_id=liquidacion_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return liquidacion


@router.delete("/liquidaciones/{liquidacion_id}", response_model=LiquidacionOSRead)
async def delete_liquidacion(
    liquidacion_id: uuid.UUID,
    datos: LiquidacionOSAnularInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> LiquidacionOSRead:
    """Anula el borrador por baja lógica, conservando cabecera y detalle (R7, D4)."""
    liquidacion = await anular_liquidacion(
        session,
        tenant_id=actor.tenant_id,
        liquidacion_id=liquidacion_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return liquidacion


@router.get("/liquidaciones/{liquidacion_id}/exportar", response_class=Response)
async def get_exportar_liquidacion(
    liquidacion_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.LIQUIDACIONES, Accion.EXPORTAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    formato: Annotated[str, Query(max_length=10)] = "csv",
) -> Response:
    """Descarga la liquidación armada en servidor, sin PHI del paciente (D7, R8, R9)."""
    exportacion = await exportar_liquidacion(
        session,
        tenant_id=actor.tenant_id,
        liquidacion_id=liquidacion_id,
        formato=formato,
    )
    return Response(
        content=exportacion.contenido,
        media_type=exportacion.media_type,
        headers=exportacion.cabeceras(),
    )
