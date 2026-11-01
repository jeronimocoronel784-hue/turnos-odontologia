"""Schemas Pydantic estrictos para Agenda, Turnos, Bloqueos y Reserva Pública (C-06, R1)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.api.schemas_pacientes import _limpiar_dni
from app.domain.bloqueo import MotivoBloqueo
from app.domain.turno import EstadoTurno, OrigenTurno


class TurnoCreate(BaseModel):
    """Alta interna de turno odontológico."""

    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime
    fin: datetime | None = None
    origen: OrigenTurno = OrigenTurno.PRESENCIAL
    sobreturno: bool = False
    observaciones: str | None = None
    sena_cobrada: bool = False

    @field_validator("observaciones")
    @classmethod
    def _normalizar_observaciones(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None

    @model_validator(mode="after")
    def _validar_reglas_turno(self) -> "TurnoCreate":
        if self.fin is not None and self.fin <= self.inicio:
            raise ValueError("La hora de fin del turno tiene que ser posterior al inicio.")
        if self.sobreturno and not self.observaciones:
            raise ValueError(
                "Para crear un sobreturno tenés que indicar el motivo en observaciones."
            )
        return self


class TurnoEstadoUpdate(BaseModel):
    """Transición de estado de un turno (RN-AG-07)."""

    model_config = ConfigDict(extra="forbid")

    estado: EstadoTurno
    motivo_cancelacion: str | None = None
    sena_cobrada: bool | None = None

    @field_validator("motivo_cancelacion")
    @classmethod
    def _limpiar_motivo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        limpio = v.strip()
        return limpio or None


class TurnoReprogramarRequest(BaseModel):
    """Solicitud de reprogramación en 1 clic (RN-AG-06)."""

    model_config = ConfigDict(extra="forbid")

    nuevo_inicio: datetime
    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None
    motivo: str | None = None


class TurnoRead(BaseModel):
    """Respuesta de turno en agenda interna y administración."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime
    fin: datetime
    estado: EstadoTurno
    origen: OrigenTurno
    sobreturno: bool
    observaciones: str | None = None
    motivo_cancelacion: str | None = None
    turno_origen_id: uuid.UUID | None = None
    sena_cobrada: bool
    created_at: datetime
    updated_at: datetime
    token_gestion: str | None = None


class BloqueoCreate(BaseModel):
    """Alta de bloqueo horario para profesional y/o sillón (RN-AG-03)."""

    model_config = ConfigDict(extra="forbid")

    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None
    desde: datetime
    hasta: datetime
    motivo: MotivoBloqueo = MotivoBloqueo.MANUAL
    descripcion: str | None = None

    @model_validator(mode="after")
    def _validar_bloqueo(self) -> "BloqueoCreate":
        if self.profesional_id is None and self.sillon_id is None:
            raise ValueError(
                "Tenés que indicar al menos un profesional o un sillón para el bloqueo."
            )
        if self.hasta <= self.desde:
            raise ValueError("La fecha/hora hasta del bloqueo tiene que ser posterior a desde.")
        return self


class BloqueoRead(BaseModel):
    """Respuesta de bloqueo horario."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None
    desde: datetime
    hasta: datetime
    motivo: MotivoBloqueo
    descripcion: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SlotDisponibleRead(BaseModel):
    """Slot horario disponible para reserva o alternativa ante conflicto."""

    model_config = ConfigDict(extra="forbid")

    inicio: datetime
    fin: datetime
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID


class AgendaVistaRead(BaseModel):
    """Vista consolidada de agenda diaria/semanal con turnos y bloqueos."""

    model_config = ConfigDict(extra="forbid")

    desde: datetime
    hasta: datetime
    turnos: list[TurnoRead]
    bloqueos: list[BloqueoRead]


class ReservaPublicaCreate(BaseModel):
    """Formulario público de reserva online sin login (Flujo 1)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    dni: str
    telefono: str
    email: str | None = None
    fecha_nac: date | None = None
    obra_social_id: uuid.UUID | None = None
    nro_afiliado: str | None = None
    optin_wa: bool = False
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    inicio: datetime

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


class ReservaPublicaRead(BaseModel):
    """Respuesta pública al reservar o consultar por token (sin exponer datos de terceros)."""

    model_config = ConfigDict(extra="forbid")

    turno_id: uuid.UUID
    estado: EstadoTurno
    inicio: datetime
    fin: datetime
    prestacion_id: uuid.UUID
    prestacion_nombre: str
    profesional_id: uuid.UUID
    profesional_nombre: str
    sillon_id: uuid.UUID
    sillon_nombre: str
    requiere_sena: bool
    monto_sena: Decimal | None = None
    sena_cobrada: bool
    token_gestion: str | None = None


class CancelarPublicoRequest(BaseModel):
    """Solicitud pública de cancelación por token."""

    model_config = ConfigDict(extra="forbid")

    motivo: str | None = None


class ReprogramarPublicoRequest(BaseModel):
    """Solicitud pública de reprogramación por token."""

    model_config = ConfigDict(extra="forbid")

    nuevo_inicio: datetime
    motivo: str | None = None
