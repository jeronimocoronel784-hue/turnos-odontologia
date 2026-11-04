"""Schemas Pydantic v2 de liquidaciones (C-13, tarea 2.3, R1/R8).

Verifica:
1. `extra='forbid'` en todos los inputs y rechazo de totales calculados por el cliente (R8).
2. `periodo` con formato `yyyymm` y `obra_social` no vacía.
3. `monto_reconocido` no negativo y con 2 decimales como máximo.
4. Débito sin motivo y motivo de anulación vacío rechazados.
5. Serialización de `Decimal` como string en las respuestas.
6. Bloque E (D10): un `turno_id` repetido se rechaza en el borde (422).
7. Bloque E (D4/D10): la lectura expone el `saldo_debito` derivado.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas_liquidaciones import (
    LiquidacionOSAnularInput,
    LiquidacionOSCreate,
    LiquidacionOSDebitosInput,
    LiquidacionOSDetalleRead,
    LiquidacionOSRead,
    ResultadoOSInput,
)
from app.domain.liquidacion_os import EstadoLiquidacionOS

TURNO_ID = uuid.uuid4()
OTRO_TURNO_ID = uuid.uuid4()


def _detalle_debito(
    monto: str = "15000.00", turno_id: uuid.UUID = TURNO_ID, **extra: object
) -> dict[str, object]:
    datos: dict[str, object] = {"turno_id": str(turno_id), "monto_reconocido": monto}
    datos.update(extra)
    return datos


def test_alta_rechaza_campos_extra_y_totales_del_cliente() -> None:
    """R1/R8: el body sólo trae OS y período; `total` o `tenant_id` no se aceptan."""
    with pytest.raises(ValidationError):
        LiquidacionOSCreate(obra_social="OSDE", periodo="202611", total="50000.00")

    with pytest.raises(ValidationError):
        LiquidacionOSCreate(obra_social="OSDE", periodo="202611", tenant_id=str(uuid.uuid4()))


def test_alta_normaliza_la_obra_social() -> None:
    """R1: `obra_social` se recorta y queda en el valor que se persiste."""
    datos = LiquidacionOSCreate(obra_social="  OSDE  ", periodo="202611")

    assert datos.obra_social == "OSDE"


@pytest.mark.parametrize("periodo", ["20261", "2026111", "abc", "2026-11", ""])
def test_alta_rechaza_periodos_invalidos(periodo: str) -> None:
    """D5: sólo `yyyymm` con mes 01..12 llega al caso de uso."""
    with pytest.raises(ValidationError):
        LiquidacionOSCreate(obra_social="OSDE", periodo=periodo)


@pytest.mark.parametrize("periodo", ["202600", "202613"])
def test_alta_rechaza_meses_fuera_de_rango(periodo: str) -> None:
    """D5: el mes `00` y el `13` no existen, aunque tengan 6 dígitos."""
    with pytest.raises(ValidationError):
        LiquidacionOSCreate(obra_social="OSDE", periodo=periodo)


def test_alta_rechaza_obra_social_vacia() -> None:
    """RN-OS-01: la liquidación siempre es de una obra social concreta."""
    with pytest.raises(ValidationError):
        LiquidacionOSCreate(obra_social="   ", periodo="202611")


def test_debitos_rechazan_monto_negativo_y_mas_de_dos_decimales() -> None:
    """R8: los montos reconocidos llegan por turno, no negativos y con centavos exactos."""
    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput(detalles=[_detalle_debito("-1.00")])

    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput(detalles=[_detalle_debito("15000.123")])


def test_debitos_rechazan_motivo_vacio_cuando_se_informa() -> None:
    """US-041: un `debito_motivo` en blanco es "sin motivo" y se rechaza."""
    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput(detalles=[_detalle_debito("15000.00", debito_motivo="   ")])


def test_debitos_aceptan_montos_y_observaciones() -> None:
    """Camino feliz: recorte con motivo y observación de cabecera."""
    datos = LiquidacionOSDebitosInput(
        observaciones="La OS devolvió dos turnos",
        detalles=[
            _detalle_debito("15000.00", debito_motivo="Arancel fuera de nomenclador"),
            _detalle_debito("20000.00", turno_id=OTRO_TURNO_ID),
        ],
    )

    assert len(datos.detalles) == 2
    assert datos.detalles[0].debito_motivo == "Arancel fuera de nomenclador"
    assert datos.detalles[1].monto_reconocido == Decimal("20000.00")


def test_debitos_rechazan_campos_extra() -> None:
    """R1: nada de `total` ni `monto_reclamado` en el input de débitos."""
    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput(detalles=[_detalle_debito(monto_reclamado="50000.00")])

    with pytest.raises(ValidationError):
        LiquidacionOSDebitosInput(detalles=[], total="10000.00")


def test_resultado_solo_acepta_pagada_o_con_debitos() -> None:
    """D4: el resultado de la OS no puede inventar estados."""
    with pytest.raises(ValidationError):
        ResultadoOSInput(resultado="anulada", detalles=[_detalle_debito("15000.00")])

    datos = ResultadoOSInput(resultado="pagada", detalles=[_detalle_debito("20000.00")])
    assert datos.resultado == "pagada"


def test_resultado_con_debitos_exige_al_menos_un_motivo() -> None:
    """US-041: `con_debitos` sin motivo de recorte no es un resultado válido."""
    with pytest.raises(ValidationError):
        ResultadoOSInput(resultado="con_debitos", detalles=[_detalle_debito("15000.00")])

    datos = ResultadoOSInput(
        resultado="con_debitos",
        detalles=[_detalle_debito("15000.00", debito_motivo="Débito por nomenclador")],
    )
    assert datos.detalles[0].debito_motivo == "Débito por nomenclador"


def test_los_debitos_rechazan_turnos_repetidos() -> None:
    """D10: el mismo `turno_id` dos veces sumaría el turno dos veces (422 en el borde)."""
    with pytest.raises(ValidationError) as error:
        LiquidacionOSDebitosInput(
            detalles=[
                _detalle_debito("15000.00", debito_motivo="Primer pase"),
                _detalle_debito("15000.00", debito_motivo="Segundo pase"),
            ]
        )

    assert "más de una vez" in str(error.value)


def test_el_resultado_rechaza_turnos_repetidos() -> None:
    """D10: el resultado informa cada turno exactamente una vez (BLOCKER 2)."""
    with pytest.raises(ValidationError) as error:
        ResultadoOSInput(
            resultado="pagada",
            detalles=[
                _detalle_debito("20000.00"),
                _detalle_debito("20000.00"),
            ],
        )

    assert "más de una vez" in str(error.value)
    assert str(TURNO_ID) in str(error.value)


def test_anulacion_exige_motivo_no_vacio() -> None:
    """R7: la baja lógica del borrador siempre deja el motivo escrito."""
    with pytest.raises(ValidationError):
        LiquidacionOSAnularInput(motivo="   ")

    with pytest.raises(ValidationError):
        LiquidacionOSAnularInput(motivo="x" * 501)

    assert LiquidacionOSAnularInput(motivo=" Se cargó el período equivocado ").motivo == (
        "Se cargó el período equivocado"
    )


def test_lectura_serializa_los_decimales_como_string() -> None:
    """R8: los montos salen como string para no perder centavos en JSON."""
    detalle = LiquidacionOSDetalleRead(
        id=uuid.uuid4(),
        turno_id=TURNO_ID,
        fecha_turno=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        prestacion="Consulta OS",
        monto_reclamado=Decimal("20000.00"),
        monto_reconocido=Decimal("15000.00"),
        debito_motivo="Arancel fuera de nomenclador",
        arancel_vencido=False,
        vigente=True,
    )
    cabecera = LiquidacionOSRead(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        obra_social="OSDE",
        periodo="202611",
        estado=EstadoLiquidacionOS.CON_DEBITOS,
        total=Decimal("20000.00"),
        total_reconocido=Decimal("15000.00"),
        observaciones=None,
        presentada_por=uuid.uuid4(),
        presentada_at=datetime(2026, 11, 30, 12, 0, tzinfo=UTC),
        resuelta_por=uuid.uuid4(),
        resuelta_at=datetime(2026, 12, 5, 12, 0, tzinfo=UTC),
        anulada_motivo=None,
        created_by=uuid.uuid4(),
        created_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        turnos_sin_cobertura=1,
        advertencias=["Un turno no tiene convenio con OSDE"],
        detalles=[detalle],
    )

    json = cabecera.model_dump(mode="json")

    assert json["total"] == "20000.00"
    assert json["total_reconocido"] == "15000.00"
    assert json["detalles"][0]["monto_reclamado"] == "20000.00"
    assert json["detalles"][0]["monto_reconocido"] == "15000.00"
    assert json["estado"] == "con_debitos"
    assert json["detalles"][0]["debito_motivo"] == "Arancel fuera de nomenclador"


def test_lectura_expone_el_saldo_debito() -> None:
    """D4/D10: el saldo pendiente es `total - total_reconocido` y se deriva solo."""
    detalle = LiquidacionOSDetalleRead(
        id=uuid.uuid4(),
        turno_id=TURNO_ID,
        fecha_turno=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        prestacion="Consulta OS",
        monto_reclamado=Decimal("20000.00"),
        monto_reconocido=Decimal("15000.00"),
        debito_motivo="Arancel fuera de nomenclador",
        arancel_vencido=False,
        vigente=True,
    )
    cabecera = LiquidacionOSRead(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        obra_social="OSDE",
        periodo="202611",
        estado=EstadoLiquidacionOS.CON_DEBITOS,
        total=Decimal("20000.00"),
        total_reconocido=Decimal("15000.00"),
        observaciones=None,
        presentada_por=uuid.uuid4(),
        presentada_at=datetime(2026, 11, 30, 12, 0, tzinfo=UTC),
        resuelta_por=uuid.uuid4(),
        resuelta_at=datetime(2026, 12, 5, 12, 0, tzinfo=UTC),
        anulada_motivo=None,
        created_by=uuid.uuid4(),
        created_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        turnos_sin_cobertura=0,
        advertencias=[],
        detalles=[detalle],
    )

    assert cabecera.saldo_debito == Decimal("5000.00")
    assert cabecera.model_dump(mode="json")["saldo_debito"] == "5000.00"


def test_lectura_sin_resultado_no_expone_saldo_debito() -> None:
    """Sin resultado de la OS no hay saldo que mostrar: `saldo_debito` es `None`."""
    cabecera = LiquidacionOSRead(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        obra_social="OSDE",
        periodo="202611",
        estado=EstadoLiquidacionOS.BORRADOR,
        total=Decimal("20000.00"),
        total_reconocido=None,
        observaciones=None,
        presentada_por=None,
        presentada_at=None,
        resuelta_por=None,
        resuelta_at=None,
        anulada_motivo=None,
        created_by=uuid.uuid4(),
        created_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 30, 10, 0, tzinfo=UTC),
        turnos_sin_cobertura=0,
        advertencias=[],
        detalles=[],
    )

    assert cabecera.saldo_debito is None
    assert cabecera.model_dump(mode="json")["saldo_debito"] is None
