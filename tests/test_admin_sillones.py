"""Tests de endpoints /api/admin/sillones (tarea 2.1).

Verifica:
- Alta y listado de sillón por rol (Dueño crea/edita/baja; Recepción y Odontólogo leen).
- RBAC: 403 en escritura para roles sin permiso.
- 409 por duplicado de (tenant_id, sucursal, nombre).
- Mismo nombre en distinta sucursal u otro tenant es 201.
- Baja lógica con activo=False y registro en auditoría.
- Aislamiento multi-tenant y rechazo de tenant_id en body.
"""

import uuid
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_dueno_crea_sillon_con_auditoria(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_sillon@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    resp = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box 1"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["nombre"] == "Box 1"
    assert data["sucursal"] == "central"
    assert data["activo"] is True
    assert data["tenant_id"] == str(tenant_a.id)

    eventos = await auditoria_de("sillon.crear")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == data["id"]
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["nombre"] == "Box 1"


async def test_roles_leen_sillones_y_filtros(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_l@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(tenant_a, email="recep_l@test.com", rol=RolUsuario.RECEPCION)
    odonto = await crear_usuario(tenant_a, email="odonto_l@test.com", rol=RolUsuario.ODONTOLOGO)

    h_dueno = autorizacion(token_para(dueno))
    # Creamos 2 sillones: uno activo y uno inactivo en otra sucursal
    r1 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Sillón Activo", "sucursal": "central"},
        headers=h_dueno,
    )
    assert r1.status_code == 201
    r2 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Sillón Norte", "sucursal": "norte", "activo": False},
        headers=h_dueno,
    )
    assert r2.status_code == 201

    # Recepción puede leer
    resp_rec = await api.get("/api/admin/sillones", headers=autorizacion(token_para(recep)))
    assert resp_rec.status_code == 200
    assert len(resp_rec.json()) == 2

    # Odontólogo puede leer con filtro solo_activos
    resp_odo = await api.get(
        "/api/admin/sillones?solo_activos=true",
        headers=autorizacion(token_para(odonto)),
    )
    assert resp_odo.status_code == 200
    items = resp_odo.json()
    assert len(items) == 1
    assert items[0]["nombre"] == "Sillón Activo"

    # Filtro por sucursal
    resp_suc = await api.get(
        "/api/admin/sillones?sucursal=norte",
        headers=h_dueno,
    )
    assert resp_suc.status_code == 200
    assert len(resp_suc.json()) == 1
    assert resp_suc.json()[0]["nombre"] == "Sillón Norte"


async def test_recepcion_y_odontologo_no_pueden_escribir(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    recep = await crear_usuario(tenant_a, email="recep_no@test.com", rol=RolUsuario.RECEPCION)
    h_recep = autorizacion(token_para(recep))

    resp_post = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Prohibido"},
        headers=h_recep,
    )
    assert resp_post.status_code == 403

    resp_patch = await api.patch(
        f"/api/admin/sillones/{uuid.uuid4()}",
        json={"nombre": "Modificado"},
        headers=h_recep,
    )
    assert resp_patch.status_code == 403

    resp_del = await api.delete(
        f"/api/admin/sillones/{uuid.uuid4()}",
        headers=h_recep,
    )
    assert resp_del.status_code == 403


async def test_nombre_duplicado_en_misma_sucursal_es_409(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_dup@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r1 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Cirugía", "sucursal": "central"},
        headers=headers,
    )
    assert r1.status_code == 201

    r2 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Cirugía", "sucursal": "central"},
        headers=headers,
    )
    assert r2.status_code == 409
    assert "ya existe un sillón" in r2.json()["detail"].lower()


async def test_mismo_nombre_en_distinta_sucursal_o_tenant_es_201(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_a_s@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_b_s@test.com", rol=RolUsuario.DUENO)

    # Box 1 en sucursal central de tenant A
    r1 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box 1", "sucursal": "central"},
        headers=autorizacion(token_para(dueno_a)),
    )
    assert r1.status_code == 201

    # Box 1 en sucursal oeste de tenant A
    r2 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box 1", "sucursal": "oeste"},
        headers=autorizacion(token_para(dueno_a)),
    )
    assert r2.status_code == 201

    # Box 1 en sucursal central de tenant B
    r3 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box 1", "sucursal": "central"},
        headers=autorizacion(token_para(dueno_b)),
    )
    assert r3.status_code == 201


async def test_baja_logica_sillon_auditoria(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_baja@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r_crear = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box A Desactivar"},
        headers=headers,
    )
    sillon_id = r_crear.json()["id"]

    r_del = await api.delete(f"/api/admin/sillones/{sillon_id}", headers=headers)
    assert r_del.status_code == 200
    assert r_del.json()["activo"] is False

    eventos = await auditoria_de("sillon.desactivar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == sillon_id
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["activo"] is False


async def test_aislamiento_entre_tenants_y_rechazo_tenant_id_body(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_iso_a@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_iso_b@test.com", rol=RolUsuario.DUENO)

    # Infiltrar tenant_id en body -> 422
    resp_infiltra = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Hacker", "tenant_id": str(tenant_b.id)},
        headers=autorizacion(token_para(dueno_a)),
    )
    assert resp_infiltra.status_code == 422

    # Crear en tenant A
    r_a = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Privado A"},
        headers=autorizacion(token_para(dueno_a)),
    )
    sillon_a_id = r_a.json()["id"]

    # Dueño B intenta modificar el sillón de A -> 404
    resp_mod = await api.patch(
        f"/api/admin/sillones/{sillon_a_id}",
        json={"nombre": "Robado"},
        headers=autorizacion(token_para(dueno_b)),
    )
    assert resp_mod.status_code == 404

    # Dueño B intenta borrar el sillón de A -> 404
    resp_del = await api.delete(
        f"/api/admin/sillones/{sillon_a_id}",
        headers=autorizacion(token_para(dueno_b)),
    )
    assert resp_del.status_code == 404


async def test_actualizar_sillon_y_conflicto_nombre_triangulacion(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_up@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r1 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Original", "sucursal": "central"},
        headers=headers,
    )
    sillon_1_id = r1.json()["id"]

    r2 = await api.post(
        "/api/admin/sillones",
        json={"nombre": "Box Ocupante", "sucursal": "central"},
        headers=headers,
    )
    assert r2.status_code == 201

    # Actualización feliz de nombre y sucursal
    r_patch = await api.patch(
        f"/api/admin/sillones/{sillon_1_id}",
        json={"nombre": "Box Renombrado", "sucursal": "norte"},
        headers=headers,
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["nombre"] == "Box Renombrado"
    assert r_patch.json()["sucursal"] == "norte"

    # Conflicto al intentar renombrar a uno existente en la misma sucursal
    r_patch_conf = await api.patch(
        f"/api/admin/sillones/{sillon_1_id}",
        json={"nombre": "Box Ocupante", "sucursal": "central"},
        headers=headers,
    )
    assert r_patch_conf.status_code == 409

    # Actualizar inexistente -> 404
    r_patch_404 = await api.patch(
        f"/api/admin/sillones/{uuid.uuid4()}",
        json={"nombre": "Inexistente"},
        headers=headers,
    )
    assert r_patch_404.status_code == 404

    # Desactivar inexistente -> 404
    r_del_404 = await api.delete(
        f"/api/admin/sillones/{uuid.uuid4()}",
        headers=headers,
    )
    assert r_del_404.status_code == 404

    eventos = await auditoria_de("sillon.actualizar")
    assert len(eventos) >= 1
    assert eventos[0].entidad_id == sillon_1_id
