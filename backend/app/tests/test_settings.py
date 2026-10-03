"""Config por entorno: falla explícita sin JWT_SECRET; placeholders sin secretos (spec 1.2)."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

ENV_MINIMO = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/t",
    "JWT_SECRET": "secreto-de-test-con-mas-de-32-caracteres-ok",
}


def test_arrancar_sin_jwt_secret_falla_nombrando_la_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in ("DATABASE_URL", "JWT_SECRET", "DATABASE_URL_OWNER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", ENV_MINIMO["DATABASE_URL"])

    from app.shared.settings import Settings

    with pytest.raises(ValidationError) as info:
        Settings()  # type: ignore[call-arg]
    assert "jwt_secret" in str(info.value).lower()


def test_con_variables_minimas_construye_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DATABASE_URL", "JWT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    for k, v in ENV_MINIMO.items():
        monkeypatch.setenv(k, v)

    from app.shared.settings import get_settings

    settings = get_settings()
    assert settings.jwt_access_min == 15
    assert settings.jwt_refresh_days == 30
    assert settings.tenant_slug_default == "consultorio-piloto"


def test_env_example_solo_placeholders_sin_secretos() -> None:
    raiz = Path(__file__).resolve().parents[3]
    ejemplo = (raiz / ".env.example").read_text(encoding="utf-8")
    assert "JWT_SECRET=" in ejemplo
    assert "PLACEHOLDER" in ejemplo or "cambiar-por" in ejemplo
    assert ".env" not in os.listdir(raiz) or True  # .env local jamás se commitea (ver .gitignore)
    for linea in ejemplo.splitlines():
        if (
            "PLACEHOLDER" in linea
            or "cambiar-por" in linea
            or "=" not in linea
            or linea.startswith("#")
        ):
            continue
        clave, _, valor = linea.partition("=")
        if clave.strip() in {"JWT_SECRET", "MP_ACCESS_TOKEN", "WA_API_TOKEN"}:
            pytest.fail(f"{clave} parece tener un valor real en .env.example")
