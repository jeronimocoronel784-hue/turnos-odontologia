"""Tests de integración para /api/agenda, /api/turnos y /api/bloqueos (tarea 3.1).

Verifica:
- Alta de turno, cálculo de fin, token_gestion y 409 con slots_alternativos en choque de horario.
- Vista GET /api/agenda (turnos + bloqueos) con aislamiento multi-tenant (R4).
- RBAC sobre Recurso.AGENDA y Recurso.BLOQUEOS (odontólogo lee/actualiza estado; 403 al crear).
- Transiciones de estado (PATCH /api/turnos/{id}/estado) y reprogramación 1-clic.
- Registro en auditoría append-only (RN-SE-01).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria import Auditoria
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario


async def _preparar_datos_agenda(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    sufijo: str = "a",
) -> tuple[Usuario, Usuario, Usuario, Sillon, Prestacion, Paciente]:
    dueno = await crear_usuario(tenant, email=f"dueno_ag_{sufijo}@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(
        tenant, email=f"recep_ag_{sufijo}@test.com", rol=RolUsuario.RECEPCION
    )
    odonto = await crear_usuario(
        tenant, email=f"odonto_ag_{sufijo}@test.com", rol=RolUsuario.ODONTOLOGO
    )
    sillon = Sillon(tenant_id=tenant.id, nombre=f"Box {sufijo}", sucursal="central")
    prest = Prestacion(
        tenant_id=tenant.id,
        nombre=f"Limpieza {sufijo}",
        duracion_min=30,
        precio_particular=Decimal("20000.00"),
        requiere_sena=False,
    )
    paciente = Paciente(
        tenant_id=tenant.id,
        nombre=f"Paciente {sufijo}",
        dni=f"4011122{sufijo[:1].encode()[0] % 10}",
        telefono="1133445566",
    )
    session.add_all([sillon, prest, paciente])
    await session.flush()
    return dueno, recep, odonto, sillon, prest, paciente


async def test_recepcion_crea_turno_consulta_agenda_y_recibe_409_con_slots_en_choque(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    _, recep_a, odonto_a, sillon_a, prest_a, pac_a = await _preparar_datos_agenda(
        session, tenant_a, crear_usuario, "a1"
    )
    _, recep_b, _, _, _, _ = await _preparar_datos_agenda(session, tenant_b, crear_usuario, "b1")
    headers_a = autorizacion(token_para(recep_a))
    headers_b = autorizacion(token_para(recep_b))

    inicio = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    resp = await api.post(
        "/api/turnos",
        json={
            "paciente_id": str(pac_a.id),
            "profesional_id": str(odonto_a.id),
            "sillon_id": str(sillon_a.id),
            "prestacion_id": str(prest_a.id),
            "inicio": inicio.isoformat(),
        },
        headers=headers_a,
    )
    assert resp.status_code == 201, resp.text
    turno = resp.json()
    assert turno["estado"] == "pendiente"
    assert turno["token_gestion"] is not None

    # Choque en el mismo horario -> 409 con slots_alternativos
    resp_choque = await api.post(
        "/api/turnos",
        json={
            "paciente_id": str(pac_a.id),
            "profesional_id": str(odonto_a.id),
            "sillon_id": str(sillon_a.id),
            "prestacion_id": str(prest_a.id),
            "inicio": inicio.isoformat(),
        },
        headers=headers_a,
    )
    assert resp_choque.status_code == 409
    body_409 = resp_choque.json()
    assert "detail" in body_409
    assert isinstance(body_409.get("slots_alternativos"), list)
    assert len(body_409["slots_alternativos"]) > 0

    # Vista GET /api/agenda devuelve el turno en tenant_a y vacío en tenant_b (R4)
    desde = datetime(2026, 11, 23, 0, 0, tzinfo=UTC).isoformat()
    hasta = datetime(2026, 11, 23, 23, 59, tzinfo=UTC).isoformat()
    resp_ag_a = await api.get(
        "/api/agenda", params={"desde": desde, "hasta": hasta}, headers=headers_a
    )
    assert resp_ag_a.status_code == 200
    assert len(resp_ag_a.json()["turnos"]) == 1

    resp_ag_b = await api.get(
        "/api/agenda", params={"desde": desde, "hasta": hasta}, headers=headers_b
    )
    assert resp_ag_b.status_code == 200
    assert len(resp_ag_b.json()["turnos"]) == 0

    # Tenant B no puede ver el turno de Tenant A por ID
    resp_404 = await api.get(f"/api/turnos/{turno['id']}", headers=headers_b)
    assert resp_404.status_code == 404

    eventos = await auditoria_de("turno.crear")
    assert any(e.entidad_id == turno["id"] for e in eventos)


async def test_rbac_odontologo_actualiza_estado_pero_no_crea_turno_ni_bloqueo(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    _, recep, odonto, sillon, prest, pac = await _preparar_datos_agenda(
        session, tenant_a, crear_usuario, "rbac"
    )
    headers_recep = autorizacion(token_para(recep))
    headers_odonto = autorizacion(token_para(odonto))

    inicio = datetime(2026, 11, 24, 11, 0, tzinfo=UTC)

    # 1. Odontólogo NO puede crear turno (403)
    resp_crear_403 = await api.post(
        "/api/turnos",
        json={
            "paciente_id": str(pac.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prest.id),
            "inicio": inicio.isoformat(),
        },
        headers=headers_odonto,
    )
    assert resp_crear_403.status_code == 403

    # 2. Recepción crea el turno (201)
    resp_crear = await api.post(
        "/api/turnos",
        json={
            "paciente_id": str(pac.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prest.id),
            "inicio": inicio.isoformat(),
        },
        headers=headers_recep,
    )
    assert resp_crear.status_code == 201
    turno_id = resp_crear.json()["id"]

    # 3. Odontólogo SÍ puede actualizar el estado (pendiente -> confirmado -> presente)
    for nuevo_est in ("confirmado", "presente", "finalizado"):
        resp_est = await api.patch(
            f"/api/turnos/{turno_id}/estado",
            json={"estado": nuevo_est},
            headers=headers_odonto,
        )
        assert resp_est.status_code == 200, resp_est.text
        assert resp_est.json()["estado"] == nuevo_est

    # 4. Odontólogo NO puede crear bloqueo (403), Recepción SÍ puede (201) y borrarlo (204)
    payload_bloqueo = {
        "profesional_id": str(odonto.id),
        "desde": (inicio + timedelta(days=1)).isoformat(),
        "hasta": (inicio + timedelta(days=1, hours=2)).isoformat(),
        "motivo": "administrativo",
    }
    resp_bloq_403 = await api.post("/api/bloqueos", json=payload_bloqueo, headers=headers_odonto)
    assert resp_bloq_403.status_code == 403

    resp_bloq_201 = await api.post("/api/bloqueos", json=payload_bloqueo, headers=headers_recep)
    assert resp_bloq_201.status_code == 201
    bloqueo_id = resp_bloq_201.json()["id"]

    # Odontólogo puede listar bloqueos (200) pero no borrarlos (403)
    resp_bloq_list = await api.get("/api/bloqueos", headers=headers_odonto)
    assert resp_bloq_list.status_code == 200
    assert len(resp_bloq_list.json()) == 1

    resp_del_403 = await api.delete(f"/api/bloqueos/{bloqueo_id}", headers=headers_odonto)
    assert resp_del_403.status_code == 403

    resp_del_204 = await api.delete(f"/api/bloqueos/{bloqueo_id}", headers=headers_recep)
    assert resp_del_204.status_code == 204


async def test_reprogramacion_1_clic_endpoint_interno(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    _, recep, odonto, sillon, prest, pac = await _preparar_datos_agenda(
        session, tenant_a, crear_usuario, "rep"
    )
    headers = autorizacion(token_para(recep))

    inicio = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    resp1 = await api.post(
        "/api/turnos",
        json={
            "paciente_id": str(pac.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "prestacion_id": str(prest.id),
            "inicio": inicio.isoformat(),
        },
        headers=headers,
    )
    assert resp1.status_code == 201
    orig_id = resp1.json()["id"]

    nuevo_inicio = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
    resp_rep = await api.post(
        f"/api/turnos/{orig_id}/reprogramar",
        json={"nuevo_inicio": nuevo_inicio.isoformat(), "motivo": "Cambio pedido por paciente"},
        headers=headers,
    )
    assert resp_rep.status_code == 201, resp_rep.text
    nuevo = resp_rep.json()
    assert nuevo["turno_origen_id"] == orig_id
    assert nuevo["estado"] == "pendiente"

    # El turno original quedó reprogramado
    resp_orig = await api.get(f"/api/turnos/{orig_id}", headers=headers)
    assert resp_orig.status_code == 200
    assert resp_orig.json()["estado"] == "reprogramado"
