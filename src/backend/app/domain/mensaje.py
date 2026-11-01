"""Entidad Mensaje (Outbox): cola persistente de envíos WA/email con idempotencia (C-08).

Reglas implementadas:
- RN-CO-01: respeta optin_wa obligatorio (estado `omitido` si no tiene opt-in).
- RN-CO-02: `idempotency_key` único por tenant evita doble recordatorio/envío.
- RN-CO-03: reintentos asíncronos con `intentos`, `max_intentos` y `programado_para`.
- RN-CO-04: persiste `plantilla_version` y `cuerpo_renderizado` enviado.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class CanalMensaje(enum.StrEnum):
    """Canales de mensajería soportados en v1."""

    WA = "wa"
    EMAIL = "email"


class EstadoMensaje(enum.StrEnum):
    """Estados del ciclo de vida del mensaje en el outbox."""

    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    OMITIDO = "omitido"


def generar_idempotency_key_mensaje(
    *,
    entidad_id: uuid.UUID,
    codigo_plantilla: str,
    ventana: str,
) -> str:
    """Construye la clave determinística única para un (entidad, plantilla, ventana) (RN-CO-02)."""
    return f"msg:{entidad_id}:{codigo_plantilla.strip()}:{ventana.strip()}"


class Mensaje(TenantMixin, AuditMixin, Base):
    """Registro outbox de comunicación WA/email multi-tenant."""

    __tablename__ = "mensaje"
    __table_args__ = (
        CheckConstraint("intentos >= 0", name="ck_mensaje_intentos_no_negativos"),
        CheckConstraint("max_intentos >= 1", name="ck_mensaje_max_intentos_positivo"),
        CheckConstraint("canal IN ('wa', 'email')", name="ck_mensaje_canal_valido"),
        CheckConstraint(
            "estado IN ('pendiente', 'enviado', 'entregado', 'leido', 'fallido', 'omitido')",
            name="ck_mensaje_estado_valido",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_mensaje_tenant_idempotency_key",
        ),
        Index(
            "ix_mensaje_tenant_estado_programado",
            "tenant_id",
            "estado",
            "programado_para",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("paciente.id", ondelete="SET NULL"),
        nullable=True,
    )
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("turno.id", ondelete="SET NULL"),
        nullable=True,
    )
    lista_espera_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("lista_espera.id", ondelete="SET NULL"),
        nullable=True,
    )
    canal: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=CanalMensaje.WA.value,
    )
    plantilla: Mapped[str] = mapped_column(String(64), nullable=False)
    plantilla_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    destino: Mapped[str] = mapped_column(String(160), nullable=False)
    cuerpo_renderizado: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    estado: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EstadoMensaje.PENDIENTE.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    programado_para: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enviado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    proveedor_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
