"""Guard de PHI en los textos libres (C-13, E.11/N4, R9).

`R9` prohíbe que datos personales (DNI, teléfono) entren en logs, errores o textos
libres. Los motivos de débito, las observaciones y el motivo de anulación son campos
de texto libre que el usuario escribe: sin un control, un DNI o un teléfono pueden
quedar persistidos (y después exportados) sin que nadie lo note.

El patrón es **conservador** a propósito: se busca algo que *parezca* un DNI o un
teléfono, no se intenta interpretar el texto. Un motivo legítimo del negocio
("Arancel fuera de nomenclador") nunca tiene 7 u 8 dígitos seguidos ni 10 dígitos
consecutivos, así que no se ve afectado.
"""

import re

from app.shared.exceptions import EntidadInvalida

# DNI: 7 u 8 dígitos, con o sin un guion en el medio ("1234567", "12345678", "12-34567").
PATRON_DNI = re.compile(r"(?<!\d)(?:\d{7,8}|\d{4}-\d{4}|\d{3}-\d{4})(?!\d)")

# Teléfono: prefijo `+` con 10 a 13 dígitos, o 10 o más dígitos consecutivos.
PATRON_TELEFONO = re.compile(r"(?<![0-9A-Za-z])(?:\+\d{10,13}|\d{10,})(?![0-9A-Za-z])")

MENSAJE_PHI = "Che, {campo} no puede incluir datos personales como DNI o teléfono."


def parece_phi(texto: str) -> bool:
    """True si el texto parece contener un DNI o un teléfono (R9)."""
    return bool(PATRON_DNI.search(texto) or PATRON_TELEFONO.search(texto))


def exigir_texto_sin_phi(texto: str | None, *, campo: str) -> None:
    """Rechaza con 422 un texto libre que parece contener un DNI o un teléfono (R9).

    El mensaje de error **no** repite el dato detectado: sólo dice qué campo falló.
    """
    if texto is None:
        return
    if parece_phi(texto):
        raise EntidadInvalida(MENSAJE_PHI.format(campo=campo))
