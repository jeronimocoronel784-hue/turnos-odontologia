"""Tests de schemas Pydantic v2 para Mercado Pago (tarea 1.2).

Cumple:
- R1: schemas estrictos con extra='forbid', request/response explícitos.
- R8: Decimal para montos, nunca float.
- Validación de datos de webhook, creación de preferencia y lectura de cobros/discrepancias.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas_mercadopago import (
    CobroMPRead,
    DiscrepanciaMPRead,
    PreferenciaCreate,
    PreferenciaRead,
    WebhookPayloadMP,
)


def test_preferencia_create_valida() -> None:
    """PreferenciaCreate valida montos positivos, campos requeridos y extra='forbid'."""
    sena_id = uuid.uuid4()
    vence = datetime.now(UTC) + timedelta(hours=24)

    pref = PreferenciaCreate(
        sena_id=sena_id,
        monto=Decimal("12500.50"),
        titulo="Seña de turno odontológico",
        vence_at=vence,
    )
    assert pref.sena_id == sena_id
    assert pref.monto == Decimal("12500.50")

    # Rechazo de monto cero o negativo
    with pytest.raises(ValidationError):
        PreferenciaCreate(
            sena_id=sena_id,
            monto=Decimal("0.00"),
            titulo="Seña inválida",
            vence_at=vence,
        )

    # R1: Rechazo de campos extra
    with pytest.raises(ValidationError):
        PreferenciaCreate(
            sena_id=sena_id,
            monto=Decimal("1000.00"),
            titulo="Seña",
            vence_at=vence,
            campo_invalido="hack",  # type: ignore[call-arg]
        )


def test_preferencia_read_valida() -> None:
    """PreferenciaRead serializa los datos entregados por Mercado Pago."""
    vence = datetime.now(UTC) + timedelta(hours=24)
    pref_read = PreferenciaRead(
        id="pref_abc_123",
        init_point="https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_abc_123",
        sandbox_init_point="https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_abc_123",
        external_reference=str(uuid.uuid4()),
        monto=Decimal("15000.00"),
        expiration_date_to=vence,
    )
    assert pref_read.id == "pref_abc_123"
    assert pref_read.monto == Decimal("15000.00")


def test_webhook_payload_mp_valido() -> None:
    """WebhookPayloadMP valida estructura típica de notificaciones de MP."""
    payload = {
        "id": 123456789,
        "live_mode": False,
        "type": "payment",
        "action": "payment.created",
        "data": {"id": "9876543210"},
    }
    wh = WebhookPayloadMP.model_validate(payload)
    assert wh.type == "payment"
    assert wh.data["id"] == "9876543210"

    # Rechazo de payload sin campo data
    with pytest.raises(ValidationError):
        WebhookPayloadMP.model_validate({"id": 123, "type": "payment"})


def test_cobro_mp_read_y_discrepancia_read() -> None:
    """CobroMPRead y DiscrepanciaMPRead formatean datos para el cliente."""
    cobro_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    ahora = datetime.now(UTC)

    cobro = CobroMPRead(
        id=cobro_id,
        tenant_id=tenant_id,
        turno_id=None,
        sena_id=None,
        mp_payment_id="pay_998877",
        mp_preference_id="pref_1122",
        monto=Decimal("20000.00"),
        estado_mp="approved",
        estado_conciliacion="conciliado",
        created_at=ahora,
    )
    assert cobro.monto == Decimal("20000.00")
    assert cobro.estado_mp == "approved"

    disc = DiscrepanciaMPRead(
        id=cobro_id,
        mp_payment_id="pay_998877",
        monto=Decimal("20000.00"),
        estado_mp="approved",
        sena_id=None,
        turno_id=None,
        motivo="Pago recibido tras vencimiento de la seña",
        created_at=ahora,
    )
    assert "vencimiento" in disc.motivo
