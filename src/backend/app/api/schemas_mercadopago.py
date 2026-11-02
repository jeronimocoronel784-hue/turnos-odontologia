"""Schemas Pydantic v2 para Mercado Pago (C-12, US-031).

Cumple:
- R1: schemas estrictos con extra='forbid', campos explícitos.
- R8: Decimal para montos, nunca float.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PreferenciaCreate(BaseModel):
    """Input para generar una preferencia de checkout en Mercado Pago."""

    model_config = ConfigDict(extra="forbid")

    sena_id: uuid.UUID
    monto: Decimal = Field(..., gt=0, decimal_places=2)
    titulo: str = Field(..., min_length=1, max_length=255)
    vence_at: datetime
    paciente_email: str | None = Field(default=None, max_length=255)


class PreferenciaRead(BaseModel):
    """Datos de la preferencia creada en Mercado Pago devueltos al frontend o paciente."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    init_point: str
    sandbox_init_point: str
    external_reference: str
    monto: Decimal = Field(..., decimal_places=2)
    expiration_date_to: datetime


class WebhookPayloadMP(BaseModel):
    """Estructura de la notificación HTTP que envía Mercado Pago."""

    model_config = ConfigDict(extra="ignore")

    id: int | str
    live_mode: bool = False
    type: str = "payment"
    date_created: str | None = None
    user_id: int | str | None = None
    api_version: str | None = None
    action: str | None = None
    data: dict[str, Any]


class CobroMPRead(BaseModel):
    """Lectura de cobro de Mercado Pago para auditoría y administración."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    turno_id: uuid.UUID | None = None
    sena_id: uuid.UUID | None = None
    mp_payment_id: str
    mp_preference_id: str | None = None
    monto: Decimal = Field(..., decimal_places=2)
    estado_mp: str
    estado_conciliacion: str
    created_at: datetime


class DiscrepanciaMPRead(BaseModel):
    """Representación de una discrepancia detectada en Mercado Pago para resolución manual."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    mp_payment_id: str
    monto: Decimal = Field(..., decimal_places=2)
    estado_mp: str
    sena_id: uuid.UUID | None = None
    turno_id: uuid.UUID | None = None
    motivo: str
    created_at: datetime
