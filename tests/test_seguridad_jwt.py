"""Access token JWT: claims exactos, vigencia y rechazos (C-03, tarea 2.2).

D1: HS256 con `python-jose`, claims `sub`, `tenant_id`, `roles`, `email`, `jti`,
`type`, `iat`, `exp`; leeway de 30 s para tolerar skew de reloj.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.infrastructure.security.jwt import (
    ALGORITMO,
    LEEWAY_SEGUNDOS,
    decodificar_access,
    emitir_access,
)
from app.shared.exceptions import NoAutenticado
from app.shared.settings import Settings

CLAIMS_ESPERADOS = {"sub", "tenant_id", "roles", "email", "jti", "type", "iat", "exp"}


def _claims(token: str, settings: Settings) -> dict:
    """Decodifica sin validar `exp` para poder inspeccionar tokens vencidos."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITMO],
        options={"verify_exp": False},
    )


def _token_manual(settings: Settings, **overrides: object) -> str:
    """Token firmado con la clave de test pero claims controlados por el test."""
    ahora = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "roles": ["recepcion"],
        "email": "staff@example.com",
        "jti": uuid.uuid4().hex,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=15),
    }
    claims.update(overrides)
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITMO)


def test_claims_exactos_del_access_token(settings_test: Settings) -> None:
    usuario_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    token, jti = emitir_access(
        usuario_id=usuario_id,
        tenant_id=tenant_id,
        roles=["dueno", "odontologo"],
        email="duena@example.com",
        settings=settings_test,
    )
    claims = _claims(token, settings_test)

    assert set(claims) == CLAIMS_ESPERADOS
    assert claims["sub"] == str(usuario_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert claims["roles"] == ["dueno", "odontologo"]
    assert claims["email"] == "duena@example.com"
    assert claims["jti"] == jti
    assert claims["type"] == "access"
    assert isinstance(claims["iat"], int)
    assert isinstance(claims["exp"], int)


def test_vigencia_sale_de_jwt_access_min_y_el_jti_es_unico(settings_test: Settings) -> None:
    corto = settings_test.model_copy(update={"jwt_access_min": 2})
    token, jti_1 = emitir_access(
        usuario_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        roles=["recepcion"],
        email="staff@example.com",
        settings=corto,
    )
    otro, jti_2 = emitir_access(
        usuario_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        roles=["recepcion"],
        email="staff@example.com",
        settings=corto,
    )
    claims = _claims(token, corto)

    assert claims["exp"] - claims["iat"] == 2 * 60
    assert jti_1 != jti_2
    assert _claims(otro, corto)["jti"] == jti_2


def test_token_vigente_y_bien_firmado_se_acepta(settings_test: Settings) -> None:
    token, jti = emitir_access(
        usuario_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        roles=["recepcion"],
        email="staff@example.com",
        settings=settings_test,
    )

    assert decodificar_access(token, settings_test)["jti"] == jti


def test_token_vencido_se_rechaza(settings_test: Settings) -> None:
    token = _token_manual(
        settings_test,
        iat=datetime.now(UTC) - timedelta(minutes=20),
        exp=datetime.now(UTC) - timedelta(seconds=LEEWAY_SEGUNDOS + 30),
    )

    with pytest.raises(NoAutenticado):
        decodificar_access(token, settings_test)


def test_leeway_de_30_segundos_tolera_skew_de_reloj(settings_test: Settings) -> None:
    # Vencido hace 10 s: dentro del leeway, sigue sirviendo.
    token = _token_manual(
        settings_test,
        iat=datetime.now(UTC) - timedelta(minutes=16),
        exp=datetime.now(UTC) - timedelta(seconds=10),
    )

    assert decodificar_access(token, settings_test)["type"] == "access"
    assert LEEWAY_SEGUNDOS == 30


def test_firma_invalida_se_rechaza(settings_test: Settings) -> None:
    otro_secreto = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="otro-secreto-de-test-con-mas-de-32-caracteres",
        bcrypt_rounds=4,
    )
    token, _ = emitir_access(
        usuario_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        roles=["dueno"],
        email="duena@example.com",
        settings=otro_secreto,
    )

    with pytest.raises(NoAutenticado):
        decodificar_access(token, settings_test)


@pytest.mark.parametrize("tipo", ["refresh", "access ", "", None])
def test_type_distinto_de_access_se_rechaza(settings_test: Settings, tipo: str | None) -> None:
    token = _token_manual(settings_test, type=tipo)

    with pytest.raises(NoAutenticado):
        decodificar_access(token, settings_test)


def test_token_manipulado_o_basura_se_rechaza(settings_test: Settings) -> None:
    token = _token_manual(settings_test)
    manipulados = [
        token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb"),
        "no.es.un.jwt",
        "",
    ]

    for candidato in manipulados:
        with pytest.raises(NoAutenticado):
            decodificar_access(candidato, settings_test)
