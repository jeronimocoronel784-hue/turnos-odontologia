"""Tests unitarios de schemas de catálogo y políticas (tarea 1.2).

Verifica:
- Inputs estrictos con extra='forbid' (rechazo de tenant_id u otros campos espurios).
- Validaciones de negocio con mensajes rioplatenses de acción clara.
- Casos válidos (happy paths) y casos inválidos (duracion <= 0,
  sena sin monto, vigencia invertida, rangos de politicas).
- Normalización automática de monto_sena = None cuando requiere_sena = False.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas_catalogo import (
    CoberturaOSCreate,
    CoberturaOSUpdate,
    PoliticasRead,
    PoliticasUpdate,
    PrestacionCreate,
    PrestacionUpdate,
    SillonCreate,
    SillonUpdate,
)


def test_sillon_create_rechaza_extra_fields_y_nombre_vacio() -> None:
    with pytest.raises(ValidationError) as exc:
        SillonCreate.model_validate({"nombre": "Box 1", "tenant_id": uuid.uuid4()})
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        SillonCreate(nombre="   ")
    assert "nombre del sillón" in str(exc.value).lower()


def test_sillon_create_defaults() -> None:
    s = SillonCreate(nombre="Box Central")
    assert s.sucursal == "central"
    assert s.activo is True


def test_sillon_update_rechaza_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        SillonUpdate.model_validate({"nombre": "Nuevo", "tenant_id": uuid.uuid4()})
    assert "extra_forbidden" in str(exc.value)


def test_prestacion_create_valida_duracion_positiva() -> None:
    with pytest.raises(ValidationError) as exc:
        PrestacionCreate(
            nombre="Consulta",
            duracion_min=0,
            precio_particular=Decimal("15000.00"),
            requiere_sena=False,
        )
    assert "duración" in str(exc.value).lower()


def test_prestacion_create_valida_precio_no_negativo() -> None:
    with pytest.raises(ValidationError) as exc:
        PrestacionCreate(
            nombre="Consulta",
            duracion_min=30,
            precio_particular=Decimal("-1.00"),
            requiere_sena=False,
        )
    assert "precio" in str(exc.value).lower()


def test_prestacion_create_requiere_sena_exige_monto_positivo() -> None:
    with pytest.raises(ValidationError) as exc:
        PrestacionCreate(
            nombre="Endodoncia",
            duracion_min=60,
            precio_particular=Decimal("45000.00"),
            requiere_sena=True,
            monto_sena=None,
        )
    assert "seña" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PrestacionCreate(
            nombre="Endodoncia",
            duracion_min=60,
            precio_particular=Decimal("45000.00"),
            requiere_sena=True,
            monto_sena=Decimal("0.00"),
        )
    assert "seña" in str(exc.value).lower()


def test_prestacion_create_normaliza_monto_sena_si_no_requiere_sena() -> None:
    p = PrestacionCreate(
        nombre="Limpieza",
        duracion_min=30,
        precio_particular=Decimal("12000.00"),
        requiere_sena=False,
        monto_sena=Decimal("5000.00"),
    )
    assert p.monto_sena is None


def test_prestacion_create_rechaza_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        PrestacionCreate.model_validate(
            {
                "nombre": "Consulta",
                "duracion_min": 20,
                "precio_particular": Decimal("10000.00"),
                "tenant_id": uuid.uuid4(),
            }
        )
    assert "extra_forbidden" in str(exc.value)


def test_prestacion_update_normaliza_sena() -> None:
    u = PrestacionUpdate(requiere_sena=False, monto_sena=Decimal("1000.00"))
    assert u.monto_sena is None


def test_cobertura_create_valida_vigencia_ordenada() -> None:
    hoy = datetime.now(UTC).date()
    with pytest.raises(ValidationError) as exc:
        CoberturaOSCreate(
            obra_social="OSDE",
            prestacion_id=uuid.uuid4(),
            arancel=Decimal("20000.00"),
            copago=Decimal("3000.00"),
            vigencia_desde=hoy,
            vigencia_hasta=hoy - timedelta(days=5),
        )
    assert "vigencia" in str(exc.value).lower()


def test_cobertura_create_valida_montos_no_negativos() -> None:
    hoy = datetime.now(UTC).date()
    with pytest.raises(ValidationError) as exc:
        CoberturaOSCreate(
            obra_social="OSDE",
            prestacion_id=uuid.uuid4(),
            arancel=Decimal("-50.00"),
            copago=Decimal("0.00"),
            vigencia_desde=hoy,
        )
    assert "arancel" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoberturaOSCreate(
            obra_social="OSDE",
            prestacion_id=uuid.uuid4(),
            arancel=Decimal("1000.00"),
            copago=Decimal("-10.00"),
            vigencia_desde=hoy,
        )
    assert "copago" in str(exc.value).lower()


def test_cobertura_create_rechaza_extra_fields() -> None:
    hoy = datetime.now(UTC).date()
    with pytest.raises(ValidationError) as exc:
        CoberturaOSCreate.model_validate(
            {
                "obra_social": "OSDE",
                "prestacion_id": uuid.uuid4(),
                "arancel": Decimal("20000.00"),
                "copago": Decimal("3000.00"),
                "vigencia_desde": hoy,
                "tenant_id": uuid.uuid4(),
            }
        )
    assert "extra_forbidden" in str(exc.value)


def test_politicas_update_valida_rangos_y_rechaza_extra() -> None:
    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate(sena_default_pct=150)
    assert "100" in str(exc.value) or "porcentaje" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate(sena_default_pct=-5)
    assert "seña" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate(cancelacion_horas=-1)
    assert "cancelación" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate(anticipacion_min_dias=-2)
    assert "anticipación" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate.model_validate({"tenant_id": uuid.uuid4()})
    assert "extra_forbidden" in str(exc.value)


def test_politicas_read_y_update_happy_path() -> None:
    p_up = PoliticasUpdate(
        anticipacion_min_dias=2,
        sena_default_pct=40,
        cancelacion_horas=48,
        anticipacion_min_hs=48,
    )
    assert p_up.anticipacion_min_dias == 2
    assert p_up.sena_default_pct == 40
    assert p_up.cancelacion_horas == 48

    p_read = PoliticasRead(
        anticipacion_min_dias=2,
        sena_default_pct=40,
        cancelacion_horas=48,
    )
    assert p_read.sena_default_pct == 40


def test_cobertura_update_valida_fechas_invertidas_y_montos_negativos() -> None:
    hoy = datetime.now(UTC).date()
    with pytest.raises(ValidationError) as exc:
        CoberturaOSUpdate(
            vigencia_desde=hoy,
            vigencia_hasta=hoy - timedelta(days=2),
        )
    assert "vigencia" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoberturaOSUpdate(arancel=Decimal("-10.00"))
    assert "arancel" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoberturaOSUpdate(copago=Decimal("-5.00"))
    assert "copago" in str(exc.value).lower()


def test_prestacion_update_valida_duracion_y_precio_negativo() -> None:
    with pytest.raises(ValidationError) as exc:
        PrestacionUpdate(duracion_min=0)
    assert "duración" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PrestacionUpdate(precio_particular=Decimal("-100.00"))
    assert "precio" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        PrestacionUpdate(requiere_sena=True, monto_sena=Decimal("0.00"))
    assert "seña" in str(exc.value).lower()


def test_politicas_update_valida_anticipacion_min_hs_negativa() -> None:
    with pytest.raises(ValidationError) as exc:
        PoliticasUpdate(anticipacion_min_hs=-3)
    assert "horas de anticipación" in str(exc.value).lower()
