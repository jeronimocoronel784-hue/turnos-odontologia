"""Endpoints para la gestión de pacientes y consentimiento de comunicación (/api/pacientes).

Cumple:
- R1: Schemas Pydantic estrictos con extra='forbid'.
- R4: tenant_id proviene exclusivamente del actor autenticado.
- R7: Baja lógica uniforme (activo = False) sin borrado físico.
- R9: Sin PHI en logs de auditoría ni mensajes de error.
- RBAC: Recurso.PACIENTES (Dueño/Recepción: CRUD, Odontólogo: Lectura).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.schemas_pacientes import (
    PacienteCreate,
    PacienteOptinUpdate,
    PacienteRead,
    PacienteUpdate,
    _limpiar_dni,
)
from app.api.security import ActorAutenticado, requiere
from app.application.auditoria import registrar_auditoria
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.rbac import Accion, Recurso
from app.shared.exceptions import Conflicto, NoEncontrado

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


@router.get("", response_model=list[PacienteRead])
async def listar_pacientes(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    dni: str | None = None,
    telefono: str | None = None,
    q: str | None = None,
    solo_activos: bool = False,
) -> list[Paciente]:
    """Lista o busca pacientes del consultorio del token."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == actor.tenant_id)
    )

    if solo_activos:
        stmt = stmt.where(Paciente.activo.is_(True))

    if dni:
        dni_limpio = _limpiar_dni(dni)
        stmt = stmt.where(Paciente.dni == dni_limpio)

    if telefono:
        tel_limpio = telefono.strip()
        stmt = stmt.where(Paciente.telefono.ilike(f"%{tel_limpio}%"))

    if q:
        termino = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Paciente.nombre.ilike(termino),
                Paciente.dni.ilike(termino),
                Paciente.telefono.ilike(termino),
            )
        )

    stmt = stmt.order_by(Paciente.nombre.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/{paciente_id}", response_model=PacienteRead)
async def obtener_paciente(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Paciente:
    """Obtiene el detalle de un paciente del consultorio."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == actor.tenant_id, Paciente.id == paciente_id)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado en este consultorio.")
    return paciente


@router.post("", response_model=PacienteRead, status_code=status.HTTP_201_CREATED)
async def crear_paciente(
    datos: PacienteCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Paciente:
    """Crea un nuevo paciente junto con su ficha clínica vacía 1:1."""
    # Verificar si ya existe el DNI en el mismo consultorio
    stmt = select(Paciente.id).where(
        Paciente.tenant_id == actor.tenant_id, Paciente.dni == datos.dni
    )
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is not None:
        raise Conflicto("Che, ya existe un paciente registrado con el DNI en este consultorio.")

    nuevo_paciente = Paciente(
        tenant_id=actor.tenant_id,
        nombre=datos.nombre,
        dni=datos.dni,
        telefono=datos.telefono,
        email=str(datos.email) if datos.email else None,
        fecha_nac=datos.fecha_nac,
        obra_social_id=datos.obra_social_id,
        nro_afiliado=datos.nro_afiliado,
        optin_wa=datos.optin_wa,
        observaciones=datos.observaciones,
        activo=True,
    )
    session.add(nuevo_paciente)
    await session.flush()

    # Inicializar FichaClinica 1:1
    ficha = FichaClinica(
        tenant_id=actor.tenant_id,
        paciente_id=nuevo_paciente.id,
    )
    session.add(ficha)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="paciente.crear",
        entidad="paciente",
        entidad_id=str(nuevo_paciente.id),
        despues={
            "id": str(nuevo_paciente.id),
            "optin_wa": nuevo_paciente.optin_wa,
            "activo": nuevo_paciente.activo,
        },
    )

    nuevo_paciente.ficha_clinica = ficha
    return nuevo_paciente


@router.patch("/{paciente_id}", response_model=PacienteRead)
async def actualizar_paciente(
    paciente_id: uuid.UUID,
    datos: PacienteUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Paciente:
    """Actualiza datos de contacto o cobertura de un paciente."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == actor.tenant_id, Paciente.id == paciente_id)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado para actualizar.")

    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return paciente

    antes: dict[str, object] = {"activo": paciente.activo, "optin_wa": paciente.optin_wa}

    for campo, valor in cambios.items():
        if campo == "email" and valor is not None:
            valor = str(valor)
        setattr(paciente, campo, valor)

    await session.flush()

    despues: dict[str, object] = {"activo": paciente.activo, "optin_wa": paciente.optin_wa}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="paciente.actualizar",
        entidad="paciente",
        entidad_id=str(paciente.id),
        antes=antes,
        despues=despues,
    )

    return paciente


@router.delete("/{paciente_id}", response_model=PacienteRead)
async def dar_de_baja_paciente(
    paciente_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.BORRAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Paciente:
    """Baja lógica de paciente (activo = False, R7)."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == actor.tenant_id, Paciente.id == paciente_id)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado para dar de baja.")

    if not paciente.activo:
        return paciente

    paciente.activo = False
    await session.flush()

    antes_baja: dict[str, object] = {"activo": True}
    despues_baja: dict[str, object] = {"activo": False}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="paciente.baja",
        entidad="paciente",
        entidad_id=str(paciente.id),
        antes=antes_baja,
        despues=despues_baja,
    )

    return paciente


@router.patch("/{paciente_id}/optin", response_model=PacienteRead)
async def actualizar_optin_whatsapp(
    paciente_id: uuid.UUID,
    datos: PacienteOptinUpdate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.PACIENTES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> Paciente:
    """Actualiza el consentimiento para mensajes de WhatsApp (alta o baja STOP)."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == actor.tenant_id, Paciente.id == paciente_id)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()
    if paciente is None:
        raise NoEncontrado("Che, no encontramos al paciente solicitado.")

    antes_optin = paciente.optin_wa
    paciente.optin_wa = datos.optin_wa
    await session.flush()

    antes_dict: dict[str, object] = {"optin_wa": antes_optin}
    despues_dict: dict[str, object] = {"optin_wa": datos.optin_wa}

    await registrar_auditoria(
        session,
        tenant_id=actor.tenant_id,
        actor_id=actor.usuario_id,
        accion="paciente.optin",
        entidad="paciente",
        entidad_id=str(paciente.id),
        antes=antes_dict,
        despues=despues_dict,
    )

    return paciente
