"""Tests de schemas Pydantic de agenda y turnos (tarea 1.2).

Verifica:
- Schemas estrictos con extra='forbid' y rechazo de tenant_id en body (R1, R4).
- Validación de sobreturno=True exigiendo observaciones/motivo (RN-AG-04).
- Validación de rango horario (fin > inicio en override, hasta > desde en BloqueoCreate).
- Validación de BloqueoCreate exigiendo profesional_id o sillon_id.
- Validación y normalización de DNI/teléfono en ReservaPublicaCreate.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.api.schemas_agenda import (
    BloqueoCreate,
    ReservaPublicaCreate,
    TurnoCreate,
    TurnoEstadoUpdate,
    TurnoReprogramarRequest,
)
from app.domain.bloqueo import MotivoBloqueo
from app.domain.turno import EstadoTurno, OrigenTurno


def test_turno_create_valido_y_defaults() -> None:
    inicio = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    schema = TurnoCreate(
        paciente_id=uuid.uuid4(),
        profesional_id=uuid.uuid4(),
        sillon_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        inicio=inicio,
    )
    assert schema.sobreturno is False
    assert schema.origen == OrigenTurno.PRESENCIAL
    assert schema.fin is None
    assert schema.sena_cobrada is False


def test_turno_create_rechaza_sobreturno_sin_motivo() -> None:
    inicio = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc:
        TurnoCreate(
            paciente_id=uuid.uuid4(),
            profesional_id=uuid.uuid4(),
            sillon_id=uuid.uuid4(),
            prestacion_id=uuid.uuid4(),
            inicio=inicio,
            sobreturno=True,
            observaciones="   ",
        )
    assert "motivo" in str(exc.value).lower() or "sobreturno" in str(exc.value).lower()


def test_turno_create_rechaza_fin_menor_o_igual_inicio() -> None:
    inicio = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc:
        TurnoCreate(
            paciente_id=uuid.uuid4(),
            profesional_id=uuid.uuid4(),
            sillon_id=uuid.uuid4(),
            prestacion_id=uuid.uuid4(),
            inicio=inicio,
            fin=inicio - timedelta(minutes=10),
        )
    assert "fin" in str(exc.value).lower() or "posterior" in str(exc.value).lower()


def test_turno_create_rechaza_tenant_id_extra_forbid() -> None:
    inicio = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc:
        TurnoCreate.model_validate(
            {
                "paciente_id": str(uuid.uuid4()),
                "profesional_id": str(uuid.uuid4()),
                "sillon_id": str(uuid.uuid4()),
                "prestacion_id": str(uuid.uuid4()),
                "inicio": inicio.isoformat(),
                "tenant_id": str(uuid.uuid4()),
            }
        )
    assert "extra_forbidden" in str(exc.value) or "tenant_id" in str(exc.value)


def test_bloqueo_create_validaciones() -> None:
    desde = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    hasta = desde + timedelta(hours=2)

    # 1. Válido con profesional_id
    b = BloqueoCreate(
        profesional_id=uuid.uuid4(),
        desde=desde,
        hasta=hasta,
        motivo=MotivoBloqueo.VACACIONES,
    )
    assert b.motivo == MotivoBloqueo.VACACIONES

    # 2. Rechaza sin profesional ni sillón
    with pytest.raises(ValidationError) as exc1:
        BloqueoCreate(
            profesional_id=None,
            sillon_id=None,
            desde=desde,
            hasta=hasta,
            motivo=MotivoBloqueo.FERIADO,
        )
    assert "profesional" in str(exc1.value).lower() or "sillón" in str(exc1.value).lower()

    # 3. Rechaza hasta <= desde
    with pytest.raises(ValidationError) as exc2:
        BloqueoCreate(
            sillon_id=uuid.uuid4(),
            desde=desde,
            hasta=desde,
            motivo=MotivoBloqueo.MANUAL,
        )
    assert "hasta" in str(exc2.value).lower() or "posterior" in str(exc2.value).lower()


def test_reserva_publica_create_normaliza_dni_y_rechaza_extras() -> None:
    inicio = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    res = ReservaPublicaCreate(
        nombre="  Lucia Fernandez  ",
        dni=" 38.456.789 ",
        telefono=" +54 9 11 5555-6666 ",
        prestacion_id=uuid.uuid4(),
        profesional_id=uuid.uuid4(),
        sillon_id=uuid.uuid4(),
        inicio=inicio,
        optin_wa=True,
    )
    assert res.nombre == "Lucia Fernandez"
    assert res.dni == "38456789"
    assert res.telefono == "+54 9 11 5555-6666"
    assert res.optin_wa is True

    # Rechaza campo extra
    with pytest.raises(ValidationError):
        ReservaPublicaCreate.model_validate(
            {
                "nombre": "Lucia",
                "dni": "38456789",
                "telefono": "1155556666",
                "prestacion_id": str(uuid.uuid4()),
                "profesional_id": str(uuid.uuid4()),
                "sillon_id": str(uuid.uuid4()),
                "inicio": inicio.isoformat(),
                "tenant_id": str(uuid.uuid4()),
            }
        )


def test_turno_estado_y_reprogramar_estrictos() -> None:
    est = TurnoEstadoUpdate(estado=EstadoTurno.CONFIRMADO)
    assert est.estado == EstadoTurno.CONFIRMADO

    rep = TurnoReprogramarRequest(nuevo_inicio=datetime(2026, 11, 12, 10, 0, tzinfo=UTC))
    assert rep.profesional_id is None
