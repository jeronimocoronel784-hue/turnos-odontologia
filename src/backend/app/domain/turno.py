"""Modelo Turno (Cita): máquina de estados, duración por prestación, sobreturno y reprogramación."""

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class EstadoTurno(enum.StrEnum):
    """Estados posibles de un turno odontológico (RN-AG-07)."""

    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    PRESENTE = "presente"
    FINALIZADO = "finalizado"
    CANCELADO = "cancelado"
    AUSENTE = "ausente"
    REPROGRAMADO = "reprogramado"


class OrigenTurno(enum.StrEnum):
    """Canal por el cual se originó el turno."""

    PRESENCIAL = "presencial"
    ONLINE = "online"
    WHATSAPP = "whatsapp"


ESTADOS_ACTIVOS_AGENDA: frozenset[EstadoTurno] = frozenset(
    {
        EstadoTurno.PENDIENTE,
        EstadoTurno.CONFIRMADO,
        EstadoTurno.PRESENTE,
    }
)

TRANSICIONES_PERMITIDAS: dict[EstadoTurno, frozenset[EstadoTurno]] = {
    EstadoTurno.PENDIENTE: frozenset(
        {
            EstadoTurno.CONFIRMADO,
            EstadoTurno.CANCELADO,
            EstadoTurno.AUSENTE,
            EstadoTurno.REPROGRAMADO,
        }
    ),
    EstadoTurno.CONFIRMADO: frozenset(
        {
            EstadoTurno.PRESENTE,
            EstadoTurno.CANCELADO,
            EstadoTurno.AUSENTE,
            EstadoTurno.REPROGRAMADO,
        }
    ),
    EstadoTurno.PRESENTE: frozenset({EstadoTurno.FINALIZADO}),
    EstadoTurno.FINALIZADO: frozenset(),
    EstadoTurno.CANCELADO: frozenset(),
    EstadoTurno.AUSENTE: frozenset(),
    EstadoTurno.REPROGRAMADO: frozenset(),
}


def calcular_fin_turno(inicio: datetime, duracion_min: int) -> datetime:
    """Calcula `fin = inicio + duracion_min` según la prestación (RN-AG-02)."""
    return inicio + timedelta(minutes=duracion_min)


def es_transicion_valida(actual: EstadoTurno | str, destino: EstadoTurno | str) -> bool:
    """Evalúa si la transición está permitida en el grafo cerrado (RN-AG-07)."""
    try:
        est_actual = EstadoTurno(actual)
        est_destino = EstadoTurno(destino)
    except ValueError:
        return False
    return est_destino in TRANSICIONES_PERMITIDAS.get(est_actual, frozenset())


class Turno(Base, TenantMixin, AuditMixin):
    """Cita odontológica vinculada a paciente, profesional, sillón y prestación."""

    __tablename__ = "turno"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False
    )
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    sillon_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("sillon.id", ondelete="RESTRICT"), nullable=False
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prestacion.id", ondelete="RESTRICT"), nullable=False
    )
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoTurno.PENDIENTE.value
    )
    origen: Mapped[str] = mapped_column(
        String(24), nullable=False, default=OrigenTurno.PRESENCIAL.value
    )
    sobreturno: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    turno_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="SET NULL"), nullable=True
    )
    sena_cobrada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("fin > inicio", name="ck_turno_rango_valido"),
        CheckConstraint(
            "(NOT sobreturno) OR (observaciones IS NOT NULL AND length(trim(observaciones)) > 0)",
            name="ck_turno_sobreturno_motivo",
        ),
        Index("ix_turno_tenant_profesional_inicio", "tenant_id", "profesional_id", "inicio"),
        Index("ix_turno_tenant_sillon_inicio", "tenant_id", "sillon_id", "inicio"),
        Index("ix_turno_tenant_estado_inicio", "tenant_id", "estado", "inicio"),
    )
