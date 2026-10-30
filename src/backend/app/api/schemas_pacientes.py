"""Schemas Pydantic para el dominio de pacientes y fichas clínicas.

Cumple R1 (schemas estrictos con extra='forbid'), R4 (sin tenant_id en body),
R9 (sin PHI en logs de error) y RN-GL-02 (mensajes en rioplatense).
"""

import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _limpiar_dni(valor: str) -> str:
    """Limpia puntos, guiones y espacios del DNI."""
    limpio = re.sub(r"[\s.\-_]", "", valor.strip())
    return limpio


class PacienteCreate(_Estricto):
    """Alta de un paciente en el consultorio."""

    nombre: str = Field(min_length=1, max_length=160)
    dni: str = Field(min_length=1, max_length=30)
    telefono: str = Field(min_length=1, max_length=40)
    email: EmailStr | None = None
    fecha_nac: date | None = None
    obra_social_id: UUID | None = None
    nro_afiliado: str | None = Field(default=None, max_length=60)
    optin_wa: bool = Field(default=False)
    observaciones: str | None = None

    @model_validator(mode="after")
    def _validar_y_normalizar(self) -> "PacienteCreate":
        if not self.nombre.strip():
            raise ValueError("Che, el nombre del paciente no puede estar vacío.")
        self.nombre = self.nombre.strip()

        dni_norm = _limpiar_dni(self.dni)
        if len(dni_norm) < 4:
            raise ValueError("Che, el DNI ingresado no es válido o es demasiado corto.")
        self.dni = dni_norm

        if not self.telefono.strip():
            raise ValueError("Che, el teléfono de contacto no puede estar vacío.")
        self.telefono = self.telefono.strip()

        if self.nro_afiliado is not None:
            self.nro_afiliado = self.nro_afiliado.strip() or None

        if self.observaciones is not None:
            self.observaciones = self.observaciones.strip() or None

        return self


class PacienteUpdate(_Estricto):
    """Actualización parcial de los datos de un paciente."""

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    telefono: str | None = Field(default=None, min_length=1, max_length=40)
    email: EmailStr | None = None
    fecha_nac: date | None = None
    obra_social_id: UUID | None = None
    nro_afiliado: str | None = Field(default=None, max_length=60)
    observaciones: str | None = None
    activo: bool | None = None

    @model_validator(mode="after")
    def _validar_y_normalizar(self) -> "PacienteUpdate":
        if self.nombre is not None:
            if not self.nombre.strip():
                raise ValueError("Che, el nombre del paciente no puede estar vacío.")
            self.nombre = self.nombre.strip()

        if self.telefono is not None:
            if not self.telefono.strip():
                raise ValueError("Che, el teléfono no puede estar vacío.")
            self.telefono = self.telefono.strip()

        if self.nro_afiliado is not None:
            self.nro_afiliado = self.nro_afiliado.strip() or None

        if self.observaciones is not None:
            self.observaciones = self.observaciones.strip() or None

        return self


class PacienteOptinUpdate(_Estricto):
    """Actualización del consentimiento para mensajes de WhatsApp (alta o STOP)."""

    optin_wa: bool


class FichaClinicaRead(BaseModel):
    """Lectura de la ficha clínica de un paciente."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    antecedentes: str | None = None
    alergias: str | None = None
    medicacion: str | None = None
    habitos: str | None = None
    datos_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class PacienteRead(BaseModel):
    """Lectura de un paciente con su ficha clínica vinculada."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    nombre: str
    dni: str
    telefono: str
    email: str | None = None
    fecha_nac: date | None = None
    obra_social_id: UUID | None = None
    nro_afiliado: str | None = None
    optin_wa: bool
    observaciones: str | None = None
    activo: bool
    created_at: datetime
    updated_at: datetime
    ficha_clinica: FichaClinicaRead | None = None
