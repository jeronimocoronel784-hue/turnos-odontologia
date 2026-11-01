"""Schemas Pydantic v2 estrictos para Historia Clínica, Odontograma FDI y Consentimiento (C-09).

Cumple:
- R1: extra='forbid' en todos los inputs y modelos de lectura explícitos.
- RN-CL-01..03: Validación de pieza FDI, superficies, eventos e inmutabilidad.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.clinica import (
    CanalFirmaConsentimiento,
    SuperficieDental,
    TipoAdjunto,
    TipoEventoPieza,
    es_pieza_fdi_valida,
)


def _limpiar_texto_obligatorio(v: str, nombre_campo: str) -> str:
    limpio = v.strip()
    if not limpio:
        raise ValueError(f"Che, el campo '{nombre_campo}' no puede estar vacío.")
    return limpio


class FichaClinicaUpdate(BaseModel):
    """Input para actualizar la anamnesis/ficha clínica de un paciente (solo rol clínico)."""

    model_config = ConfigDict(extra="forbid")

    antecedentes: str | None = Field(default=None, max_length=8000)
    alergias: str | None = Field(default=None, max_length=4000)
    medicacion: str | None = Field(default=None, max_length=4000)
    habitos: str | None = Field(default=None, max_length=4000)
    datos_json: dict[str, Any] | None = None
    nota_evolucion: str | None = Field(default=None, max_length=4000)


class FichaClinicaDetalleRead(BaseModel):
    """Representación de la ficha clínica 1:1 del paciente."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    antecedentes: str | None = None
    alergias: str | None = None
    medicacion: str | None = None
    habitos: str | None = None
    datos_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EvolucionCreate(BaseModel):
    """Input para registrar una evolución clínica append-only o una enmienda aditiva."""

    model_config = ConfigDict(extra="forbid")

    nota: str = Field(..., min_length=1, max_length=12000)
    turno_id: uuid.UUID | None = None
    es_correccion_de_id: uuid.UUID | None = None

    @field_validator("nota")
    @classmethod
    def _validar_nota(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "nota")


class EvolucionRead(BaseModel):
    """Representación de una evolución clínica inmutable."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    ficha_clinica_id: uuid.UUID
    paciente_id: uuid.UUID
    turno_id: uuid.UUID | None = None
    profesional_id: uuid.UUID
    nota: str
    es_correccion_de_id: uuid.UUID | None = None
    created_at: datetime


class AdjuntoCreate(BaseModel):
    """Input para registrar metadatos de un estudio o imagen clínica (RX, foto, PDF)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoAdjunto
    nombre_archivo: str = Field(..., min_length=1, max_length=200)
    mime_type: str = Field(..., min_length=3, max_length=80)
    tamano_bytes: int = Field(..., gt=0, le=50_000_000)
    storage_key: str = Field(..., min_length=1, max_length=255)
    evolucion_id: uuid.UUID | None = None
    pieza_evento_id: uuid.UUID | None = None

    @field_validator("nombre_archivo")
    @classmethod
    def _validar_nombre(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "nombre_archivo")

    @field_validator("storage_key")
    @classmethod
    def _validar_key(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "storage_key")


class AdjuntoRead(BaseModel):
    """Representación de un adjunto clínico."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    ficha_clinica_id: uuid.UUID
    evolucion_id: uuid.UUID | None = None
    pieza_evento_id: uuid.UUID | None = None
    tipo: str
    nombre_archivo: str
    mime_type: str
    tamano_bytes: int
    storage_key: str
    created_by: uuid.UUID
    created_at: datetime


class PiezaEventoCreate(BaseModel):
    """Input para registrar un evento inmutable sobre una pieza/superficie del odontograma FDI."""

    model_config = ConfigDict(extra="forbid")

    pieza_fdi: int
    superficie: SuperficieDental
    evento: TipoEventoPieza
    turno_id: uuid.UUID | None = None
    observacion: str | None = Field(default=None, max_length=2000)

    @field_validator("pieza_fdi")
    @classmethod
    def _validar_pieza_fdi(cls, v: int) -> int:
        if not es_pieza_fdi_valida(v):
            raise ValueError(
                f"Che, la pieza FDI '{v}' no es válida. "
                "Usá numeración FDI permanente (11–48) o decidua (51–85)."
            )
        return v

    @field_validator("observacion")
    @classmethod
    def _limpiar_obs(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None


class PiezaEventoRead(BaseModel):
    """Representación de un evento del odontograma FDI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    odontograma_id: uuid.UUID
    pieza_fdi: int
    superficie: str
    evento: str
    turno_id: uuid.UUID | None = None
    observacion: str | None = None
    created_by: uuid.UUID
    created_at: datetime


class EstadoPiezaFDIRead(BaseModel):
    """Estado proyectado actual de una pieza dental por superficie."""

    pieza_fdi: int
    superficies: dict[str, str]
    ultimo_evento_id: uuid.UUID
    updated_at: datetime


class OdontogramaRead(BaseModel):
    """Representación del odontograma FDI de un paciente con estado proyectado y eventos."""

    odontograma_id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    piezas: list[EstadoPiezaFDIRead]
    eventos: list[PiezaEventoRead]


class ConsentimientoCreate(BaseModel):
    """Input para generar un consentimiento informado para una prestación."""

    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    prestacion_id: uuid.UUID
    turno_id: uuid.UUID | None = None
    texto_version: str = Field(..., min_length=1, max_length=64)
    texto_contenido: str = Field(..., min_length=1, max_length=20000)

    @field_validator("texto_version")
    @classmethod
    def _validar_version(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "texto_version")

    @field_validator("texto_contenido")
    @classmethod
    def _validar_contenido(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "texto_contenido")


class ConsentimientoFirmaInput(BaseModel):
    """Input para firmar un consentimiento informado (presencial o por token)."""

    model_config = ConfigDict(extra="forbid")

    firmado_por: str = Field(..., min_length=1, max_length=160)
    firma_datos: str = Field(..., min_length=1, max_length=20000)
    canal: CanalFirmaConsentimiento = CanalFirmaConsentimiento.PRESENCIAL

    @field_validator("firmado_por")
    @classmethod
    def _validar_firmado_por(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "firmado_por")

    @field_validator("firma_datos")
    @classmethod
    def _validar_firma_datos(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "firma_datos")


class ConsentimientoRevocarInput(BaseModel):
    """Input para revocar un consentimiento informado con auditoría obligatoria."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(..., min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def _validar_motivo(cls, v: str) -> str:
        return _limpiar_texto_obligatorio(v, "motivo")


class ConsentimientoRead(BaseModel):
    """Representación de un consentimiento informado."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    prestacion_id: uuid.UUID
    turno_id: uuid.UUID | None = None
    texto_version: str
    texto_contenido: str
    firma_hash: str | None = None
    firmado_por: str | None = None
    firmado_at: datetime | None = None
    canal: str
    revocado: bool
    revocado_motivo: str | None = None
    revocado_at: datetime | None = None
    token_firma: str | None = None
    created_at: datetime
    updated_at: datetime


class ConsentimientoPublicoRead(BaseModel):
    """Representación pública mínima para firma por token sin exponer PHI (RN-SE-03, R9)."""

    consentimiento_id: uuid.UUID
    prestacion_id: uuid.UUID
    texto_version: str
    texto_contenido: str
    firmado: bool
    firmado_at: datetime | None = None
    revocado: bool
