"""Casos de uso y lógica de aplicación para Pacientes (C-05).

Incluye:
- `get_or_create_paciente`: alta implícita para reserva pública sin login (resuelve PO).
- `procesar_baja_stop`: corte inmediato de envíos de WhatsApp ante comando STOP (RN-CO-01).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas_pacientes import _limpiar_dni
from app.application.auditoria import registrar_auditoria
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente


async def get_or_create_paciente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nombre: str,
    dni: str,
    telefono: str,
    email: str | None = None,
    fecha_nac: date | None = None,
    obra_social_id: uuid.UUID | None = None,
    nro_afiliado: str | None = None,
    optin_wa: bool = False,
) -> tuple[Paciente, bool]:
    """Obtiene un paciente por su DNI dentro del consultorio o lo crea con su ficha clínica.

    Retorna una tupla `(paciente, creado: bool)`.
    """
    dni_norm = _limpiar_dni(dni)
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.ficha_clinica))
        .where(Paciente.tenant_id == tenant_id, Paciente.dni == dni_norm)
    )
    res = await session.execute(stmt)
    paciente = res.scalar_one_or_none()

    if paciente is not None:
        # Actualizar datos de contacto si fueron provistos
        if nombre and nombre.strip():
            paciente.nombre = nombre.strip()
        if telefono and telefono.strip():
            paciente.telefono = telefono.strip()
        if email:
            paciente.email = email.strip()
        if fecha_nac is not None:
            paciente.fecha_nac = fecha_nac
        if obra_social_id is not None:
            paciente.obra_social_id = obra_social_id
        if nro_afiliado:
            paciente.nro_afiliado = nro_afiliado.strip()

        # Si estaba dado de baja y vuelve a reservar, reactivar
        if not paciente.activo:
            paciente.activo = True

        # Asegurar ficha clínica 1:1
        if paciente.ficha_clinica is None:
            ficha = FichaClinica(tenant_id=tenant_id, paciente_id=paciente.id)
            session.add(ficha)
            await session.flush()
            paciente.ficha_clinica = ficha

        await session.flush()
        return paciente, False

    # Crear nuevo paciente
    nuevo_paciente = Paciente(
        tenant_id=tenant_id,
        nombre=nombre.strip(),
        dni=dni_norm,
        telefono=telefono.strip(),
        email=email.strip() if email else None,
        fecha_nac=fecha_nac,
        obra_social_id=obra_social_id,
        nro_afiliado=nro_afiliado.strip() if nro_afiliado else None,
        optin_wa=optin_wa,
        activo=True,
    )
    session.add(nuevo_paciente)
    await session.flush()

    # Crear FichaClinica 1:1
    ficha = FichaClinica(
        tenant_id=tenant_id,
        paciente_id=nuevo_paciente.id,
    )
    session.add(ficha)
    await session.flush()

    despues_crear: dict[str, object] = {
        "id": str(nuevo_paciente.id),
        "optin_wa": nuevo_paciente.optin_wa,
        "activo": nuevo_paciente.activo,
    }

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        accion="paciente.crear",
        entidad="paciente",
        entidad_id=str(nuevo_paciente.id),
        despues=despues_crear,
    )

    nuevo_paciente.ficha_clinica = ficha
    return nuevo_paciente, True


async def procesar_baja_stop(
    session: AsyncSession,
    paciente: Paciente,
    actor_id: uuid.UUID | None = None,
) -> Paciente:
    """Procesa una baja STOP de WhatsApp cortando inmediatamente los envíos (RN-CO-01)."""
    antes_optin = paciente.optin_wa
    paciente.optin_wa = False
    await session.flush()

    antes_stop: dict[str, object] = {"optin_wa": antes_optin}
    despues_stop: dict[str, object] = {"optin_wa": False}

    await registrar_auditoria(
        session,
        tenant_id=paciente.tenant_id,
        actor_id=actor_id,
        accion="paciente.baja_stop",
        entidad="paciente",
        entidad_id=str(paciente.id),
        antes=antes_stop,
        despues=despues_stop,
    )

    return paciente
