"""Mixins de dominio: TenantMixin (aislamiento multi-tenant) + AuditMixin (trazabilidad).

Toda tabla de negocio SHALL llevar `tenant_id` (spec core-models). `Tenant` es la raíz
y NO lleva TenantMixin; el resto sí.

Portabilidad deliberada (Postgres en CI/Docker, SQLite local sin Docker):
- `GUID` guarda UUID como CHAR(32) hexadecimal en TODOS los motores (nada de UUID
  nativo): la migración 001 y `create_all` generan el mismo DDL en ambos.
- Timestamps con default del lado Python (UTC): sin `NOW()`/`func.now()` que rompan
  en SQLite.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CHAR, DateTime, ForeignKey
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def ahora_utc() -> datetime:
    """Timestamp UTC para defaults del lado cliente."""
    return datetime.now(UTC)


def asegurar_utc(valor: datetime) -> datetime:
    """Normaliza a UTC aware: SQLite devuelve naive aunque la columna sea timezone=True."""
    if valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC)


class GUID(TypeDecorator[uuid.UUID]):
    """UUID como CHAR(32) hexadecimal en todos los dialectos.

    `TypeDecorator` (y no una subclase de `CHAR`) porque el dialecto asyncpg
    sustituye `CHAR` por `AsyncpgCHAR`, que anula `bind_processor`: sin esto
    asyncpg recibe un `UUID` y falla con "expected str, got UUID".
    """

    impl = CHAR(32)
    cache_ok = True

    def process_bind_param(self, value: uuid.UUID | str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value.hex
        return uuid.UUID(str(value)).hex

    def process_result_value(self, value: object, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class TenantMixin:
    """Agrega `tenant_id` FK a `tenant.id`. El repositorio base filtra por él siempre (D3)."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )


class AuditMixin:
    """Timestamps de auditoría. `updated_at` se refresca en cada UPDATE del ORM."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc, nullable=False
    )
