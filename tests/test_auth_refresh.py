"""POST /api/auth/refresh: rotación real, reúso revoca la familia y auditoría (tarea 3.2).

D2: el refresh es opaco y se guarda hasheado; cada uso rota y el reúso de uno ya
rotado mata toda la cadena (`familia_id`) y audita `auth.refresh_reuso`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.domain.refresh_token import RefreshToken
from app.domain.tenant import Tenant
from app.domain.usuario import Usuario
from app.infrastructure.security.tokens_publicos import hashear_token

EMAIL = "dueno@example.com"
PASSWORD = "secreto-de-prueba"


async def _login(api) -> str:
    respuesta = await api.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _cookie(api) -> str:
    valor = api.cookies.get("refresh_token")
    assert valor
    return valor


def _usar_cookie(api, valor: str) -> None:
    api.cookies.set("refresh_token", valor, path="/")


async def _refresh(api):
    return await api.post("/api/auth/refresh")


async def _fila(session, valor: str) -> RefreshToken:
    return (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hashear_token(valor))
        )
    ).scalar_one()


async def test_refresh_normal_rota_el_token_y_el_viejo_deja_de_servir(
    api, session, tenant_a: Tenant, crear_usuario, settings_test
) -> None:
    await crear_usuario(tenant_a, email=EMAIL, nombre="Dueña Test")
    access_viejo = await _login(api)
    refresh_viejo = _cookie(api)
    fila_vieja = await _fila(session, refresh_viejo)

    respuesta = await _refresh(api)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["access_token"] != access_viejo
    assert cuerpo["usuario"]["email"] == EMAIL
    assert cuerpo["expira_en_segundos"] == settings_test.jwt_access_min * 60
    assert "refresh_token" not in cuerpo

    refresh_nuevo = _cookie(api)
    assert refresh_nuevo != refresh_viejo
    cookies = respuesta.headers.get_list("set-cookie")
    assert len(cookies) == 1
    assert f"refresh_token={refresh_nuevo}" in cookies[0]
    assert "HttpOnly" in cookies[0]

    await session.refresh(fila_vieja)
    assert fila_vieja.revocado_at is not None
    fila_nueva = await _fila(session, refresh_nuevo)
    assert fila_vieja.reemplazado_por_id == fila_nueva.id
    assert fila_nueva.familia_id == fila_vieja.familia_id
    assert fila_nueva.revocado_at is None


async def test_reuso_revoca_toda_la_familia_y_audita(
    api, session, tenant_a: Tenant, crear_usuario, auditoria_de
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    refresh_viejo = _cookie(api)
    assert (await _refresh(api)).status_code == 200
    refresh_nuevo = _cookie(api)
    familia = (await _fila(session, refresh_viejo)).familia_id

    # Alguien presenta el refresh ya rotado: se revoca la familia entera.
    _usar_cookie(api, refresh_viejo)
    reuso = await _refresh(api)

    assert reuso.status_code == 401
    assert "sesión" in reuso.json()["detail"]
    assert reuso.headers.get_list("set-cookie") == []

    eventos = await auditoria_de("auth.refresh_reuso")
    assert len(eventos) == 1
    assert eventos[0].actor_id == usuario.id
    assert eventos[0].tenant_id == tenant_a.id
    assert eventos[0].despues == {"familia_id": str(familia)}
    assert refresh_viejo not in f"{eventos[0].antes}{eventos[0].despues}"

    # El refresh vigente de esa familia tampoco sirve: hay que loguearse de nuevo.
    _usar_cookie(api, refresh_nuevo)
    assert (await _refresh(api)).status_code == 401

    familiares = list(
        (await session.execute(select(RefreshToken).where(RefreshToken.familia_id == familia)))
        .scalars()
        .all()
    )
    assert familiares and all(fila.revocado_at is not None for fila in familiares)


async def test_refresh_vencido_se_rechaza(api, session, tenant_a: Tenant, crear_usuario) -> None:
    await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    valor = _cookie(api)
    fila = await _fila(session, valor)
    fila.vence_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    respuesta = await _refresh(api)

    assert respuesta.status_code == 401
    assert respuesta.headers.get_list("set-cookie") == []
    await session.refresh(fila)
    assert fila.revocado_at is None, "un refresh vencido no se marca como reuso"


async def test_refresh_revocado_por_logout_se_rechaza(api, tenant_a: Tenant, crear_usuario) -> None:
    await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    valor = _cookie(api)
    assert (await api.post("/api/auth/logout")).status_code == 204

    _usar_cookie(api, valor)
    respuesta = await _refresh(api)

    assert respuesta.status_code == 401
    assert respuesta.headers.get_list("set-cookie") == []


async def test_refresh_sin_cookie_o_con_token_inventado_es_401(api) -> None:
    sin_cookie = await api.post("/api/auth/refresh")
    assert sin_cookie.status_code == 401

    api.cookies.set("refresh_token", "token-que-no-existe", path="/")
    inventado = await api.post("/api/auth/refresh")
    assert inventado.status_code == 401
    assert inventado.headers.get_list("set-cookie") == []


async def test_refresh_de_usuario_desactivado_se_rechaza(
    api, session, tenant_a: Tenant, crear_usuario
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)
    usuario.activo = False
    await session.flush()

    respuesta = await _refresh(api)

    assert respuesta.status_code == 401
    assert respuesta.headers.get_list("set-cookie") == []


async def test_refresh_emite_access_con_identidad_del_usuario(
    api, tenant_a: Tenant, crear_usuario, settings_test
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)
    await _login(api)

    from app.infrastructure.security.jwt import decodificar_access

    claims = decodificar_access((await _refresh(api)).json()["access_token"], settings_test)

    assert claims["sub"] == str(usuario.id)
    assert claims["tenant_id"] == str(tenant_a.id)
    assert claims["roles"] == ["recepcion"]
    assert claims["email"] == EMAIL
