"""Cookie del refresh: flags, vigencia y borrado (tarea 3.4).

D3: `HttpOnly` + `SameSite=Lax` + `Path=/api/auth` siempre; `Secure` según
`COOKIE_SECURE` (default true en producción, false solo en dev sobre http).
El refresh NUNCA viaja en el body.
"""

import httpx

from app.api import deps
from app.api.routers import auth
from app.shared.settings import Settings

EMAIL = "cookies@example.com"
PASSWORD = "secreto-de-prueba"


async def _cliente(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def _cookie_set(respuesta: httpx.Response) -> str:
    cookies = respuesta.headers.get_list("set-cookie")
    assert len(cookies) == 1
    return cookies[0]


async def test_cookie_en_dev_no_lleva_secure_pero_si_httponly(
    api, tenant_a, crear_usuario, settings_test: Settings
) -> None:
    await crear_usuario(tenant_a, email=EMAIL)

    respuesta = await api.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})

    cookie = _cookie_set(respuesta)
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/auth" in cookie
    assert f"Max-Age={settings_test.jwt_refresh_days * 24 * 3600}" in cookie
    assert "Secure" not in cookie  # COOKIE_SECURE=false en tests (http local)


async def test_cookie_en_produccion_lleva_secure(
    app_factory, tenant_a, crear_usuario, settings_test: Settings
) -> None:
    seguro = settings_test.model_copy(update={"cookie_secure": True})
    app = app_factory(auth.router)
    app.dependency_overrides[deps.settings_cacheados] = lambda: seguro
    await crear_usuario(tenant_a, email=EMAIL)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as cliente:
        respuesta = await cliente.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )

    cookie = _cookie_set(respuesta)
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


async def test_el_refresh_rota_la_cookie_con_los_mismos_flags(
    app_factory, tenant_a, crear_usuario, settings_test: Settings
) -> None:
    seguro = settings_test.model_copy(update={"cookie_secure": True})
    app = app_factory(auth.router)
    app.dependency_overrides[deps.settings_cacheados] = lambda: seguro
    await crear_usuario(tenant_a, email=EMAIL)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as cliente:
        login = await cliente.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        respuesta = await cliente.post("/api/auth/refresh")

    assert login.status_code == 200
    assert respuesta.status_code == 200
    cookie = _cookie_set(respuesta)
    assert cookie != _cookie_set(login)
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/auth" in cookie


async def test_la_cookie_borrada_expira_en_el_cliente(api, tenant_a, crear_usuario) -> None:
    await crear_usuario(tenant_a, email=EMAIL)
    await api.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})

    respuesta = await api.post("/api/auth/logout")

    cookie = _cookie_set(respuesta)
    assert cookie.startswith("refresh_token=")
    assert "Max-Age=0" in cookie
    assert "Path=/api/auth" in cookie


async def test_el_refresh_no_viaja_en_el_body(api, tenant_a, crear_usuario) -> None:
    usuario = await crear_usuario(tenant_a, email=EMAIL)

    login = await api.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    valor = login.headers.get_list("set-cookie")[0].split(";")[0].split("=", 1)[1]
    cuerpo = login.json()

    assert "refresh_token" not in cuerpo
    assert valor not in login.text
    assert set(cuerpo) == {"access_token", "token_type", "expira_en_segundos", "usuario"}
    assert cuerpo["usuario"]["email"] == usuario.email

    refresh = await api.post("/api/auth/refresh")
    nuevo = refresh.headers.get_list("set-cookie")[0].split(";")[0].split("=", 1)[1]
    assert "refresh_token" not in refresh.json()
    assert nuevo not in refresh.text
