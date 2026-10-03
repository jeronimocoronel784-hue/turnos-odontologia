"""Traducción de errores de integridad a mensajes rioplatenses (RN-GL-02).

La constraint vive en la DB (unicidad, checks); este helper mapea el motivo a un
AppError mostrable. La detección del motivo la hace la capa que atrapa
IntegrityError (C-03 en endpoints); acá solo el diccionario de mensajes.
"""

from app.shared.exceptions import AppError

_MENSAJES = {
    "email_duplicado": (
        "Che, ese correo ya está en uso en este consultorio. Probá con otro o recuperá el acceso."
    ),
    "slug_duplicado": ("Che, ese identificador de consultorio ya existe. Elegí otro slug."),
    "matricula_faltante": ("Che, la matrícula profesional es obligatoria para odontólogos."),
}


def error_integridad(motivo: str) -> AppError:
    """Devuelve un AppError 409 con mensaje rioplatense para el motivo dado."""
    return AppError(_MENSAJES.get(motivo, "Che, esos datos chocan con un registro existente."), 409)
