"""Schemas Pydantic v2 estrictos para Presupuestos y Planes de Tratamiento (C-10).

Cumple:
- R1: extra='forbid' en todos los inputs y modelos de lectura explícitos.
- R8: ningún input admite montos calculados por el cliente (`precio_unit`, `a_cargo`, `total`).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.clinica import es_pieza_fdi_valida


class PresupuestoItemInput(BaseModel):
    """Input de un item de presupuesto (montos calculados siempre en servidor, R8)."""

    model_config = ConfigDict(extra="forbid")

    prestacion_id: uuid.UUID
    pieza_fdi: int | None = None
    cantidad: int = Field(default=1, ge=1, le=32)

    @field_validator("pieza_fdi")
    @classmethod
    def _validar_pieza_fdi(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not es_pieza_fdi_valida(v):
            raise ValueError(
                f"Che, la pieza FDI '{v}' no es válida. "
                "Usá numeración FDI permanente (11–48) o decidua (51–85)."
            )
        return v


class PresupuestoItemRead(BaseModel):
    """Representación de un renglón del presupuesto con montos calculados en servidor."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    prestacion_id: uuid.UUID
    pieza_fdi: int | None = None
    cantidad: int
    precio_unit: Decimal
    cobertura_os: Decimal
    a_cargo: Decimal
    created_at: datetime


class PresupuestoCreate(BaseModel):
    """Input para crear un presupuesto con sus renglones iniciales (sin montos cliente, R8)."""

    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    obra_social: str | None = Field(default=None, max_length=160)
    validez_hasta: date | None = None
    observaciones: str | None = Field(default=None, max_length=2000)
    items: list[PresupuestoItemInput] = Field(..., min_length=1, max_length=100)

    @field_validator("obra_social")
    @classmethod
    def _limpiar_os(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None


class PresupuestoVincularTurnoInput(BaseModel):
    """Input para vincular un turno del paciente al plan de tratamiento."""

    model_config = ConfigDict(extra="forbid")

    turno_id: uuid.UUID
    presupuesto_item_id: uuid.UUID | None = None


class PresupuestoTurnoRead(BaseModel):
    """Representación de un vínculo entre un presupuesto y una cita (Turno)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    turno_id: uuid.UUID
    presupuesto_item_id: uuid.UUID | None = None
    created_at: datetime


class PresupuestoRead(BaseModel):
    """Representación completa de un presupuesto y sus items."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    obra_social: str | None = None
    estado: str
    total: Decimal
    total_cobertura_os: Decimal
    total_a_cargo: Decimal
    validez_hasta: date | None = None
    observaciones: str | None = None
    created_by: uuid.UUID
    items: list[PresupuestoItemRead] = Field(default_factory=list)
    turnos_vinculados: list[PresupuestoTurnoRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
