"""Endpoints de Señas y Caja diaria (/api/senas*, /api/caja/*, C-11).

Cumple:
- R1 / R8: Schemas Pydantic v2 estrictos (`extra='forbid'`); montos calculados en servidor.
- R4: `tenant_id` proviene exclusivamente del JWT (`ActorAutenticado`), nunca del body/query.
- RBAC: `Recurso.CAJA` (Dueño: CRUD; Recepción: CRUD; Odontólogo: solo lectura) y
  `Accion.REABRIR_CIERRE` exclusiva del Dueño para reabrir un cierre cerrado.
- RN-PA-05: el cierre cerrado es inmutable (`409` al intentar cerrarlo de nuevo).
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_caja import (
    CierreCajaAbrirInput,
    CierreCajaCerrarInput,
    CierreCajaReabrirInput,
    CierreCajaRead,
    CobrarTurnoInput,
    LiquidacionTurnoRead,
    MovimientoCajaCreate,
    MovimientoCajaRead,
    SenaCobrarInput,
    SenaCreate,
    SenaRead,
    SenaResolverCancelacionInput,
)
from app.api.security import ActorAutenticado, requiere
from app.application.caja import (
    abrir_cierre_caja,
    calcular_liquidacion_turno,
    cerrar_caja,
    cobrar_saldo_turno,
    cobrar_sena,
    crear_sena,
    listar_cierres,
    listar_movimientos,
    listar_senas,
    obtener_cierre,
    obtener_sena,
    reabrir_caja,
    registrar_movimiento_caja,
    resolver_sena_por_cancelacion,
    vencer_sena_impaga,
)
from app.domain.caja import EstadoCierreCaja, EstadoSena
from app.domain.rbac import Accion, Recurso

router = APIRouter(tags=["caja"])


# ---------------------------------------------------------------------------
# Señas
# ---------------------------------------------------------------------------


@router.get("/senas", response_model=list[SenaRead])
async def get_senas(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    turno_id: Annotated[uuid.UUID | None, Query()] = None,
    estado: Annotated[EstadoSena | None, Query()] = None,
) -> list[SenaRead]:
    """Lista las señas del consultorio filtrables por turno o estado."""
    senas = await listar_senas(
        session,
        tenant_id=actor.tenant_id,
        turno_id=turno_id,
        estado=estado,
    )
    return [SenaRead.model_validate(s) for s in senas]


@router.post("/senas", response_model=SenaRead, status_code=status.HTTP_201_CREATED)
async def post_sena(
    datos: SenaCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> SenaRead:
    """Genera la seña `pendiente` de un turno con el monto de su prestación (RN-PA-02, R8)."""
    sena = await crear_sena(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return SenaRead.model_validate(sena)


@router.get("/senas/{sena_id}", response_model=SenaRead)
async def get_sena(
    sena_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> SenaRead:
    """Consulta una seña del consultorio."""
    sena = await obtener_sena(session, tenant_id=actor.tenant_id, sena_id=sena_id)
    return SenaRead.model_validate(sena)


@router.post("/senas/{sena_id}/cobrar", response_model=SenaRead)
async def post_cobrar_sena(
    sena_id: uuid.UUID,
    datos: SenaCobrarInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> SenaRead:
    """Cobra la seña, habilita la confirmación del turno y registra el ingreso (RN-PA-01/05)."""
    sena = await cobrar_sena(
        session,
        tenant_id=actor.tenant_id,
        sena_id=sena_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return SenaRead.model_validate(sena)


@router.post("/senas/{sena_id}/cancelacion", response_model=SenaRead)
async def post_resolver_sena_cancelacion(
    sena_id: uuid.UUID,
    datos: SenaResolverCancelacionInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> SenaRead:
    """Resuelve la seña al cancelar el turno: `devuelta` en término, `aplicada` fuera (RN-PA-04)."""
    sena = await resolver_sena_por_cancelacion(
        session,
        tenant_id=actor.tenant_id,
        sena_id=sena_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return SenaRead.model_validate(sena)


@router.post("/senas/{sena_id}/vencer", response_model=SenaRead)
async def post_vencer_sena(
    sena_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> SenaRead:
    """Vence la seña impaga y cancela el turno liberando el slot (Flujo 1 paso 6)."""
    sena = await vencer_sena_impaga(
        session,
        tenant_id=actor.tenant_id,
        sena_id=sena_id,
        actor_id=actor.usuario_id,
    )
    return SenaRead.model_validate(sena)


# ---------------------------------------------------------------------------
# Caja: movimientos
# ---------------------------------------------------------------------------


@router.get("/caja/movimientos", response_model=list[MovimientoCajaRead])
async def get_movimientos(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    cierre_id: Annotated[uuid.UUID | None, Query()] = None,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
) -> list[MovimientoCajaRead]:
    """Lista los movimientos append-only del consultorio (R7) con filtros de conciliación."""
    movimientos = await listar_movimientos(
        session,
        tenant_id=actor.tenant_id,
        cierre_id=cierre_id,
        desde=desde,
        hasta=hasta,
    )
    return [MovimientoCajaRead.model_validate(m) for m in movimientos]


@router.post(
    "/caja/movimientos",
    response_model=MovimientoCajaRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_movimiento(
    datos: MovimientoCajaCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> MovimientoCajaRead:
    """Registra un ingreso/egreso asociado automáticamente al cierre abierto (RN-PA-05)."""
    movimiento = await registrar_movimiento_caja(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return MovimientoCajaRead.model_validate(movimiento)


# ---------------------------------------------------------------------------
# Caja: cierres diarios
# ---------------------------------------------------------------------------


@router.get("/caja/cierre", response_model=list[CierreCajaRead])
async def get_cierres(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    fecha: Annotated[date | None, Query()] = None,
    estado: Annotated[EstadoCierreCaja | None, Query()] = None,
) -> list[CierreCajaRead]:
    """Lista los cierres diarios del consultorio."""
    cierres = await listar_cierres(
        session,
        tenant_id=actor.tenant_id,
        fecha=fecha,
        estado=estado,
    )
    return [CierreCajaRead.model_validate(c) for c in cierres]


@router.post(
    "/caja/cierre",
    response_model=CierreCajaRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_abrir_cierre(
    datos: CierreCajaAbrirInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CierreCajaRead:
    """Abre el cierre diario de caja (uno por fecha y consultorio, D3)."""
    cierre = await abrir_cierre_caja(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return CierreCajaRead.model_validate(cierre)


@router.get("/caja/cierre/{cierre_id}", response_model=CierreCajaRead)
async def get_cierre(
    cierre_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CierreCajaRead:
    """Consulta un cierre de caja con sus totales y diferencia."""
    cierre = await obtener_cierre(session, tenant_id=actor.tenant_id, cierre_id=cierre_id)
    return CierreCajaRead.model_validate(cierre)


@router.post("/caja/cierre/{cierre_id}/cerrar", response_model=CierreCajaRead)
async def post_cerrar_caja(
    cierre_id: uuid.UUID,
    datos: CierreCajaCerrarInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CierreCajaRead:
    """Cierra la caja calculando `total_sistema` y la `diferencia` visible (RN-PA-05)."""
    cierre = await cerrar_caja(
        session,
        tenant_id=actor.tenant_id,
        cierre_id=cierre_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return CierreCajaRead.model_validate(cierre)


@router.post("/caja/cierre/{cierre_id}/reabrir", response_model=CierreCajaRead)
async def post_reabrir_caja(
    cierre_id: uuid.UUID,
    datos: CierreCajaReabrirInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.REABRIR_CIERRE))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> CierreCajaRead:
    """Reabre un cierre cerrado: exclusivo del Dueño y auditado (RN-SE-01, US-030)."""
    cierre = await reabrir_caja(
        session,
        tenant_id=actor.tenant_id,
        cierre_id=cierre_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return CierreCajaRead.model_validate(cierre)


# ---------------------------------------------------------------------------
# Caja: liquidación y cobro del saldo de la atención (Flujo 4)
# ---------------------------------------------------------------------------


@router.get("/caja/turnos/{turno_id}/liquidacion", response_model=LiquidacionTurnoRead)
async def get_liquidacion_turno(
    turno_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    obra_social: Annotated[str | None, Query(max_length=160)] = None,
) -> LiquidacionTurnoRead:
    """Calcula en servidor el saldo de la atención (R8, Flujo 4)."""
    return await calcular_liquidacion_turno(
        session,
        tenant_id=actor.tenant_id,
        turno_id=turno_id,
        obra_social=obra_social,
    )


@router.post(
    "/caja/turnos/{turno_id}/cobrar",
    response_model=MovimientoCajaRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_cobrar_turno(
    turno_id: uuid.UUID,
    datos: CobrarTurnoInput,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CAJA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> MovimientoCajaRead:
    """Cobra el saldo de la atención y aplica la seña cobrada (Flujo 4, R8)."""
    movimiento = await cobrar_saldo_turno(
        session,
        tenant_id=actor.tenant_id,
        turno_id=turno_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    return MovimientoCajaRead.model_validate(movimiento)
