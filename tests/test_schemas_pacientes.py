"""Tests de schemas Pydantic de pacientes (tarea 1.2).

Verifica:
- Schemas estrictos con extra='forbid' (R1).
- Normalización automática de DNI y teléfono.
- Mensajes de error en español rioplatense (RN-GL-02).
- Rechazo de tenant_id en body (R4).
- Validación de opt-in booleano en PacienteOptinUpdate.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas_pacientes import (
    FichaClinicaRead,
    PacienteCreate,
    PacienteOptinUpdate,
    PacienteRead,
    PacienteUpdate,
)


def test_paciente_create_valido_y_normalizacion_dni() -> None:
    data = {
        "nombre": "  Ana Gomez  ",
        "dni": " 40.123.456 ",
        "telefono": " +54 9 11 2233-4455 ",
        "email": "ana@example.com",
        "fecha_nac": "1995-05-12",
        "optin_wa": True,
    }
    schema = PacienteCreate.model_validate(data)
    assert schema.nombre == "Ana Gomez"
    assert schema.dni == "40123456"
    assert schema.telefono == "+54 9 11 2233-4455"
    assert schema.optin_wa is True
    assert schema.obra_social_id is None
    assert schema.nro_afiliado is None


def test_paciente_create_defaults() -> None:
    schema = PacienteCreate(
        nombre="Pedro Picapiedra",
        dni="30999888",
        telefono="1144556677",
    )
    assert schema.optin_wa is False
    assert schema.email is None
    assert schema.fecha_nac is None
    assert schema.obra_social_id is None
    assert schema.nro_afiliado is None


def test_paciente_create_rechaza_nombre_vacio() -> None:
    with pytest.raises(ValidationError) as exc:
        PacienteCreate(
            nombre="   ",
            dni="40123456",
            telefono="1122334455",
        )
    assert "nombre" in str(exc.value)


def test_paciente_create_rechaza_dni_vacio_o_invalido() -> None:
    with pytest.raises(ValidationError) as exc:
        PacienteCreate(
            nombre="Carlos",
            dni=" ... ",
            telefono="1122334455",
        )
    assert "dni" in str(exc.value).lower()


def test_paciente_create_rechaza_telefono_vacio() -> None:
    with pytest.raises(ValidationError) as exc:
        PacienteCreate(
            nombre="Carlos",
            dni="40123456",
            telefono="   ",
        )
    assert "teléfono" in str(exc.value).lower() or "telefono" in str(exc.value).lower()


def test_paciente_create_rechaza_campo_extra_o_tenant_id() -> None:
    with pytest.raises(ValidationError) as exc:
        PacienteCreate.model_validate(
            {
                "nombre": "Carlos",
                "dni": "40123456",
                "telefono": "1122334455",
                "tenant_id": str(uuid.uuid4()),
            }
        )
    assert "extra_forbidden" in str(exc.value) or "tenant_id" in str(exc.value)


def test_paciente_optin_update_valido_y_estricto() -> None:
    schema = PacienteOptinUpdate(optin_wa=True)
    assert schema.optin_wa is True

    schema_stop = PacienteOptinUpdate(optin_wa=False)
    assert schema_stop.optin_wa is False

    with pytest.raises(ValidationError):
        PacienteOptinUpdate.model_validate({"optin_wa": True, "otro_campo": 123})


def test_paciente_update_parcial_estricto() -> None:
    schema = PacienteUpdate(nombre="Nuevo Nombre")
    assert schema.nombre == "Nuevo Nombre"
    assert schema.telefono is None

    with pytest.raises(ValidationError):
        PacienteUpdate.model_validate({"dni": "12345678"})  # DNI no se muta por update


def test_paciente_read_con_ficha_clinica() -> None:
    paciente_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    ficha_id = uuid.uuid4()
    ahora = datetime.now(UTC)

    ficha = FichaClinicaRead(
        id=ficha_id,
        paciente_id=paciente_id,
        antecedentes=None,
        alergias=None,
        medicacion=None,
        habitos=None,
        datos_json=None,
        created_at=ahora,
        updated_at=ahora,
    )

    paciente = PacienteRead(
        id=paciente_id,
        tenant_id=tenant_id,
        nombre="Lucia Suarez",
        dni="38111222",
        telefono="1122334455",
        email=None,
        fecha_nac=date(1990, 1, 1),
        obra_social_id=None,
        nro_afiliado=None,
        optin_wa=False,
        observaciones=None,
        activo=True,
        created_at=ahora,
        updated_at=ahora,
        ficha_clinica=ficha,
    )

    dump = paciente.model_dump()
    assert dump["nombre"] == "Lucia Suarez"
    assert dump["dni"] == "38111222"
    assert dump["ficha_clinica"]["id"] == ficha_id
