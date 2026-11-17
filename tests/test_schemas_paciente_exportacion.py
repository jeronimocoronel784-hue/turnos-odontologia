"""Schemas del paquete de datos del paciente (C-14, D8, tarea 6.2)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas_paciente_exportacion import (
    AdjuntoExportacion,
    ConsentimientoExportacion,
    OdontogramaExportacion,
    PacienteExportacionRead,
)


def test_envoltorio_expone_las_secciones_de_d8() -> None:
    ahora = datetime.now(UTC)
    consultorio = {"nombre": "Consultorio Test", "slug": "consultorio-test"}
    paciente = {
        "id": uuid.uuid4(),
        "nombre": "Paciente Test",
        "dni": "12345678",
        "telefono": "111",
    }
    paquete = PacienteExportacionRead(
        generado_at=ahora,
        consultorio=consultorio,
        paciente=paciente,
    )
    dump = paquete.model_dump()
    assert set(dump.keys()) >= {
        "generado_at",
        "consultorio",
        "paciente",
        "turnos",
        "ficha_clinica",
        "evoluciones",
        "odontograma",
        "presupuestos",
        "consentimientos",
        "adjuntos",
        "movimientos",
    }
    assert dump["ficha_clinica"] is None
    assert dump["adjuntos"]["cantidad"] == 0
    assert dump["adjuntos"]["items"] == []
    assert dump["odontograma"]["eventos"] == []


def test_adjuntos_sin_nombre_de_archivo() -> None:
    adj = AdjuntoExportacion(tipo="rx", mime_type="image/png", tamano_bytes=100)
    assert "nombre_archivo" not in adj.model_dump()
    assert "storage_key" not in adj.model_dump()


def test_consentimiento_incluye_firma_hash_y_no_texto_completo() -> None:
    c = ConsentimientoExportacion(
        id=uuid.uuid4(),
        paciente_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        texto_version="v1",
        firma_hash="a" * 64,
        canal="presencial",
    )
    dump = c.model_dump()
    assert dump["firma_hash"] == "a" * 64
    assert "texto_contenido" not in dump
    assert "texto_contenido" not in ConsentimientoExportacion.model_fields


def test_odontograma_por_defecto_vacio() -> None:
    od = OdontogramaExportacion()
    assert od.eventos == []


def test_extra_forbid_en_inputs() -> None:
    with pytest.raises(ValidationError):
        PacienteExportacionRead.model_validate(
            {
                "generado_at": datetime.now(UTC),
                "consultorio": {"nombre": "C", "slug": "c", "extra": 1},
                "paciente": {"id": str(uuid.uuid4()), "nombre": "P", "dni": "1", "telefono": "2"},
            }
        )


def test_montos_como_string() -> None:
    from app.api.schemas_paciente_exportacion import PresupuestoExportacion

    p = PresupuestoExportacion(
        id=uuid.uuid4(),
        paciente_id=uuid.uuid4(),
        estado="borrador",
        total="100.50",
        total_cobertura_os="10.00",
        total_a_cargo="90.50",
    )
    dump = p.model_dump(mode="json")
    assert dump["total"] == "100.50"
    assert isinstance(dump["total"], str)
