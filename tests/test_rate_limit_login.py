"""Rate limiting de login en Redis: 5/60 s, ventana, normalización y fail-closed (tarea 2.4).

D4: clave `login:{ip}:{sha256(email normalizado)}`, así `Ana@X.com` y `ana@x.com`
comparten balde y el email nunca queda en claro en Redis ni en logs (R9). Si Redis
no responde, el login falla cerrado (503): es un control de seguridad.
"""

import asyncio
import hashlib
import logging

import pytest

from app.infrastructure.security import rate_limit
from app.infrastructure.security.rate_limit import clave_login, verificar_limite_login
from app.shared.exceptions import DemasiadosIntentos, ServicioNoDisponible

IP = "10.0.0.7"
EMAIL = "ana@example.com"
LIMITE = 5
VENTANA = 60


async def _intentar(cliente, *, ip: str = IP, email: str = EMAIL, ventana: int = VENTANA) -> None:
    await verificar_limite_login(
        cliente, ip=ip, email=email, limite=LIMITE, ventana_segundos=ventana
    )


async def test_el_sexto_intento_en_la_ventana_da_429(redis_fake) -> None:
    for _ in range(LIMITE):
        await _intentar(redis_fake)

    with pytest.raises(DemasiadosIntentos) as info:
        await _intentar(redis_fake)

    assert info.value.status_code == 429
    assert "segundos" in info.value.mensaje
    assert "Demasiados intentos" in info.value.mensaje


async def test_otro_email_u_otra_ip_no_comparten_el_balde(redis_fake) -> None:
    for _ in range(LIMITE):
        await _intentar(redis_fake)

    # El balde es por IP + email: otra IP y otro email siguen habilitados.
    await _intentar(redis_fake, ip="10.0.0.8")
    await _intentar(redis_fake, email="otra@example.com")
    with pytest.raises(DemasiadosIntentos):
        await _intentar(redis_fake)


async def test_ventana_expirada_habilita_un_intento_nuevo(redis_fake) -> None:
    for _ in range(LIMITE):
        await _intentar(redis_fake, ventana=1)
    with pytest.raises(DemasiadosIntentos):
        await _intentar(redis_fake, ventana=1)

    await asyncio.sleep(1.1)

    await _intentar(redis_fake, ventana=1)  # vuelve a evaluarse normalmente


async def test_mayusculas_y_espacios_comparten_balde(redis_fake) -> None:
    for _ in range(LIMITE):
        await _intentar(redis_fake, email="Ana@Example.com")

    with pytest.raises(DemasiadosIntentos):
        await _intentar(redis_fake, email="  ana@example.COM  ")


def test_la_clave_no_lleva_el_email_en_claro() -> None:
    clave = clave_login(IP, "Ana@Example.com")
    esperado = hashlib.sha256(b"ana@example.com").hexdigest()

    assert clave == f"login:{IP}:{esperado}"
    assert "ana" not in clave.lower()
    assert "@" not in clave
    assert clave_login(IP, "ana@example.com") == clave


async def test_falla_cerrado_si_redis_no_responde() -> None:
    class _RedisCaido:
        async def incr(self, key: str) -> int:
            raise ConnectionError("redis caído")

        async def expire(self, key: str, seconds: int) -> bool:  # pragma: no cover - no llega
            return False

        async def ttl(self, key: str) -> int:  # pragma: no cover - no llega
            return -1

    with pytest.raises(ServicioNoDisponible) as info:
        await _intentar(_RedisCaido())

    assert info.value.status_code == 503
    assert "intentos de ingreso" in info.value.mensaje


async def test_el_bloqueo_se_registra_sin_el_email_completo(redis_fake, monkeypatch) -> None:
    registros: list[logging.LogRecord] = []

    class _Espia(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            registros.append(record)

    logger = logging.getLogger("turnos.rate_limit.test")
    logger.addHandler(_Espia())
    logger.setLevel(logging.DEBUG)
    monkeypatch.setattr(rate_limit, "logger", logger, raising=False)

    for _ in range(LIMITE):
        await _intentar(redis_fake)
    with pytest.raises(DemasiadosIntentos):
        await _intentar(redis_fake)

    mensajes = "\n".join(record.getMessage() for record in registros)
    assert IP in mensajes
    assert "bloque" in mensajes.lower()
    assert EMAIL not in mensajes
