"""Helper compartido de montos (C-13, E.10/N2): una sola fuente de verdad para los `Decimal`.

Verifica:
1. `monto_2dp` normaliza cualquier monto a `Decimal` con 2 decimales (R8: nunca `float`).
2. Los módulos que antes duplicaban el helper (liquidaciones, cobertura y caja) usan el
   compartido: no queda un `_monto` propio en cada uno.
"""

from decimal import Decimal

from app.application import caja, liquidaciones
from app.domain import cobertura_os
from app.shared.montos import CENTAVOS, CERO, monto_2dp


def test_monto_2dp_normaliza_a_decimal_con_dos_decimales() -> None:
    """R8: el monto siempre sale como `Decimal` con 2 decimales, venga de donde venga."""
    assert monto_2dp(1500) == Decimal("1500.00")
    assert monto_2dp("1500.5") == Decimal("1500.50")
    assert monto_2dp(Decimal("1500.554")) == Decimal("1500.55")
    assert monto_2dp(Decimal("1500.00")) == Decimal("1500.00")
    assert isinstance(monto_2dp(1500), Decimal)


def test_los_constantes_compartidos_son_los_de_la_aplicacion() -> None:
    """`CERO` y `CENTAVOS` son los mismos números que usaba cada módulo."""
    assert CERO == Decimal("0.00")
    assert CENTAVOS == Decimal("0.01")


def test_los_modulos_usan_el_helper_compartido_sin_duplicarlo() -> None:
    """N2: liquidaciones, cobertura y caja importan el helper, no redefinen el suyo."""
    assert liquidaciones.monto_2dp is monto_2dp
    assert cobertura_os.monto_2dp is monto_2dp
    assert caja.monto_2dp is monto_2dp

    for modulo in (liquidaciones, cobertura_os, caja):
        assert not hasattr(modulo, "_monto"), (
            f"{modulo.__name__} no debe volver a definir su propio `_monto`"
        )
