"""Migración 010: sena, cierre_caja y movimiento_caja (tarea 1.1).

Verifica:
1. Grafo de estados de la seña (RN-PA-01, RN-PA-04, design D1).
2. Esquema desplegado: tablas sena, cierre_caja y movimiento_caja.
3. Persistencia y constraints (seña única por turno, checks de estado/medio/monto).
4. Encadenamiento 010_caja_senas, GRANT/REVOKE y round-trip upgrade/downgrade.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.caja import (
    CierreCaja,
    EstadoCierreCaja,
    EstadoSena,
    MedioPago,
    MovimientoCaja,
    Sena,
    TipoMovimientoCaja,
    es_transicion_sena_valida,
)
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario


def test_grafo_estados_sena_permite_cobrar_aplicar_devolver_y_vencer() -> None:
    """D1: pendiente -> cobrada|vencida|devuelta; cobrada -> aplicada|devuelta; resto terminal."""
    assert es_transicion_sena_valida(EstadoSena.PENDIENTE, EstadoSena.COBRADA) is True
    assert es_transicion_sena_valida(EstadoSena.PENDIENTE, EstadoSena.VENCIDA) is True
    assert es_transicion_sena_valida(EstadoSena.PENDIENTE, EstadoSena.DEVUELTA) is True
    assert es_transicion_sena_valida(EstadoSena.COBRADA, EstadoSena.APLICADA) is True
    assert es_transicion_sena_valida(EstadoSena.COBRADA, EstadoSena.DEVUELTA) is True

    assert es_transicion_sena_valida(EstadoSena.PENDIENTE, EstadoSena.APLICADA) is False
    assert es_transicion_sena_valida(EstadoSena.COBRADA, EstadoSena.PENDIENTE) is False
    for terminal in (EstadoSena.APLICADA, EstadoSena.DEVUELTA, EstadoSena.VENCIDA):
        for destino in EstadoSena:
            assert es_transicion_sena_valida(terminal, destino) is False

    # Acepta strings (valores persistidos en la columna `estado`).
    assert es_transicion_sena_valida("pendiente", "cobrada") is True
    assert es_transicion_sena_valida("pendiente", "inventada") is False


async def test_esquema_tablas_sena_cierre_y_movimiento(session: AsyncSession) -> None:
    """Verifica columnas e índices de sena, cierre_caja y movimiento_caja (§04)."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> dict[str, set[str]]:
        insp = inspect(sync_conn)
        return {
            "sena": {c["name"] for c in insp.get_columns("sena")},
            "cierre_caja": {c["name"] for c in insp.get_columns("cierre_caja")},
            "movimiento_caja": {c["name"] for c in insp.get_columns("movimiento_caja")},
            "idx_sena": {i["name"] for i in insp.get_indexes("sena")},
            "idx_mov": {i["name"] for i in insp.get_indexes("movimiento_caja")},
        }

    info = await conn.run_sync(_inspeccionar)
    assert {
        "id",
        "tenant_id",
        "turno_id",
        "monto",
        "estado",
        "mp_payment_id",
        "vence_at",
        "created_at",
        "updated_at",
    }.issubset(info["sena"])
    assert {
        "id",
        "tenant_id",
        "fecha",
        "total_sistema",
        "total_contado",
        "diferencia",
        "estado",
        "abierto_por",
        "cerrado_por",
        "cerrado_at",
        "reabierto_motivo",
        "created_at",
        "updated_at",
    }.issubset(info["cierre_caja"])
    assert {
        "id",
        "tenant_id",
        "tipo",
        "concepto",
        "medio",
        "monto",
        "turno_id",
        "sena_id",
        "cobro_mp_id",
        "cierre_id",
        "created_by",
        "created_at",
    }.issubset(info["movimiento_caja"])
    assert "ix_sena_tenant_estado" in info["idx_sena"]
    assert "ix_movimiento_caja_tenant_created_at" in info["idx_mov"]
    assert "ix_movimiento_caja_tenant_cierre_id" in info["idx_mov"]


async def _escenario_caja(session: AsyncSession, tenant: Tenant) -> dict[str, Any]:
    """Fixture local: profesional, paciente, sillón, prestación con seña, turno y cierre abierto."""
    odontologo = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="odonto-caja010@consultorio.test",
        nombre="Dra. Caja",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-10010",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Lucía Seña",
        dni="30111222",
        telefono="+5491155556666",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box Caja 1", activo=True)
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Blanqueamiento con seña",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=Decimal("10000.00"),
        invasiva=False,
        activa=True,
    )
    session.add_all([odontologo, paciente, sillon, prestacion])
    await session.flush()

    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        fin=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
        estado=EstadoTurno.PENDIENTE.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    # Segundo turno real: permite aislar un CHECK de una violación de FK en Postgres (R11).
    turno_alt = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=odontologo.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=datetime(2026, 11, 10, 11, 0, tzinfo=UTC),
        fin=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
        estado=EstadoTurno.PENDIENTE.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    cierre = CierreCaja(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        fecha=date(2026, 11, 10),
        estado=EstadoCierreCaja.ABIERTO.value,
        abierto_por=odontologo.id,
    )
    session.add_all([turno, turno_alt, cierre])
    await session.flush()
    return {
        "odontologo": odontologo,
        "paciente": paciente,
        "prestacion": prestacion,
        "turno": turno,
        "turno_alt": turno_alt,
        "cierre": cierre,
    }


async def _flush_rechazado(session: AsyncSession, *objetos: Any) -> None:
    """Agrega objetos dentro de un savepoint y exige que la DB los rechace (IntegrityError)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objetos)
            await session.flush()


async def test_persistencia_sena_y_movimiento_caja_conciliado(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-02/05: seña pendiente del turno y su ingreso vinculado al cierre abierto."""
    esc = await _escenario_caja(session, tenant_a)

    sena = Sena(
        id=uuid.uuid4(), tenant_id=tenant_a.id, turno_id=esc["turno"].id, monto=Decimal("10000.00")
    )
    session.add(sena)
    await session.flush()

    # Default del servidor: la seña nace `pendiente` (RN-PA-02).
    assert sena.estado == EstadoSena.PENDIENTE.value
    assert sena.vence_at is None

    movimiento = MovimientoCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        tipo=TipoMovimientoCaja.INGRESO.value,
        concepto="Cobro de seña",
        medio=MedioPago.EFECTIVO.value,
        monto=Decimal("10000.00"),
        turno_id=esc["turno"].id,
        sena_id=sena.id,
        cierre_id=esc["cierre"].id,
        created_by=esc["odontologo"].id,
    )
    session.add(movimiento)
    await session.flush()

    total = (
        await session.execute(
            select(func.coalesce(func.sum(MovimientoCaja.monto), 0)).where(
                MovimientoCaja.cierre_id == esc["cierre"].id
            )
        )
    ).scalar_one()
    assert Decimal(str(total)) == Decimal("10000.00")
    assert movimiento.created_at is not None


async def test_sena_unica_por_turno_y_estado_valido(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-02: una sola seña por turno y estado dentro del enum del §04."""
    esc = await _escenario_caja(session, tenant_a)
    session.add(
        Sena(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            turno_id=esc["turno"].id,
            monto=Decimal("10000.00"),
        )
    )
    await session.flush()

    await _flush_rechazado(
        session,
        Sena(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            turno_id=esc["turno"].id,
            monto=Decimal("5000.00"),
        ),
    )
    await _flush_rechazado(
        session,
        Sena(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            turno_id=esc["turno_alt"].id,
            monto=Decimal("5000.00"),
            estado="regalada",
        ),
    )
    await _flush_rechazado(
        session,
        Sena(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            turno_id=esc["turno_alt"].id,
            monto=Decimal("0.00"),
        ),
    )


async def test_movimiento_caja_rechaza_tipo_medio_y_monto_invalidos(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """RN-PA-05: tipo/medio del enum cerrado y monto estrictamente positivo (R8)."""
    esc = await _escenario_caja(session, tenant_a)

    def _movimiento(**overrides: Any) -> MovimientoCaja:
        datos: dict[str, Any] = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_a.id,
            "tipo": TipoMovimientoCaja.INGRESO.value,
            "concepto": "Cobro de saldo",
            "medio": MedioPago.DEBITO.value,
            "monto": Decimal("20000.00"),
            "created_by": esc["odontologo"].id,
        }
        datos.update(overrides)
        return MovimientoCaja(**datos)

    session.add(_movimiento())
    await session.flush()

    await _flush_rechazado(session, _movimiento(tipo="transferencia"))
    await _flush_rechazado(session, _movimiento(medio="cheque"))
    await _flush_rechazado(session, _movimiento(monto=Decimal("0.00")))
    await _flush_rechazado(session, _movimiento(monto=Decimal("-1500.00")))
    await _flush_rechazado(session, _movimiento(concepto="   "))


async def test_cierre_caja_unico_por_fecha_y_completo_al_cerrar(
    session: AsyncSession,
    tenant_a: Tenant,
) -> None:
    """D3/RN-PA-05: un cierre por fecha y un `cerrado` exige contado, actor y fecha de cierre."""
    esc = await _escenario_caja(session, tenant_a)

    await _flush_rechazado(
        session,
        CierreCaja(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            fecha=esc["cierre"].fecha,
            abierto_por=esc["odontologo"].id,
        ),
    )
    await _flush_rechazado(
        session,
        CierreCaja(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            fecha=date(2026, 11, 11),
            estado=EstadoCierreCaja.CERRADO.value,
            abierto_por=esc["odontologo"].id,
        ),
    )
    await _flush_rechazado(
        session,
        CierreCaja(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            fecha=date(2026, 11, 12),
            estado="conciliando",
            abierto_por=esc["odontologo"].id,
        ),
    )

    cerrado = CierreCaja(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        fecha=date(2026, 11, 13),
        estado=EstadoCierreCaja.CERRADO.value,
        total_sistema=Decimal("30000.00"),
        total_contado=Decimal("29500.00"),
        diferencia=Decimal("-500.00"),
        abierto_por=esc["odontologo"].id,
        cerrado_por=esc["odontologo"].id,
        cerrado_at=datetime(2026, 11, 13, 20, 0, tzinfo=UTC),
    )
    session.add(cerrado)
    await session.flush()
    assert cerrado.diferencia == Decimal("-500.00")


RAIZ = Path(__file__).resolve().parents[1]


def _tablas_sqlite(ruta_db: Path) -> set[str]:
    """Lee el catálogo de una DB SQLite sin abrir el event loop de los tests async."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {fila[0] for fila in filas}


def test_migracion_010_caja_senas_encadenada_con_grants_y_modelos() -> None:
    """La migración encadena con 009, otorga permisos a `turnos_app` y registra los modelos."""
    ruta_mig = RAIZ / "src" / "backend" / "alembic" / "versions" / "010_caja_senas.py"
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "010_caja_senas"' in contenido
    assert 'down_revision: str | None = "009_presupuestos_planes"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in contenido
    assert "sena, cierre_caja, movimiento_caja TO turnos_app" in contenido
    assert "REVOKE ALL PRIVILEGES ON TABLE" in contenido
    assert "sena, cierre_caja, movimiento_caja FROM turnos_app" in contenido

    contenido_env = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    for simbolo in ("Sena", "CierreCaja", "MovimientoCaja"):
        assert simbolo in contenido_env


def test_migracion_010_upgrade_y_downgrade_reversibles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R11: `alembic upgrade head` crea las tablas y `downgrade 009` las elimina sin residuos."""
    from alembic import command
    from alembic.config import Config

    ruta_db = tmp_path / "caja_migracion.db"
    monkeypatch.delenv("DATABASE_URL_OWNER", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{ruta_db.as_posix()}")

    cfg = Config(str(RAIZ / "src" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "src" / "backend" / "alembic"))

    command.upgrade(cfg, "head")
    tablas_nuevas = {"sena", "cierre_caja", "movimiento_caja"}
    assert tablas_nuevas.issubset(_tablas_sqlite(ruta_db))

    command.downgrade(cfg, "009_presupuestos_planes")
    assert not (tablas_nuevas & _tablas_sqlite(ruta_db))

    command.upgrade(cfg, "head")
    assert tablas_nuevas.issubset(_tablas_sqlite(ruta_db))
