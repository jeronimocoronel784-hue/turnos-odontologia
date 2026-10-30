"""Contrato documentado de /api/auth coincide con los schemas reales (tarea 3.5).

El ejemplo del README se valida contra `TokenResponse`: si cambia el contrato y no
la documentación (o al revés), este test falla.
"""

import re
from pathlib import Path

from app.api.schemas_auth import LoginRequest, TokenResponse

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")


def _bloque_contrato() -> str:
    match = re.search(r"<!-- contrato-login -->\s*```json\s*(.*?)\s*```", README, re.DOTALL)
    assert match, "Falta el bloque <!-- contrato-login --> en README.md"
    return match.group(1)


def test_el_ejemplo_documentado_valida_contra_el_schema_real() -> None:
    ejemplo = TokenResponse.model_validate_json(_bloque_contrato())

    assert ejemplo.token_type == "bearer"
    assert ejemplo.expira_en_segundos > 0
    assert set(ejemplo.model_dump()) == {
        "access_token",
        "token_type",
        "expira_en_segundos",
        "usuario",
    }
    assert "refresh_token" not in ejemplo.model_dump()


def test_el_login_documentado_es_un_request_valido() -> None:
    request = LoginRequest(email="duena.piloto@example.com", password="secreto-de-prueba")

    assert request.tenant_slug is None


def test_el_readme_documenta_endpoints_codigos_y_cookie() -> None:
    for endpoint in (
        "POST /api/auth/login",
        "POST /api/auth/refresh",
        "POST /api/auth/logout",
        "GET /api/auth/me",
    ):
        assert endpoint in README, endpoint

    for codigo in ("`400`", "`401`", "`204`", "`200`", "`422`", "`429`", "`503`"):
        assert codigo in README, codigo

    for flag in ("HttpOnly", "SameSite=Lax", "Path=/api/auth", "Secure", "COOKIE_SECURE"):
        assert flag in README, flag

    assert "Authorization: Bearer" in README
    assert "refresh token nunca viaja en el body" in README
