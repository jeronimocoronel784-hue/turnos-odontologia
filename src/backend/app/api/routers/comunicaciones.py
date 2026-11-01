"""Routers de Comunicaciones (`/api/mensajes`, `/api/plantillas`) y Webhook (`/webhooks/whatsapp`).

Reglas implementadas:
- RN-CO-01: opt-in WA obligatorio; evento `stop` en webhook revoca `optin_wa` de inmediato.
- RN-CO-02 / RN-CO-03: outbox idempotente, procesamiento bajo demanda y reenvío manual.
- RN-CO-04: gestión de plantillas versionadas.
- RN-AG-08: confirmación de turno por webhook WA idempotente.
- R4 / R8 / RN-SE-04: RBAC `Recurso.MENSAJES` y verificación HMAC-SHA256 obligatoria en webhook.
"""

import hmac
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_comunicaciones import (
    MensajeCreate,
    MensajeRead,
    PlantillaCreate,
    PlantillaRead,
    WebhookWhatsAppPayload,
)
from app.api.security import ActorAutenticado, requiere
from app.application.agenda import cambiar_estado_turno
from app.application.comunicaciones import (
    crear_version_plantilla,
    encolar_mensaje,
    procesar_outbox_pendientes,
    reenviar_mensaje,
    verificar_firma_hmac_wa,
)
from app.application.pacientes import procesar_baja_stop
from app.domain.mensaje import CanalMensaje, EstadoMensaje, Mensaje
from app.domain.paciente import Paciente
from app.domain.plantilla import Plantilla
from app.domain.rbac import Accion, Recurso
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, Turno
from app.infrastructure.security.tokens_publicos import resolver_token_gestion_recurso
from app.shared.exceptions import NoAutenticado, NoEncontrado
from app.shared.settings import Settings

router = APIRouter(tags=["comunicaciones"])
router_webhook = APIRouter(tags=["webhooks-whatsapp"])


def _serializar_mensaje(msg: Mensaje) -> MensajeRead:
    return MensajeRead(
        id=msg.id,
        tenant_id=msg.tenant_id,
        paciente_id=msg.paciente_id,
        turno_id=msg.turno_id,
        lista_espera_id=msg.lista_espera_id,
        canal=CanalMensaje(msg.canal),
        plantilla=msg.plantilla,
        plantilla_version=msg.plantilla_version,
        destino=msg.destino,
        cuerpo_renderizado=msg.cuerpo_renderizado,
        payload=msg.payload or {},
        estado=EstadoMensaje(msg.estado),
        idempotency_key=msg.idempotency_key,
        intentos=msg.intentos,
        max_intentos=msg.max_intentos,
        programado_para=msg.programado_para,
        enviado_at=msg.enviado_at,
        error=msg.error,
        proveedor_message_id=msg.proveedor_message_id,
        created_at=msg.created_at,
        updated_at=msg.updated_at,
    )


@router.get("/mensajes", response_model=list[MensajeRead])
async def listar_mensajes_endpoint(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    estado: Annotated[EstadoMensaje | None, Query()] = None,
    turno_id: Annotated[uuid.UUID | None, Query()] = None,
    paciente_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[MensajeRead]:
    stmt = select(Mensaje).where(Mensaje.tenant_id == actor.tenant_id)
    if estado is not None:
        stmt = stmt.where(Mensaje.estado == estado.value)
    if turno_id is not None:
        stmt = stmt.where(Mensaje.turno_id == turno_id)
    if paciente_id is not None:
        stmt = stmt.where(Mensaje.paciente_id == paciente_id)
    stmt = stmt.order_by(Mensaje.created_at.desc())
    filas = (await session.execute(stmt)).scalars().all()
    return [_serializar_mensaje(m) for m in filas]


@router.post("/mensajes", response_model=MensajeRead, status_code=status.HTTP_201_CREATED)
async def crear_mensaje_endpoint(
    payload: MensajeCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> MensajeRead:
    entidad_ref = payload.turno_id or payload.lista_espera_id or payload.paciente_id or uuid.uuid4()
    msg = await encolar_mensaje(
        session,
        tenant_id=actor.tenant_id,
        entidad_id=entidad_ref,
        codigo_plantilla=payload.plantilla,
        ventana=payload.ventana,
        canal=payload.canal,
        destino=payload.destino,
        variables=payload.variables,
        paciente_id=payload.paciente_id,
        turno_id=payload.turno_id,
        lista_espera_id=payload.lista_espera_id,
        programado_para=payload.programado_para,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return _serializar_mensaje(msg)


@router.post("/mensajes/{mensaje_id}/reenviar", response_model=MensajeRead)
async def reenviar_mensaje_endpoint(
    mensaje_id: uuid.UUID,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.REENVIAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> MensajeRead:
    msg = await reenviar_mensaje(
        session,
        tenant_id=actor.tenant_id,
        mensaje_id=mensaje_id,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return _serializar_mensaje(msg)


@router.post("/mensajes/procesar-outbox", response_model=list[MensajeRead])
async def procesar_outbox_endpoint(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.ACTUALIZAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[MensajeRead]:
    procesados = await procesar_outbox_pendientes(session, tenant_id=actor.tenant_id)
    await session.commit()
    return [_serializar_mensaje(m) for m in procesados]


@router.get("/plantillas", response_model=list[PlantillaRead])
async def listar_plantillas_endpoint(
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.LEER))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> list[PlantillaRead]:
    stmt = (
        select(Plantilla)
        .where(Plantilla.tenant_id == actor.tenant_id)
        .order_by(Plantilla.codigo.asc(), Plantilla.version.desc())
    )
    filas = (await session.execute(stmt)).scalars().all()
    return [PlantillaRead.model_validate(p) for p in filas]


@router.post(
    "/plantillas",
    response_model=PlantillaRead,
    status_code=status.HTTP_201_CREATED,
)
async def crear_plantilla_endpoint(
    payload: PlantillaCreate,
    actor: Annotated[ActorAutenticado, Depends(requiere(Recurso.MENSAJES, Accion.CREAR))],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
) -> PlantillaRead:
    plantilla = await crear_version_plantilla(
        session,
        tenant_id=actor.tenant_id,
        codigo=payload.codigo,
        canal=payload.canal,
        cuerpo=payload.cuerpo,
        asunto=payload.asunto,
        activa=payload.activa,
        actor_id=actor.usuario_id,
    )
    await session.commit()
    return PlantillaRead.model_validate(plantilla)


@router_webhook.get("/webhooks/whatsapp")
async def verificar_webhook_whatsapp_endpoint(
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    if (
        hub_mode != "subscribe"
        or not hub_verify_token
        or not settings.wa_webhook_token
        or not hmac.compare_digest(hub_verify_token, settings.wa_webhook_token)
    ):
        raise NoAutenticado("Che, el token de verificación del webhook de WhatsApp no es válido.")
    return Response(content=hub_challenge or "", media_type="text/plain")


@router_webhook.post("/webhooks/whatsapp")
async def recibir_webhook_whatsapp_endpoint(
    request: Request,
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
    redis: Annotated[Any, Depends(deps.cliente_redis)],
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, int]:
    raw_body = await request.body()
    verificar_firma_hmac_wa(
        secret=settings.wa_webhook_token,
        raw_body=raw_body,
        signature_header=x_hub_signature_256,
    )

    payload = WebhookWhatsAppPayload.model_validate_json(raw_body)
    procesados = 0
    duplicados = 0

    for ev in payload.eventos:
        dedup_key = f"wa:webhook:event:{ev.event_id}"
        ya_visto = await redis.get(dedup_key)
        if ya_visto:
            duplicados += 1
            continue

        if ev.tipo == "confirmar":
            turno: Turno | None = None
            if ev.token_gestion:
                fila_token = await resolver_token_gestion_recurso(
                    session, token=ev.token_gestion, recurso="turno"
                )
                turno = await session.get(Turno, uuid.UUID(fila_token.recurso_id))
            elif ev.turno_id is not None:
                turno = await session.get(Turno, ev.turno_id)

            if turno is None:
                raise NoEncontrado("Che, no encontramos el turno a confirmar.")

            await cambiar_estado_turno(
                session,
                tenant_id=turno.tenant_id,
                turno_id=turno.id,
                nuevo_estado=EstadoTurno.CONFIRMADO,
                idempotente=True,
            )

        elif ev.tipo == "stop" and ev.telefono:
            stmt_pac = select(Paciente).where(Paciente.telefono == ev.telefono.strip())
            if ev.tenant_slug:
                tenant = (
                    await session.execute(select(Tenant).where(Tenant.slug == ev.tenant_slug))
                ).scalar_one_or_none()
                if tenant is not None:
                    stmt_pac = stmt_pac.where(Paciente.tenant_id == tenant.id)

            pacientes = (await session.execute(stmt_pac)).scalars().all()
            for pac in pacientes:
                await procesar_baja_stop(session, pac)

        elif ev.tipo == "estado" and ev.mensaje_id and ev.estado_entrega:
            msg = await session.get(Mensaje, ev.mensaje_id)
            if msg is not None:
                msg.estado = ev.estado_entrega
                await session.flush()

        await redis.set(dedup_key, "1", ex=86400 * 7)
        procesados += 1

    await session.commit()
    return {"procesados": procesados, "duplicados": duplicados}
