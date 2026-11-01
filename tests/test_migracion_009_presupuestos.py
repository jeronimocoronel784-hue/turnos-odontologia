"""Migración 009: tablas presupuesto, presupuesto_item y presupuesto_turno (tarea 1.1).

Verifica:
1. Grafo de estados de presupuesto (es_transicion_presupuesto_valida).
2. Esquema desplegado: tablas presupuesto, presupuesto_item y presupuesto_turno.
3. Persistencia y constraints de unicidad en presupuesto_turno.
4. Encadenamiento de migración 009_presupuestos_planes y GRANT/REVOKE.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.presupuesto import (
    EstadoPresupuesto,
    Presupuesto,
    PresupuestoItem,
    PresupuestoTurno,
    es_transicion_presupuesto_valida,
)
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario


def test_grafo_estados_presupuesto() -> None:
    """Verifica transiciones válidas e inválidas de EstadoPresupuesto."""
    assert es_transicion_presupuesto_valida(
        EstadoPresupuesto.BORRADOR, EstadoPresupuesto.PRESENTADO
    )
    assert es_transicion_presupuesto_valida(
        EstadoPresupuesto.PRESENTADO, EstadoPresupuesto.ACEPTADO
    )
    assert es_transicion_presupuesto_valida(EstadoPresupuesto.ACEPTADO, EstadoPresupuesto.EN_CURSO)
    assert es_transicion_presupuesto_valida(
        EstadoPresupuesto.EN_CURSO, EstadoPresupuesto.FINALIZADO
    )
    assert not es_transicion_presupuesto_valida(
        EstadoPresupuesto.FINALIZADO, EstadoPresupuesto.BORRADOR
    )
    assert not es_transicion_presupuesto_valida(
        EstadoPresupuesto.RECHAZADO, EstadoPresupuesto.EN_CURSO
    )


async def test_esquema_tablas_presupuesto(session: AsyncSession) -> None:
    """Verifica columnas e índices de presupuesto, presupuesto_item y presupuesto_turno."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> dict[str, set[str]]:
        insp = inspect(sync_conn)
        return {
            "presupuesto": {c["name"] for c in insp.get_columns("presupuesto")},
            "presupuesto_item": {c["name"] for c in insp.get_columns("presupuesto_item")},
            "presupuesto_turno": {c["name"] for c in insp.get_columns("presupuesto_turno")},
            "idx_pres": {i["name"] for i in insp.get_indexes("presupuesto")},
        }

    info = await conn.run_sync(_inspeccionar)
    assert {
        "id",
        "tenant_id",
        "paciente_id",
        "obra_social",
        "estado",
        "total",
        "total_cobertura_os",
        "total_a_cargo",
        "validez_hasta",
        "observaciones",
        "created_by",
        "created_at",
        "updated_at",
    }.issubset(info["presupuesto"])
    assert {
        "id",
        "tenant_id",
        "presupuesto_id",
        "prestacion_id",
        "pieza_fdi",
        "cantidad",
        "precio_unit",
        "cobertura_os",
        "a_cargo",
        "created_at",
    }.issubset(info["presupuesto_item"])
    assert {
        "id",
        "tenant_id",
        "presupuesto_id",
        "turno_id",
        "presupuesto_item_id",
        "created_at",
    }.issubset(info["presupuesto_turno"])
    assert "ix_presupuesto_tenant_paciente_estado" in info["idx_pres"]


async def test_persistencia_y_constraints_presupuesto(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """Verifica persistencia de Presupuesto, PresupuestoItem, PresupuestoTurno y unicidad."""
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email="odonto-pres009@consultorio.test",
        nombre="Dr. Plan",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-10009",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Carlos Presupuesto",
        dni="36777888",
        telefono="+5491133334444",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box Plan 1",
        activo=True,
    )
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Corona Porcelana",
        duracion_min=45,
        precio_particular=Decimal("120000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()

    pres = Presupuesto(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        obra_social="OSDE",
        estado=EstadoPresupuesto.BORRADOR.value,
        total=Decimal("120000.00"),
        total_cobertura_os=Decimal("40000.00"),
        total_a_cargo=Decimal("80000.00"),
        created_by=odontologo.id,
    )
    session.add(pres)
    await session.flush()

    item = PresupuestoItem(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        prestacion_id=prestacion.id,
        pieza_fdi=21,
        cantidad=1,
        precio_unit=Decimal("120000.00"),
        cobertura_os=Decimal("40000.00"),
        a_cargo=Decimal("80000.00"),
    )
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 11, 28, 10, 0, tzinfo=UTC),
        fin=datetime(2026, 11, 28, 10, 45, tzinfo=UTC),
        estado=EstadoTurno.PENDIENTE.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add_all([item, turno])
    await session.flush()

    pt1 = PresupuestoTurno(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        turno_id=turno.id,
        presupuesto_item_id=item.id,
    )
    session.add(pt1)
    await session.flush()

    # Duplicar el mismo vínculo (presupuesto_id, turno_id) -> IntegrityError
    pt_dup = PresupuestoTurno(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        presupuesto_id=pres.id,
        turno_id=turno.id,
    )
    session.add(pt_dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


def test_migracion_009_presupuestos_encadenada() -> None:
    """Verifica archivo 009_presupuestos_planes.py y registro en alembic/env.py."""
    ruta_mig = Path("src/backend/alembic/versions/009_presupuestos_planes.py")
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "009_presupuestos_planes"' in contenido
    assert 'down_revision: str | None = "008_historia_clinica_odontograma"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in contenido
    assert "presupuesto, presupuesto_item, presupuesto_turno TO turnos_app" in contenido
    assert "REVOKE ALL PRIVILEGES ON TABLE" in contenido
    assert "presupuesto, presupuesto_item, presupuesto_turno FROM turnos_app" in contenido

    ruta_env = Path("src/backend/alembic/env.py")
    contenido_env = ruta_env.read_text(encoding="utf-8")
    for simbolo in ("Presupuesto", "PresupuestoItem", "PresupuestoTurno"):
        assert simbolo in contenido_env
