"""Schemas de autenticación y usuarios (R1: nunca se exponen modelos ORM crudos)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.usuario import RolUsuario


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Estricto):
    """Credenciales del staff. `tenant_slug` solo hace falta si el email está repetido."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
    tenant_slug: str | None = Field(default=None, min_length=3, max_length=120)


class IdentidadRead(BaseModel):
    """Identidad mínima del usuario autenticado: sin hash ni datos clínicos."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    tenant_slug: str
    email: str
    nombre: str
    roles: list[RolUsuario]


class TokenResponse(BaseModel):
    """Respuesta de login/refresh: el access viaja acá, el refresh solo en cookie."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expira_en_segundos: int
    usuario: IdentidadRead


class RolUpdate(_Estricto):
    """Cambio de rol y matrícula de un usuario del tenant."""

    rol: RolUsuario
    matricula: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _matricula_si_odontologo(self) -> "RolUpdate":
        if self.rol == RolUsuario.ODONTOLOGO and not (self.matricula and self.matricula.strip()):
            raise ValueError("Che, la matrícula profesional es obligatoria para odontólogos.")
        return self
