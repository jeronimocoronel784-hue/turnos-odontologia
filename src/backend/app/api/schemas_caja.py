"""Schemas Pydantic v2 estrictos para señas, movimientos y cierres de caja (C-11).

Cumple:
- R1: `extra='forbid'` en todos los inputs y modelos de lectura explícitos (nunca el ORM).
- R8: ningún input acepta montos calculados en servidor (seña, saldo del turno).
- `tenant_id` y `created_by` salen del token, jamás del body (R4).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.caja import EstadoCierreCaja, EstadoSena, MedioPago, TipoMovimientoCaja


def _texto_limpio(valor: str | None) -> str | None:
    """Normaliza un texto opcional: recorta y convierte el vacío en `None`."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


class SenaCreate(BaseModel):
    """Alta manual de la seña de un turno: `monto` y `estado` los fija el servidor (R8)."""

    model_config = ConfigDict(extra="forbid")

    turno_id: uuid.UUID
    vence_at: datetime | None = None

    @field_validator("vence_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("`vence_at` tiene que incluir zona horaria (UTC).")
        return v


class SenaCobrarInput(BaseModel):
    """Cobro de una seña: el importe sale de la seña persistida, nunca del body (R8)."""

    model_config = ConfigDict(extra="forbid")

    medio: MedioPago


class SenaResolverCancelacionInput(BaseModel):
    """Resolución de la seña cobrada al cancelar el turno (RN-PA-04)."""

    model_config = ConfigDict(extra="forbid")

    ausente: bool = False
    motivo: str | None = Field(default=None, max_length=500)

    @field_validator("motivo")
    @classmethod
    def _limpiar_motivo(cls, v: str | None) -> str | None:
        return _texto_limpio(v)


class SenaRead(BaseModel):
    """Representación de una seña con sus montos calculados en servidor."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    turno_id: uuid.UUID
    monto: Decimal
    estado: EstadoSena
    mp_payment_id: str | None = None
    vence_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MovimientoCajaCreate(BaseModel):
    """Alta manual de un movimiento; el cierre abierto lo asigna el servidor (D3)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoMovimientoCaja
    concepto: str = Field(min_length=1, max_length=160)
    medio: MedioPago
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    turno_id: uuid.UUID | None = None
    sena_id: uuid.UUID | None = None

    @field_validator("concepto")
    @classmethod
    def _exigir_concepto(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El concepto del movimiento no puede quedar vacío.")
        return limpio


class MovimientoCajaRead(BaseModel):
    """Representación append-only de un movimiento de caja (R7)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    tipo: TipoMovimientoCaja
    concepto: str
    medio: MedioPago
    monto: Decimal
    turno_id: uuid.UUID | None = None
    sena_id: uuid.UUID | None = None
    cobro_mp_id: uuid.UUID | None = None
    cierre_id: uuid.UUID | None = None
    created_by: uuid.UUID
    created_at: datetime


class CierreCajaAbrirInput(BaseModel):
    """Apertura del cierre diario: un cierre por fecha y consultorio (D3)."""

    model_config = ConfigDict(extra="forbid")

    fecha: date


class CierreCajaCerrarInput(BaseModel):
    """Cierre de caja: el `total_contado` lo declara quien cierra, el sistema lo contrasta."""

    model_config = ConfigDict(extra="forbid")

    total_contado: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CierreCajaReabrirInput(BaseModel):
    """Reapertura exclusiva del Dueño: el motivo es obligatorio y queda auditado (RN-SE-01)."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def _exigir_motivo(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("La reapertura del cierre exige un motivo.")
        return limpio


class CierreCajaRead(BaseModel):
    """Representación del cierre diario con `diferencia = total_contado - total_sistema`."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    fecha: date
    total_sistema: Decimal
    total_contado: Decimal | None = None
    diferencia: Decimal | None = None
    estado: EstadoCierreCaja
    abierto_por: uuid.UUID
    cerrado_por: uuid.UUID | None = None
    cerrado_at: datetime | None = None
    reabierto_motivo: str | None = None
    created_at: datetime
    updated_at: datetime


class LiquidacionTurnoRead(BaseModel):
    """Saldo de atención calculado en servidor: `precio - cobertura_os - sena_cobrada` (R8)."""

    model_config = ConfigDict(extra="forbid")

    turno_id: uuid.UUID
    precio_particular: Decimal
    cobertura_os: Decimal
    sena_cobrada: Decimal
    saldo: Decimal
    obra_social: str | None = None


class CobrarTurnoInput(BaseModel):
    """Cobro del saldo del turno: el importe lo calcula el servidor (Flujo 4, R8)."""

    model_config = ConfigDict(extra="forbid")

    medio: MedioPago
    obra_social: str | None = Field(default=None, max_length=160)

    @field_validator("obra_social")
    @classmethod
    def _limpiar_os(cls, v: str | None) -> str | None:
        return _texto_limpio(v)
