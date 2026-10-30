"""Tests de endpoints /api/admin/prestaciones (tarea 2.2).

Verifica:
- Alta válida de prestación con o sin seña, normalización de monto_sena.
- Listado por rol (Dueño, Recepción, Odontólogo) y filtro solo_activas.
- Rechazo 422 con mensaje rioplatense para duracion <= 0 o requiere_sena sin monto.
- Conflicto 409 para nombre duplicado en el mismo consultorio.
- Baja lógica con activa=False y trazabilidad en auditoría.
- RBAC y aislamiento multi-tenant.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import httpx

from app.domain.auditoria import Auditoria
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def test_dueno_crea_prestacion_con_sena_e_invasiva(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_prest@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    resp = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Endodoncia Multirradicular",
            "duracion_min": 60,
            "precio_particular": "55000.00",
            "requiere_sena": True,
            "monto_sena": "20000.00",
            "invasiva": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["nombre"] == "Endodoncia Multirradicular"
    assert data["duracion_min"] == 60
    assert Decimal(str(data["precio_particular"])) == Decimal("55000.00")
    assert data["requiere_sena"] is True
    assert Decimal(str(data["monto_sena"])) == Decimal("20000.00")
    assert data["invasiva"] is True
    assert data["activa"] is True
    assert data["tenant_id"] == str(tenant_a.id)

    eventos = await auditoria_de("prestacion.crear")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == data["id"]
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["nombre"] == "Endodoncia Multirradicular"


async def test_prestacion_sin_sena_normaliza_monto_a_null(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_sinsena@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    resp = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Limpieza Básica",
            "duracion_min": 30,
            "precio_particular": "15000.00",
            "requiere_sena": False,
            "monto_sena": "5000.00",  # Debe normalizarse a None
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["monto_sena"] is None
    assert resp.json()["requiere_sena"] is False


async def test_roles_leen_prestaciones_y_filtro_activas(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_prest_l@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(tenant_a, email="recep_prest_l@test.com", rol=RolUsuario.RECEPCION)
    odonto = await crear_usuario(
        tenant_a, email="odonto_prest_l@test.com", rol=RolUsuario.ODONTOLOGO
    )

    h_dueno = autorizacion(token_para(dueno))
    # Creamos 2 prestaciones: 1 activa, 1 inactiva
    r1 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Consulta Activa",
            "duracion_min": 20,
            "precio_particular": "10000.00",
            "activa": True,
        },
        headers=h_dueno,
    )
    assert r1.status_code == 201

    r2 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Tratamiento Descontinuado",
            "duracion_min": 40,
            "precio_particular": "30000.00",
            "activa": False,
        },
        headers=h_dueno,
    )
    assert r2.status_code == 201

    # Recepción lee todas
    resp_rec = await api.get("/api/admin/prestaciones", headers=autorizacion(token_para(recep)))
    assert resp_rec.status_code == 200
    assert len(resp_rec.json()) == 2

    # Odontólogo filtra solo activas
    resp_odo = await api.get(
        "/api/admin/prestaciones?solo_activas=true",
        headers=autorizacion(token_para(odonto)),
    )
    assert resp_odo.status_code == 200
    assert len(resp_odo.json()) == 1
    assert resp_odo.json()[0]["nombre"] == "Consulta Activa"


async def test_rechazo_422_duracion_invalida_o_sena_invalida(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_val@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    # Duración <= 0
    r_dur = await api.post(
        "/api/admin/prestaciones",
        json={"nombre": "Invalida", "duracion_min": 0, "precio_particular": "1000.00"},
        headers=headers,
    )
    assert r_dur.status_code == 422
    assert "duración" in r_dur.text.lower()

    # requiere_sena sin monto_sena
    r_sena = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Invalida 2",
            "duracion_min": 30,
            "precio_particular": "1000.00",
            "requiere_sena": True,
            "monto_sena": "0.00",
        },
        headers=headers,
    )
    assert r_sena.status_code == 422
    assert "seña" in r_sena.text.lower()


async def test_nombre_prestacion_duplicado_es_409(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_prest_dup@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r1 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Ortodoncia",
            "duracion_min": 30,
            "precio_particular": "40000.00",
        },
        headers=headers,
    )
    assert r1.status_code == 201

    r2 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Ortodoncia",
            "duracion_min": 45,
            "precio_particular": "45000.00",
        },
        headers=headers,
    )
    assert r2.status_code == 409
    assert "ya existe una prestación" in r2.json()["detail"].lower()


async def test_baja_logica_prestacion_auditoria(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_prest_baja@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r_crear = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "A Desactivar",
            "duracion_min": 15,
            "precio_particular": "5000.00",
        },
        headers=headers,
    )
    prestacion_id = r_crear.json()["id"]

    r_del = await api.delete(f"/api/admin/prestaciones/{prestacion_id}", headers=headers)
    assert r_del.status_code == 200
    assert r_del.json()["activa"] is False

    eventos = await auditoria_de("prestacion.desactivar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == prestacion_id
    assert isinstance(eventos[0].despues, dict)
    assert eventos[0].despues["activa"] is False


async def test_prestacion_actualizar_parcial_y_revalidacion_combinada(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_prest_patch@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r_crear = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Blanqueamiento",
            "duracion_min": 45,
            "precio_particular": "35000.00",
            "requiere_sena": False,
        },
        headers=headers,
    )
    prestacion_id = r_crear.json()["id"]

    # Intento de activar requiere_sena sin monto_sena en un PATCH cuando antes no tenía
    r_patch_inval = await api.patch(
        f"/api/admin/prestaciones/{prestacion_id}",
        json={"requiere_sena": True},
        headers=headers,
    )
    assert r_patch_inval.status_code == 422
    assert "seña" in r_patch_inval.text.lower()

    # Actualización combinada válida: activa requiere_sena con monto
    r_patch_val = await api.patch(
        f"/api/admin/prestaciones/{prestacion_id}",
        json={"requiere_sena": True, "monto_sena": "10000.00", "duracion_min": 50},
        headers=headers,
    )
    assert r_patch_val.status_code == 200
    data = r_patch_val.json()
    assert data["requiere_sena"] is True
    assert Decimal(str(data["monto_sena"])) == Decimal("10000.00")
    assert data["duracion_min"] == 50

    eventos = await auditoria_de("prestacion.actualizar")
    assert len(eventos) == 1
    assert eventos[0].entidad_id == prestacion_id


async def test_prestacion_rbac_escritura_prohibida_y_aislamiento(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno_a = await crear_usuario(tenant_a, email="dueno_iso_pa@test.com", rol=RolUsuario.DUENO)
    dueno_b = await crear_usuario(tenant_b, email="dueno_iso_pb@test.com", rol=RolUsuario.DUENO)
    recep_a = await crear_usuario(tenant_a, email="recep_iso_pa@test.com", rol=RolUsuario.RECEPCION)

    # Recepción intenta crear -> 403
    r_403 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "No Permitida",
            "duracion_min": 30,
            "precio_particular": "1000.00",
        },
        headers=autorizacion(token_para(recep_a)),
    )
    assert r_403.status_code == 403

    # Crear en Tenant A
    r_a = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Prestacion Exclusiva A",
            "duracion_min": 30,
            "precio_particular": "1000.00",
        },
        headers=autorizacion(token_para(dueno_a)),
    )
    p_a_id = r_a.json()["id"]

    # Dueño B intenta acceder al ID de A -> 404
    r_patch_b = await api.patch(
        f"/api/admin/prestaciones/{p_a_id}",
        json={"nombre": "Robada"},
        headers=autorizacion(token_para(dueno_b)),
    )
    assert r_patch_b.status_code == 404

    r_del_b = await api.delete(
        f"/api/admin/prestaciones/{p_a_id}",
        headers=autorizacion(token_para(dueno_b)),
    )
    assert r_del_b.status_code == 404


async def test_prestacion_patch_desactivar_sena_y_errores_triangulacion(
    api: httpx.AsyncClient,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    dueno = await crear_usuario(tenant_a, email="dueno_triang_p@test.com", rol=RolUsuario.DUENO)
    headers = autorizacion(token_para(dueno))

    r1 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Prestacion Con Sena",
            "duracion_min": 30,
            "precio_particular": "20000.00",
            "requiere_sena": True,
            "monto_sena": "5000.00",
        },
        headers=headers,
    )
    p1_id = r1.json()["id"]

    r2 = await api.post(
        "/api/admin/prestaciones",
        json={
            "nombre": "Prestacion Hermana",
            "duracion_min": 30,
            "precio_particular": "20000.00",
        },
        headers=headers,
    )
    assert r2.status_code == 201

    # Desactivar requiere_sena -> monto_sena debe pasar a None
    r_patch_nosena = await api.patch(
        f"/api/admin/prestaciones/{p1_id}",
        json={"requiere_sena": False},
        headers=headers,
    )
    assert r_patch_nosena.status_code == 200
    assert r_patch_nosena.json()["requiere_sena"] is False
    assert r_patch_nosena.json()["monto_sena"] is None

    # Conflicto al renombrar a nombre de otra prestación en el mismo tenant
    r_patch_dup = await api.patch(
        f"/api/admin/prestaciones/{p1_id}",
        json={"nombre": "Prestacion Hermana"},
        headers=headers,
    )
    assert r_patch_dup.status_code == 409

    # 404 al actualizar inexistente
    r_404_patch = await api.patch(
        f"/api/admin/prestaciones/{uuid.uuid4()}",
        json={"nombre": "Fantasma"},
        headers=headers,
    )
    assert r_404_patch.status_code == 404

    # 404 al borrar inexistente
    r_404_del = await api.delete(
        f"/api/admin/prestaciones/{uuid.uuid4()}",
        headers=headers,
    )
    assert r_404_del.status_code == 404
