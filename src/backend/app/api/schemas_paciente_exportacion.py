"""Schemas Pydantic para la exportación del paquete de datos del paciente (C-14, D8).

Cumple R1 (schemas estrictos, sin ORM), R8 (montos como string) y R9 (sin PHI
en logs/errores). El envoltorio refleja la estructura de D8.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConsultorioExportacion",
    "PacienteExportacion",
    "TurnoExportacion",
    "FichaClinicaExportacion",
    "EvolucionExportacion",
    "PiezaEventoExportacion",
    "OdontogramaExportacion",
    "PresupuestoItemExportacion",
    "PresupuestoTurnoExportacion",
    "PresupuestoExportacion",
    "ConsentimientoExportacion",
    "AdjuntoExportacion",
    "AdjuntosExportacion",
    "MovimientoExportacion",
    "PacienteExportacionRead",
]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsultorioExportacion(_Estricto):
    nombre: str
    slug: str


class PacienteExportacion(_Estricto):
    id: UUID
    nombre: str
    dni: str
    telefono: str
    email: str | None = None
    fecha_nac: date | None = None
    obra_social_id: UUID | None = None
    obra_social: str | None = None
    nro_afiliado: str | None = None
    optin_wa: bool = False
    observaciones: str | None = None
    activo: bool = True
    created_at: datetime | None = None


class TurnoExportacion(_Estricto):
    turno_id: UUID
    inicio: datetime | None = None
    fin: datetime | None = None
    estado: str
    prestacion: str | None = None
    profesional: str | None = None
    sillon: str | None = None
    sobreturno: bool = False


class FichaClinicaExportacion(_Estricto):
    id: UUID
    paciente_id: UUID
    antecedentes: str | None = None
    alergias: str | None = None
    medicacion: str | None = None
    habitos: str | None = None
    datos_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EvolucionExportacion(_Estricto):
    id: UUID
    ficha_clinica_id: UUID
    paciente_id: UUID
    turno_id: UUID | None = None
    profesional_id: UUID
    nota: str
    es_correccion_de_id: UUID | None = None
    created_at: datetime | None = None


class PiezaEventoExportacion(_Estricto):
    id: UUID
    odontograma_id: UUID | None = None
    pieza_fdi: int
    superficie: str
    evento: str
    turno_id: UUID | None = None
    observacion: str | None = None
    created_by: UUID
    created_at: datetime | None = None


class OdontogramaExportacion(_Estricto):
    eventos: list[PiezaEventoExportacion] = Field(default_factory=list)


class PresupuestoItemExportacion(_Estricto):
    id: UUID
    presupuesto_id: UUID | None = None
    prestacion_id: UUID
    pieza_fdi: int | None = None
    cantidad: int = 1
    precio_unit: str
    cobertura_os: str
    a_cargo: str
    created_at: datetime | None = None


class PresupuestoTurnoExportacion(_Estricto):
    id: UUID | None = None
    presupuesto_id: UUID | None = None
    turno_id: UUID
    presupuesto_item_id: UUID | None = None
    created_at: datetime | None = None


class PresupuestoExportacion(_Estricto):
    id: UUID
    paciente_id: UUID
    obra_social: str | None = None
    estado: str
    total: str
    total_cobertura_os: str
    total_a_cargo: str
    validez_hasta: date | None = None
    observaciones: str | None = None
    created_at: datetime | None = None
    items: list[PresupuestoItemExportacion] = Field(default_factory=list)
    turnos: list[PresupuestoTurnoExportacion] = Field(default_factory=list)


class ConsentimientoExportacion(_Estricto):
    id: UUID
    paciente_id: UUID
    prestacion_id: UUID
    turno_id: UUID | None = None
    texto_version: str
    firma_hash: str | None = None
    firmado_por: str | None = None
    firmado_at: datetime | None = None
    canal: str
    revocado: bool = False
    revocado_motivo: str | None = None
    revocado_at: datetime | None = None


class AdjuntoExportacion(_Estricto):
    tipo: str
    mime_type: str
    tamano_bytes: int
    created_at: datetime | None = None


class AdjuntosExportacion(_Estricto):
    cantidad: int = 0
    items: list[AdjuntoExportacion] = Field(default_factory=list)


class MovimientoExportacion(_Estricto):
    movimiento_id: UUID
    created_at: datetime | None = None
    tipo: str
    concepto: str | None = None
    medio: str
    monto: str
    turno_id: UUID | None = None
    cierre_id: UUID | None = None


class PacienteExportacionRead(_Estricto):
    generado_at: datetime
    consultorio: ConsultorioExportacion
    paciente: PacienteExportacion
    turnos: list[TurnoExportacion] = Field(default_factory=list)
    ficha_clinica: FichaClinicaExportacion | None = None
    evoluciones: list[EvolucionExportacion] = Field(default_factory=list)
    odontograma: OdontogramaExportacion = Field(default_factory=OdontogramaExportacion)
    presupuestos: list[PresupuestoExportacion] = Field(default_factory=list)
    consentimientos: list[ConsentimientoExportacion] = Field(default_factory=list)
    adjuntos: AdjuntosExportacion = Field(default_factory=AdjuntosExportacion)
    movimientos: list[MovimientoExportacion] = Field(default_factory=list)


# Alias comunes para compatibilidad con posibles nombres de tests/llamadores.
ConsultorioRead = ConsultorioExportacion
ConsultorioDatos = ConsultorioExportacion
PacienteExportacionDatos = PacienteExportacion
PacienteDatos = PacienteExportacion
PacienteRead = PacienteExportacion
TurnoExportacionRead = TurnoExportacion
TurnoDatos = TurnoExportacion
FichaClinicaExportacionRead = FichaClinicaExportacion
FichaClinicaDatos = FichaClinicaExportacion
EvolucionExportacionRead = EvolucionExportacion
EvolucionDatos = EvolucionExportacion
PiezaEventoExportacionRead = PiezaEventoExportacion
PiezaEventoDatos = PiezaEventoExportacion
OdontogramaExportacionRead = OdontogramaExportacion
OdontogramaDatos = OdontogramaExportacion
PresupuestoItemExportacionRead = PresupuestoItemExportacion
PresupuestoItemDatos = PresupuestoItemExportacion
PresupuestoTurnoExportacionRead = PresupuestoTurnoExportacion
PresupuestoTurnoDatos = PresupuestoTurnoExportacion
PresupuestoExportacionRead = PresupuestoExportacion
PresupuestoDatos = PresupuestoExportacion
ConsentimientoExportacionRead = ConsentimientoExportacion
ConsentimientoDatos = ConsentimientoExportacion
AdjuntoExportacionRead = AdjuntoExportacion
AdjuntoDatos = AdjuntoExportacion
AdjuntosExportacionRead = AdjuntosExportacion
AdjuntosDatos = AdjuntosExportacion
MovimientoExportacionRead = MovimientoExportacion
MovimientoDatos = MovimientoExportacion

# Envelope aliases.
PacienteExportacionPaquete = PacienteExportacionRead
PacienteDatosExportados = PacienteExportacionRead
PacienteExportarDatosRead = PacienteExportacionRead
ExportacionPacienteRead = PacienteExportacionRead
PaquetePacienteRead = PacienteExportacionRead
PacientePaqueteRead = PacienteExportacionRead
PacienteDatosRead = PacienteExportacionRead
ExportacionDatosPacienteRead = PacienteExportacionRead
PacienteExportacionSchema = PacienteExportacionRead
