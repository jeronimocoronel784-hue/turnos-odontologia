"""Tests unitarios para el cliente y servicio de Mercado Pago (tarea 2.1).

Verifica:
1. Verificación criptográfica de firma HMAC (x-signature con ts y v1, RN-SE-04).
2. Rechazo de firmas alteradas, secretos erróneos o timestamps expirados (replay attacks).
3. Generación de preferencias con external_reference, vencimiento y montos exactos.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_caja import SenaCobrarInput
from app.application.agenda import crear_turno
from app.application.caja import cobrar_sena
from app.application.mercadopago import (
    crear_preferencia_para_sena,
    resolver_sena_por_external_reference,
)
from app.domain.caja import EstadoSena, MedioPago, Sena
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.mercadopago.client import (
    MercadoPagoClient,
    calcular_firma_mp,
    verificar_firma_webhook_mp,
)
from app.shared.exceptions import EntidadInvalida, NoEncontrado
from app.shared.settings import Settings


def test_verificacion_firma_hmac_valida() -> None:
    """Verifica que una firma correctamente armada con secreto y ts sea aceptada."""
    secret = "test_webhook_secret_key_12345"
    data_id = "1234567890"
    request_id = "req_uuid_abc"
    ts = int(time.time())

    # Genera la firma válida
    firma_v1 = calcular_firma_mp(
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        secret=secret,
    )
    x_signature = f"ts={ts},v1={firma_v1}"

    es_valida = verificar_firma_webhook_mp(
        x_signature=x_signature,
        request_id=request_id,
        data_id=data_id,
        secret=secret,
    )
    assert es_valida is True


def test_rechazo_firmas_invalidas_o_secretos_erroneos() -> None:
    """Firma alterada o secreto erróneo devuelve False."""
    secret = "secreto_original"
    data_id = "998877"
    request_id = "req_123"
    ts = int(time.time())

    firma_v1 = calcular_firma_mp(
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        secret=secret,
    )

    # 1. Secreto incorrecto
    assert (
        verificar_firma_webhook_mp(
            x_signature=f"ts={ts},v1={firma_v1}",
            request_id=request_id,
            data_id=data_id,
            secret="secreto_otro",
        )
        is False
    )

    # 2. Firma manipulada
    assert (
        verificar_firma_webhook_mp(
            x_signature=f"ts={ts},v1=firma_trucha",
            request_id=request_id,
            data_id=data_id,
            secret=secret,
        )
        is False
    )

    # 3. Formato corrupto de x-signature
    assert (
        verificar_firma_webhook_mp(
            x_signature="formato_invalido_sin_comas",
            request_id=request_id,
            data_id=data_id,
            secret=secret,
        )
        is False
    )


def test_rechazo_firma_expirada_replay_attack() -> None:
    """Un timestamp con más de 10 minutos de antigüedad es rechazado."""
    secret = "secreto"
    data_id = "112233"
    request_id = "req_old"
    ts_viejo = int(time.time()) - 700  # Más de 10 minutos atrás

    firma_v1 = calcular_firma_mp(
        data_id=data_id,
        request_id=request_id,
        ts=ts_viejo,
        secret=secret,
    )

    assert (
        verificar_firma_webhook_mp(
            x_signature=f"ts={ts_viejo},v1={firma_v1}",
            request_id=request_id,
            data_id=data_id,
            secret=secret,
            tolerancia_s=600,
        )
        is False
    )


@pytest.mark.asyncio
async def test_crear_preferencia_mp_mock() -> None:
    """MercadoPagoClient genera la preferencia con external_reference y expiración."""
    sena_id = uuid.uuid4()
    vence = datetime.now(UTC) + timedelta(hours=24)
    monto = Decimal("15000.00")

    cliente = MercadoPagoClient(access_token="TEST-ACCESS-TOKEN")
    pref = await cliente.crear_preferencia(
        sena_id=sena_id,
        monto=monto,
        titulo="Seña de consulta",
        vence_at=vence,
        paciente_email="paciente@test.com",
    )

    assert pref.external_reference == str(sena_id)
    assert pref.monto == monto
    assert "pref_" in pref.id
    assert "http" in pref.init_point
    assert pref.expiration_date_to == vence


# ---------------------------------------------------------------------------
# Servicio de aplicación: preferencia atada a una seña `pendiente` (tarea 2.1)
# ---------------------------------------------------------------------------


async def _sena_pendiente(session: AsyncSession, tenant: Tenant) -> tuple[Sena, Turno, Usuario]:
    """Crea un turno con `requiere_sena` y devuelve su seña `pendiente`."""
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-pref-{tenant.slug}@test.com",
        nombre="Dr. Preferencia",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-60601",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente Preferencia",
        dni=f"45{uuid.uuid4().int % 10**7:07d}",
        telefono=f"+54911666{uuid.uuid4().int % 10**6:06d}",
        email="paciente-pref@test.com",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Box Preferencia",
        sucursal="central",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Implante con seña preferencia",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=Decimal("10000.00"),
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()
    turno, _ = await crear_turno(
        session,
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 12, 5, 10, 0, tzinfo=UTC),
        actor_id=odontologo.id,
    )
    await session.flush()
    sena = (await session.execute(select(Sena).where(Sena.turno_id == turno.id))).scalar_one()
    return sena, turno, odontologo


async def test_crear_preferencia_para_sena_vincula_id_y_vencimiento(
    session: AsyncSession,
    tenant_a: Tenant,
    settings_test: Settings,
) -> None:
    """RN-PA-02: `external_reference = sena.id` y `expiration_date_to = vence_at`."""
    sena, _, _ = await _sena_pendiente(session, tenant_a)

    pref = await crear_preferencia_para_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        settings=settings_test,
        paciente_email="paciente-pref@test.com",
    )

    assert pref.external_reference == str(sena.id)
    assert pref.monto == Decimal("10000.00")
    assert pref.expiration_date_to.replace(tzinfo=None) == sena.vence_at.replace(tzinfo=None)
    assert pref.init_point.startswith("http")


async def test_crear_preferencia_rechaza_sena_no_pendiente_o_de_otro_tenant(
    session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    settings_test: Settings,
) -> None:
    """Sólo una seña `pendiente` del tenant puede generar preferencia (RN-PA-02, R4)."""
    sena, _, odontologo = await _sena_pendiente(session, tenant_a)

    with pytest.raises(NoEncontrado):
        await crear_preferencia_para_sena(
            session,
            tenant_id=tenant_b.id,
            sena_id=sena.id,
            settings=settings_test,
        )

    await cobrar_sena(
        session,
        tenant_id=tenant_a.id,
        sena_id=sena.id,
        datos=SenaCobrarInput(medio=MedioPago.EFECTIVO),
        actor_id=odontologo.id,
    )
    await session.flush()

    with pytest.raises(EntidadInvalida):
        await crear_preferencia_para_sena(
            session,
            tenant_id=tenant_a.id,
            sena_id=sena.id,
            settings=settings_test,
        )


async def test_resolver_sena_por_external_reference(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """El webhook resuelve la seña por `external_reference` y deriva el tenant de ella."""
    sena, turno, _ = await _sena_pendiente(session, tenant_a)

    resuelto = await resolver_sena_por_external_reference(session, str(sena.id))
    assert resuelto is not None
    sena_resuelta, turno_resuelto = resuelto
    assert sena_resuelta.id == sena.id
    assert sena_resuelta.tenant_id == tenant_a.id
    assert turno_resuelto.id == turno.id

    assert await resolver_sena_por_external_reference(session, str(uuid.uuid4())) is None
    assert await resolver_sena_por_external_reference(session, "no-es-un-uuid") is None
    assert await resolver_sena_por_external_reference(session, None) is None


async def test_sena_pendiente_arranca_en_estado_pendiente(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Guard de regresión: el helper de test realmente crea la seña `pendiente`."""
    sena, _, _ = await _sena_pendiente(session, tenant_a)
    assert sena.estado == EstadoSena.PENDIENTE.value
