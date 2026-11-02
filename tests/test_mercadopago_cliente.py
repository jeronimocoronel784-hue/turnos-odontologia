"""Tests unitarios para el cliente y servicio de Mercado Pago (tarea 2.1).

Verifica:
1. Verificación criptográfica de firma HMAC (x-signature con ts y v1, RN-SE-04).
2. Rechazo de firmas alteradas, secretos erróneos o timestamps expirados (replay attacks).
3. Generación de preferencias con external_reference, vencimiento y montos exactos.
"""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.infrastructure.mercadopago.client import (
    MercadoPagoClient,
    calcular_firma_mp,
    verificar_firma_webhook_mp,
)


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
