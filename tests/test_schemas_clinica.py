"""Tests unitarios de schemas Pydantic v2 para HC, odontograma y consentimiento (tarea 1.2).

Verifica:
1. extra='forbid' en todos los inputs clínicos (R1).
2. Validación de pieza FDI (11–48 y 51–85) y rechazo de piezas inválidas (19, 99, 0).
3. Validación de evolución (nota obligatoria no vacía) y adjunto clínico (tipo válido y tamaño > 0).
4. Validación de creación y firma de consentimiento informado.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.api.schemas_clinica import (
    AdjuntoCreate,
    ConsentimientoCreate,
    ConsentimientoFirmaInput,
    ConsentimientoRevocarInput,
    EvolucionCreate,
    FichaClinicaUpdate,
    PiezaEventoCreate,
)
from app.domain.clinica import (
    CanalFirmaConsentimiento,
    SuperficieDental,
    TipoAdjunto,
    TipoEventoPieza,
)


def test_ficha_y_evolucion_rechazan_campos_extra_y_notas_vacias() -> None:
    """R1: extra='forbid' y validación de notas en FichaClinicaUpdate y EvolucionCreate."""
    ficha_ok = FichaClinicaUpdate(
        antecedentes="Hipertensión controlada",
        alergias="Penicilina",
        datos_json={"grupo_sanguineo": "O+"},
    )
    assert ficha_ok.alergias == "Penicilina"

    with pytest.raises(ValidationError):
        FichaClinicaUpdate(alergias="Ninguna", campo_extra="prohibido")  # type: ignore[call-arg]

    ev_ok = EvolucionCreate(
        nota="  Se realiza control clínico y radiográfico.  ",
        turno_id=uuid.uuid4(),
    )
    assert ev_ok.nota == "Se realiza control clínico y radiográfico."

    with pytest.raises(ValidationError):
        EvolucionCreate(nota="   ")

    with pytest.raises(ValidationError):
        EvolucionCreate(nota="Nota", campo_extra=123)  # type: ignore[call-arg]


def test_pieza_evento_create_valida_nomenclatura_fdi_y_enums() -> None:
    """Valida piezas FDI permanentes y deciduas y rechaza números inexistentes (19, 99, 0)."""
    ev_adulto = PiezaEventoCreate(
        pieza_fdi=16,
        superficie=SuperficieDental.OCLUSAL,
        evento=TipoEventoPieza.OBTURACION,
        observacion="  Resina compuesta A2  ",
    )
    assert ev_adulto.pieza_fdi == 16
    assert ev_adulto.observacion == "Resina compuesta A2"

    ev_decidua = PiezaEventoCreate(
        pieza_fdi=55,
        superficie=SuperficieDental.TOTAL,
        evento=TipoEventoPieza.SELLADOR,
    )
    assert ev_decidua.pieza_fdi == 55

    for pieza_invalida in (0, 10, 19, 29, 39, 49, 56, 99):
        with pytest.raises(ValidationError):
            PiezaEventoCreate(
                pieza_fdi=pieza_invalida,
                superficie=SuperficieDental.OCLUSAL,
                evento=TipoEventoPieza.CARIES,
            )

    with pytest.raises(ValidationError):
        PiezaEventoCreate(
            pieza_fdi=11,
            superficie=SuperficieDental.VESTIBULAR,
            evento=TipoEventoPieza.SANO,
            intruso="no",  # type: ignore[call-arg]
        )


def test_adjunto_y_consentimiento_schemas_validacion() -> None:
    """Valida AdjuntoCreate, ConsentimientoCreate, ConsentimientoFirmaInput y RevocarInput."""
    adj = AdjuntoCreate(
        tipo=TipoAdjunto.RX,
        nombre_archivo="  rx_pieza_26.png  ",
        mime_type="image/png",
        tamano_bytes=204800,
        storage_key="tenants/t1/adjuntos/rx_26.png",
    )
    assert adj.nombre_archivo == "rx_pieza_26.png"

    with pytest.raises(ValidationError):
        AdjuntoCreate(
            tipo=TipoAdjunto.RX,
            nombre_archivo="rx.png",
            mime_type="image/png",
            tamano_bytes=0,
            storage_key="k",
        )

    cons = ConsentimientoCreate(
        paciente_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        texto_version="  v1.0-exodoncia  ",
        texto_contenido="  Declaro haber sido informado sobre el procedimiento invasivo.  ",
    )
    assert cons.texto_version == "v1.0-exodoncia"

    firma = ConsentimientoFirmaInput(
        firmado_por="  Juan Pérez  ",
        firma_datos="  data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==  ",
        canal=CanalFirmaConsentimiento.PRESENCIAL,
    )
    assert firma.firmado_por == "Juan Pérez"

    with pytest.raises(ValidationError):
        ConsentimientoFirmaInput(
            firmado_por="   ",
            firma_datos="abc",
        )

    rev = ConsentimientoRevocarInput(motivo="  Paciente revoca autorización antes de la práctica  ")
    assert rev.motivo == "Paciente revoca autorización antes de la práctica"
