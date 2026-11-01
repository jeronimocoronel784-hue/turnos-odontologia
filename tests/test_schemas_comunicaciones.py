"""Tests unitarios para los schemas Pydantic de Comunicaciones y Mensajería (tarea 1.2, R1)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas_comunicaciones import (
    MensajeCreate,
    PlantillaCreate,
    WebhookWhatsAppEvento,
)
from app.domain.mensaje import CanalMensaje
from app.domain.plantilla import CodigoPlantilla


def test_plantilla_create_valida_y_rechaza_extra() -> None:
    """R1: acepta plantilla válida y rechaza campos desconocidos o cuerpo vacío."""
    dto = PlantillaCreate(
        codigo=CodigoPlantilla.RECORDATORIO_24H.value,
        canal=CanalMensaje.WA,
        cuerpo="  Hola {{paciente_nombre}}, recordá tu turno del {{fecha_hora}}.  ",
    )
    assert dto.cuerpo.startswith("Hola {{paciente_nombre}}")

    with pytest.raises(ValidationError):
        PlantillaCreate(
            codigo=CodigoPlantilla.RECORDATORIO_24H.value,
            canal=CanalMensaje.WA,
            cuerpo="   ",
        )

    with pytest.raises(ValidationError):
        PlantillaCreate.model_validate(
            {
                "codigo": "recordatorio_24h",
                "canal": "wa",
                "cuerpo": "Hola",
                "tenant_id": str(uuid.uuid4()),
            }
        )


def test_mensaje_create_valida_campos_y_rechaza_extra() -> None:
    """Valida solicitud de encolado de mensaje outbox y rechaza extra."""
    dto = MensajeCreate(
        paciente_id=uuid.uuid4(),
        turno_id=uuid.uuid4(),
        canal=CanalMensaje.WA,
        plantilla=CodigoPlantilla.RECORDATORIO_24H.value,
        destino=" +5491155551111 ",
        variables={"paciente_nombre": "Ana", "fecha_hora": "20/11 10:00"},
        ventana="24h",
        programado_para=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )
    assert dto.destino == "+5491155551111"

    with pytest.raises(ValidationError):
        MensajeCreate(
            canal=CanalMensaje.WA,
            plantilla="recordatorio_24h",
            destino="   ",
            ventana="24h",
        )

    with pytest.raises(ValidationError):
        MensajeCreate.model_validate(
            {
                "canal": "wa",
                "plantilla": "recordatorio_24h",
                "destino": "+5491155551111",
                "ventana": "24h",
                "extra_field": 1,
            }
        )


def test_webhook_whatsapp_evento_valida_tipos() -> None:
    """Valida evento de webhook de WhatsApp (confirmación, stop, estado de entrega)."""
    ev = WebhookWhatsAppEvento(
        event_id="wamid.HBgMNTQ5MTE1NTU1MTExMQ==",
        tipo="confirmar",
        turno_id=uuid.uuid4(),
    )
    assert ev.tipo == "confirmar"

    with pytest.raises(ValidationError):
        WebhookWhatsAppEvento.model_validate(
            {
                "event_id": "   ",
                "tipo": "confirmar",
            }
        )
