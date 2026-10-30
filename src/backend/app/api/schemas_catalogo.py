"""Schemas Pydantic para el catálogo clínico-administrativo y configuración.

Cumple R1 (schemas estrictos con extra='forbid'), R8 (Decimal en importes monetarios)
y R9/RN-GL-02 (mensajes de error en rioplatense sin PHI).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- SILLÓN ---


class SillonCreate(_Estricto):
    """Alta de un sillón o box de atención."""

    nombre: str = Field(min_length=1, max_length=120)
    sucursal: str = Field(default="central", min_length=1, max_length=120)
    activo: bool = Field(default=True)

    @model_validator(mode="after")
    def _validar_nombre(self) -> "SillonCreate":
        if not self.nombre.strip():
            raise ValueError("Che, el nombre del sillón no puede estar vacío.")
        self.nombre = self.nombre.strip()
        self.sucursal = self.sucursal.strip()
        return self


class SillonUpdate(_Estricto):
    """Actualización parcial de un sillón."""

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    sucursal: str | None = Field(default=None, min_length=1, max_length=120)
    activo: bool | None = None

    @model_validator(mode="after")
    def _validar_campos(self) -> "SillonUpdate":
        if self.nombre is not None:
            if not self.nombre.strip():
                raise ValueError("Che, el nombre del sillón no puede estar vacío.")
            self.nombre = self.nombre.strip()
        if self.sucursal is not None:
            if not self.sucursal.strip():
                raise ValueError("Che, la sucursal del sillón no puede estar vacía.")
            self.sucursal = self.sucursal.strip()
        return self


class SillonRead(BaseModel):
    """Representación pública de un sillón."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    nombre: str
    sucursal: str
    activo: bool
    created_at: datetime
    updated_at: datetime


# --- PRESTACIÓN ---


class PrestacionCreate(_Estricto):
    """Alta de prestación odontológica."""

    nombre: str = Field(min_length=1, max_length=160)
    duracion_min: int
    precio_particular: Decimal
    requiere_sena: bool = False
    monto_sena: Decimal | None = None
    invasiva: bool = False
    activa: bool = True

    @model_validator(mode="after")
    def _validar_negocio(self) -> "PrestacionCreate":
        if not self.nombre.strip():
            raise ValueError("Che, el nombre de la prestación no puede estar vacío.")
        self.nombre = self.nombre.strip()

        if self.duracion_min <= 0:
            raise ValueError("Che, la duración debe ser mayor a cero minutos.")
        if self.precio_particular < Decimal("0.00"):
            raise ValueError("Che, el precio particular no puede ser negativo.")

        if self.requiere_sena:
            if self.monto_sena is None or self.monto_sena <= Decimal("0.00"):
                raise ValueError(
                    "Che, tenés que informar un monto de seña mayor a cero "
                    "cuando la prestación requiere seña."
                )
        else:
            self.monto_sena = None
        return self


class PrestacionUpdate(_Estricto):
    """Actualización parcial de prestación odontológica."""

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    duracion_min: int | None = None
    precio_particular: Decimal | None = None
    requiere_sena: bool | None = None
    monto_sena: Decimal | None = None
    invasiva: bool | None = None
    activa: bool | None = None

    @model_validator(mode="after")
    def _validar_negocio(self) -> "PrestacionUpdate":
        if self.nombre is not None:
            if not self.nombre.strip():
                raise ValueError("Che, el nombre de la prestación no puede estar vacío.")
            self.nombre = self.nombre.strip()

        if self.duracion_min is not None and self.duracion_min <= 0:
            raise ValueError("Che, la duración debe ser mayor a cero minutos.")
        if self.precio_particular is not None and self.precio_particular < Decimal("0.00"):
            raise ValueError("Che, el precio particular no puede ser negativo.")

        if self.requiere_sena is True:
            if self.monto_sena is not None and self.monto_sena <= Decimal("0.00"):
                raise ValueError(
                    "Che, tenés que informar un monto de seña mayor a cero "
                    "cuando la prestación requiere seña."
                )
        elif self.requiere_sena is False:
            self.monto_sena = None
        return self


class PrestacionRead(BaseModel):
    """Representación pública de una prestación."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    nombre: str
    duracion_min: int
    precio_particular: Decimal
    requiere_sena: bool
    monto_sena: Decimal | None
    invasiva: bool
    activa: bool
    created_at: datetime
    updated_at: datetime


# --- COBERTURA OBRA SOCIAL ---


class CoberturaOSCreate(_Estricto):
    """Alta de convenio con obra social."""

    obra_social: str = Field(min_length=1, max_length=160)
    prestacion_id: UUID
    arancel: Decimal = Field(ge=Decimal("0.00"))
    copago: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    vigencia_desde: date
    vigencia_hasta: date | None = None
    activa: bool = True

    @model_validator(mode="after")
    def _validar_fechas_y_montos(self) -> "CoberturaOSCreate":
        if not self.obra_social.strip():
            raise ValueError("Che, el nombre de la obra social no puede estar vacío.")
        self.obra_social = self.obra_social.strip()

        if self.arancel < Decimal("0.00"):
            raise ValueError("Che, el arancel no puede ser negativo.")
        if self.copago < Decimal("0.00"):
            raise ValueError("Che, el copago no puede ser negativo.")

        if self.vigencia_hasta is not None and self.vigencia_hasta < self.vigencia_desde:
            raise ValueError(
                "Che, la vigencia hasta debe ser posterior o igual a la vigencia desde."
            )
        return self


class CoberturaOSUpdate(_Estricto):
    """Actualización parcial de convenio con obra social."""

    obra_social: str | None = Field(default=None, min_length=1, max_length=160)
    arancel: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    copago: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    activa: bool | None = None

    @model_validator(mode="after")
    def _validar_fechas_y_montos(self) -> "CoberturaOSUpdate":
        if self.obra_social is not None:
            if not self.obra_social.strip():
                raise ValueError("Che, el nombre de la obra social no puede estar vacío.")
            self.obra_social = self.obra_social.strip()

        if self.arancel is not None and self.arancel < Decimal("0.00"):
            raise ValueError("Che, el arancel no puede ser negativo.")
        if self.copago is not None and self.copago < Decimal("0.00"):
            raise ValueError("Che, el copago no puede ser negativo.")

        if (
            self.vigencia_desde is not None
            and self.vigencia_hasta is not None
            and self.vigencia_hasta < self.vigencia_desde
        ):
            raise ValueError(
                "Che, la vigencia hasta debe ser posterior o igual a la vigencia desde."
            )
        return self


class CoberturaOSRead(BaseModel):
    """Representación pública de una cobertura de obra social."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    obra_social: str
    prestacion_id: UUID
    arancel: Decimal
    copago: Decimal
    vigencia_desde: date
    vigencia_hasta: date | None
    activa: bool
    created_at: datetime
    updated_at: datetime


# --- POLÍTICAS OPERATIVAS DEL CONSULTORIO ---


class PoliticasRead(BaseModel):
    """Políticas operativas del consultorio."""

    anticipacion_min_dias: int
    sena_default_pct: int
    cancelacion_horas: int
    anticipacion_min_hs: int | None = None


class PoliticasUpdate(_Estricto):
    """Actualización parcial de políticas operativas del consultorio."""

    anticipacion_min_dias: int | None = None
    sena_default_pct: int | None = None
    cancelacion_horas: int | None = None
    anticipacion_min_hs: int | None = None

    @model_validator(mode="after")
    def _validar_rangos(self) -> "PoliticasUpdate":
        if self.sena_default_pct is not None and not (0 <= self.sena_default_pct <= 100):
            raise ValueError("Che, el porcentaje de seña por defecto debe estar entre 0 y 100.")
        if self.anticipacion_min_dias is not None and self.anticipacion_min_dias < 0:
            raise ValueError("Che, los días de anticipación mínima no pueden ser negativos.")
        if self.cancelacion_horas is not None and self.cancelacion_horas < 0:
            raise ValueError("Che, las horas de cancelación no pueden ser negativas.")
        if self.anticipacion_min_hs is not None and self.anticipacion_min_hs < 0:
            raise ValueError("Che, las horas de anticipación mínima no pueden ser negativas.")
        return self
