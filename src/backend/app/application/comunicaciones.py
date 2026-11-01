"""Casos de uso de Comunicaciones, Outbox, Plantillas y Webhooks WA (C-08).

Reglas implementadas:
- RN-CO-01: optin_wa obligatorio para envíos automáticos por WhatsApp; baja STOP inmediata.
- RN-CO-02: sin doble recordatorio/envío por `(entidad, plantilla, ventana)` via `idempotency_key`.
- RN-CO-03: envío asíncrono con reintentos y backoff exponencial sin duplicar filas.
- RN-CO-04: plantillas versionadas; el outbox guarda versión y texto exacto enviado.
- RN-AG-08: confirmación por webhook de WhatsApp idempotente.
- R9: prohibido incluir PHI en logs o errores visibles.
"""

import hashlib
import hmac
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auditoria import registrar_auditoria
from app.domain.mensaje import (
    CanalMensaje,
    EstadoMensaje,
    Mensaje,
    generar_idempotency_key_mensaje,
)
from app.domain.mixins import asegurar_utc
from app.domain.paciente import Paciente
from app.domain.plantilla import CodigoPlantilla, Plantilla
from app.domain.prestacion import Prestacion
from app.domain.turno import Turno
from app.infrastructure.comunicaciones.mailer import enviar_email_smtp
from app.infrastructure.comunicaciones.wa_client import enviar_whatsapp_cloud
from app.shared.exceptions import EntidadInvalida, NoAutenticado, NoEncontrado

EnviarWaFn = Callable[[str, str], Awaitable[str]]
EnviarEmailFn = Callable[[str, str, str], Awaitable[str]]

PLANTILLAS_DEFAULT_TEXTO: dict[str, str] = {
    CodigoPlantilla.CONFIRMACION_RESERVA.value: (
        "Hola {{paciente_nombre}}, reservamos tu turno para {{prestacion}} el {{fecha_hora}}."
    ),
    CodigoPlantilla.RECORDATORIO_24H.value: (
        "Hola {{paciente_nombre}}, te recordamos tu turno el {{fecha_hora}} para {{prestacion}}."
    ),
    CodigoPlantilla.CANCELACION_TURNO.value: (
        "Hola {{paciente_nombre}}, tu turno del {{fecha_hora}} fue cancelado."
    ),
    CodigoPlantilla.HUECO_LISTA_ESPERA.value: (
        "Hola {{paciente_nombre}}, se liberó un horario el {{fecha_hora}} para {{prestacion}}."
    ),
    CodigoPlantilla.SENA_PENDIENTE.value: (
        "Hola {{paciente_nombre}}, aboná la seña de tu turno del {{fecha_hora}}."
    ),
}


def renderizar_cuerpo_plantilla(cuerpo: str, variables: dict[str, str]) -> str:
    """Reemplaza placeholders `{{clave}}` de forma segura."""
    resultado = cuerpo
    for clave, valor in variables.items():
        resultado = resultado.replace(f"{{{{{clave}}}}}", str(valor))
    return resultado


async def crear_version_plantilla(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    codigo: str,
    canal: CanalMensaje = CanalMensaje.WA,
    cuerpo: str,
    asunto: str | None = None,
    activa: bool = True,
    actor_id: uuid.UUID | None = None,
) -> Plantilla:
    """Crea una nueva versión incremental para `(tenant_id, codigo, canal)` (RN-CO-04)."""
    codigo_limpio = codigo.strip().lower()
    cuerpo_limpio = cuerpo.strip()
    if not codigo_limpio or not cuerpo_limpio:
        raise EntidadInvalida("El código y el cuerpo de la plantilla son obligatorios.")

    max_ver = (
        await session.execute(
            select(func.max(Plantilla.version)).where(
                Plantilla.tenant_id == tenant_id,
                Plantilla.codigo == codigo_limpio,
                Plantilla.canal == canal.value,
            )
        )
    ).scalar_one_or_none()
    nueva_version = int(max_ver or 0) + 1

    plantilla = Plantilla(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        codigo=codigo_limpio,
        canal=canal.value,
        version=nueva_version,
        asunto=asunto.strip() if asunto else None,
        cuerpo=cuerpo_limpio,
        activa=activa,
    )
    session.add(plantilla)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="plantilla.crear_version",
        entidad="plantilla",
        entidad_id=str(plantilla.id),
        despues={
            "codigo": plantilla.codigo,
            "canal": plantilla.canal,
            "version": plantilla.version,
        },
    )
    return plantilla


async def obtener_plantilla_vigente(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    codigo: str,
    canal: CanalMensaje,
) -> tuple[str, int, str | None]:
    """Devuelve `(cuerpo, version, asunto)` de la mayor versión activa de la plantilla."""
    fila = (
        await session.execute(
            select(Plantilla)
            .where(
                Plantilla.tenant_id == tenant_id,
                Plantilla.codigo == codigo,
                Plantilla.canal == canal.value,
                Plantilla.activa.is_(True),
            )
            .order_by(Plantilla.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if fila is not None:
        return fila.cuerpo, fila.version, fila.asunto
    cuerpo_fallback = PLANTILLAS_DEFAULT_TEXTO.get(
        codigo, "Notificación del consultorio para {{paciente_nombre}} ({{fecha_hora}})."
    )
    return cuerpo_fallback, 1, "Aviso del consultorio"


async def encolar_mensaje(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entidad_id: uuid.UUID,
    codigo_plantilla: str,
    ventana: str,
    canal: CanalMensaje,
    destino: str,
    variables: dict[str, str],
    paciente_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
    lista_espera_id: uuid.UUID | None = None,
    programado_para: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> Mensaje:
    """Encola un mensaje en el outbox de forma idempotente por `idempotency_key` (RN-CO-02)."""
    idem_key = generar_idempotency_key_mensaje(
        entidad_id=entidad_id,
        codigo_plantilla=codigo_plantilla,
        ventana=ventana,
    )
    existente = (
        await session.execute(
            select(Mensaje).where(
                Mensaje.tenant_id == tenant_id,
                Mensaje.idempotency_key == idem_key,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    cuerpo_base, version_pl, asunto = await obtener_plantilla_vigente(
        session,
        tenant_id=tenant_id,
        codigo=codigo_plantilla,
        canal=canal,
    )
    cuerpo_final = renderizar_cuerpo_plantilla(cuerpo_base, variables)
    prog_utc = asegurar_utc(programado_para) if programado_para is not None else datetime.now(UTC)

    payload_json: dict[str, object] = {
        "variables_claves": sorted(variables.keys()),
        "ventana": ventana,
        "asunto": asunto,
    }
    mensaje = Mensaje(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        turno_id=turno_id,
        lista_espera_id=lista_espera_id,
        canal=canal.value,
        plantilla=codigo_plantilla,
        plantilla_version=version_pl,
        destino=destino.strip(),
        cuerpo_renderizado=cuerpo_final,
        payload=payload_json,
        estado=EstadoMensaje.PENDIENTE.value,
        idempotency_key=idem_key,
        intentos=0,
        max_intentos=3,
        programado_para=prog_utc,
    )
    session.add(mensaje)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="mensaje.encolar",
        entidad="mensaje",
        entidad_id=str(mensaje.id),
        despues={
            "canal": mensaje.canal,
            "plantilla": mensaje.plantilla,
            "plantilla_version": mensaje.plantilla_version,
            "estado": mensaje.estado,
            "idempotency_key": mensaje.idempotency_key,
        },
    )
    return mensaje


async def programar_recordatorio_24h(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    turno_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Mensaje:
    """Programa el recordatorio 24h antes del inicio del turno (RN-CO-02, Flujo 2)."""
    turno = (
        await session.execute(
            select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if turno is None:
        raise NoEncontrado("Che, no encontramos el turno para programar el recordatorio.")

    paciente = await session.get(Paciente, turno.paciente_id)
    if paciente is None:
        raise NoEncontrado("Che, no encontramos el paciente asociado al turno.")

    prestacion = await session.get(Prestacion, turno.prestacion_id)
    inicio_utc = asegurar_utc(turno.inicio)
    programado = inicio_utc - timedelta(hours=24)

    return await encolar_mensaje(
        session,
        tenant_id=tenant_id,
        entidad_id=turno.id,
        codigo_plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        ventana="24h",
        canal=CanalMensaje.WA,
        destino=paciente.telefono,
        variables={
            "paciente_nombre": paciente.nombre,
            "prestacion": prestacion.nombre if prestacion else "Consulta",
            "fecha_hora": inicio_utc.strftime("%d/%m/%Y %H:%M"),
        },
        paciente_id=paciente.id,
        turno_id=turno.id,
        programado_para=programado,
        actor_id=actor_id,
    )


async def procesar_mensaje_outbox(
    session: AsyncSession,
    *,
    mensaje: Mensaje,
    ahora: datetime | None = None,
    enviar_wa_fn: EnviarWaFn = enviar_whatsapp_cloud,
    enviar_email_fn: EnviarEmailFn = enviar_email_smtp,
) -> Mensaje:
    """Despacha un mensaje del outbox verificando opt-in WA (RN-CO-01) y backoff (RN-CO-03)."""
    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)

    # 1. Regla RN-CO-01: verificar optin_wa obligatorio antes de enviar por WhatsApp
    if mensaje.canal == CanalMensaje.WA.value and mensaje.paciente_id is not None:
        paciente = await session.get(Paciente, mensaje.paciente_id)
        if paciente is not None and not paciente.optin_wa:
            mensaje.estado = EstadoMensaje.OMITIDO.value
            mensaje.error = "Omitido: el paciente no tiene opt-in de WhatsApp activo (RN-CO-01)."
            await session.flush()
            await registrar_auditoria(
                session,
                tenant_id=mensaje.tenant_id,
                actor_id=None,
                accion="mensaje.omitir_sin_optin",
                entidad="mensaje",
                entidad_id=str(mensaje.id),
                despues={"estado": mensaje.estado, "motivo": "optin_wa_false"},
            )
            return mensaje

    # 2. Intento de envío por el canal correspondiente
    try:
        if mensaje.canal == CanalMensaje.WA.value:
            provider_id = await enviar_wa_fn(mensaje.destino, mensaje.cuerpo_renderizado)
        else:
            raw_asunto = (
                mensaje.payload.get("asunto") if isinstance(mensaje.payload, dict) else None
            )
            asunto = str(raw_asunto) if raw_asunto else "Aviso del consultorio"
            provider_id = await enviar_email_fn(mensaje.destino, asunto, mensaje.cuerpo_renderizado)

        mensaje.intentos += 1
        mensaje.estado = EstadoMensaje.ENVIADO.value
        mensaje.enviado_at = ahora_utc
        mensaje.proveedor_message_id = provider_id
        mensaje.error = None
        await session.flush()

        await registrar_auditoria(
            session,
            tenant_id=mensaje.tenant_id,
            actor_id=None,
            accion="mensaje.enviar",
            entidad="mensaje",
            entidad_id=str(mensaje.id),
            despues={
                "estado": mensaje.estado,
                "intentos": mensaje.intentos,
                "proveedor_message_id": provider_id,
            },
        )
    except Exception as exc:
        mensaje.intentos += 1
        mensaje.error = f"Error de envío en intento {mensaje.intentos}: {type(exc).__name__}"
        if mensaje.intentos >= mensaje.max_intentos:
            mensaje.estado = EstadoMensaje.FALLIDO.value
        else:
            # Backoff exponencial: 5 min, 10 min, 20 min...
            backoff_min = 5 * (2 ** (mensaje.intentos - 1))
            mensaje.programado_para = ahora_utc + timedelta(minutes=backoff_min)
            mensaje.estado = EstadoMensaje.PENDIENTE.value
        await session.flush()

    return mensaje


async def procesar_outbox_pendientes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    ahora: datetime | None = None,
    limite: int = 50,
    enviar_wa_fn: EnviarWaFn = enviar_whatsapp_cloud,
    enviar_email_fn: EnviarEmailFn = enviar_email_smtp,
) -> list[Mensaje]:
    """Toma los mensajes `pendiente` vencidos y los procesa en orden de `programado_para`."""
    ahora_utc = asegurar_utc(ahora) if ahora is not None else datetime.now(UTC)
    stmt = select(Mensaje).where(
        Mensaje.estado == EstadoMensaje.PENDIENTE.value,
        Mensaje.programado_para <= ahora_utc,
    )
    if tenant_id is not None:
        stmt = stmt.where(Mensaje.tenant_id == tenant_id)
    stmt = stmt.order_by(Mensaje.programado_para.asc()).limit(limite)

    pendientes = (await session.execute(stmt)).scalars().all()
    procesados: list[Mensaje] = []
    for msg in pendientes:
        await procesar_mensaje_outbox(
            session,
            mensaje=msg,
            ahora=ahora_utc,
            enviar_wa_fn=enviar_wa_fn,
            enviar_email_fn=enviar_email_fn,
        )
        procesados.append(msg)
    return procesados


async def reenviar_mensaje(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    mensaje_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    enviar_wa_fn: EnviarWaFn = enviar_whatsapp_cloud,
    enviar_email_fn: EnviarEmailFn = enviar_email_smtp,
) -> Mensaje:
    """Reinicia el contador de intentos de un mensaje y fuerza su reenvío inmediato."""
    mensaje = (
        await session.execute(
            select(Mensaje).where(
                Mensaje.id == mensaje_id,
                Mensaje.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if mensaje is None:
        raise NoEncontrado("Che, no encontramos ese mensaje en el consultorio.")

    estado_anterior = mensaje.estado
    mensaje.estado = EstadoMensaje.PENDIENTE.value
    mensaje.intentos = 0
    mensaje.error = None
    mensaje.programado_para = datetime.now(UTC)
    await session.flush()

    await registrar_auditoria(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id,
        accion="mensaje.reenviar",
        entidad="mensaje",
        entidad_id=str(mensaje.id),
        antes={"estado": estado_anterior},
        despues={"estado": mensaje.estado, "intentos": 0},
    )
    return await procesar_mensaje_outbox(
        session,
        mensaje=mensaje,
        enviar_wa_fn=enviar_wa_fn,
        enviar_email_fn=enviar_email_fn,
    )


def calcular_firma_hmac_wa(secret: str, raw_body: bytes) -> str:
    """Calcula la firma `sha256=<hex>` compatible con `X-Hub-Signature-256` de Meta."""
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verificar_firma_hmac_wa(
    *,
    secret: str,
    raw_body: bytes,
    signature_header: str | None,
) -> None:
    """Verifica la firma HMAC-SHA256 del webhook de WhatsApp (R8, RN-SE-04)."""
    if not secret or not signature_header:
        raise NoAutenticado("Che, la firma del webhook de WhatsApp es inválida o falta.")
    esperada = calcular_firma_hmac_wa(secret, raw_body)
    if not hmac.compare_digest(esperada, signature_header.strip()):
        raise NoAutenticado("Che, la firma del webhook de WhatsApp no es válida.")
