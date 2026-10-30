"""POST /api/auth/login: credenciales, 401 genérico, multi-tenant y auditoría (tarea 3.1)."""

from sqlalchemy import select

from app.domain.refresh_token import RefreshToken
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.db.repository import BaseRepository
from app.infrastructure.security.jwt import decodificar_access
from app.infrastructure.security.tokens_publicos import hashear_token
from app.shared.settings import Settings

EMAIL = "recepcion@example.com"
PASSWORD = "secreto-de-prueba"


async def _login(api, email: str = EMAIL, password: str = PASSWORD, **extra: str):
    return await api.post("/api/auth/login", json={"email": email, "password": password, **extra})


async def test_login_exitoso_devuelve_access_y_cookie_httponly(
    api, tenant_a: Tenant, crear_usuario, settings_test: Settings
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL, nombre="Recep Test")

    respuesta = await _login(api)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"access_token", "token_type", "expira_en_segundos", "usuario"}
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expira_en_segundos"] == settings_test.jwt_access_min * 60
    assert cuerpo["usuario"] == {
        "id": str(usuario.id),
        "tenant_id": str(tenant_a.id),
        "tenant_slug": "tenant-a-test",
        "email": EMAIL,
        "nombre": "Recep Test",
        "roles": ["recepcion"],
    }
    # El refresh jamás viaja en el body: solo en cookie.
    assert "refresh_token" not in cuerpo
    assert "refresh_token=" not in respuesta.text

    claims = decodificar_access(cuerpo["access_token"], settings_test)
    assert claims["sub"] == str(usuario.id)
    assert claims["tenant_id"] == str(tenant_a.id)
    assert claims["roles"] == ["recepcion"]

    cookies = respuesta.headers.get_list("set-cookie")
    assert len(cookies) == 1
    assert cookies[0].startswith("refresh_token=")
    assert "HttpOnly" in cookies[0]
    assert "Path=/api/auth" in cookies[0]


async def test_password_incorrecto_email_inexistente_e_inactivo_dan_el_mismo_401(
    api, tenant_a: Tenant, crear_usuario
) -> None:
    await crear_usuario(tenant_a, email="activo@example.com")
    await crear_usuario(tenant_a, email="inactivo@example.com", activo=False)

    incorrecto = await _login(api, email="activo@example.com", password="no-es-la-clave")
    inexistente = await _login(api, email="nadie@example.com", password=PASSWORD)
    inactivo = await _login(api, email="inactivo@example.com")

    assert [r.status_code for r in (incorrecto, inexistente, inactivo)] == [401, 401, 401]
    detalles = {r.json()["detail"] for r in (incorrecto, inexistente, inactivo)}
    assert len(detalles) == 1, "el 401 no debe revelar cuál de los tres falló"
    assert "email o la contraseña" in detalles.pop()


async def test_usuario_inactivo_no_recibe_ningun_token(
    api, tenant_a: Tenant, crear_usuario
) -> None:
    await crear_usuario(tenant_a, email="inactivo@example.com", activo=False)

    respuesta = await _login(api, email="inactivo@example.com")

    assert respuesta.status_code == 401
    assert "access_token" not in respuesta.text
    assert respuesta.headers.get_list("set-cookie") == []


async def test_email_en_dos_tenants_pide_consultorio_y_con_slug_autentica_el_correcto(
    api, tenant_a: Tenant, tenant_b: Tenant, crear_usuario
) -> None:
    en_a: Usuario = await crear_usuario(tenant_a, email=EMAIL, nombre="Persona en A")
    en_b: Usuario = await crear_usuario(tenant_b, email=EMAIL, nombre="Persona en B")

    ambiguo = await _login(api)

    assert ambiguo.status_code == 400
    assert "consultorio" in ambiguo.json()["detail"]
    assert "access_token" not in ambiguo.text

    con_slug = await _login(api, tenant_slug="tenant-b-test")

    assert con_slug.status_code == 200
    identidad = con_slug.json()["usuario"]
    assert identidad["id"] == str(en_b.id)
    assert identidad["tenant_id"] == str(tenant_b.id)
    assert identidad["nombre"] == "Persona en B"
    assert en_a.id != en_b.id


async def test_tenant_inactivo_no_permite_login(api, tenant_a: Tenant, crear_usuario) -> None:
    await crear_usuario(tenant_a, email=EMAIL)
    tenant_a.activo = False

    respuesta = await _login(api)

    assert respuesta.status_code == 401
    assert respuesta.headers.get_list("set-cookie") == []


async def test_login_exitoso_deja_auditoria_sin_credenciales(
    api, session, tenant_a: Tenant, crear_usuario, auditoria_de
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)

    respuesta = await _login(api)

    eventos = await auditoria_de("auth.login")
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.tenant_id == tenant_a.id
    assert evento.actor_id == usuario.id
    assert evento.entidad == "usuario"
    assert evento.entidad_id == str(usuario.id)

    rastro = f"{evento.antes}{evento.despues}{evento.entidad_id}"
    assert PASSWORD not in rastro
    assert usuario.password_hash not in rastro
    assert respuesta.json()["access_token"] not in rastro


async def test_login_fallido_con_usuario_existente_deja_auditoria(
    api, tenant_a: Tenant, crear_usuario, auditoria_de
) -> None:
    usuario: Usuario = await crear_usuario(tenant_a, email=EMAIL)

    await _login(api, password="no-es-la-clave")
    await _login(api, email="nadie@example.com")

    fallidos = await auditoria_de("auth.login_fallido")
    assert len(fallidos) == 1
    assert fallidos[0].actor_id == usuario.id
    assert fallidos[0].tenant_id == tenant_a.id
    assert PASSWORD not in f"{fallidos[0].antes}{fallidos[0].despues}"


async def test_sexto_intento_da_429_sin_verificar_credenciales(
    api, tenant_a: Tenant, crear_usuario
) -> None:
    await crear_usuario(tenant_a, email=EMAIL)

    for _ in range(5):
        assert (await _login(api, password="no-es-la-clave")).status_code == 401

    # El 6º intento trae la password CORRECTA: igual debe frenarse antes de validar.
    bloqueado = await _login(api)

    assert bloqueado.status_code == 429
    assert "Esperá" in bloqueado.json()["detail"]
    assert bloqueado.headers.get_list("set-cookie") == []


async def test_login_con_usuario_de_otro_tenant_no_filtra_datos(
    api, session, tenant_a: Tenant, tenant_b: Tenant, crear_usuario
) -> None:
    await crear_usuario(tenant_a, email=EMAIL, rol=RolUsuario.DUENO, nombre="Dueña A")
    en_b: Usuario = await crear_usuario(tenant_b, email="otro@example.com")

    respuesta = await _login(api, email=en_b.email)

    assert respuesta.status_code == 200
    assert respuesta.json()["usuario"]["tenant_id"] == str(tenant_b.id)
    # El login no mezcla tenants: A sigue teniendo un solo usuario.
    de_a = await BaseRepository(session, tenant_a.id, Usuario).listar()
    assert [u.email for u in de_a] == [EMAIL]


async def test_el_login_guarda_un_refresh_hasheado(
    api, session, tenant_a: Tenant, crear_usuario
) -> None:
    await crear_usuario(tenant_a, email=EMAIL)
    respuesta = await _login(api)
    cookie = respuesta.headers.get_list("set-cookie")[0]
    valor = cookie.split(";")[0].split("=", 1)[1]

    filas = list((await session.execute(select(RefreshToken))).scalars().all())
    assert len(filas) == 1
    assert filas[0].token_hash == hashear_token(valor)
    assert filas[0].token_hash != valor
    assert filas[0].revocado_at is None
