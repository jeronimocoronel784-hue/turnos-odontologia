"""Tests de integración para endpoints de Mensajería y Webhook WhatsApp HMAC (tarea 3.1).

Verifica:
- RBAC sobre Recurso.MENSAJES (odontólogo 403, recepción lee/reenvía, dueño CRUD) y multi-tenant.
- GET /webhooks/whatsapp (challenge) y POST /webhooks/whatsapp con firma HMAC-SHA256.
- Firma inválida rechazada con 401.
- Webhook de confirmación repetido confirma el turno una sola vez (RN-AG-08).
- Webhook STOP revoca optin_wa del paciente (RN-CO-01).
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import crear_turno
from app.application.comunicaciones import calcular_firma_hmac_wa, programar_recordatorio_24h
from app.domain.auditoria import Auditoria
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.domain.usuario import RolUsuario, Usuario
from app.shared.settings import Settings


async def _preparar_escenario_msg(
    session: AsyncSession,
    tenant: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    sufijo: str = "a",
) -> tuple[Usuario, Usuario, Usuario, Paciente, Turno]:
    dueno = await crear_usuario(tenant, email=f"dueno-msg-{sufijo}@test.com", rol=RolUsuario.DUENO)
    recep = await crear_usuario(
        tenant, email=f"recep-msg-{sufijo}@test.com", rol=RolUsuario.RECEPCION
    )
    odonto = await crear_usuario(
        tenant, email=f"odonto-msg-{sufijo}@test.com", rol=RolUsuario.ODONTOLOGO
    )
    sillon = Sillon(tenant_id=tenant.id, nombre=f"Box Msg {sufijo}", sucursal="central")
    prest = Prestacion(
        tenant_id=tenant.id,
        nombre=f"Limpieza Msg {sufijo}",
        duracion_min=30,
        precio_particular=Decimal("18000.00"),
        requiere_sena=False,
    )
    paciente = Paciente(
        tenant_id=tenant.id,
        nombre=f"Paciente Msg {sufijo}",
        dni=f"4100022{sufijo[:1].encode()[0] % 10}",
        telefono=f"+549117777888{sufijo[:1].encode()[0] % 10}",
        optin_wa=True,
    )
    session.add_all([sillon, prest, paciente])
    await session.flush()

    inicio = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        prestacion_id=prest.id,
        inicio=inicio,
    )
    return dueno, recep, odonto, paciente, turno


async def test_api_mensajes_y_plantillas_rbac_y_multitenant(
    api: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    token_para: Callable[..., str],
    autorizacion: Callable[[str], dict[str, str]],
) -> None:
    """RBAC: odontólogo 403, recepción lee y reenvía (pero 403 al crear plantilla), dueño CRUD."""
    dueno_a, recep_a, odonto_a, _, turno_a = await _preparar_escenario_msg(
        session, tenant_a, crear_usuario, "a"
    )
    _, recep_b, _, _, _ = await _preparar_escenario_msg(session, tenant_b, crear_usuario, "b")

    h_dueno_a = autorizacion(token_para(dueno_a))
    h_recep_a = autorizacion(token_para(recep_a))
    h_odonto_a = autorizacion(token_para(odonto_a))
    h_recep_b = autorizacion(token_para(recep_b))

    msg = await programar_recordatorio_24h(session, tenant_id=tenant_a.id, turno_id=turno_a.id)
    await session.commit()

    # 1. Odontólogo recibe 403 en /api/mensajes
    resp_odonto = await api.get("/api/mensajes", headers=h_odonto_a)
    assert resp_odonto.status_code == 403

    # 2. Recepción puede listar mensajes (200) y reenviar (200)
    resp_list = await api.get("/api/mensajes", headers=h_recep_a)
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    resp_reenviar = await api.post(f"/api/mensajes/{msg.id}/reenviar", headers=h_recep_a)
    assert resp_reenviar.status_code == 200
    assert resp_reenviar.json()["estado"] == "enviado"

    # 3. Tenant B no puede reenviar un mensaje de Tenant A (404, R4)
    resp_b = await api.post(f"/api/mensajes/{msg.id}/reenviar", headers=h_recep_b)
    assert resp_b.status_code == 404

    # 4. Recepción recibe 403 al crear plantilla; Dueño recibe 201
    payload_pl = {
        "codigo": "recordatorio_24h",
        "canal": "wa",
        "cuerpo": "Hola {{paciente_nombre}}, te esperamos el {{fecha_hora}}.",
    }
    resp_pl_403 = await api.post("/api/plantillas", json=payload_pl, headers=h_recep_a)
    assert resp_pl_403.status_code == 403

    resp_pl_201 = await api.post("/api/plantillas", json=payload_pl, headers=h_dueno_a)
    assert resp_pl_201.status_code == 201
    assert resp_pl_201.json()["version"] == 1


async def test_webhook_whatsapp_hmac_confirmacion_idempotente_y_stop(
    api: httpx.AsyncClient,
    session: AsyncSession,
    settings_test: Settings,
    tenant_a: Tenant,
    crear_usuario: Callable[..., Awaitable[Usuario]],
    auditoria_de: Callable[[str], Awaitable[list[Auditoria]]],
) -> None:
    """Firma inválida -> 401; webhook repetido confirma 1 sola vez (RN-AG-08); STOP baja opt-in."""
    settings_test.wa_webhook_token = "secreto-webhook-wa-test"
    _, _, _, paciente, turno = await _preparar_escenario_msg(session, tenant_a, crear_usuario, "wh")
    await session.commit()

    # 1. GET /webhooks/whatsapp challenge
    resp_challenge = await api.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "secreto-webhook-wa-test",
            "hub.challenge": "123456789",
        },
    )
    assert resp_challenge.status_code == 200
    assert resp_challenge.text == "123456789"

    # 2. POST con firma HMAC inválida -> 401
    body_confirm = json.dumps(
        {
            "eventos": [
                {
                    "event_id": "wamid.confirm.001",
                    "tipo": "confirmar",
                    "turno_id": str(turno.id),
                }
            ]
        }
    ).encode("utf-8")

    resp_401 = await api.post(
        "/webhooks/whatsapp",
        content=body_confirm,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=firmainvalida0000",
        },
    )
    assert resp_401.status_code == 401

    # 3. POST con firma HMAC válida confirma el turno; repetir el mismo webhook es idempotente
    firma_ok = calcular_firma_hmac_wa("secreto-webhook-wa-test", body_confirm)
    resp_ok_1 = await api.post(
        "/webhooks/whatsapp",
        content=body_confirm,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma_ok},
    )
    assert resp_ok_1.status_code == 200
    assert resp_ok_1.json()["procesados"] == 1

    resp_ok_2 = await api.post(
        "/webhooks/whatsapp",
        content=body_confirm,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma_ok},
    )
    assert resp_ok_2.status_code == 200
    assert resp_ok_2.json()["duplicados"] == 1

    await session.refresh(turno)
    assert turno.estado == EstadoTurno.CONFIRMADO.value

    cambios_estado = await auditoria_de("turno.cambiar_estado")
    assert len(cambios_estado) == 1

    # 4. Evento STOP revoca optin_wa del paciente (RN-CO-01)
    body_stop = json.dumps(
        {
            "eventos": [
                {
                    "event_id": "wamid.stop.001",
                    "tipo": "stop",
                    "tenant_slug": tenant_a.slug,
                    "telefono": paciente.telefono,
                }
            ]
        }
    ).encode("utf-8")
    firma_stop = calcular_firma_hmac_wa("secreto-webhook-wa-test", body_stop)
    resp_stop = await api.post(
        "/webhooks/whatsapp",
        content=body_stop,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma_stop},
    )
    assert resp_stop.status_code == 200
    await session.refresh(paciente)
    assert paciente.optin_wa is False
