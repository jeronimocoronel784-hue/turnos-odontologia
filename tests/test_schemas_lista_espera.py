"""Tests unitarios para los schemas Pydantic de Lista de Espera (tarea 1.2, R1)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.api.schemas_lista_espera import (
    ListaEsperaCreate,
    ListaEsperaPublicaCreate,
    ListaEsperaUpdate,
    OfrecerHuecoRequest,
)
from app.domain.lista_espera import CanalAviso, EstadoListaEspera


def test_lista_espera_create_valido_y_rechaza_extra() -> None:
    """R1: acepta alta válida y rechaza campos extra o tenant_id inyectado."""
    dto = ListaEsperaCreate(
        paciente_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        profesional_id=None,
        prioridad=0,
        canal_aviso=CanalAviso.WA,
        observaciones="  Prefiere turno por la mañana  ",
    )
    assert dto.prioridad == 0
    assert dto.observaciones == "Prefiere turno por la mañana"

    with pytest.raises(ValidationError):
        ListaEsperaCreate.model_validate(
            {
                "paciente_id": str(uuid.uuid4()),
                "prestacion_id": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
            }
        )


def test_lista_espera_create_rechaza_prioridad_negativa() -> None:
    """La prioridad no puede ser negativa."""
    with pytest.raises(ValidationError):
        ListaEsperaCreate(
            paciente_id=uuid.uuid4(),
            prestacion_id=uuid.uuid4(),
            prioridad=-1,
        )


def test_lista_espera_update_valida_campos_y_rechaza_extra() -> None:
    """Permite actualizar prioridad/estado/canal y rechaza campos desconocidos."""
    upd = ListaEsperaUpdate(prioridad=2, estado=EstadoListaEspera.BAJA)
    assert upd.prioridad == 2
    assert upd.estado == EstadoListaEspera.BAJA

    with pytest.raises(ValidationError):
        ListaEsperaUpdate.model_validate({"prioridad": -2})

    with pytest.raises(ValidationError):
        ListaEsperaUpdate.model_validate({"campo_extra": 123})


def test_ofrecer_hueco_request_valida_rango_y_ventana() -> None:
    """El fin del hueco debe ser posterior al inicio y la ventana en minutos > 0."""
    inicio = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    req = OfrecerHuecoRequest(
        prestacion_id=uuid.uuid4(),
        profesional_id=uuid.uuid4(),
        sillon_id=uuid.uuid4(),
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        ventana_min=60,
    )
    assert req.ventana_min == 60

    with pytest.raises(ValidationError):
        OfrecerHuecoRequest(
            prestacion_id=uuid.uuid4(),
            profesional_id=uuid.uuid4(),
            sillon_id=uuid.uuid4(),
            inicio=inicio,
            fin=inicio,
            ventana_min=60,
        )

    with pytest.raises(ValidationError):
        OfrecerHuecoRequest(
            prestacion_id=uuid.uuid4(),
            profesional_id=uuid.uuid4(),
            sillon_id=uuid.uuid4(),
            inicio=inicio,
            fin=inicio + timedelta(minutes=30),
            ventana_min=0,
        )


def test_lista_espera_publica_create_normaliza_dni_y_valida_optin_wa() -> None:
    """Normaliza DNI y valida campos obligatorios en alta pública de lista de espera."""
    pub = ListaEsperaPublicaCreate(
        nombre="  Carla Gómez ",
        dni="33.444.555",
        telefono=" +5491144445555 ",
        prestacion_id=uuid.uuid4(),
        canal_aviso=CanalAviso.WA,
        optin_wa=True,
    )
    assert pub.nombre == "Carla Gómez"
    assert pub.dni == "33444555"
    assert pub.telefono == "+5491144445555"

    with pytest.raises(ValidationError):
        ListaEsperaPublicaCreate(
            nombre="   ",
            dni="33444555",
            telefono="+5491144445555",
            prestacion_id=uuid.uuid4(),
        )
