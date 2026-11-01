"""Tests de reglas de negocio de Comunicaciones, Outbox y Worker (tarea 2.1).

Verifica:
- RN-CO-02 / RN-CO-04: idempotencia por (turno, plantilla, ventana) y versionado de plantilla.
- RN-CO-01: sin optin_wa no se envía por WhatsApp y se registra omisión auditada (estado omitido).
- RN-CO-03: reintento con backoff exponencial ante fallo del proveedor sin duplicar fila;
  al agotar max_intentos pasa a fallido y permite reenvío manual.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda import crear_turno
from app.application.comunicaciones import (
    crear_version_plantilla,
    procesar_mensaje_outbox,
    procesar_outbox_pendientes,
    programar_recordatorio_24h,
    reenviar_mensaje,
)
from app.domain.mensaje import CanalMensaje, EstadoMensaje, Mensaje
from app.domain.paciente import Paciente
from app.domain.plantilla import CodigoPlantilla
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.security.passwords import hashear_password


async def _preparar_turno_comunicaciones(
    session: AsyncSession,
    tenant: Tenant,
    *,
    optin_wa: bool = True,
    sufijo: str = "1",
) -> tuple[Paciente, Turno]:
    paciente = Paciente(
        tenant_id=tenant.id,
        nombre=f"Paciente Msg {sufijo}",
        dni=f"3900{sufijo}111",
        telefono=f"+54911555599{sufijo[:2]}",
        email=f"pac-msg-{sufijo}@test.com",
        optin_wa=optin_wa,
    )
    odonto = Usuario(
        tenant_id=tenant.id,
        nombre=f"Dr. Msg {sufijo}",
        email=f"odonto-msg-{sufijo}@test.com",
        password_hash=hashear_password("Secret123!", rounds=4),
        rol=RolUsuario.ODONTOLOGO.value,
        matricula=f"MN-MSG-{sufijo}",
        activo=True,
    )
    sillon = Sillon(
        tenant_id=tenant.id,
        nombre=f"Box Msg {sufijo}",
        sucursal="central",
        activo=True,
    )
    prest = Prestacion(
        tenant_id=tenant.id,
        nombre=f"Consulta Msg {sufijo}",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
        activa=True,
    )
    session.add_all([paciente, odonto, sillon, prest])
    await session.flush()

    inicio = datetime(2026, 11, 25, 15, 0, tzinfo=UTC)
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odonto.id,
        sillon_id=sillon.id,
        prestacion_id=prest.id,
        inicio=inicio,
    )
    return paciente, turno


async def test_idempotencia_recordatorio_24h_y_versionado_plantilla(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CO-02/04: no duplica recordatorio por (turno, plantilla, ventana) y usa última versión."""
    _, turno = await _preparar_turno_comunicaciones(session, tenant_a, optin_wa=True, sufijo="idem")

    await crear_version_plantilla(
        session,
        tenant_id=tenant_a.id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA,
        cuerpo="V1: Hola {{paciente_nombre}}",
    )
    pl_v2 = await crear_version_plantilla(
        session,
        tenant_id=tenant_a.id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA,
        cuerpo="V2: Hola {{paciente_nombre}}, turno el {{fecha_hora}}",
    )
    assert pl_v2.version == 2

    m1 = await programar_recordatorio_24h(session, tenant_id=tenant_a.id, turno_id=turno.id)
    m2 = await programar_recordatorio_24h(session, tenant_id=tenant_a.id, turno_id=turno.id)

    assert m1.id == m2.id
    assert m1.plantilla_version == 2
    assert "V2: Hola Paciente Msg idem" in m1.cuerpo_renderizado

    total = (
        await session.execute(
            select(func.count()).select_from(Mensaje).where(Mensaje.tenant_id == tenant_a.id)
        )
    ).scalar_one()
    assert total == 1


async def test_sin_optin_wa_no_envia_whatsapp_y_registra_omision(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CO-01: si el paciente tiene optin_wa=False, el worker no envía WA y marca omitido."""
    _, turno = await _preparar_turno_comunicaciones(
        session, tenant_a, optin_wa=False, sufijo="noopt"
    )
    await crear_version_plantilla(
        session,
        tenant_id=tenant_a.id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA,
        cuerpo="Recordatorio {{paciente_nombre}}",
    )
    msg = await programar_recordatorio_24h(session, tenant_id=tenant_a.id, turno_id=turno.id)
    msg.programado_para = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    await session.flush()

    envios_wa: list[str] = []

    async def _wa_spy(destino: str, cuerpo: str) -> str:
        envios_wa.append(destino)
        return "wamid.test"

    procesados = await procesar_outbox_pendientes(
        session,
        ahora=datetime(2026, 11, 20, 10, 5, tzinfo=UTC),
        enviar_wa_fn=_wa_spy,
    )
    assert len(procesados) == 1
    assert len(envios_wa) == 0
    assert msg.estado == EstadoMensaje.OMITIDO.value
    assert msg.error is not None and "opt-in" in msg.error.lower()


async def test_reintento_con_backoff_sin_duplicar_y_reenvio_manual(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-CO-03: fallo incrementa intentos y reprograma con backoff; al agotar -> fallido."""
    _, turno = await _preparar_turno_comunicaciones(
        session, tenant_a, optin_wa=True, sufijo="retry"
    )
    await crear_version_plantilla(
        session,
        tenant_id=tenant_a.id,
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA,
        cuerpo="Recordatorio {{paciente_nombre}}",
    )
    msg = await programar_recordatorio_24h(session, tenant_id=tenant_a.id, turno_id=turno.id)
    msg.max_intentos = 2
    ahora_0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    msg.programado_para = ahora_0
    await session.flush()

    async def _wa_falla(destino: str, cuerpo: str) -> str:
        raise RuntimeError("Timeout Cloud API")

    # 1. Primer intento fallido: intentos=1, sigue pendiente con programado_para en el futuro
    await procesar_mensaje_outbox(
        session,
        mensaje=msg,
        ahora=ahora_0,
        enviar_wa_fn=_wa_falla,
    )
    assert msg.intentos == 1
    assert msg.estado == EstadoMensaje.PENDIENTE.value
    assert msg.programado_para > ahora_0

    # 2. Segundo intento fallido (alcanza max_intentos=2): pasa a fallido
    await procesar_mensaje_outbox(
        session,
        mensaje=msg,
        ahora=msg.programado_para + timedelta(minutes=1),
        enviar_wa_fn=_wa_falla,
    )
    assert msg.intentos == 2
    assert msg.estado == EstadoMensaje.FALLIDO.value

    # 3. Recepción solicita reenvío manual -> vuelve a pendiente e intentos=0, y luego envía OK
    async def _wa_ok(destino: str, cuerpo: str) -> str:
        return "wamid.ok.123"

    msg_reenviado = await reenviar_mensaje(
        session,
        tenant_id=tenant_a.id,
        mensaje_id=msg.id,
        enviar_wa_fn=_wa_ok,
    )
    assert msg_reenviado.estado == EstadoMensaje.ENVIADO.value
    assert msg_reenviado.proveedor_message_id == "wamid.ok.123"
