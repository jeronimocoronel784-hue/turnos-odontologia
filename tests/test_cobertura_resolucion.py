"""Función pura de resolución de cobertura por arancel (C-13, tarea 1.1, D1/D2, RN-OS-01).

Cubre sin DB:
1. Convenio vigente: `cobertura = min(precio, arancel)` y `monto_a_cargo = precio - cobertura`.
2. Sin convenio (o convenio inactivo / de otra OS): modo particular.
3. Arancel vencido: usa el último arancel cargado y devuelve la advertencia (Flujo 5).
4. Cobertura futura: particular con advertencia, nunca "vencido".
5. `cantidad > 1` multiplica cobertura y monto a cargo.
6. Triangulación: convivencia vigente/vencido/futuro, OS case-insensitive y empate de aranceles.
"""

import uuid
from datetime import date
from decimal import Decimal

from app.domain.cobertura_os import (
    CoberturaOS,
    EstadoArancel,
    ResolucionCobertura,
    resolver_cobertura_desde_candidatas,
)

PRECIO = Decimal("50000.00")
FECHA = date(2026, 11, 15)


def _convenio(
    *,
    arancel: str,
    obra_social: str = "OSDE",
    vigencia_desde: date = date(2026, 1, 1),
    vigencia_hasta: date | None = None,
    activa: bool = True,
) -> CoberturaOS:
    """Convenio sin persistir: la función pura sólo lee atributos."""
    return CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        obra_social=obra_social,
        prestacion_id=uuid.uuid4(),
        arancel=Decimal(arancel),
        copago=Decimal("0.00"),
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        activa=activa,
    )


def _resolver(
    candidatas: list[CoberturaOS],
    *,
    obra_social: str = "OSDE",
    fecha: date = FECHA,
    cantidad: int = 1,
    precio: Decimal = PRECIO,
) -> ResolucionCobertura:
    return resolver_cobertura_desde_candidatas(
        precio_particular=precio,
        candidatas=candidatas,
        fecha_referencia=fecha,
        obra_social=obra_social,
        cantidad=cantidad,
    )


def test_convenio_vigente_aplica_el_arancel_y_calcula_el_monto_a_cargo() -> None:
    """RN-OS-01: arancel vigente de 30000 sobre un precio de 50000 deja 20000 a cargo."""
    convenio = _convenio(arancel="30000.00")

    resolucion = _resolver([convenio])

    assert resolucion.estado_arancel is EstadoArancel.VIGENTE
    assert resolucion.cobertura_id == convenio.id
    assert resolucion.arancel == Decimal("30000.00")
    assert resolucion.cobertura == Decimal("30000.00")
    assert resolucion.monto_a_cargo == Decimal("20000.00")
    assert resolucion.vigencia_desde == date(2026, 1, 1)
    assert resolucion.vigencia_hasta is None
    assert resolucion.advertencia is None


# ---------------------------------------------------------------------------
# Triangulación: modo particular
# ---------------------------------------------------------------------------


def test_sin_convenio_registrado_responde_modo_particular() -> None:
    """RN-OS-01: sin convenio de la OS, `cobertura = 0` y el precio completo a cargo."""
    resolucion = _resolver([])

    assert resolucion.estado_arancel is EstadoArancel.SIN_COBERTURA
    assert resolucion.cobertura_id is None
    assert resolucion.arancel is None
    assert resolucion.cobertura == Decimal("0.00")
    assert resolucion.monto_a_cargo == PRECIO
    assert resolucion.advertencia is None


def test_convenios_inactivos_o_de_otra_obra_social_no_aplican() -> None:
    """Borde RN-OS-01: sólo cuenta el convenio `activa` de la misma OS (sin distinguir caja)."""
    baja = _convenio(arancel="30000.00", activa=False)
    otra_os = _convenio(arancel="25000.00", obra_social="SWISS MEDICAL")

    resolucion = _resolver([baja, otra_os], obra_social="osde")

    assert resolucion.estado_arancel is EstadoArancel.SIN_COBERTURA
    assert resolucion.cobertura == Decimal("0.00")
    assert resolucion.monto_a_cargo == PRECIO


def test_sin_obra_social_informada_no_consulta_ningun_convenio() -> None:
    """R8: paciente particular explícito (`obra_social` vacía) nunca aplica cobertura."""
    resolucion = _resolver([_convenio(arancel="30000.00")], obra_social="   ")

    assert resolucion.estado_arancel is EstadoArancel.SIN_COBERTURA
    assert resolucion.monto_a_cargo == PRECIO
    assert resolucion.advertencia is None


# ---------------------------------------------------------------------------
# Triangulación: arancel vencido (D2, Flujo 5)
# ---------------------------------------------------------------------------


def test_arancel_vencido_usa_el_ultimo_cargado_y_advierte_el_vencimiento() -> None:
    """D2: con `vigencia_hasta` 31/10/2026 a la fecha 15/11/2026 usamos el arancel y avisamos."""
    convenio = _convenio(
        arancel="30000.00",
        vigencia_desde=date(2025, 6, 1),
        vigencia_hasta=date(2026, 10, 31),
    )

    resolucion = _resolver([convenio])

    assert resolucion.estado_arancel is EstadoArancel.VENCIDO
    assert resolucion.arancel_vencido is True
    assert resolucion.cobertura_id == convenio.id
    assert resolucion.cobertura == Decimal("30000.00")
    assert resolucion.monto_a_cargo == Decimal("20000.00")
    assert resolucion.vigencia_hasta == date(2026, 10, 31)
    assert resolucion.advertencia is not None
    assert "31/10/2026" in resolucion.advertencia
    assert "30000.00" in resolucion.advertencia


def test_arancel_vencido_elige_el_historial_mas_reciente() -> None:
    """D2: entre varios aranceles vencidos gana el de `vigencia_desde` más nuevo."""
    viejo = _convenio(
        arancel="10000.00",
        vigencia_desde=date(2024, 1, 1),
        vigencia_hasta=date(2025, 12, 31),
    )
    ultimo = _convenio(
        arancel="32000.00",
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 8, 31),
    )

    resolucion = _resolver([viejo, ultimo])

    assert resolucion.estado_arancel is EstadoArancel.VENCIDO
    assert resolucion.cobertura_id == ultimo.id
    assert resolucion.cobertura == Decimal("32000.00")
    assert "31/08/2026" in (resolucion.advertencia or "")


# ---------------------------------------------------------------------------
# Triangulación: cobertura futura
# ---------------------------------------------------------------------------


def test_cobertura_futura_se_factura_como_particular_con_advertencia() -> None:
    """D2: `vigencia_desde` posterior a la fecha no es "vencida": es particular con aviso."""
    futura = _convenio(arancel="30000.00", vigencia_desde=date(2027, 1, 1))

    resolucion = _resolver([futura])

    assert resolucion.estado_arancel is EstadoArancel.SIN_COBERTURA
    assert resolucion.cobertura_id is None
    assert resolucion.arancel is None
    assert resolucion.cobertura == Decimal("0.00")
    assert resolucion.monto_a_cargo == PRECIO
    assert resolucion.advertencia is not None
    assert "01/01/2027" in resolucion.advertencia


# ---------------------------------------------------------------------------
# Triangulación: cantidad y topes
# ---------------------------------------------------------------------------


def test_cantidad_mayor_a_uno_multiplica_cobertura_y_monto_a_cargo() -> None:
    """R8: `cantidad = 3` de un arancel de 30000 cubre 90000 y deja 60000 a cargo."""
    resolucion = _resolver([_convenio(arancel="30000.00")], cantidad=3)

    assert resolucion.precio_particular == PRECIO
    assert resolucion.cobertura == Decimal("90000.00")
    assert resolucion.monto_a_cargo == Decimal("60000.00")


def test_arancel_mayor_al_precio_nunca_genera_monto_a_cargo_negativo() -> None:
    """R8: el arancel no puede cubrir más que el precio particular (tope en cero)."""
    resolucion = _resolver([_convenio(arancel="80000.00")], cantidad=2)

    assert resolucion.cobertura == Decimal("100000.00")
    assert resolucion.monto_a_cargo == Decimal("0.00")


def test_vigente_gana_sobre_vencido_y_empate_se_rompe_por_vigencia_hasta() -> None:
    """D2: se prioriza el convenio vigente; con dos vigentes gana el de mayor vigencia."""
    vencido = _convenio(
        arancel="40000.00",
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 6, 30),
    )
    vigente_corto = _convenio(
        arancel="20000.00",
        vigencia_desde=date(2026, 7, 1),
        vigencia_hasta=date(2026, 12, 31),
    )
    vigente_abierto = _convenio(arancel="25000.00", vigencia_desde=date(2026, 7, 1))

    resolucion = _resolver([vencido, vigente_corto, vigente_abierto])

    assert resolucion.estado_arancel is EstadoArancel.VIGENTE
    assert resolucion.cobertura_id == vigente_abierto.id
    assert resolucion.cobertura == Decimal("25000.00")
    assert resolucion.advertencia is None
