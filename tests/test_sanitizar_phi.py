"""Enmascarado de identificadores en textos libres (C-14, D12, R9).

Verifica que `sanitizar_phi` reemplace DNI, CUIT/CUIL y teléfonos por
`[dato oculto]` y deje intactos los textos legítimos del negocio, sin falsos
positivos sobre montos con coma decimal.
"""

from app.shared.sanitizar_phi import DATO_OCULTO, sanitizar_phi


def test_dni_7_digitos_se_oculta() -> None:
    assert sanitizar_phi("DNI 1234567") == f"DNI {DATO_OCULTO}"


def test_dni_8_digitos_se_oculta() -> None:
    assert sanitizar_phi("DNI 12345678") == f"DNI {DATO_OCULTO}"


def test_dni_con_puntos_se_oculta() -> None:
    assert sanitizar_phi("DNI 30.123.456") == f"DNI {DATO_OCULTO}"
    assert sanitizar_phi("DNI 3.012.345") == f"DNI {DATO_OCULTO}"
    assert sanitizar_phi("DNI 12.345.678") == f"DNI {DATO_OCULTO}"


def test_cuit_11_digitos_se_oculta() -> None:
    assert sanitizar_phi("CUIT 20301234567") == f"CUIT {DATO_OCULTO}"


def test_cuit_con_guiones_se_oculta() -> None:
    assert sanitizar_phi("CUIT 20-30123456-7") == f"CUIT {DATO_OCULTO}"


def test_cuil_con_guiones_se_oculta() -> None:
    assert sanitizar_phi("CUIL 27-12345678-9") == f"CUIL {DATO_OCULTO}"


def test_telefono_con_mas_espacios_guiones_se_oculta() -> None:
    assert sanitizar_phi("Tel +54 11 5555-1234") == f"Tel {DATO_OCULTO}"


def test_telefono_plano_se_oculta() -> None:
    assert sanitizar_phi("Tel 1155551234") == f"Tel {DATO_OCULTO}"


def test_telefono_13_digitos_se_oculta() -> None:
    assert sanitizar_phi("Contacto +5491112345678") == f"Contacto {DATO_OCULTO}"


def test_texto_legitimo_queda_intacto() -> None:
    assert sanitizar_phi("Arancel fuera de nomenclador") == "Arancel fuera de nomenclador"
    assert sanitizar_phi("Seña turno") == "Seña turno"
    assert sanitizar_phi("OS 210") == "OS 210"


def test_montos_con_coma_decimal_no_se_ocultan() -> None:
    assert sanitizar_phi("Monto 1.234,56") == "Monto 1.234,56"
    assert sanitizar_phi("Total 12.345,67") == "Total 12.345,67"
    assert sanitizar_phi("Importe 1234,50") == "Importe 1234,50"


def test_concepto_caja_se_enmascara() -> None:
    assert sanitizar_phi("Seña DNI 30.123.456") == f"Seña DNI {DATO_OCULTO}"


def test_observaciones_liquidacion_se_enmascaran() -> None:
    assert sanitizar_phi("CUIT 20-30123456-7 del afiliado") == f"CUIT {DATO_OCULTO} del afiliado"


def test_telefono_en_detalle_se_oculta() -> None:
    assert sanitizar_phi("Llamá al +54 11 5555-1234") == f"Llamá al {DATO_OCULTO}"


def test_texto_vacio() -> None:
    assert sanitizar_phi("") == ""


def test_none_devuelve_none() -> None:
    assert sanitizar_phi(None) is None
