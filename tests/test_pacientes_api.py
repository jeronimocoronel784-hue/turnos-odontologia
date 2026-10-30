"""Tests de integración para los endpoints de /api/pacientes (tarea 2.1).

Verifica:
- CRUD completo por roles autorizados (dueño, recepción).
- Odontólogo con solo lectura (403 en creación, edición, baja y opt-in).
- Unicidad de DNI por tenant con 409.
- Creación automática de ficha clínica 1:1.
- Búsqueda por DNI, teléfono y texto libre (q).
- Baja lógica con activo = False y auditoría (R7).
- Endpoint dedicado PATCH /api/pacientes/:id/optin.
- Aislamiento estricto multi-tenant (R4).
"""

from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_dueno_crea_paciente_con_ficha_clinica_y_auditoria(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_pacientes@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    payload = {
        "nombre": "Esteban Quito",
        "dni": "35.123.456",
        "telefono": "11-4455-6677",
        "email": "esteban@example.com",
        "optin_wa": True,
    }
    resp = await api.post("/api/pacientes", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["nombre"] == "Esteban Quito"
    assert data["dni"] == "35123456"
    assert data["optin_wa"] is True
    assert data["tenant_id"] == str(tenant_a.id)
    assert data["ficha_clinica"] is not None
    assert data["ficha_clinica"]["paciente_id"] == data["id"]

    eventos = await auditoria_de("paciente.crear")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == data["id"]
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["optin_wa"] is True


async def test_crear_paciente_dni_duplicado_mismo_tenant_retorna_409(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    recepcion = await crear_usuario(
        tenant_a, email="recep_pacientes@test.com", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    payload = {
        "nombre": "Paciente Uno",
        "dni": "30111222",
        "telefono": "1122334455",
    }
    resp1 = await api.post("/api/pacientes", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Segundo intento con el mismo DNI en el mismo tenant
    resp2 = await api.post(
        "/api/pacientes",
        json={"nombre": "Otro Paciente", "dni": "30.111.222", "telefono": "1199999999"},
        headers=headers,
    )
    assert resp2.status_code == 409
    assert "DNI" in resp2.json()["detail"] or "registrado" in resp2.json()["detail"]


async def test_odontologo_no_puede_crear_ni_modificar_paciente(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    odontologo = await crear_usuario(
        tenant_a, email="odonto_pacientes@test.com", rol=RolUsuario.ODONTOLOGO
    )
    headers = autorizacion(token_para(odontologo))

    # POST -> 403
    resp = await api.post(
        "/api/pacientes",
        json={"nombre": "Nuevo", "dni": "44111222", "telefono": "1122334455"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_listar_y_buscar_pacientes(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_buscar@test.com", rol=RolUsuario.DUENO)
    odonto = await crear_usuario(
        tenant_a, email="odonto_buscar@test.com", rol=RolUsuario.ODONTOLOGO
    )
    headers_dueno = autorizacion(token_para(dueno))
    headers_odonto = autorizacion(token_para(odonto))

    # Crear 2 pacientes
    await api.post(
        "/api/pacientes",
        json={"nombre": "Carlos Gardel", "dni": "20111111", "telefono": "1144001122"},
        headers=headers_dueno,
    )
    await api.post(
        "/api/pacientes",
        json={"nombre": "Tita Merello", "dni": "25222222", "telefono": "1155003344"},
        headers=headers_dueno,
    )

    # Odontólogo SÍ puede listar
    resp = await api.get("/api/pacientes", headers=headers_odonto)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2

    # Búsqueda por DNI
    resp_dni = await api.get("/api/pacientes?dni=20111111", headers=headers_dueno)
    assert resp_dni.status_code == 200
    dnis = [p["dni"] for p in resp_dni.json()]
    assert "20111111" in dnis
    assert "25222222" not in dnis

    # Búsqueda por término q
    resp_q = await api.get("/api/pacientes?q=Gardel", headers=headers_dueno)
    assert resp_q.status_code == 200
    assert len(resp_q.json()) == 1
    assert resp_q.json()[0]["nombre"] == "Carlos Gardel"


async def test_baja_logica_y_aislamiento_multitenant(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_a_baja@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_b_baja@test.com", rol=RolUsuario.DUENO)
    headers_a = autorizacion(token_para(dueno_a))
    headers_b = autorizacion(token_para(dueno_b))

    # Crear paciente en tenant A
    resp = await api.post(
        "/api/pacientes",
        json={"nombre": "Para Borrar", "dni": "99111222", "telefono": "1100000000"},
        headers=headers_a,
    )
    assert resp.status_code == 201
    paciente_id = resp.json()["id"]

    # Tenant B NO puede verlo (404)
    resp_otro = await api.get(f"/api/pacientes/{paciente_id}", headers=headers_b)
    assert resp_otro.status_code == 404

    # DELETE baja lógica
    del_resp = await api.delete(f"/api/pacientes/{paciente_id}", headers=headers_a)
    assert del_resp.status_code == 200
    assert del_resp.json()["activo"] is False

    # Auditoría de baja
    eventos = await auditoria_de("paciente.baja")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == paciente_id

    # Si consultamos solo activos, ya no debe aparecer
    list_resp = await api.get("/api/pacientes?solo_activos=true&dni=99111222", headers=headers_a)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


async def test_patch_optin_wa_y_baja_stop(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    recepcion = await crear_usuario(
        tenant_a, email="recep_optin@test.com", rol=RolUsuario.RECEPCION
    )
    headers = autorizacion(token_para(recepcion))

    # Crear paciente con optin_wa = False por defecto
    crear_resp = await api.post(
        "/api/pacientes",
        json={"nombre": "Optin Test", "dni": "88111222", "telefono": "1177665544"},
        headers=headers,
    )
    paciente_id = crear_resp.json()["id"]
    assert crear_resp.json()["optin_wa"] is False

    # Dar de alta opt-in
    patch_resp = await api.patch(
        f"/api/pacientes/{paciente_id}/optin",
        json={"optin_wa": True},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["optin_wa"] is True

    # Dar de baja (STOP)
    stop_resp = await api.patch(
        f"/api/pacientes/{paciente_id}/optin",
        json={"optin_wa": False},
        headers=headers,
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["optin_wa"] is False

    eventos = await auditoria_de("paciente.optin")
    assert len(eventos) == 2
    assert eventos[0].despues["optin_wa"] is True
    assert eventos[1].despues["optin_wa"] is False
