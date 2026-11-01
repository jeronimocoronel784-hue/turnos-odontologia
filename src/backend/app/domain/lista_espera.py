"""Entidad ListaEspera: cola priorizada de candidatos y oferta de huecos liberados (C-07).

Reglas implementadas:
- RN-LE-01: orden por `(prioridad, created_at)`, un aviso vigente por vez con ventana de respuesta.
- RN-LE-02: idempotencia un aviso por hueco por entrada (`idempotency_key`).
- RN-LE-03: colocación vincula `turno_colocado_id` y pasa a `colocada`.
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

from app.domain.mixins import GUID, AuditMixin, TenantMixin, asegurar_utc
from app.infrastructure.db.base import Base


class EstadoListaEspera(enum.StrEnum):
    """Estados permitidos para una entrada en la lista de espera."""

    ACTIVA = "activa"
    AVISADA = "avisada"
    COLOCADA = "colocada"
    BAJA = "baja"


class CanalAviso(enum.StrEnum):
    """Canales de aviso soportados para la oferta de huecos."""

    WA = "wa"
    EMAIL = "email"


def generar_idempotency_key_hueco(
    *,
    entrada_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sillon_id: uuid.UUID,
    inicio: datetime,
) -> str:
    """Construye la clave determinística única para un par (entrada, hueco) (RN-LE-02)."""
    inicio_utc = asegurar_utc(inicio)
    return f"le:{entrada_id}:{profesional_id}:{sillon_id}:{inicio_utc.isoformat()}"


class ListaEspera(TenantMixin, AuditMixin, Base):
    """Entrada en la lista de espera odontológica multi-tenant."""

    __tablename__ = "lista_espera"
    __table_args__ = (
        CheckConstraint(
            "prioridad >= 0",
            name="ck_lista_espera_prioridad_no_negativa",
        ),
        CheckConstraint(
            "estado IN ('activa', 'avisada', 'colocada', 'baja')",
            name="ck_lista_espera_estado_valido",
        ),
        CheckConstraint(
            "canal_aviso IN ('wa', 'email')",
            name="ck_lista_espera_canal_valido",
        ),
        UniqueConstraint(
            "tenant_id",
            "ultimo_idempotency_key",
            name="uq_lista_espera_tenant_idempotency_key",
        ),
        Index(
            "ix_lista_espera_tenant_estado_orden",
            "tenant_id",
            "estado",
            "prioridad",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("paciente.id", ondelete="RESTRICT"),
        nullable=False,
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("prestacion.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=True,
    )
    prioridad: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    estado: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EstadoListaEspera.ACTIVA.value,
    )
    canal_aviso: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=CanalAviso.WA.value,
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Datos de la oferta de hueco activa o última ofrecida
    hueco_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hueco_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hueco_profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    hueco_sillon_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("sillon.id", ondelete="SET NULL"),
        nullable=True,
    )
    aviso_vence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_idempotency_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    avisos_keys: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    turno_colocado_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("turno.id", ondelete="SET NULL"),
        nullable=True,
    )
