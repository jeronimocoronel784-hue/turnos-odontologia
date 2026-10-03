"""Schemas Pydantic de la API. NUNCA se exponen modelos ORM crudos (R1).

Inputs con `extra='forbid'`; sin `Any` en schemas públicos; sin PHI en errores (R9).
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.usuario import RolUsuario


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TenantCreate(_Estricto):
    """Alta de consultorio (el seed y C-03 la usan; el slug es único global)."""

    slug: str = Field(min_length=3, max_length=120)
    nombre: str = Field(min_length=3, max_length=200)
    politicas: dict[str, str | int | bool] = Field(default_factory=dict)


class TenantRead(BaseModel):
    """Lectura de tenant (salida: extra ignorado por compatibilidad)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nombre: str
    politicas: dict[str, str | int | bool]
    activo: bool


class UsuarioCreate(_Estricto):
    """Alta de staff. Matrícula obligatoria si rol odontólogo (spec 2.1)."""

    email: EmailStr
    nombre: str = Field(min_length=2, max_length=200)
    rol: RolUsuario
    matricula: str | None = Field(default=None, max_length=60)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _matricula_si_odontologo(self) -> "UsuarioCreate":
        if self.rol == RolUsuario.ODONTOLOGO and not (self.matricula and self.matricula.strip()):
            raise ValueError("Che, la matrícula profesional es obligatoria para odontólogos.")
        return self


class UsuarioRead(BaseModel):
    """Lectura de usuario: jamás expone password_hash (R9)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    email: str
    nombre: str
    rol: RolUsuario
    matricula: str | None
    activo: bool


class HealthEstado(BaseModel):
    """Respuesta de GET /api/health (sin PHI, sin stack traces)."""

    model_config = ConfigDict(extra="forbid")

    estado: str
    api: str
    base_de_datos: str
    redis: str
    detalle: str = ""
