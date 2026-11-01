"""Migración 005: tablas turno y bloqueo + máquina de estados y duración (tarea 1.1).

Verifica:
1. Esquema desplegado: tablas turno y bloqueo con columnas e índices.
2. Check constraints en turno (fin > inicio, sobreturno exige observaciones con motivo).
3. Check constraints en bloqueo (hasta > desde, al menos uno de profesional_id o sillon_id).
4. Función pura calcular_fin_turno (RN-AG-02) y grafo cerrado es_transicion_valida (RN-AG-07).
5. Encadenamiento de migración 005_agenda_turnos con 004_pacientes_ficha_clinica y env.py.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.bloqueo import Bloqueo, MotivoBloqueo
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import (
    EstadoTurno,
    OrigenTurno,
    Turno,
    calcular_fin_turno,
    es_transicion_valida,
)
from app.domain.usuario import RolUsuario, Usuario

RAIZ = Path(__file__).resolve().parents[1]


def _leer(conn: Any) -> dict[str, Any]:
    insp = inspect(conn.connection())
    return {
        "tablas": set(insp.get_table_names()),
        "turno_indexes": {i["name"] for i in (insp.get_indexes("turno") or [])},
        "bloqueo_indexes": {i["name"] for i in (insp.get_indexes("bloqueo") or [])},
        "turno_columns": {c["name"]: c["nullable"] for c in (insp.get_columns("turno") or [])},
        "bloqueo_columns": {c["name"]: c["nullable"] for c in (insp.get_columns("bloqueo") or [])},
    }


async def _esquema(session: AsyncSession) -> dict[str, Any]:
    return await session.run_sync(_leer)


@pytest.mark.asyncio
async def test_esquema_tablas_turno_y_bloqueo(session: AsyncSession) -> None:
    esq = await _esquema(session)
    assert "turno" in esq["tablas"]
    assert "bloqueo" in esq["tablas"]

    t_cols = esq["turno_columns"]
    for col in (
        "id",
        "tenant_id",
        "paciente_id",
        "profesional_id",
        "sillon_id",
        "prestacion_id",
        "inicio",
        "fin",
        "estado",
        "origen",
        "sobreturno",
        "observaciones",
        "motivo_cancelacion",
        "turno_origen_id",
        "sena_cobrada",
        "created_at",
        "updated_at",
    ):
        assert col in t_cols, f"Falta columna {col} en turno"

    assert t_cols["turno_origen_id"] is True
    assert t_cols["motivo_cancelacion"] is True
    assert t_cols["observaciones"] is True
    assert t_cols["sobreturno"] is False
    assert t_cols["sena_cobrada"] is False

    b_cols = esq["bloqueo_columns"]
    for col in (
        "id",
        "tenant_id",
        "profesional_id",
        "sillon_id",
        "desde",
        "hasta",
        "motivo",
        "descripcion",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert col in b_cols, f"Falta columna {col} en bloqueo"

    assert b_cols["profesional_id"] is True
    assert b_cols["sillon_id"] is True
    assert b_cols["desde"] is False
    assert b_cols["hasta"] is False
    assert b_cols["motivo"] is False

    assert "ix_turno_tenant_profesional_inicio" in esq["turno_indexes"]
    assert "ix_turno_tenant_sillon_inicio" in esq["turno_indexes"]
    assert "ix_turno_tenant_estado_inicio" in esq["turno_indexes"]
    assert "ix_bloqueo_tenant_desde_hasta" in esq["bloqueo_indexes"]


@pytest.mark.asyncio
async def test_constraints_turno_rango_y_sobreturno_motivo(session: AsyncSession) -> None:
    tenant = Tenant(nombre="Consultorio Turnos", slug=f"t-tur-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    prof = Usuario(
        tenant_id=tenant.id,
        nombre="Dra. Ana",
        email="ana@odonto.test",
        password_hash="hash",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MN-111",
    )
    sillon = Sillon(tenant_id=tenant.id, nombre="Box 1", sucursal="central")
    prest = Prestacion(
        tenant_id=tenant.id,
        nombre="Consulta",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
    )
    pac = Paciente(
        tenant_id=tenant.id,
        nombre="Paciente Uno",
        dni="40111222",
        telefono="1122334455",
    )
    session.add_all([prof, sillon, prest, pac])
    await session.commit()

    tenant_id = tenant.id
    pac_id = pac.id
    prof_id = prof.id
    sillon_id = sillon.id
    prest_id = prest.id

    ahora = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)

    # 1. fin <= inicio debe fallar por ck_turno_rango_valido
    t_invalido = Turno(
        tenant_id=tenant_id,
        paciente_id=pac_id,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        prestacion_id=prest_id,
        inicio=ahora,
        fin=ahora,
        estado=EstadoTurno.PENDIENTE,
        origen=OrigenTurno.PRESENCIAL,
    )
    session.add(t_invalido)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 2. sobreturno = True sin observaciones debe fallar por ck_turno_sobreturno_motivo
    t_sobre_sin_motivo = Turno(
        tenant_id=tenant_id,
        paciente_id=pac_id,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        prestacion_id=prest_id,
        inicio=ahora,
        fin=ahora + timedelta(minutes=30),
        estado=EstadoTurno.PENDIENTE,
        origen=OrigenTurno.PRESENCIAL,
        sobreturno=True,
        observaciones="   ",
    )
    session.add(t_sobre_sin_motivo)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 3. sobreturno = True con motivo válido pasa
    t_sobre_ok = Turno(
        tenant_id=tenant_id,
        paciente_id=pac_id,
        profesional_id=prof_id,
        sillon_id=sillon_id,
        prestacion_id=prest_id,
        inicio=ahora,
        fin=ahora + timedelta(minutes=30),
        estado=EstadoTurno.PENDIENTE,
        origen=OrigenTurno.PRESENCIAL,
        sobreturno=True,
        observaciones="Urgencia por dolor agudo",
    )
    session.add(t_sobre_ok)
    await session.commit()
    assert t_sobre_ok.id is not None


@pytest.mark.asyncio
async def test_constraints_bloqueo_rango_y_objetivo(session: AsyncSession) -> None:
    tenant = Tenant(nombre="Consultorio Bloqueos", slug=f"t-bloq-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    sillon = Sillon(tenant_id=tenant.id, nombre="Box 1", sucursal="central")
    session.add(sillon)
    await session.commit()

    tenant_id = tenant.id
    sillon_id = sillon.id

    desde = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)

    # 1. Sin profesional ni sillón falla por ck_bloqueo_objetivo_no_nulo
    b_sin_obj = Bloqueo(
        tenant_id=tenant_id,
        profesional_id=None,
        sillon_id=None,
        desde=desde,
        hasta=desde + timedelta(hours=2),
        motivo=MotivoBloqueo.FERIADO,
    )
    session.add(b_sin_obj)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 2. hasta <= desde falla por ck_bloqueo_rango_valido
    b_rango_inv = Bloqueo(
        tenant_id=tenant_id,
        profesional_id=None,
        sillon_id=sillon_id,
        desde=desde,
        hasta=desde,
        motivo=MotivoBloqueo.MANUAL,
    )
    session.add(b_rango_inv)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_calcular_fin_turno_y_grafo_estados_rn_ag_02_07() -> None:
    inicio = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    assert calcular_fin_turno(inicio, 45) == datetime(2026, 11, 10, 10, 45, tzinfo=UTC)

    # Transiciones válidas (RN-AG-07)
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.CONFIRMADO) is True
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.CANCELADO) is True
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.AUSENTE) is True
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.REPROGRAMADO) is True
    assert es_transicion_valida(EstadoTurno.CONFIRMADO, EstadoTurno.PRESENTE) is True
    assert es_transicion_valida(EstadoTurno.CONFIRMADO, EstadoTurno.CANCELADO) is True
    assert es_transicion_valida(EstadoTurno.CONFIRMADO, EstadoTurno.AUSENTE) is True
    assert es_transicion_valida(EstadoTurno.CONFIRMADO, EstadoTurno.REPROGRAMADO) is True
    assert es_transicion_valida(EstadoTurno.PRESENTE, EstadoTurno.FINALIZADO) is True

    # Transiciones inválidas (fuera del grafo)
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.FINALIZADO) is False
    assert es_transicion_valida(EstadoTurno.PENDIENTE, EstadoTurno.PRESENTE) is False
    assert es_transicion_valida(EstadoTurno.FINALIZADO, EstadoTurno.CONFIRMADO) is False
    assert es_transicion_valida(EstadoTurno.CANCELADO, EstadoTurno.CONFIRMADO) is False
    assert es_transicion_valida(EstadoTurno.REPROGRAMADO, EstadoTurno.CONFIRMADO) is False


def test_archivo_migracion_005_existe_y_encadena_con_004() -> None:
    archivo = RAIZ / "src" / "backend" / "alembic" / "versions" / "005_agenda_turnos.py"
    assert archivo.exists(), f"Falta {archivo}"
    contenido = archivo.read_text(encoding="utf-8")
    assert 'revision: str = "005_agenda_turnos"' in contenido
    assert 'down_revision: str | None = "004_pacientes_ficha_clinica"' in contenido

    env_py = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from app.domain.turno import Turno" in env_py
    assert "from app.domain.bloqueo import Bloqueo" in env_py
