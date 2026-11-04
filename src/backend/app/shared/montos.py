"""Helpers compartidos de montos (C-13, N2).

La normalización de un monto a `Decimal` con 2 decimales estaba duplicada en
`application/liquidaciones.py`, `domain/cobertura_os.py` y `application/caja.py`.
Una sola fuente de verdad evita que presupuesto, cobro y liquidación diverjan en el
redondeo (R8: los montos son `Decimal`, nunca `float`).
"""

from decimal import Decimal

CERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")


def monto_2dp(valor: object) -> Decimal:
    """Normaliza cualquier monto a `Decimal` con 2 decimales (R8: nunca float)."""
    return Decimal(str(valor)).quantize(CENTAVOS)
