"""Modelos clínicos: Evolucion, Odontograma, PiezaEvento, AdjuntoClinico y Consentimiento (C-09).

Cumple:
- R7 / RN-CL-01: Evolucion y PiezaEvento son append-only (correcciones son nuevos eventos).
- RN-CL-02: Consentimiento con versión de texto, hash SHA-256 de firma y revocación auditada.
"""

import enum
import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base

PIEZAS_FDI_VALIDAS: frozenset[int] = frozenset(
    {
        # Permanentes (cuadrantes 1..4, piezas 1..8)
        *(q * 10 + p for q in (1, 2, 3, 4) for p in range(1, 9)),
        # Deciduas (cuadrantes 5..8, piezas 1..5)
        *(q * 10 + p for q in (5, 6, 7, 8) for p in range(1, 6)),
    }
)


def es_pieza_fdi_valida(pieza_fdi: int) -> bool:
    """Devuelve True si el entero pertenece a la nomenclatura FDI (adulta 11–48 o decidua 51–85)."""
    return (
        isinstance(pieza_fdi, int)
        and not isinstance(pieza_fdi, bool)
        and (pieza_fdi in PIEZAS_FDI_VALIDAS)
    )


class SuperficieDental(enum.StrEnum):
    """Superficies dentales admitidas en el odontograma FDI (§04)."""

    OCLUSAL = "oclusal"
    MESIAL = "mesial"
    DISTAL = "distal"
    VESTIBULAR = "vestibular"
    LINGUAL = "lingual"
    RADICULAR = "radicular"
    TOTAL = "total"


class TipoEventoPieza(enum.StrEnum):
    """Eventos clínicos registrables por pieza/superficie (§04)."""

    SANO = "sano"
    CARIES = "caries"
    OBTURACION = "obturacion"
    CORONA = "corona"
    ENDODONCIA = "endodoncia"
    IMPLANTE = "implante"
    EXTRACCION = "extraccion"
    AUSENTE = "ausente"
    SELLADOR = "sellador"
    PROVISORIA = "provisoria"


class TipoAdjunto(enum.StrEnum):
    """Tipos de adjunto clínico admitidos en la HCE."""

    RX = "rx"
    FOTO = "foto"
    PDF = "pdf"


class CanalFirmaConsentimiento(enum.StrEnum):
    """Canal a través del cual se firmó el consentimiento informado."""

    PRESENCIAL = "presencial"
    TOKEN = "token"


def calcular_hash_consentimiento(
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    texto_version: str,
    firmado_por: str,
    firmado_at: datetime,
    firma_datos: str,
) -> str:
    """Calcula el hash SHA-256 inmutable de la firma de un consentimiento informado."""
    cadena = "|".join(
        [
            str(tenant_id),
            str(paciente_id),
            str(prestacion_id),
            texto_version.strip(),
            firmado_por.strip(),
            firmado_at.isoformat(),
            firma_datos.strip(),
        ]
    )
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


class Evolucion(Base, TenantMixin):
    """Evolución clínica append-only de una atención o enmienda aditiva (RN-CL-01, R7)."""

    __tablename__ = "evolucion"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    ficha_clinica_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("ficha_clinica.id", ondelete="RESTRICT"), nullable=False
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False
    )
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="SET NULL"), nullable=True
    )
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    nota: Mapped[str] = mapped_column(Text, nullable=False)
    es_correccion_de_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("evolucion.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_evolucion_tenant_paciente_created", "tenant_id", "paciente_id", "created_at"),
        Index("ix_evolucion_ficha_created", "ficha_clinica_id", "created_at"),
    )


class Odontograma(Base, TenantMixin, AuditMixin):
    """Cabecera de odontograma FDI 1:1 por paciente (§04)."""

    __tablename__ = "odontograma"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "paciente_id", name="uq_odontograma_tenant_paciente"),
        Index("ix_odontograma_tenant_paciente", "tenant_id", "paciente_id"),
    )


class PiezaEvento(Base, TenantMixin):
    """Evento inmutable sobre una pieza/superficie del odontograma FDI (RN-CL-01, R7)."""

    __tablename__ = "pieza_evento"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    odontograma_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("odontograma.id", ondelete="RESTRICT"), nullable=False
    )
    pieza_fdi: Mapped[int] = mapped_column(Integer, nullable=False)
    superficie: Mapped[str] = mapped_column(String(24), nullable=False)
    evento: Mapped[str] = mapped_column(String(24), nullable=False)
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="SET NULL"), nullable=True
    )
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(pieza_fdi BETWEEN 11 AND 18) OR (pieza_fdi BETWEEN 21 AND 28) OR "
            "(pieza_fdi BETWEEN 31 AND 38) OR (pieza_fdi BETWEEN 41 AND 48) OR "
            "(pieza_fdi BETWEEN 51 AND 55) OR (pieza_fdi BETWEEN 61 AND 65) OR "
            "(pieza_fdi BETWEEN 71 AND 75) OR (pieza_fdi BETWEEN 81 AND 85)",
            name="ck_pieza_evento_pieza_fdi_valida",
        ),
        CheckConstraint(
            "superficie IN ('oclusal', 'mesial', 'distal', "
            "'vestibular', 'lingual', 'radicular', 'total')",
            name="ck_pieza_evento_superficie_valida",
        ),
        CheckConstraint(
            "evento IN ('sano', 'caries', 'obturacion', 'corona', 'endodoncia', 'implante', "
            "'extraccion', 'ausente', 'sellador', 'provisoria')",
            name="ck_pieza_evento_tipo_valido",
        ),
        Index(
            "ix_pieza_evento_odontograma_pieza_created",
            "odontograma_id",
            "pieza_fdi",
            "created_at",
        ),
    )


class AdjuntoClinico(Base, TenantMixin):
    """Metadatos de adjunto clínico (RX, foto, PDF) asociado a la HCE sin exponer PHI en URLs."""

    __tablename__ = "adjunto_clinico"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False
    )
    ficha_clinica_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("ficha_clinica.id", ondelete="RESTRICT"), nullable=False
    )
    evolucion_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("evolucion.id", ondelete="SET NULL"), nullable=True
    )
    pieza_evento_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("pieza_evento.id", ondelete="SET NULL"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("tipo IN ('rx', 'foto', 'pdf')", name="ck_adjunto_clinico_tipo_valido"),
        CheckConstraint("tamano_bytes > 0", name="ck_adjunto_clinico_tamano_positivo"),
        Index("ix_adjunto_clinico_tenant_paciente", "tenant_id", "paciente_id", "created_at"),
    )


class Consentimiento(Base, TenantMixin, AuditMixin):
    """Consentimiento informado firmado presencialmente o por token público (RN-CL-02)."""

    __tablename__ = "consentimiento"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prestacion.id", ondelete="RESTRICT"), nullable=False
    )
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="SET NULL"), nullable=True
    )
    texto_version: Mapped[str] = mapped_column(String(64), nullable=False)
    texto_contenido: Mapped[str] = mapped_column(Text, nullable=False)
    firma_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmado_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    firmado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canal: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CanalFirmaConsentimiento.PRESENCIAL.value
    )
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revocado_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    revocado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "canal IN ('presencial', 'token')",
            name="ck_consentimiento_canal_valido",
        ),
        Index(
            "ix_consentimiento_tenant_paciente_prestacion",
            "tenant_id",
            "paciente_id",
            "prestacion_id",
        ),
        Index("ix_consentimiento_turno_id", "turno_id"),
    )
