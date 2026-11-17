"""Schemas de lectura del trail de auditoría (C-14, D2).

Nunca exponen el ORM (`R1`) ni `tenant_id` (el filtro sale del token, `R4`). Los
snapshots `antes`/`despues` viajan tal cual se guardaron: el trail es append-only y
no se reinterpreta al leer (`R7`).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.mixins import asegurar_utc


class AuditoriaEventoRead(BaseModel):
    """Un evento del trail, con el `created_at` siempre en UTC."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    accion: str
    entidad: str
    entidad_id: str
    antes: dict[str, object] | None
    despues: dict[str, object] | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _normalizar_utc(cls, valor: datetime) -> datetime:
        """SQLite devuelve naive y Postgres puede devolver otro offset: se unifica en UTC."""
        return asegurar_utc(valor)


class AuditoriaPaginaRead(BaseModel):
    """Página keyset: el cliente pide la siguiente con `siguiente_cursor` (D2)."""

    eventos: list[AuditoriaEventoRead]
    siguiente_cursor: str | None = None
