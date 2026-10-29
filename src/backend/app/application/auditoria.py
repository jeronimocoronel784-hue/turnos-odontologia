"""Registro de auditoría append-only reutilizable (RN-SE-01).

Nunca guarda PHI ni credenciales: solo actor, acción, entidad y el diff mínimo
necesario para reconstruir quién hizo qué y cuándo (R9).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria


async def registrar_auditoria(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    accion: str,
    entidad: str,
    entidad_id: str,
    actor_id: uuid.UUID | None = None,
    antes: dict[str, object] | None = None,
    despues: dict[str, object] | None = None,
) -> Auditoria:
    """Inserta el evento en la misma transacción del caso de uso."""
    evento = Auditoria(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        antes=antes,
        despues=despues,
    )
    session.add(evento)
    await session.flush()
    return evento
