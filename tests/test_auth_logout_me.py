"""Logout con revocación y GET /api/auth/me sin datos sensibles (tarea 3.3)."""

import uuid
from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy import select

from app.domain.refresh_token import RefreshToken
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.jwt import ALGORITMO
from app.infrastructure.security.tokens_publicos import hashear_token
from app.shared.settings import Settings

EMAIL = "staff@example.com"
PASSWORD = "secreto-de-prueba"


async def _login(api) -> str:
    respuesta = await api.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _refresh_de_la_cookie(api) -> str:
    valor = api.cookies.get("refresh_token")
    assert valor
    return valor


async def test_logout_revoca_la_sesion_borra_la_cookie_y_audita(
    api, session, tenant_a: Tenant, crear_usuario, auditoria_de
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    refresh = _refresh_de_la_cookie(api)

    respuesta = await api.post("/api/auth/logout")

    assert respuesta.status_code == 204
    assert respuesta.text == ""
    assert "Max-Age=0" in respuesta.headers.get_list("set-cookie")[0]

    fila = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hashear_token(refresh))
        )
    ).scalar_one()
    assert fila.revocado_at is not None

    eventos = await auditoria_de("auth.logout")
    assert len(eventos) == 1
    assert eventos[0].actor_id == usuario.id
    assert refresh not in f"{eventos[0].antes}{eventos[0].despues}"

    api.cookies.set("refresh_token", refresh, path="/")
    assert (await api.post("/api/auth/refresh")).status_code == 401


async def test_logout_es_idempotente(api, tenant_a: Tenant, crear_usuario) -> None:
    sin_cookie = await api.post("/api/auth/logout")
    assert sin_cookie.status_code == 204
    assert "Max-Age=0" in sin_cookie.headers.get_list("set-cookie")[0]

    await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    segundo = await api.post("/api/auth/logout")
    assert segundo.status_code == 204

    api.cookies.set("refresh_token", "cookie-basura", path="/")
    assert (await api.post("/api/auth/logout")).status_code == 204


async def test_me_devuelve_la_identidad_exacta_sin_hash(
    api, tenant_a: Tenant, crear_usuario
) -> None:
    usuario: Usuario = await crear_usuario(
        tenant_a, email=EMAIL, nombre="Persona Staff", rol=RolUsuario.RECEPCION
    )

    token = await _login(api)
    respuesta = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "id": str(usuario.id),
        "tenant_id": str(tenant_a.id),
        "tenant_slug": "tenant-a-test",
        "email": EMAIL,
        "nombre": "Persona Staff",
        "roles": ["recepcion"],
    }
    assert "password_hash" not in respuesta.text
    assert usuario.password_hash not in respuesta.text


async def test_me_sin_token_o_con_header_malformado_es_401(api) -> None:
    sin_header = await api.get("/api/auth/me")
    sin_token = await api.get("/api/auth/me", headers={"Authorization": "Bearer"})
    otro_esquema = await api.get("/api/auth/me", headers={"Authorization": f"Basic {uuid.uuid4()}"})

    assert [r.status_code for r in (sin_header, sin_token, otro_esquema)] == [401, 401, 401]


async def test_me_rechaza_token_vencido_de_otro_tipo_o_con_otro_tenant(
    api, tenant_a: Tenant, tenant_b: Tenant, crear_usuario, settings_test: Settings
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)
    ahora = datetime.now(UTC)

    def _firmar(**overrides: object) -> str:
        claims: dict[str, object] = {
            "sub": str(usuario.id),
            "tenant_id": str(tenant_a.id),
            "roles": ["recepcion"],
            "email": EMAIL,
            "jti": uuid.uuid4().hex,
            "type": "access",
            "iat": ahora,
            "exp": ahora + timedelta(minutes=15),
        }
        claims.update(overrides)
        return jwt.encode(claims, settings_test.jwt_secret, algorithm=ALGORITMO)

    vencido = _firmar(exp=ahora - timedelta(minutes=5))
    de_refresh = _firmar(type="refresh")
    otro_tenant = _firmar(tenant_id=str(tenant_b.id))

    for token in (vencido, de_refresh, otro_tenant):
        respuesta = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert respuesta.status_code == 401

    # Usuario desactivado o inexistente: el token deja de servir aunque la firma sea válida.
    usuario.activo = False
    assert (
        await api.get("/api/auth/me", headers={"Authorization": f"Bearer {_firmar()}"})
    ).status_code == 401

    fantasma = _firmar(sub=str(uuid.uuid4()))
    assert (
        await api.get("/api/auth/me", headers={"Authorization": f"Bearer {fantasma}"})
    ).status_code == 401


async def test_me_no_filtra_datos_de_otro_usuario_del_mismo_tenant(
    api, tenant_a: Tenant, crear_usuario
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL, nombre="Persona Staff")
    await crear_usuario(tenant_a, email="otra@example.com", nombre="Otra Persona")

    token = await _login(api)
    cuerpo = (await api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()

    assert cuerpo["id"] == str(usuario.id)
    assert cuerpo["email"] == EMAIL
    assert cuerpo["nombre"] != "Otra Persona"
