"""Enmascarado de identificadores en textos libres (C-14, D12, R9).

Los datasets `caja` y `liquidaciones` exportan columnas de texto libre
(`concepto`, `observaciones`, `detalle`) que pueden contener DNI, CUIT/CUIL o
teléfonos de filas anteriores a la guarda de escritura de C-13 o que llegan
desde el request. Este módulo ofrece una función pura que reemplaza esos
identificadores por ``DATO_OCULTO`` sin alterar el resto del texto.

Reutiliza los patrones de ``app.domain.textos_libres`` (C-13) y los extiende
para cubrir DNI con puntos, CUIT/CUIL con guiones y teléfonos con separadores.
"""

from __future__ import annotations

import re

from app.domain.textos_libres import PATRON_DNI, PATRON_TELEFONO

DATO_OCULTO = "[dato oculto]"

# Alias de la constante bajo nombres alternativos (compatibilidad de callers).
DatoOculto = DATO_OCULTO
OCULTO = DATO_OCULTO
TEXTO_OCULTO = DATO_OCULTO
MARCA_PHI = DATO_OCULTO
REEMPLAZO = DATO_OCULTO
REEMPLAZO_PHI = DATO_OCULTO
PHI_OCULTO = DATO_OCULTO

# DNI con puntos: 1-2 dígitos, punto, 3 dígitos, punto, 3 dígitos.
# El lookahead evita tomar parte de un monto con separadores de miles
# seguido de coma decimal (ej. "1.234.567,89").
_DNI_PUNTOS = re.compile(r"(?<![\d.])(\d{1,2}\.\d{3}\.\d{3})(?![\d.])(?!,\d)")

# CUIT/CUIL con guiones: XX-XXXXXXXX-X (11 dígitos en total).
_CUIT_GUIONES = re.compile(r"(?<![\d-])(\d{2}-\d{8}-\d)(?![\d-])")

# Teléfono con separadores (+, espacios, guiones): 10 a 13 dígitos en total.
# El candidato termina siempre en dígito para no consumir espacios finales.
_TELEFONO_SEPARADORES = re.compile(r"(?<![\w.])(\+?[\d](?:[\d\s-]*\d){9,12})(?![\d])")


def _contar_digitos(valor: str) -> int:
    return sum(1 for c in valor if c.isdigit())


def _reemplazar_telefono_separadores(texto: str) -> str:
    def _reemplazo(match: re.Match[str]) -> str:
        candidato = match.group(1)
        if 10 <= _contar_digitos(candidato) <= 13:
            return DATO_OCULTO
        return candidato

    return _TELEFONO_SEPARADORES.sub(_reemplazo, texto)


def sanitizar_phi(texto: str | None) -> str | None:
    """Devuelve ``texto`` con los identificadores detectados reemplazados.

    Es una función pura: no modifica el argumento y no tiene efectos laterales.
    Acepta ``None`` y devuelve ``None``.
    """
    if texto is None:
        return None
    if not isinstance(texto, str):
        texto = str(texto)

    resultado = texto
    # Orden: primero los formatos más específicos (CUIT, DNI con puntos),
    # luego teléfonos con separadores, y por último los patrones base de
    # textos_libres (dígitos corridos).
    resultado = _CUIT_GUIONES.sub(DATO_OCULTO, resultado)
    resultado = _DNI_PUNTOS.sub(DATO_OCULTO, resultado)
    resultado = _reemplazar_telefono_separadores(resultado)
    resultado = PATRON_TELEFONO.sub(DATO_OCULTO, resultado)
    resultado = PATRON_DNI.sub(DATO_OCULTO, resultado)
    return resultado


# Aliases de la función bajo nombres alternativos.
sanitizar = sanitizar_phi
enmascarar = sanitizar_phi
enmascarar_phi = sanitizar_phi
sanitizar_texto = sanitizar_phi
enmascarar_texto = sanitizar_phi
ocultar_phi = sanitizar_phi
mask_phi = sanitizar_phi
sanitizar_phi_texto = sanitizar_phi
enmascarar_identificadores = sanitizar_phi


__all__ = [
    "DATO_OCULTO",
    "DatoOculto",
    "OCULTO",
    "TEXTO_OCULTO",
    "MARCA_PHI",
    "REEMPLAZO",
    "REEMPLAZO_PHI",
    "PHI_OCULTO",
    "sanitizar_phi",
    "sanitizar",
    "enmascarar",
    "enmascarar_phi",
    "sanitizar_texto",
    "enmascarar_texto",
    "ocultar_phi",
    "mask_phi",
    "sanitizar_phi_texto",
    "enmascarar_identificadores",
]
