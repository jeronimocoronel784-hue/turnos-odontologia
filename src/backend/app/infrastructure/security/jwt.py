"""Emisión y validación del access token JWT (C-03, D1).

Claims: `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.
El `tenant_id` del token es la ÚNICA fuente válida para filtrar datos (R4).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt

from app.shared.exceptions import NoAutenticado
from app.shared.settings import Settings

ALGORITMO = "HS256"
LEEWAY_SEGUNDOS = 30


def emitir_access(
    *,
    usuario_id: uuid.UUID,
    tenant_id: uuid.UUID,
    roles: list[str],
    email: str,
    settings: Settings,
) -> tuple[str, str]:
    """Devuelve `(token, jti)` con la vigencia configurada."""
    ahora = datetime.now(UTC)
    jti = uuid.uuid4().hex
    claims: dict[str, Any] = {
        "sub": str(usuario_id),
        "tenant_id": str(tenant_id),
        "roles": roles,
        "email": email,
        "jti": jti,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.jwt_access_min),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITMO), jti


def decodificar_access(token: str, settings: Settings) -> dict[str, Any]:
    """Valida firma, vigencia y `type`; cualquier falla es 401 genérico."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITMO],
            options={"leeway": LEEWAY_SEGUNDOS},
        )
    except JWTError as exc:
        raise NoAutenticado() from exc
    datos = cast(dict[str, Any], claims)
    if datos.get("type") != "access":
        raise NoAutenticado()
    return datos
