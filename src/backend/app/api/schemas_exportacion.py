"""Schemas Pydantic para la exportación de datasets del consultorio (C-14, D4/D6).

Cumple R1 (schemas estrictos, sin ORM) y R9 (sin PHI en logs/errores).
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetExportable(enum.StrEnum):
    """Datasets exportables del consultorio (D4)."""

    AGENDA = "agenda"
    PACIENTES = "pacientes"
    CAJA = "caja"
    LIQUIDACIONES = "liquidaciones"


class FormatoExportacion(enum.StrEnum):
    """Formatos de salida soportados (D4)."""

    CSV = "csv"
    JSON = "json"


class ExportacionJobRead(_Estricto):
    """Estado de un job de exportación asíncrona (D6)."""

    job_id: str
    estado: str = Field(default="pendiente")
    dataset: str | None = None
    formato: str | None = None
    filas: int | None = None
    creado_at: datetime | None = None
    expira_at: datetime | None = None
    nombre_archivo: str | None = None
    error: str | None = None


class ExportacionDatasetRead(BaseModel):
    """Representación auxiliar de un dataset exportado (documentación)."""

    model_config = ConfigDict(extra="forbid")

    dataset: str
    formato: str
    filas: int = 0
    nombre_archivo: str | None = None


__all__ = [
    "DatasetExportable",
    "FormatoExportacion",
    "ExportacionJobRead",
    "ExportacionDatasetRead",
]
