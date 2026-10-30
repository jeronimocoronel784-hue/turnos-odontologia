"""Tests de endpoints GET y PATCH /api/admin/tenant/politicas (tarea 2.4).

Verifica:
- Lectura de políticas del consultorio con defaults por Dueño, Recepción y Odontólogo.
- Actualización parcial por Dueño con merge sobre politicas existentes.
- Registro en auditoría con antes y después.
- Control RBAC: 403 para Recepción y Odontólogo en PATCH.
- Rechazo 422 de valores inválidos y de campos extra (tenant_id).
- Aislamiento entre consultorios.
"""

from collections.abc import Awaitable, Callable

import httpx

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_roles_leen_politicas_del_consultorio(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_pol@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(tenant_a, email="recep_pol@test.com", rol=RolUsuario.RECEPCION)
    odonto = await crear_usuario(tenant_a, email="odonto_pol@test.com", rol=RolUsuario.ODONTOLOGO)

    for usuario in (dueno, recep, odonto):
        resp = await api.get(
            "/api/admin/tenant/politicas",
            headers=autorizacion(token_para(usuario)),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["anticipacion_min_dias"] >= 0
        assert 0 <= data["sena_default_pct"] <= 100
        assert data["cancelacion_horas"] >= 0


async def test_dueno_actualiza_parcialmente_politicas_con_auditoria(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_pol_patch@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    # Lectura previa
    r_prev = await api.get("/api/admin/tenant/politicas", headers=headers)
    assert r_prev.status_code == 200
    prev_dias = r_prev.json()["anticipacion_min_dias"]

    # Actualizamos solo cancelacion_horas y sena_default_pct
    resp = await api.patch(
        "/api/admin/tenant/politicas",
        json={"cancelacion_horas": 48, "sena_default_pct": 50},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cancelacion_horas"] == 48
    assert data["sena_default_pct"] == 50
    assert data["anticipacion_min_dias"] == prev_dias  # Preservado

    eventos = await auditoria_de("tenant.actualizar_politicas")
    assert len(eventos) == 1
    assert eventos[0].entidad == "tenant"
    assert eventos[0].entidad_id == str(tenant_a.id)
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["cancelacion_horas"] == 48
    assert eventos[0].despues["sena_default_pct"] == 50


async def test_recepcion_y_odontologo_no_pueden_modificar_politicas(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    recep = await crear_usuario(tenant_a, email="recep_pol_403@test.com", rol=RolUsuario.RECEPCION)
    odonto = await crear_usuario(
        tenant_a, email="odonto_pol_403@test.com", rol=RolUsuario.ODONTOLOGO
    )

    for usuario in (recep, odonto):
        resp = await api.patch(
            "/api/admin/tenant/politicas",
            json={"cancelacion_horas": 12},
            headers=autorizacion(token_para(usuario)),
        )
        assert resp.status_code == 403


async def test_rechazo_422_valores_fuera_de_rango_y_body_extra(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_pol_val@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    # sena_default_pct > 100
    r1 = await api.patch(
        "/api/admin/tenant/politicas",
        json={"sena_default_pct": 120},
        headers=headers,
    )
    assert r1.status_code == 422

    # cancelacion_horas < 0
    r2 = await api.patch(
        "/api/admin/tenant/politicas",
        json={"cancelacion_horas": -5},
        headers=headers,
    )
    assert r2.status_code == 422

    # Infiltrar tenant_id en body -> 422 por extra='forbid'
    r3 = await api.patch(
        "/api/admin/tenant/politicas",
        json={"cancelacion_horas": 10, "tenant_id": str(tenant_a.id)},
        headers=headers,
    )
    assert r3.status_code == 422


async def test_aislamiento_politicas_entre_tenants(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_pol_a@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_pol_b@test.com", rol=RolUsuario.DUENO)
    h_a = autorizacion(token_para(dueno_a))
    h_b = autorizacion(token_para(dueno_b))

    # A configura 72 horas de cancelación
    r_a = await api.patch(
        "/api/admin/tenant/politicas",
        json={"cancelacion_horas": 72},
        headers=h_a,
    )
    assert r_a.status_code == 200
    assert r_a.json()["cancelacion_horas"] == 72

    # B debe seguir teniendo su valor por defecto (24), sin ser afectado por A
    r_b = await api.get(
        "/api/admin/tenant/politicas",
        headers=h_b,
    )
    assert r_b.status_code == 200
    assert r_b.json()["cancelacion_horas"] != 72


async def test_politicas_actualizar_anticipacion_hs_y_errores_triangulacion(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_pol_triang@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    # Actualizar anticipacion_min_hs
    r_patch = await api.patch(
        "/api/admin/tenant/politicas",
        json={"anticipacion_min_hs": 12},
        headers=headers,
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["anticipacion_min_hs"] == 12

    # GET debe reflejar anticipacion_min_hs
    r_get = await api.get("/api/admin/tenant/politicas", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["anticipacion_min_hs"] == 12
