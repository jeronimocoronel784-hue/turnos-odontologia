"""Tests unitarios de schemas Pydantic v2 para presupuestos y planes de tratamiento (tarea 1.2).

Verifica:
1. extra='forbid' y rechazo de montos inyectados por el cliente en inputs (R1, R8).
2. Validación de pieza FDI opcional en PresupuestoItemInput y cantidad >= 1.
3. Validación de PresupuestoVincularTurnoInput.
"""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.api.schemas_presupuestos import (
    PresupuestoCreate,
    PresupuestoItemInput,
    PresupuestoVincularTurnoInput,
)


def test_presupuesto_item_input_valida_pieza_fdi_cantidad_y_bloquea_montos_cliente() -> None:
    """R1, R8: PresupuestoItemInput no acepta montos del cliente y valida pieza_fdi y cantidad."""
    item_ok = PresupuestoItemInput(
        prestacion_id=uuid.uuid4(),
        pieza_fdi=16,
        cantidad=2,
    )
    assert item_ok.pieza_fdi == 16
    assert item_ok.cantidad == 2

    # Pieza FDI inválida -> ValidationError
    with pytest.raises(ValidationError):
        PresupuestoItemInput(prestacion_id=uuid.uuid4(), pieza_fdi=19, cantidad=1)

    # Cantidad <= 0 -> ValidationError
    with pytest.raises(ValidationError):
        PresupuestoItemInput(prestacion_id=uuid.uuid4(), cantidad=0)

    # R8: cliente intenta inyectar precio_unit o a_cargo -> ValidationError por extra='forbid'
    with pytest.raises(ValidationError):
        PresupuestoItemInput(
            prestacion_id=uuid.uuid4(),
            cantidad=1,
            precio_unit=100,  # type: ignore[call-arg]
        )


def test_presupuesto_create_y_vincular_turno_validacion() -> None:
    """Valida PresupuestoCreate (requiere >= 1 item, extra='forbid') y VincularTurnoInput."""
    pres_ok = PresupuestoCreate(
        paciente_id=uuid.uuid4(),
        obra_social="  OSDE  ",
        validez_hasta=date(2026, 12, 31),
        items=[
            PresupuestoItemInput(prestacion_id=uuid.uuid4(), pieza_fdi=24, cantidad=1),
        ],
    )
    assert pres_ok.obra_social == "OSDE"
    assert len(pres_ok.items) == 1

    # Sin items -> ValidationError
    with pytest.raises(ValidationError):
        PresupuestoCreate(paciente_id=uuid.uuid4(), items=[])

    # R8: cliente intenta inyectar total -> ValidationError
    with pytest.raises(ValidationError):
        PresupuestoCreate(
            paciente_id=uuid.uuid4(),
            items=[PresupuestoItemInput(prestacion_id=uuid.uuid4(), cantidad=1)],
            total=50000,  # type: ignore[call-arg]
        )

    vinc = PresupuestoVincularTurnoInput(
        turno_id=uuid.uuid4(),
        presupuesto_item_id=uuid.uuid4(),
    )
    assert vinc.turno_id is not None
