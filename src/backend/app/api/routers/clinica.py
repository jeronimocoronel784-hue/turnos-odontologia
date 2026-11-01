"""Endpoints para Historia Clínica, Odontograma FDI, Consentimientos y Firma Pública (C-09).

Cumple:
- R1: Schemas Pydantic v2 estrictos con extra='forbid'.
- R4: tenant_id proviene exclusivamente del JWT (ActorAutenticado) o del TokenGestion público.
- R7 / RN-CL-01: Sin endpoints destructivos en evolución ni pieza_evento.
- RN-CL-03: Recurso.CLINICA (ODONTOLOGO/DUENO: CRUD, RECEPCION: SOLO_LECTURA).
- RN-CL-02 / RN-SE-03: Recurso.CONSENTIMIENTOS y ruta pública `/firmar/{token}`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_clinica import (
    AdjuntoCreate,
    AdjuntoRead,
    ConsentimientoCreate,
    ConsentimientoFirmaInput,
    ConsentimientoPublicoRead,
    ConsentimientoRead,
    ConsentimientoRevocarInput,
    EvolucionCreate,
    EvolucionRead,
    FichaClinicaDetalleRead,
    FichaClinicaUpdate,
    OdontogramaRead,
    PiezaEventoCreate,
    PiezaEventoRead,
)
from app.api.security import ActorAutenticado, requiere
from app.application.clinica import (
    actualizar_ficha_clinica,
    crear_adjunto_clinico,
    crear_consentimiento,
    crear_evolucion,
    firmar_consentimiento,
    firmar_consentimiento_por_token,
    listar_adjuntos_paciente,
    listar_consentimientos,
    listar_evoluciones_paciente,
    listar_historial_pieza,
    obtener_consentimiento_por_token,
    obtener_ficha_clinica,
    obtener_odontograma_paciente,
    registrar_evento_pieza,
    revocar_consentimiento,
)
from app.domain.clinica import AdjuntoClinico, Consentimiento, Evolucion, PiezaEvento
from app.domain.ficha_clinica import FichaClinica
from app.domain.rbac import Accion, Recurso

router = APIRouter(tags=["clinica"])
router_publico_firma = APIRouter(prefix="/firmar", tags=["consentimiento-publico"])


@router.get("/pacientes/{paciente_id}/ficha", response_model=FichaClinicaDetalleRead)
async def get_ficha_paciente(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> FichaClinica:
    """Obtiene la ficha clínica/anamnesis 1:1 del paciente (Dueño, Odontólogo y Recepción)."""
    return await obtener_ficha_clinica(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
    )


@router.put("/pacientes/{paciente_id}/ficha", response_model=FichaClinicaDetalleRead)
async def put_ficha_paciente(
    paciente_id: uuid.UUID,
    datos: FichaClinicaUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> FichaClinica:
    """Actualiza la ficha clínica (solo rol clínico) y genera Evolucion + Auditoria."""
    return await actualizar_ficha_clinica(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.get("/pacientes/{paciente_id}/evoluciones", response_model=list[EvolucionRead])
async def get_evoluciones_paciente(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[Evolucion]:
    """Lista las evoluciones clínicas inmutables de un paciente."""
    return await listar_evoluciones_paciente(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
    )


@router.post(
    "/pacientes/{paciente_id}/evoluciones",
    response_model=EvolucionRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_evolucion_paciente(
    paciente_id: uuid.UUID,
    datos: EvolucionCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Evolucion:
    """Registra una evolución clínica append-only o una enmienda aditiva (solo rol clínico)."""
    return await crear_evolucion(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.get("/pacientes/{paciente_id}/adjuntos", response_model=list[AdjuntoRead])
async def get_adjuntos_paciente(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[AdjuntoClinico]:
    """Lista los adjuntos clínicos asociados a la HCE del paciente."""
    return await listar_adjuntos_paciente(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
    )


@router.post(
    "/pacientes/{paciente_id}/adjuntos",
    response_model=AdjuntoRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_adjunto_paciente(
    paciente_id: uuid.UUID,
    datos: AdjuntoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> AdjuntoClinico:
    """Registra metadatos de un adjunto clínico (RX, foto, PDF) en la HCE del paciente."""
    return await crear_adjunto_clinico(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.get("/odontograma/{paciente_id}", response_model=OdontogramaRead)
async def get_odontograma(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> OdontogramaRead:
    """Obtiene el odontograma FDI del paciente con el estado proyectado por pieza/superficie."""
    return await obtener_odontograma_paciente(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
    )


@router.post(
    "/odontograma/{paciente_id}/eventos",
    response_model=PiezaEventoRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_evento_odontograma(
    paciente_id: uuid.UUID,
    datos: PiezaEventoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PiezaEvento:
    """Registra un evento inmutable sobre una pieza y superficie del odontograma FDI (RN-CL-01)."""
    return await registrar_evento_pieza(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.get(
    "/odontograma/{paciente_id}/piezas/{pieza_fdi}/historial",
    response_model=list[PiezaEventoRead],
)
async def get_historial_pieza_odontograma(
    paciente_id: uuid.UUID,
    pieza_fdi: int,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CLINICA, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[PiezaEvento]:
    """Devuelve el historial cronológico inmutable de eventos de una pieza FDI."""
    return await listar_historial_pieza(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        pieza_fdi=pieza_fdi,
    )


@router.get("/consentimientos", response_model=list[ConsentimientoRead])
async def get_consentimientos(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONSENTIMIENTOS, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    paciente_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
) -> list[Consentimiento]:
    """Lista los consentimientos informados del consultorio."""
    return await listar_consentimientos(
        session,
        tenant_id=actor.tenant_id,
        paciente_id=paciente_id,
        turno_id=turno_id,
    )


@router.post(
    "/consentimientos",
    response_model=ConsentimientoRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_consentimiento(
    datos: ConsentimientoCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.CONSENTIMIENTOS, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ConsentimientoRead:
    """Emite un consentimiento informado pendiente de firma y devuelve su token público."""
    cons, token_firma = await crear_consentimiento(
        session,
        tenant_id=actor.tenant_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )
    lectura = ConsentimientoRead.model_validate(cons)
    lectura.token_firma = token_firma
    return lectura


@router.post("/consentimientos/{consentimiento_id}/firmar", response_model=ConsentimientoRead)
async def post_firmar_consentimiento(
    consentimiento_id: uuid.UUID,
    datos: ConsentimientoFirmaInput,
    actor: Annotated[
        ActorAutenticado, Depends(requiere(Recurso.CONSENTIMIENTOS, Accion.ACTUALIZAR))
    ],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Consentimiento:
    """Registra la firma presencial de un consentimiento informado."""
    return await firmar_consentimiento(
        session,
        tenant_id=actor.tenant_id,
        consentimiento_id=consentimiento_id,
        datos=datos,
        actor_id=actor.usuario_id,
    )


@router.post("/consentimientos/{consentimiento_id}/revocar", response_model=ConsentimientoRead)
async def post_revocar_consentimiento(
    consentimiento_id: uuid.UUID,
    datos: ConsentimientoRevocarInput,
    actor: Annotated[
        ActorAutenticado, Depends(requiere(Recurso.CONSENTIMIENTOS, Accion.ACTUALIZAR))
    ],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Consentimiento:
    """Revoca un consentimiento informado dejando registro en Auditoria (RN-CL-02)."""
    return await revocar_consentimiento(
        session,
        tenant_id=actor.tenant_id,
        consentimiento_id=consentimiento_id,
        motivo=datos.motivo,
        actor_id=actor.usuario_id,
    )


@router_publico_firma.get("/{token}", response_model=ConsentimientoPublicoRead)
async def get_consentimiento_publico(
    token: str,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> ConsentimientoPublicoRead:
    """Obtiene el consentimiento para firma pública por token sin login (RN-SE-03)."""
    return await obtener_consentimiento_por_token(session, token=token)


@router_publico_firma.post("/{token}", response_model=ConsentimientoRead)
async def post_firmar_consentimiento_publico(
    token: str,
    datos: ConsentimientoFirmaInput,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Consentimiento:
    """Firma el consentimiento informado mediante su token_gestion público (`/firmar/{token}`)."""
    return await firmar_consentimiento_por_token(session, token=token, datos=datos)
