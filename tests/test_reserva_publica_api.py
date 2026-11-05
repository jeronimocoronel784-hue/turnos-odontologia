"""Tests de integración para el flujo público de Reserva Online y Autogestión por Token (tarea 3.2).

Verifica:
- Flujo 1: GET /reservar/{slug} lista catálogo y calcula slots reales descontando turnos/bloqueos.
- POST /reservar/{slug} crea Paciente, Turno pendiente, token_gestion y 409 con slots_alternativos.
- GET /mis-turnos/{token} muestra el turno propio; token inválido o vencido devuelve 401 (RN-SE-03).
- POST /mis-turnos/{token}/confirmar es idempotente (RN-AG-08) y exige seña paga (RN-PA-01).
- POST /mis-turnos/{token}/reprogramar y /cancelar respetan anticipación (RN-AG-05) y RN-AG-06.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.tokens_publicos import crear_token_gestion


async def _preparar_consultorio_publico(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> tuple[Usuario, Sillon, Prestacion, Prestacion]:
    odonto = await crear_usuario(
        tenant,
        email="odonto_pub@test.com",
        rol=RolUsuario.ODONTOLOGO,
        nombre="Dr. Roberto Dientes",
    )
    sillon = Sillon(tenant_id=tenant.id, nombre="Box Publico 1", sucursal="central")
    prest_sin_sena = Prestacion(
        tenant_id=tenant.id,
        nombre="Consulta Diagnóstico",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
    )
    prest_con_sena = Prestacion(
        tenant_id=tenant.id,
        nombre="Implante Dental",
        duracion_min=60,
        precio_particular=Decimal("150000.00"),
        requiere_sena=True,
        monto_sena=Decimal("30000.00"),
    )
    session.add_all([sillon, prest_sin_sena, prest_con_sena])
    await session.flush()
    return odonto, sillon, prest_sin_sena, prest_con_sena


async def test_flujo_reserva_publica_slots_alta_confirmacion_y_choque_409(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    odonto, sillon, prest_sin_sena, _ = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )

    # 1. GET /reservar/{slug} con parámetros de búsqueda de slots
    fecha_futura = (datetime.now(UTC) + timedelta(days=5)).date()
    resp_disp = await api.get(
        f"/reservar/{tenant_a.slug}",
        params={
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "fecha": fecha_futura.isoformat(),
        },
    )
    assert resp_disp.status_code == 200, resp_disp.text
    disp = resp_disp.json()
    assert disp["tenant_slug"] == tenant_a.slug
    assert len(disp["prestaciones"]) >= 2
    assert len(disp["profesionales"]) >= 1
    assert len(disp["slots_disponibles"]) > 0

    primer_slot_inicio = disp["slots_disponibles"][0]["inicio"]

    # 2. POST /reservar/{slug} crea paciente + turno pendiente + token_gestion
    resp_res = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Valeria Sosa",
            "dni": "39.111.222",
            "telefono": "+54 9 11 6677-8899",
            "optin_wa": True,
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": primer_slot_inicio,
        },
    )
    assert resp_res.status_code == 201, resp_res.text
    reserva = resp_res.json()
    assert reserva["estado"] == "pendiente"
    assert reserva["requiere_sena"] is False
    token = reserva["token_gestion"]
    assert isinstance(token, str) and len(token) > 20

    # 3. Intentar reservar el mismo slot devuelve 409 con slots_alternativos
    resp_choque = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Otro Paciente",
            "dni": "41.222.333",
            "telefono": "1144445555",
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": primer_slot_inicio,
        },
    )
    assert resp_choque.status_code == 409
    assert len(resp_choque.json()["slots_alternativos"]) > 0

    # 4. GET /mis-turnos/{token} devuelve el turno y POST /confirmar es idempotente
    resp_ver = await api.get(f"/mis-turnos/{token}")
    assert resp_ver.status_code == 200
    assert resp_ver.json()["turno_id"] == reserva["turno_id"]

    resp_conf1 = await api.post(f"/mis-turnos/{token}/confirmar")
    assert resp_conf1.status_code == 200
    assert resp_conf1.json()["estado"] == "confirmado"

    resp_conf2 = await api.post(f"/mis-turnos/{token}/confirmar")
    assert resp_conf2.status_code == 200
    assert resp_conf2.json()["estado"] == "confirmado"


async def test_reserva_publica_con_sena_impaga_bloquea_confirmacion_y_valida_token_ajeno(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    odonto, sillon, _, prest_con_sena = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )
    inicio = (datetime.now(UTC) + timedelta(days=6)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )

    resp_res = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Marcos Paz",
            "dni": "36.777.888",
            "telefono": "1177778888",
            "prestacion_id": str(prest_con_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": inicio.isoformat(),
        },
    )
    assert resp_res.status_code == 201
    datos = resp_res.json()
    assert datos["requiere_sena"] is True
    assert Decimal(str(datos["monto_sena"])) == Decimal("30000.00")
    token = datos["token_gestion"]

    # Confirmar con seña impaga -> 409 (RN-PA-01)
    resp_conf = await api.post(f"/mis-turnos/{token}/confirmar")
    assert resp_conf.status_code == 409
    assert "seña" in resp_conf.json()["detail"].lower()

    # Token de otro recurso (ej. consentimiento) o token inventado -> 401 (RN-SE-03)
    token_otro_recurso = await crear_token_gestion(
        session,
        tenant_id=tenant_a.id,
        recurso="consentimiento",
        recurso_id=datos["turno_id"],
        vence_at=datetime.now(UTC) + timedelta(days=1),
    )
    await session.commit()

    resp_401_recurso = await api.get(f"/mis-turnos/{token_otro_recurso}")
    assert resp_401_recurso.status_code == 401

    resp_401_falso = await api.get("/mis-turnos/token-inexistente-12345")
    assert resp_401_falso.status_code == 401


async def test_autogestion_reprogramar_y_cancelar_por_token(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    odonto, sillon, prest_sin_sena, _ = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )
    inicio = (datetime.now(UTC) + timedelta(days=4)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )

    resp_res = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Sofia Castro",
            "dni": "42.333.444",
            "telefono": "1199990000",
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": inicio.isoformat(),
        },
    )
    assert resp_res.status_code == 201
    token_orig = resp_res.json()["token_gestion"]

    # Reprogramar a +1 día (dentro de término > 24h)
    nuevo_inicio = inicio + timedelta(days=1)
    resp_rep = await api.post(
        f"/mis-turnos/{token_orig}/reprogramar",
        json={"nuevo_inicio": nuevo_inicio.isoformat(), "motivo": "Viaje laboral"},
    )
    assert resp_rep.status_code == 201, resp_rep.text
    nuevo_turno = resp_rep.json()
    nuevo_token = nuevo_turno["token_gestion"]
    assert nuevo_token is not None and nuevo_token != token_orig

    # Cancelar el nuevo turno por su nuevo token (en término)
    resp_canc = await api.post(
        f"/mis-turnos/{nuevo_token}/cancelar",
        json={"motivo": "Se reprogramará el mes que viene"},
    )
    assert resp_canc.status_code == 200
    assert resp_canc.json()["estado"] == "cancelado"


async def test_slots_publicos_sin_filtro_de_profesional_ni_sillon(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    """El portal público sólo manda prestación y fecha: el backend arma el producto.

    Antes exigía profesional y sillón, por lo que el frontend (que no los manda en
    el primer paso) recibía siempre `slots_disponibles` vacío.
    """
    odonto, sillon, prest_sin_sena, _ = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )
    fecha_futura = (datetime.now(UTC) + timedelta(days=3)).date()

    resp = await api.get(
        f"/reservar/{tenant_a.slug}",
        params={"prestacion_id": str(prest_sin_sena.id), "fecha": fecha_futura.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    slots = resp.json()["slots_disponibles"]
    assert len(slots) > 0
    for slot in slots:
        assert slot["profesional_id"] == str(odonto.id)
        assert slot["sillon_id"] == str(sillon.id)
        assert slot["inicio"] < slot["fin"]


async def test_pago_publico_de_sena_genera_preferencia_y_404_sin_sena(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    odonto, sillon, prest_sin_sena, prest_con_sena = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )
    inicio = (datetime.now(UTC) + timedelta(days=7)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )

    resp_res = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Lucia Ferreyra",
            "dni": "35.111.222",
            "telefono": "1160001111",
            "prestacion_id": str(prest_con_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": inicio.isoformat(),
        },
    )
    assert resp_res.status_code == 201, resp_res.text
    token = resp_res.json()["token_gestion"]

    # La preferencia se arma con el monto de la seña persistida (R8: el paciente no manda montos).
    resp_pago = await api.post(f"/mis-turnos/{token}/pago")
    assert resp_pago.status_code == 200, resp_pago.text
    preferencia = resp_pago.json()
    assert preferencia["init_point"].startswith("https://")
    assert preferencia["sandbox_init_point"].startswith("https://")
    assert Decimal(str(preferencia["monto"])) == Decimal("30000.00")
    assert preferencia["external_reference"]

    # Un turno sin seña no tiene nada que cobrar -> 404.
    resp_res_sin = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Pedro Gomez",
            "dni": "33.444.555",
            "telefono": "1155556666",
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": (inicio + timedelta(hours=2)).isoformat(),
        },
    )
    assert resp_res_sin.status_code == 201, resp_res_sin.text
    token_sin_sena = resp_res_sin.json()["token_gestion"]

    resp_pago_sin = await api.post(f"/mis-turnos/{token_sin_sena}/pago")
    assert resp_pago_sin.status_code == 404


async def test_disponibilidad_para_reprogramar_por_token(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    odonto, sillon, prest_sin_sena, _ = await _preparar_consultorio_publico(
        session, tenant_a, crear_usuario
    )
    inicio = (datetime.now(UTC) + timedelta(days=8)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )

    resp_res = await api.post(
        f"/reservar/{tenant_a.slug}",
        json={
            "nombre": "Ana Ruiz",
            "dni": "30.222.333",
            "telefono": "1144443333",
            "prestacion_id": str(prest_sin_sena.id),
            "profesional_id": str(odonto.id),
            "sillon_id": str(sillon.id),
            "inicio": inicio.isoformat(),
        },
    )
    assert resp_res.status_code == 201, resp_res.text
    token = resp_res.json()["token_gestion"]

    resp_disp = await api.get(
        f"/mis-turnos/{token}/disponibilidad",
        params={"fecha": inicio.date().isoformat()},
    )
    assert resp_disp.status_code == 200, resp_disp.text
    slots = resp_disp.json()
    assert isinstance(slots, list) and len(slots) > 0
    for slot in slots:
        assert slot["profesional_id"] == str(odonto.id)
        assert slot["sillon_id"] == str(sillon.id)
    # El horario ya reservado por este mismo turno no debe ofrecerse de nuevo.
    assert inicio.isoformat() not in {slot["inicio"] for slot in slots}
