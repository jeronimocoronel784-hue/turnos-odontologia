"""Settings centralizados (Pydantic v2). Toda config sensible viene de entorno (RN-SE-04)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la API leída solo desde variables de entorno."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        description="Conexión PostgreSQL (ej: postgresql+asyncpg://user:pass@db:5432/turnos)"
    )
    database_url_owner: str = Field(
        default="",
        description="Conexión owner para Alembic/seed (D4: rol separado del rol app restringido)",
    )
    redis_url: str = Field(default="redis://redis:6379/0", description="Conexión Redis")
    jwt_secret: str = Field(description="Firma de tokens (aleatorio 32+ caracteres)")
    jwt_access_min: int = Field(default=15, description="Vida útil del access token en minutos")
    jwt_refresh_days: int = Field(default=30, description="Vida útil del refresh token en días")
    mp_access_token: str = Field(default="", description="Credencial Mercado Pago")
    mp_webhook_secret: str = Field(default="", description="Firma webhook Mercado Pago")
    wa_api_token: str = Field(default="", description="Token Cloud API WhatsApp")
    wa_phone_id: str = Field(default="", description="ID número emisor WhatsApp")
    wa_webhook_token: str = Field(default="", description="Verificación webhook WhatsApp")
    smtp_url: str = Field(default="", description="Servidor de email transaccional")
    front_url: str = Field(default="http://localhost:5173", description="URL pública del frontend")
    tenant_slug_default: str = Field(
        default="consultorio-piloto", description="Slug del tenant piloto"
    )


def get_settings() -> Settings:
    """Construye Settings; falla con el nombre de la variable faltante (spec 1.2)."""
    return Settings()  # type: ignore[call-arg]
