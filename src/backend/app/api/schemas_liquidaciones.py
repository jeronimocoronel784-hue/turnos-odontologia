"""Schemas Pydantic v2 de cobertura y liquidaciones de obras sociales (C-13).

Cumple:
- R1: `extra='forbid'` en todos los inputs y modelos de lectura explícitos (nunca el ORM).
- R8: ningún input acepta totales ni montos calculados en servidor; todo `Decimal` viaja como
  string en la respuesta.
- R9: la cobertura y la liquidación no exponen datos personales del paciente.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.domain.cobertura_os import EstadoArancel
from app.domain.liquidacion_os import EstadoLiquidacionOS, periodo_valido

PATRON_PERIODO = r"^\d{6}$"
MENSAJE_PERIODO = "El período tiene que tener el formato 'yyyymm' (por ejemplo 202611)."
MENSAJE_TURNOS_REPETIDOS = "No podés informar el mismo turno más de una vez."


def _texto_limpio(valor: str | None) -> str | None:
    """Normaliza un texto opcional: recorta y convierte el vacío en `None`."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


def _exigir_turnos_unicos(detalles: list["LiquidacionOSDetalleDebitoInput"]) -> None:
    """D10: un `turno_id` repetido haría que el total sume dos veces el mismo turno.

    Se rechaza en el borde (422) para que ni el cliente ni el servidor puedan duplicar
    el reclamo de un turno (R8: los totales salen del detalle persistido).
    """
    vistos: set[uuid.UUID] = set()
    repetidos: list[uuid.UUID] = []
    for detalle in detalles:
        if detalle.turno_id in vistos:
            if detalle.turno_id not in repetidos:
                repetidos.append(detalle.turno_id)
        else:
            vistos.add(detalle.turno_id)
    if repetidos:
        raise ValueError(
            f"{MENSAJE_TURNOS_REPETIDOS} Se repiten: "
            + ", ".join(str(turno_id) for turno_id in repetidos)
            + "."
        )


def _periodo_validado(valor: str) -> str:
    """Valida longitud, dígitos y mes 01..12 del período (D5)."""
    limpio = valor.strip()
    if not limpio.isdigit() or len(limpio) != 6 or not periodo_valido(limpio):
        raise ValueError(MENSAJE_PERIODO)
    return limpio


class CoberturaLookupRead(BaseModel):
    """Cobertura resuelta en servidor para una prestación + obra social + fecha (US-040)."""

    model_config = ConfigDict(extra="forbid")

    prestacion_id: uuid.UUID
    obra_social: str | None = None
    cobertura_id: uuid.UUID | None = None
    precio_particular: Decimal
    cobertura: Decimal
    monto_a_cargo: Decimal
    estado_arancel: EstadoArancel
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    arancel_vencido: bool
    advertencia: str | None = None


# ---------------------------------------------------------------------------
# Liquidaciones: inputs
# ---------------------------------------------------------------------------


class LiquidacionOSCreate(BaseModel):
    """Alta del borrador: sólo OS y período; los turnos y totales los resuelve el servidor."""

    model_config = ConfigDict(extra="forbid")

    obra_social: str = Field(min_length=1, max_length=160)
    periodo: str = Field(pattern=PATRON_PERIODO)

    @field_validator("obra_social")
    @classmethod
    def _exigir_obra_social(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("La liquidación tiene que indicar la obra social.")
        return limpio

    @field_validator("periodo")
    @classmethod
    def _validar_periodo(cls, v: str) -> str:
        return _periodo_validado(v)


class LiquidacionOSDetalleDebitoInput(BaseModel):
    """Débito de la OS sobre un turno: `monto_reconocido` y motivo del recorte (US-041)."""

    model_config = ConfigDict(extra="forbid")

    turno_id: uuid.UUID
    monto_reconocido: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    debito_motivo: str | None = Field(default=None, max_length=500)

    @field_validator("debito_motivo")
    @classmethod
    def _limpiar_motivo(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("El motivo del débito no puede quedar vacío.")
        return _texto_limpio(v)


class LiquidacionOSDebitosInput(BaseModel):
    """Edición de débitos del borrador: los totales se recalculan en servidor (R8)."""

    model_config = ConfigDict(extra="forbid")

    observaciones: str | None = Field(default=None, max_length=2000)
    detalles: list[LiquidacionOSDetalleDebitoInput] = Field(min_length=1)

    @field_validator("observaciones")
    @classmethod
    def _limpiar_observaciones(cls, v: str | None) -> str | None:
        return _texto_limpio(v)

    @model_validator(mode="after")
    def _rechazar_turnos_repetidos(self) -> "LiquidacionOSDebitosInput":
        """D10: el mismo turno no se debita dos veces (el total se recalcula en servidor)."""
        _exigir_turnos_unicos(self.detalles)
        return self


class ResultadoOSInput(BaseModel):
    """Resultado informado por la OS: `pagada` (total) o `con_debitos` (con recortes)."""

    model_config = ConfigDict(extra="forbid")

    resultado: Literal["pagada", "con_debitos"]
    observaciones: str | None = Field(default=None, max_length=2000)
    detalles: list[LiquidacionOSDetalleDebitoInput] = Field(min_length=1)

    @field_validator("observaciones")
    @classmethod
    def _limpiar_observaciones(cls, v: str | None) -> str | None:
        return _texto_limpio(v)

    @model_validator(mode="after")
    def _exigir_motivo_en_recortes(self) -> "ResultadoOSInput":
        """`con_debitos` sin ningún motivo de recorte no es un resultado válido (US-041)."""
        if self.resultado == "con_debitos" and not any(d.debito_motivo for d in self.detalles):
            raise ValueError("Un resultado con débitos necesita al menos un motivo de recorte.")
        return self

    @model_validator(mode="after")
    def _rechazar_turnos_repetidos(self) -> "ResultadoOSInput":
        """D10: el resultado informa cada turno exactamente una vez (R8)."""
        _exigir_turnos_unicos(self.detalles)
        return self


class LiquidacionOSAnularInput(BaseModel):
    """Anulación de un borrador: baja lógica con motivo obligatorio (R7)."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def _exigir_motivo(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("La anulación exige un motivo.")
        return limpio


class LiquidacionOSCerrarInput(BaseModel):
    """Presentación del borrador a la obra social (D4)."""

    model_config = ConfigDict(extra="forbid")

    observaciones: str | None = Field(default=None, max_length=2000)

    @field_validator("observaciones")
    @classmethod
    def _limpiar_observaciones(cls, v: str | None) -> str | None:
        return _texto_limpio(v)


# ---------------------------------------------------------------------------
# Liquidaciones: lecturas
# ---------------------------------------------------------------------------


class LiquidacionOSDetalleRead(BaseModel):
    """Una fila por turno liquidado, sin datos personales del paciente (R9)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    turno_id: uuid.UUID
    fecha_turno: datetime
    prestacion: str
    monto_reclamado: Decimal
    monto_reconocido: Decimal | None = None
    debito_motivo: str | None = None
    arancel_vencido: bool
    vigente: bool


class LiquidacionOSRead(BaseModel):
    """Cabecera de la liquidación con sus totales calculados y su detalle por turno."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    obra_social: str
    periodo: str
    estado: EstadoLiquidacionOS
    total: Decimal
    total_reconocido: Decimal | None = None
    observaciones: str | None = None
    presentada_por: uuid.UUID | None = None
    presentada_at: datetime | None = None
    resuelta_por: uuid.UUID | None = None
    resuelta_at: datetime | None = None
    anulada_motivo: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    turnos_sin_cobertura: int = 0
    advertencias: list[str] = Field(default_factory=list)
    detalles: list[LiquidacionOSDetalleRead] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def saldo_debito(self) -> Decimal | None:
        """Saldo pendiente = total reclamado - total reconocido (D4/D10).

        Es `None` mientras la obra social no informó el resultado: sin saldo reconocido
        no hay deuda que mostrar.
        """
        if self.total_reconocido is None:
            return None
        return self.total - self.total_reconocido


class LiquidacionOSExportacionRead(BaseModel):
    """Borrador de exportación JSON: cabecera + detalle tal como se entrega a la OS (D7)."""

    model_config = ConfigDict(extra="forbid")

    obra_social: str
    periodo: str
    estado: EstadoLiquidacionOS
    total: Decimal
    total_reconocido: Decimal | None = None
    detalles: list[LiquidacionOSDetalleRead] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def saldo_debito(self) -> Decimal | None:
        """Saldo pendiente = total reclamado - total reconocido (D4/D10)."""
        if self.total_reconocido is None:
            return None
        return self.total - self.total_reconocido
