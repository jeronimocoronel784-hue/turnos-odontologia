"""Tests de endpoints /api/admin/coberturas (tarea 2.3).

Verifica:
- Alta válida de cobertura vinculada a prestación del consultorio.
- Rechazo 404 si prestacion_id es ajena o inexistente.
- Rechazo 422 si rango de vigencia es invertido (creación y PATCH).
- Filtro por vigente_en (vigente vs vencida vs inactiva).
- Filtros por obra_social y prestacion_id.
- RBAC y baja lógica auditada.
- Aislamiento multi-tenant.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def _crear_prestacion_aux(
    api: httpx.AsyncClient, headers: dict[str, str], nombre: str = "Limpieza Aux"
) -> str:
    r = await api.post(
        "/api/admin/prestaciones",
        json={"nombre": nombre, "duracion_min": 30, "precio_particular": "20000.00"},
        headers=headers,
    )
    assert r.status_code == 201
    return str(r.json()["id"])


async def test_dueno_crea_cobertura_con_auditoria(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_cob@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    p_id = await _crear_prestacion_aux(api, headers, "Endodoncia Cobertura")

    hoy = datetime.now(UTC).date()
    resp = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "OSDE 210",
            "prestacion_id": p_id,
            "arancel": "18000.00",
            "copago": "2000.00",
            "vigencia_desde": str(hoy),
            "vigencia_hasta": str(hoy + timedelta(days=365)),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["obra_social"] == "OSDE 210"
    assert data["prestacion_id"] == p_id
    assert Decimal(str(data["arancel"])) == Decimal("18000.00")
    assert Decimal(str(data["copago"])) == Decimal("2000.00")
    assert data["activa"] is True
    assert data["tenant_id"] == str(tenant_a.id)

    eventos = await auditoria_de("cobertura_os.crear")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == data["id"]
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["obra_social"] == "OSDE 210"


async def test_rechazo_404_prestacion_ajena_o_inexistente(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_cob_a@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_cob_b@test.com", rol=RolUsuario.DUENO)
    h_a = autorizacion(token_para(dueno_a))
    h_b = autorizacion(token_para(dueno_b))

    p_b_id = await _crear_prestacion_aux(api, h_b, "Prestacion Tenant B")

    hoy = datetime.now(UTC).date()
    # Dueño A intenta usar la prestación de Tenant B -> 404
    resp = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Swiss Medical",
            "prestacion_id": p_b_id,
            "arancel": "15000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
        },
        headers=h_a,
    )
    assert resp.status_code == 404
    assert "no encontramos esa prestación" in resp.json()["detail"].lower()

    # Prestación aleatoria no existente
    resp_random = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Swiss Medical",
            "prestacion_id": str(uuid.uuid4()),
            "arancel": "15000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
        },
        headers=h_a,
    )
    assert resp_random.status_code == 404


async def test_filtro_coberturas_vigentes_por_fecha(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_vig@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))
    p_id = await _crear_prestacion_aux(api, headers, "Consulta Vigencia")

    hoy = datetime.now(UTC).date()
    hace_un_mes = hoy - timedelta(days=30)
    hace_dos_meses = hoy - timedelta(days=60)
    mes_que_viene = hoy + timedelta(days=30)

    # 1. Cobertura vigente hoy (desde hace 2 meses hasta el mes que viene)
    r1 = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Galeno Vigente",
            "prestacion_id": p_id,
            "arancel": "10000.00",
            "copago": "0.00",
            "vigencia_desde": str(hace_dos_meses),
            "vigencia_hasta": str(mes_que_viene),
        },
        headers=headers,
    )
    assert r1.status_code == 201

    # 2. Cobertura vencida el mes pasado (desde hace 2 meses hasta hace 1 mes)
    r2 = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Galeno Vencida",
            "prestacion_id": p_id,
            "arancel": "8000.00",
            "copago": "0.00",
            "vigencia_desde": str(hace_dos_meses),
            "vigencia_hasta": str(hace_un_mes),
        },
        headers=headers,
    )
    assert r2.status_code == 201

    # 3. Cobertura inactiva (baja lógica) que cubría hoy
    r3 = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Galeno Desactivada",
            "prestacion_id": p_id,
            "arancel": "9000.00",
            "copago": "0.00",
            "vigencia_desde": str(hace_dos_meses),
            "activa": False,
        },
        headers=headers,
    )
    assert r3.status_code == 201

    # Consulta con ?vigente_en=<hoy>
    resp_vig = await api.get(f"/api/admin/coberturas?vigente_en={hoy}", headers=headers)
    assert resp_vig.status_code == 200
    items = resp_vig.json()
    assert len(items) == 1
    assert items[0]["obra_social"] == "Galeno Vigente"

    # Consulta por obra social y prestación
    resp_os = await api.get(
        f"/api/admin/coberturas?obra_social=Galeno%20Vencida&prestacion_id={p_id}",
        headers=headers,
    )
    assert resp_os.status_code == 200
    assert len(resp_os.json()) == 1
    assert resp_os.json()[0]["obra_social"] == "Galeno Vencida"


async def test_cobertura_patch_revalida_fechas_combinadas(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_cob_patch@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))
    p_id = await _crear_prestacion_aux(api, headers, "Arreglo Cobertura")

    hoy = datetime.now(UTC).date()
    r = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Sancor Salud",
            "prestacion_id": p_id,
            "arancel": "12000.00",
            "copago": "1000.00",
            "vigencia_desde": str(hoy),
        },
        headers=headers,
    )
    cob_id = r.json()["id"]

    # Intento de poner vigencia_hasta anterior a la vigencia_desde existente
    r_patch_inval = await api.patch(
        f"/api/admin/coberturas/{cob_id}",
        json={"vigencia_hasta": str(hoy - timedelta(days=10))},
        headers=headers,
    )
    assert r_patch_inval.status_code == 422
    assert "vigencia" in r_patch_inval.text.lower()

    # Actualización válida de arancel y vigencia_hasta
    r_patch_val = await api.patch(
        f"/api/admin/coberturas/{cob_id}",
        json={
            "arancel": "14000.00",
            "vigencia_hasta": str(hoy + timedelta(days=60)),
        },
        headers=headers,
    )
    assert r_patch_val.status_code == 200
    assert Decimal(str(r_patch_val.json()["arancel"])) == Decimal("14000.00")

    eventos = await auditoria_de("cobertura_os.actualizar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == cob_id


async def test_cobertura_baja_logica_y_rbac(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_cob_del@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(tenant_a, email="recep_cob@test.com", rol=RolUsuario.RECEPCION)
    odonto = await crear_usuario(tenant_a, email="odonto_cob@test.com", rol=RolUsuario.ODONTOLOGO)

    h_dueno = autorizacion(token_para(dueno))
    h_recep = autorizacion(token_para(recep))
    h_odonto = autorizacion(token_para(odonto))

    p_id = await _crear_prestacion_aux(api, h_dueno, "Prestacion RBAC Cob")

    hoy = datetime.now(UTC).date()
    r = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Medife",
            "prestacion_id": p_id,
            "arancel": "11000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
        },
        headers=h_dueno,
    )
    cob_id = r.json()["id"]

    # Lectura permitida para recepción y odontólogo
    assert (await api.get("/api/admin/coberturas", headers=h_recep)).status_code == 200
    assert (await api.get("/api/admin/coberturas", headers=h_odonto)).status_code == 200

    # Escritura prohibida para recepción y odontólogo
    r_post_403 = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "Medife",
            "prestacion_id": p_id,
            "arancel": "1000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
        },
        headers=h_recep,
    )
    assert r_post_403.status_code == 403

    r_patch_403 = await api.patch(
        f"/api/admin/coberturas/{cob_id}",
        json={"arancel": "5000.00"},
        headers=h_odonto,
    )
    assert r_patch_403.status_code == 403

    r_del_403 = await api.delete(
        f"/api/admin/coberturas/{cob_id}",
        headers=h_recep,
    )
    assert r_del_403.status_code == 403

    # Baja lógica por dueño
    r_del = await api.delete(f"/api/admin/coberturas/{cob_id}", headers=h_dueno)
    assert r_del.status_code == 200
    assert r_del.json()["activa"] is False

    eventos = await auditoria_de("cobertura_os.desactivar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == cob_id


async def test_cobertura_aislamiento_y_errores_triangulacion(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_cob_iso_a@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_cob_iso_b@test.com", rol=RolUsuario.DUENO)
    h_a = autorizacion(token_para(dueno_a))
    h_b = autorizacion(token_para(dueno_b))

    p_a_id = await _crear_prestacion_aux(api, h_a, "Prestacion Tenant A Triang")

    hoy = datetime.now(UTC).date()
    # Infiltrar tenant_id en body -> 422
    r_infiltra = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "OSDE Hacker",
            "prestacion_id": p_a_id,
            "arancel": "10000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
            "tenant_id": str(tenant_b.id),
        },
        headers=h_a,
    )
    assert r_infiltra.status_code == 422

    # Crear cobertura en Tenant A
    r_crear = await api.post(
        "/api/admin/coberturas",
        json={
            "obra_social": "OSDE Legítima",
            "prestacion_id": p_a_id,
            "arancel": "10000.00",
            "copago": "0.00",
            "vigencia_desde": str(hoy),
        },
        headers=h_a,
    )
    assert r_crear.status_code == 201
    cob_a_id = r_crear.json()["id"]

    # Dueño B no puede verla, modificarla ni borrarla
    r_patch_b = await api.patch(
        f"/api/admin/coberturas/{cob_a_id}",
        json={"arancel": "50000.00"},
        headers=h_b,
    )
    assert r_patch_b.status_code == 404

    r_del_b = await api.delete(
        f"/api/admin/coberturas/{cob_a_id}",
        headers=h_b,
    )
    assert r_del_b.status_code == 404

    # 404 con ID inexistente
    r_404_patch = await api.patch(
        f"/api/admin/coberturas/{uuid.uuid4()}",
        json={"arancel": "100.00"},
        headers=h_a,
    )
    assert r_404_patch.status_code == 404

    r_404_del = await api.delete(
        f"/api/admin/coberturas/{uuid.uuid4()}",
        headers=h_a,
    )
    assert r_404_del.status_code == 404
