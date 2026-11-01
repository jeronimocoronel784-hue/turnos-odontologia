"""Schemas Pydantic estrictos para Lista de Espera y Oferta de Huecos (C-07, R1)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.api.schemas_pacientes import _limpiar_dni
from app.domain.lista_espera import CanalAviso, EstadoListaEspera


class ListaEsperaCreate(BaseModel):
    """Alta interna de entrada en lista de espera."""

    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    prioridad: int = 1
    canal_aviso: CanalAviso = CanalAviso.WA
    observaciones: str | None = None

    @field_validator("prioridad")
    @classmethod
    def _validar_prioridad(cls, v: int) -> int:
        if v < 0:
            raise ValueError("La prioridad tiene que ser mayor o igual a 0.")
        return v

    @field_validator("observaciones")
    @classmethod
    def _normalizar_obs(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None


class ListaEsperaUpdate(BaseModel):
    """Actualización parcial de entrada en lista de espera."""

    model_config = ConfigDict(extra="forbid")

    prioridad: int | None = None
    canal_aviso: CanalAviso | None = None
    observaciones: str | None = None
    estado: EstadoListaEspera | None = None

    @field_validator("prioridad")
    @classmethod
    def _validar_prioridad(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("La prioridad tiene que ser mayor o igual a 0.")
        return v

    @field_validator("observaciones")
    @classmethod
    def _normalizar_obs(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None


class ListaEsperaRead(BaseModel):
    """Respuesta interna de entrada en lista de espera."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    prioridad: int
    estado: EstadoListaEspera
    canal_aviso: CanalAviso
    observaciones: str | None = None
    hueco_inicio: datetime | None = None
    hueco_fin: datetime | None = None
    hueco_profesional_id: uuid.UUID | None = None
    hueco_sillon_id: uuid.UUID | None = None
    aviso_vence_at: datetime | None = None
    ultimo_idempotency_key: str | None = None
    turno_colocado_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    token_gestion: str | None = None


class OfrecerHuecoRequest(BaseModel):
    """Solicitud para ofrecer o rotar un hueco liberado en la lista de espera."""

    model_config = ConfigDict(extra="forbid")

    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    inicio: datetime
    fin: datetime
    ventana_min: int = 60

    @model_validator(mode="after")
    def _validar_rango_y_ventana(self) -> "OfrecerHuecoRequest":
        if self.fin <= self.inicio:
            raise ValueError("La fecha/hora de fin del hueco tiene que ser posterior al inicio.")
        if self.ventana_min <= 0:
            raise ValueError("La ventana de respuesta en minutos tiene que ser mayor a 0.")
        return self


class ListaEsperaPublicaCreate(BaseModel):
    """Alta pública en lista de espera desde el portal del consultorio."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    dni: str
    telefono: str
    email: str | None = None
    fecha_nac: date | None = None
    obra_social_id: uuid.UUID | None = None
    nro_afiliado: str | None = None
    optin_wa: bool = True
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    canal_aviso: CanalAviso = CanalAviso.WA
    observaciones: str | None = None

    @field_validator("nombre")
    @classmethod
    def _validar_nombre(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("Che, el nombre del paciente no puede estar vacío.")
        return limpio

    @field_validator("dni")
    @classmethod
    def _validar_dni(cls, v: str) -> str:
        return _limpiar_dni(v)

    @field_validator("telefono")
    @classmethod
    def _validar_telefono(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("Che, el teléfono de contacto es obligatorio.")
        return limpio


class ListaEsperaPublicaRead(BaseModel):
    """Respuesta pública para gestionar la entrada de lista de espera por token opaco."""

    model_config = ConfigDict(extra="forbid")

    entrada_id: uuid.UUID
    estado: EstadoListaEspera
    prestacion_id: uuid.UUID
    prestacion_nombre: str
    profesional_id: uuid.UUID | None = None
    profesional_nombre: str | None = None
    canal_aviso: CanalAviso
    hueco_inicio: datetime | None = None
    hueco_fin: datetime | None = None
    aviso_vence_at: datetime | None = None
    turno_colocado_id: uuid.UUID | None = None
    token_gestion: str | None = None
