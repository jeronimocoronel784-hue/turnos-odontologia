"""Dominio de liquidaciones de obra social: estados y períodos (C-13, tarea 2.1, D4/D5).

Cubre sin DB:
1. Grafo de estados de la liquidación (`D4`): permitidas y rechazadas, incluidos terminales.
2. Helpers de período `yyyymm`: derivación desde fecha, rango UTC semiabierto y rechazos.
"""

from datetime import UTC, date, datetime

import pytest

from app.domain.liquidacion_os import (
    EstadoLiquidacionOS,
    es_transicion_liquidacion_valida,
    periodo_desde_fecha,
    periodo_valido,
    rango_periodo,
)
from app.shared.exceptions import EntidadInvalida


def test_grafo_de_estados_permite_el_ciclo_de_la_liquidacion() -> None:
    """D4: borrador -> presentada|anulada; presentada -> pagada|con_debitos.

    `con_debitos` sólo puede pasar a `pagada`.
    """
    assert es_transicion_liquidacion_valida(
        EstadoLiquidacionOS.BORRADOR, EstadoLiquidacionOS.PRESENTADA
    )
    assert es_transicion_liquidacion_valida(
        EstadoLiquidacionOS.BORRADOR, EstadoLiquidacionOS.ANULADA
    )
    assert es_transicion_liquidacion_valida(
        EstadoLiquidacionOS.PRESENTADA, EstadoLiquidacionOS.PAGADA
    )
    assert es_transicion_liquidacion_valida(
        EstadoLiquidacionOS.PRESENTADA, EstadoLiquidacionOS.CON_DEBITOS
    )
    assert es_transicion_liquidacion_valida(
        EstadoLiquidacionOS.CON_DEBITOS, EstadoLiquidacionOS.PAGADA
    )


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        (EstadoLiquidacionOS.BORRADOR, EstadoLiquidacionOS.PAGADA),
        (EstadoLiquidacionOS.BORRADOR, EstadoLiquidacionOS.CON_DEBITOS),
        (EstadoLiquidacionOS.PRESENTADA, EstadoLiquidacionOS.ANULADA),
        (EstadoLiquidacionOS.PRESENTADA, EstadoLiquidacionOS.BORRADOR),
        (EstadoLiquidacionOS.CON_DEBITOS, EstadoLiquidacionOS.ANULADA),
        (EstadoLiquidacionOS.CON_DEBITOS, EstadoLiquidacionOS.PRESENTADA),
    ],
)
def test_transiciones_invalidas_se_rechazan(
    actual: EstadoLiquidacionOS, nuevo: EstadoLiquidacionOS
) -> None:
    """D4: no se saltean estados ni se anula una liquidación ya presentada."""
    assert es_transicion_liquidacion_valida(actual, nuevo) is False


def test_pagada_y_anulada_son_terminales() -> None:
    """D4: `pagada` y `anulada` cierran el ciclo; ninguna transición sale de ellas."""
    for terminal in (EstadoLiquidacionOS.PAGADA, EstadoLiquidacionOS.ANULADA):
        for destino in EstadoLiquidacionOS:
            assert es_transicion_liquidacion_valida(terminal, destino) is False


def test_grafo_acepta_los_valores_persistidos_y_rechaza_desconocidos() -> None:
    """El grafo sirve igual con los strings de la columna `estado`."""
    assert es_transicion_liquidacion_valida("borrador", "presentada") is True
    assert es_transicion_liquidacion_valida("borrador", "inventada") is False
    assert es_transicion_liquidacion_valida("inventada", "presentada") is False


def test_periodo_desde_fecha_usa_el_mes_calendario() -> None:
    """D5: el período de un turno es el mes calendario UTC de su inicio."""
    assert periodo_desde_fecha(date(2026, 11, 30)) == "202611"
    assert periodo_desde_fecha(date(2026, 1, 1)) == "202601"
    assert periodo_desde_fecha(date(2027, 12, 31)) == "202712"


def test_rango_periodo_es_semiabierto_en_utc() -> None:
    """D5: `202611` abarca del 01/11 inclusive al 01/12 exclusivo."""
    desde, hasta = rango_periodo("202611")

    assert desde == datetime(2026, 11, 1, tzinfo=UTC)
    assert hasta == datetime(2026, 12, 1, tzinfo=UTC)
    assert desde < hasta


def test_rango_periodo_de_diciembre_rueda_al_ano_siguiente() -> None:
    """Borde: el último período del año cierra el 1 de enero siguiente."""
    desde, hasta = rango_periodo("202612")

    assert desde == datetime(2026, 12, 1, tzinfo=UTC)
    assert hasta == datetime(2027, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("periodo", ["20261", "2026111", "202613", "202600", "abc", ""])
def test_periodo_invalido_se_rechaza(periodo: str) -> None:
    """D5: sólo `yyyymm` con mes 01..12; el resto no es un período liquidable."""
    assert periodo_valido(periodo) is False
    with pytest.raises(EntidadInvalida):
        rango_periodo(periodo)


def test_periodo_valido_acepta_los_doce_meses() -> None:
    """Borde: los 12 meses del año son períodos válidos."""
    for mes in range(1, 13):
        assert periodo_valido(f"2026{mes:02d}") is True
