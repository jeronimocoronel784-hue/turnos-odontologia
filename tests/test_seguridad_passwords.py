"""Password hashing con bcrypt: rounds configurables y hash nunca expuesto (C-03, tarea 2.1).

D1b: `bcrypt` directo (sin `passlib`), formato `$2b$` y `BCRYPT_ROUNDS` configurable
(4 en tests, 12 por defecto). R9: el hash y el password jamás salen en una respuesta
ni en un log.
"""

import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import UsuarioCreate
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.passwords import (
    PasswordInvalido,
    hashear_password,
    verificar_password,
)
from app.shared.settings import Settings

PASSWORD = "secreto-de-prueba"


def test_password_correcto_verifica_y_el_incorrecto_no() -> None:
    hash_guardado = hashear_password(PASSWORD, rounds=4)

    assert verificar_password(PASSWORD, hash_guardado) is True
    assert verificar_password("secreto-de-prueba-2", hash_guardado) is False
    assert verificar_password("", hash_guardado) is False


def test_mismo_password_con_dos_sales_genera_hashes_distintos() -> None:
    primero = hashear_password(PASSWORD, rounds=4)
    segundo = hashear_password(PASSWORD, rounds=4)

    assert primero != segundo
    assert verificar_password(PASSWORD, primero) is True
    assert verificar_password(PASSWORD, segundo) is True


def test_bcrypt_rounds_es_configurable_y_doce_es_el_default() -> None:
    assert hashear_password(PASSWORD, rounds=4).startswith("$2b$04$")
    assert hashear_password(PASSWORD, rounds=5).startswith("$2b$05$")
    assert (
        Settings(database_url="sqlite+aiosqlite:///:memory:", jwt_secret="x" * 40).bcrypt_rounds
        == 12
    )


def test_password_de_mas_de_72_bytes_no_se_trunca_en_silencio() -> None:
    # 30 emojis = 120 bytes: bcrypt solo mira 72, así que se rechaza explícitamente.
    with pytest.raises(PasswordInvalido):
        hashear_password("🙂" * 30, rounds=4)


def test_hash_corrupto_cuenta_como_password_incorrecto() -> None:
    # Un seed viejo (pbkdf2) o una fila corrupta no deben romper con 500 ni autenticar.
    assert verificar_password(PASSWORD, "pbkdf2_sha256$100000$sal$digest") is False
    assert verificar_password(PASSWORD, "") is False


async def test_hash_y_password_nunca_aparecen_en_la_respuesta_ni_en_logs(
    api, session: AsyncSession, tenant_a: Tenant, crear_usuario, caplog
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email="hash@example.com")
    capturado: list[logging.LogRecord] = []

    class _Espia(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            capturado.append(record)

    logger_app = logging.getLogger("turnos")
    logger_app.addHandler(_Espia())
    try:
        with caplog.at_level(logging.DEBUG):
            login = await api.post(
                "/api/auth/login", json={"email": usuario.email, "password": PASSWORD}
            )
    finally:
        logger_app.handlers = [h for h in logger_app.handlers if not isinstance(h, _Espia)]

    assert login.status_code == 200
    assert usuario.password_hash not in login.text
    assert PASSWORD not in login.text
    assert all(usuario.password_hash not in record.getMessage() for record in capturado)
    assert all(PASSWORD not in record.getMessage() for record in capturado)

    token = login.json()["access_token"]
    listado = await api.get("/api/usuarios", headers={"Authorization": f"Bearer {token}"})
    assert listado.status_code == 200
    assert usuario.password_hash not in listado.text
    assert "password_hash" not in listado.text


def test_el_schema_de_alta_limita_el_password_para_bcrypt() -> None:
    # El tope del schema (72 caracteres) no alcanza para multibyte: el router debe
    # rechazar el caso con un 400 rioplatense, nunca con un 500 (ver test_usuarios_api).
    with pytest.raises(ValueError):
        UsuarioCreate(
            email="odonto@example.com",
            nombre="Odonto Test",
            rol=RolUsuario.ODONTOLOGO,
            password="x" * 129,
        )
