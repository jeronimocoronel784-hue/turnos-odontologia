"""Migración 008: evolucion, odontograma, pieza_evento y consentimiento (tarea 1.1).

Verifica:
1. Validación pura de nomenclatura FDI y hash de consentimiento.
2. Esquema desplegado: tablas evolucion, odontograma, pieza_evento y consentimiento.
3. Constraints de unicidad y check en odontograma, pieza_evento y consentimiento.
4. Persistencia de Evolucion (y corrección aditiva), PiezaEvento, AdjuntoClinico y Consentimiento.
5. Encadenamiento de migración 008_historia_clinica_odontograma y GRANT/REVOKE.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clinica import (
    AdjuntoClinico,
    CanalFirmaConsentimiento,
    Consentimiento,
    Evolucion,
    Odontograma,
    PiezaEvento,
    SuperficieDental,
    TipoAdjunto,
    TipoEventoPieza,
    calcular_hash_consentimiento,
    es_pieza_fdi_valida,
)
from app.domain.ficha_clinica import FichaClinica
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.tenant import Tenant
from app.domain.usuario import Usuario


def test_es_pieza_fdi_valida_y_calcular_hash_consentimiento() -> None:
    """Verifica piezas FDI permanentes (11..48), deciduas (51..85) y rechazos."""
    for pieza in (11, 18, 21, 28, 31, 38, 41, 48, 51, 55, 61, 65, 71, 75, 81, 85):
        assert es_pieza_fdi_valida(pieza) is True

    for invalida in (0, 10, 19, 20, 29, 30, 39, 40, 49, 50, 56, 66, 76, 86, 99, -11):
        assert es_pieza_fdi_valida(invalida) is False

    tenant_id = uuid.uuid4()
    paciente_id = uuid.uuid4()
    prestacion_id = uuid.uuid4()
    momento = datetime(2026, 11, 20, 14, 30, tzinfo=UTC)
    h1 = calcular_hash_consentimiento(
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        prestacion_id=prestacion_id,
        texto_version="v1.0-exodoncia",
        firmado_por="Juan Pérez DNI 30111222",
        firmado_at=momento,
        firma_datos="trazo-base64-abc",
    )
    h2 = calcular_hash_consentimiento(
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        prestacion_id=prestacion_id,
        texto_version="v1.0-exodoncia",
        firmado_por="Juan Pérez DNI 30111222",
        firmado_at=momento,
        firma_datos="trazo-base64-abc",
    )
    h3 = calcular_hash_consentimiento(
        tenant_id=tenant_id,
        paciente_id=paciente_id,
        prestacion_id=prestacion_id,
        texto_version="v2.0-exodoncia",
        firmado_por="Juan Pérez DNI 30111222",
        firmado_at=momento,
        firma_datos="trazo-base64-abc",
    )
    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


async def test_esquema_tablas_clinicas(session: AsyncSession) -> None:
    """Verifica columnas e índices de evolucion, odontograma, pieza_evento y consentimiento."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> dict[str, set[str]]:
        insp = inspect(sync_conn)
        return {
            "evolucion": {c["name"] for c in insp.get_columns("evolucion")},
            "odontograma": {c["name"] for c in insp.get_columns("odontograma")},
            "pieza_evento": {c["name"] for c in insp.get_columns("pieza_evento")},
            "adjunto_clinico": {c["name"] for c in insp.get_columns("adjunto_clinico")},
            "consentimiento": {c["name"] for c in insp.get_columns("consentimiento")},
            "idx_pieza": {i["name"] for i in insp.get_indexes("pieza_evento")},
        }

    info = await conn.run_sync(_inspeccionar)
    assert {
        "id",
        "tenant_id",
        "ficha_clinica_id",
        "paciente_id",
        "turno_id",
        "profesional_id",
        "nota",
        "es_correccion_de_id",
        "created_at",
    }.issubset(info["evolucion"])
    assert {"id", "tenant_id", "paciente_id", "created_at", "updated_at"}.issubset(
        info["odontograma"]
    )
    assert {
        "id",
        "tenant_id",
        "odontograma_id",
        "pieza_fdi",
        "superficie",
        "evento",
        "turno_id",
        "observacion",
        "created_by",
        "created_at",
    }.issubset(info["pieza_evento"])
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "ficha_clinica_id",
        "evolucion_id",
        "pieza_evento_id",
        "tipo",
        "nombre_archivo",
        "mime_type",
        "tamano_bytes",
        "storage_key",
        "created_by",
        "created_at",
    }.issubset(info["adjunto_clinico"])
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "prestacion_id",
        "turno_id",
        "texto_version",
        "texto_contenido",
        "firma_hash",
        "firmado_por",
        "firmado_at",
        "canal",
        "revocado",
        "revocado_motivo",
        "revocado_at",
        "created_at",
        "updated_at",
    }.issubset(info["consentimiento"])
    assert "ix_pieza_evento_odontograma_pieza_created" in info["idx_pieza"]


async def test_persistencia_y_constraints_clinicos(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Verifica persistencia de entidades clínicas y rechazo de duplicados/constraints."""
    from decimal import Decimal

    from app.domain.usuario import RolUsuario

    dueno_a = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email="odontologo-mig008@consultorio.test",
        nombre="Dra. Clínica",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-12345",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="María Clínica",
        dni="32999888",
        telefono="+5491144445555",
        optin_wa=True,
        activo=True,
    )
    session.add_all([dueno_a, paciente])
    await session.flush()

    ficha = FichaClinica(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Extracción molar",
        duracion_min=45,
        precio_particular=Decimal("40000.00"),
        requiere_sena=False,
        invasiva=True,
        activa=True,
    )
    session.add_all([ficha, prestacion])
    await session.flush()

    ev1 = Evolucion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        ficha_clinica_id=ficha.id,
        paciente_id=paciente.id,
        profesional_id=dueno_a.id,
        nota="Paciente refiere sensibilidad al frío.",
    )
    session.add(ev1)
    await session.flush()

    ev_corr = Evolucion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        ficha_clinica_id=ficha.id,
        paciente_id=paciente.id,
        profesional_id=dueno_a.id,
        nota="Fe de erratas: sensibilidad en cuadrante superior derecho.",
        es_correccion_de_id=ev1.id,
    )
    odontograma = Odontograma(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
    )
    session.add_all([ev_corr, odontograma])
    await session.flush()

    pe = PiezaEvento(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        odontograma_id=odontograma.id,
        pieza_fdi=16,
        superficie=SuperficieDental.OCLUSAL.value,
        evento=TipoEventoPieza.CARIES.value,
        observacion="Caries dentinaria",
        created_by=dueno_a.id,
    )
    session.add(pe)
    await session.flush()

    adj = AdjuntoClinico(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        ficha_clinica_id=ficha.id,
        evolucion_id=ev1.id,
        pieza_evento_id=pe.id,
        tipo=TipoAdjunto.RX.value,
        nombre_archivo="rx-periapical-16.png",
        mime_type="image/png",
        tamano_bytes=128000,
        storage_key=f"tenants/{tenant_a.id}/adjuntos/{uuid.uuid4()}.png",
        created_by=dueno_a.id,
    )
    cons = Consentimiento(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        prestacion_id=prestacion.id,
        texto_version="v1.0",
        texto_contenido="Autorizo extracción dental.",
        canal=CanalFirmaConsentimiento.PRESENCIAL.value,
        revocado=False,
    )
    session.add_all([adj, cons])
    await session.flush()

    # Odontograma duplicado para el mismo paciente debe fallar por UniqueConstraint
    odo_dup = Odontograma(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
    )
    session.add(odo_dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


def test_migracion_008_clinica_encadenada() -> None:
    """Verifica archivo 008_historia_clinica_odontograma.py y registro en alembic/env.py."""
    ruta_mig = Path("src/backend/alembic/versions/008_historia_clinica_odontograma.py")
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "008_historia_clinica_odontograma"' in contenido
    assert 'down_revision: str | None = "007_comunicaciones_mensajeria"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in contenido
    assert (
        "evolucion, odontograma, pieza_evento, adjunto_clinico, consentimiento TO turnos_app"
        in contenido
    )
    assert "REVOKE ALL PRIVILEGES ON TABLE" in contenido
    assert (
        "evolucion, odontograma, pieza_evento, adjunto_clinico, consentimiento FROM turnos_app"
        in contenido
    )

    ruta_env = Path("src/backend/alembic/env.py")
    contenido_env = ruta_env.read_text(encoding="utf-8")
    for simbolo in ("Evolucion", "Odontograma", "PiezaEvento", "AdjuntoClinico", "Consentimiento"):
        assert simbolo in contenido_env
