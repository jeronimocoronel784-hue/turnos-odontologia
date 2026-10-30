"""Rate limiting de login en Redis (C-03, D4).

Clave `login:{ip}:{sha256(email_normalizado)}`: el email nunca queda en claro en
Redis ni en logs (R9) y las variantes de mayúsculas comparten balde. Si Redis no
responde se falla cerrado (503): es un control de seguridad, no un adorno.
"""

import hashlib
from typing import Protocol

from app.shared.exceptions import DemasiadosIntentos, ServicioNoDisponible
from app.shared.logging import logger


class ClienteRedis(Protocol):
    """Subconjunto de Redis que usa el limiter (real en prod, fakeredis en tests)."""

    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> bool: ...

    async def ttl(self, key: str) -> int: ...


def normalizar_email(email: str) -> str:
    """Minúsculas y sin espacios: `Ana@X.com` y `ana@x.com` son el mismo balde."""
    return email.strip().lower()


def clave_login(ip: str, email: str) -> str:
    """Clave opaca: el email se hashea para no guardarlo en claro."""
    huella = hashlib.sha256(normalizar_email(email).encode("utf-8")).hexdigest()
    return f"login:{ip}:{huella}"


async def verificar_limite_login(
    cliente: ClienteRedis,
    *,
    ip: str,
    email: str,
    limite: int,
    ventana_segundos: int,
) -> None:
    """Cuenta el intento; si supera el límite levanta 429 con la espera restante."""
    clave = clave_login(ip, email)
    try:
        cantidad = await cliente.incr(clave)
        if cantidad == 1:
            await cliente.expire(clave, ventana_segundos)
        espera = max(await cliente.ttl(clave), 1)
    except Exception as exc:  # fail-closed: sin contador no se permite adivinar passwords
        raise ServicioNoDisponible(
            "Che, no pudimos verificar los intentos de ingreso. Probá en un rato."
        ) from exc

    if cantidad > limite:
        # Registro del bloqueo sin el email completo: solo IP + huella del email (R9).
        logger.warning(
            "login bloqueado por rate limit ip=%s email_sha256=%s espera=%ss",
            ip,
            clave.rsplit(":", 1)[-1][:16],
            espera,
        )
        raise DemasiadosIntentos(
            f"Demasiados intentos de ingreso. Esperá {espera} segundos y probá de nuevo."
        )
