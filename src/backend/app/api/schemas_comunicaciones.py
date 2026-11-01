"""Schemas Pydantic estrictos para Comunicaciones, Outbox y Webhooks WA (C-08, R1)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.mensaje import CanalMensaje, EstadoMensaje


class PlantillaCreate(BaseModel):
    """Alta o nueva versión de plantilla de mensajería (RN-CO-04)."""

    model_config = ConfigDict(extra="forbid")

    codigo: str
    canal: CanalMensaje = CanalMensaje.WA
    asunto: str | None = None
    cuerpo: str
    activa: bool = True

    @field_validator("codigo")
    @classmethod
    def _limpiar_codigo(cls, v: str) -> str:
        limpio = v.strip().lower()
        if not limpio:
            raise ValueError("El código de la plantilla no puede estar vacío.")
        return limpio

    @field_validator("cuerpo")
    @classmethod
    def _limpiar_cuerpo(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El cuerpo de la plantilla no puede estar vacío.")
        return limpio


class PlantillaRead(BaseModel):
    """Respuesta de plantilla versionada."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    codigo: str
    canal: CanalMensaje
    version: int
    asunto: str | None = None
    cuerpo: str
    activa: bool
    created_at: datetime
    updated_at: datetime


class MensajeCreate(BaseModel):
    """Solicitud interna para encolar un mensaje en el outbox."""

    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID | None = None
    turno_id: uuid.UUID | None = None
    lista_espera_id: uuid.UUID | None = None
    canal: CanalMensaje = CanalMensaje.WA
    plantilla: str
    destino: str
    variables: dict[str, str] = {}
    ventana: str = "manual"
    programado_para: datetime | None = None

    @field_validator("plantilla", "destino", "ventana")
    @classmethod
    def _validar_no_vacio(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El campo no puede estar vacío.")
        return limpio


class MensajeRead(BaseModel):
    """Respuesta de un registro del outbox de mensajes."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID | None = None
    turno_id: uuid.UUID | None = None
    lista_espera_id: uuid.UUID | None = None
    canal: CanalMensaje
    plantilla: str
    plantilla_version: int
    destino: str
    cuerpo_renderizado: str
    payload: dict[str, object]
    estado: EstadoMensaje
    idempotency_key: str
    intentos: int
    max_intentos: int
    programado_para: datetime
    enviado_at: datetime | None = None
    error: str | None = None
    proveedor_message_id: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookWhatsAppEvento(BaseModel):
    """Evento individual normalizado de webhook de WhatsApp (Flujo 2, RN-AG-08, RN-CO-01)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    tipo: Literal["confirmar", "stop", "estado"]
    tenant_slug: str | None = None
    turno_id: uuid.UUID | None = None
    token_gestion: str | None = None
    telefono: str | None = None
    mensaje_id: uuid.UUID | None = None
    estado_entrega: Literal["enviado", "entregado", "leido", "fallido"] | None = None

    @field_validator("event_id")
    @classmethod
    def _validar_event_id(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("El event_id del webhook no puede estar vacío.")
        return limpio


class WebhookWhatsAppPayload(BaseModel):
    """Payload de eventos entrantes en POST /webhooks/whatsapp."""

    model_config = ConfigDict(extra="forbid")

    eventos: list[WebhookWhatsAppEvento]
