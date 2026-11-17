"""Registro de auditor��a append-only reutilizable (RN-SE-01).

Nunca guarda PHI ni credenciales: solo actor, acci��n, entidad y el diff m��nimo
necesario para reconstruir quiǸn hizo quǸ y cuǭndo (R9).
"""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.shared.exceptions import EntidadInvalida

# Zona horaria de Buenos Aires (sin DST; offset fijo -03:00).
ZONA_ART = timezone(timedelta(hours=-3))


def _normalizar_fecha(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=ZONA_ART)
    return valor.astimezone(UTC)


def _encode_cursor(created_at: datetime, evento_id: uuid.UUID) -> str:
    from app.domain.mixins import asegurar_utc

    payload = {
        "created_at": asegurar_utc(created_at).isoformat(),
        "id": str(evento_id),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    from app.domain.mixins import asegurar_utc

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw)
        created = datetime.fromisoformat(str(data["created_at"]))
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        else:
            created = created.astimezone(UTC)
        evento_id = uuid.UUID(str(data["id"]))
    except Exception as exc:  # pragma: no cover - se valida por tests
        raise EntidadInvalida("El cursor no es vǭlido. Repet�� la consulta sin cursor.") from exc
    # Validaci��n expl��cita para mensajes claros.
    try:
        _ = asegurar_utc(created)
    except Exception as exc:  # pragma: no cover
        raise EntidadInvalida("El cursor no es vǭlido. Repet�� la consulta sin cursor.") from exc
    return created, evento_id


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
    """Inserta el evento en la misma transacci��n del caso de uso."""
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


async def listar_auditoria(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entidad: str | None = None,
    entidad_id: str | None = None,
    actor_id: uuid.UUID | None = None,
    accion: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: int = 50,
    cursor: str | None = None,
) -> tuple[list[Auditoria], str | None]:
    """Lee el trail del tenant con filtros, orden descendente y paginaci��n keyset."""
    if not (1 <= limite <= 200):
        raise EntidadInvalida("El l��mite debe estar entre 1 y 200.")

    desde_utc = _normalizar_fecha(desde)
    hasta_utc = _normalizar_fecha(hasta)
    if desde_utc is not None and hasta_utc is not None and desde_utc > hasta_utc:
        raise EntidadInvalida(
            "El rango de fechas estǭ al revǸs: 'desde' es posterior a 'hasta'. Corregilo."
        )

    stmt = select(Auditoria).where(Auditoria.tenant_id == tenant_id)
    if entidad is not None:
        stmt = stmt.where(Auditoria.entidad == entidad)
    if entidad_id is not None:
        stmt = stmt.where(Auditoria.entidad_id == entidad_id)
    if actor_id is not None:
        stmt = stmt.where(Auditoria.actor_id == actor_id)
    if accion is not None:
        stmt = stmt.where(Auditoria.accion == accion)
    if desde_utc is not None:
        stmt = stmt.where(Auditoria.created_at >= desde_utc)
    if hasta_utc is not None:
        stmt = stmt.where(Auditoria.created_at < hasta_utc)

    if cursor is not None:
        created_cursor, id_cursor = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Auditoria.created_at < created_cursor,
                and_(
                    Auditoria.created_at == created_cursor,
                    Auditoria.id < id_cursor,
                ),
            )
        )

    stmt = stmt.order_by(Auditoria.created_at.desc(), Auditoria.id.desc()).limit(limite + 1)

    result = await session.execute(stmt)
    filas = list(result.scalars().all())

    siguiente_cursor: str | None = None
    if len(filas) > limite:
        ultimo = filas[limite - 1]
        siguiente_cursor = _encode_cursor(ultimo.created_at, ultimo.id)
        filas = filas[:limite]

    return filas, siguiente_cursor
