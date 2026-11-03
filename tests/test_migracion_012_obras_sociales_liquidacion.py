"""Migración 012: liquidacion_os y liquidacion_detalle (C-13, tarea 2.2, D3/D4/D6).

Verifica:
1. Esquema desplegado: columnas, índices y únicos parciales del design.
2. Constraints de cabecera: estado del enum, período de 6, totales y baja lógica con motivo.
3. Constraints de detalle: montos, débito con motivo y período de 6.
4. Un único borrador por OS/período (D6) y liberación del turno al anular (D3/RN-OS-02).
5. Encadenamiento con 011, GRANT/REVOKE de `turnos_app` y round-trip upgrade/downgrade.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.liquidacion_os import (
    EstadoLiquidacionOS,
    LiquidacionOS,
    LiquidacionOSDetalle,
)
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.domain.turno import EstadoTurno, OrigenTurno, Turno
from app.domain.usuario import RolUsuario, Usuario

RAIZ = Path(__file__).resolve().parents[1]
CERO = Decimal("0.00")


async def _escenario(session: AsyncSession, tenant: Tenant) -> dict[str, Any]:
    """Profesional, paciente, sillón, prestación, dos turnos y un usuario creador."""
    usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="odonto-liquidacion-012@consultorio.test",
        nombre="Dr. Liquidación",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-50120",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Tomás Liquidación",
        dni="33555444",
        telefono="+5491166667777",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box OS", activo=True)
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Consulta OS",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([usuario, paciente, sillon, prestacion])
    await session.flush()

    turnos: list[Turno] = []
    for hora in (9, 11):
        turno = Turno(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            paciente_id=paciente.id,
            profesional_id=usuario.id,
            sillon_id=sillon.id,
            prestacion_id=prestacion.id,
            inicio=datetime(2026, 11, 10, hora, 0, tzinfo=UTC),
            fin=datetime(2026, 11, 10, hora + 1, 0, tzinfo=UTC),
            estado=EstadoTurno.FINALIZADO.value,
            origen=OrigenTurno.PRESENCIAL.value,
        )
        session.add(turno)
        turnos.append(turno)
    await session.flush()
    return {"usuario": usuario, "turnos": turnos, "prestacion": prestacion}


def _liquidacion(tenant: Tenant, esc: dict[str, Any], **overrides: Any) -> LiquidacionOS:
    datos: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "obra_social": "OSDE",
        "periodo": "202611",
        "estado": EstadoLiquidacionOS.BORRADOR.value,
        "total": Decimal("50000.00"),
        "created_by": esc["usuario"].id,
    }
    datos.update(overrides)
    return LiquidacionOS(**datos)


def _presentada(tenant: Tenant, esc: dict[str, Any], **overrides: Any) -> LiquidacionOS:
    datos: dict[str, Any] = {
        "estado": EstadoLiquidacionOS.PRESENTADA.value,
        "presentada_por": esc["usuario"].id,
        "presentada_at": datetime(2026, 11, 30, 12, 0, tzinfo=UTC),
    }
    datos.update(overrides)
    return _liquidacion(tenant, esc, **datos)


def _detalle(
    tenant: Tenant, liquidacion: LiquidacionOS, turno_id: uuid.UUID, **overrides: Any
) -> LiquidacionOSDetalle:
    datos: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "liquidacion_id": liquidacion.id,
        "turno_id": turno_id,
        "obra_social": liquidacion.obra_social,
        "periodo": liquidacion.periodo,
        "monto_reclamado": Decimal("50000.00"),
        "arancel_vencido": False,
        "vigente": True,
    }
    datos.update(overrides)
    return LiquidacionOSDetalle(**datos)


async def _flush_rechazado(session: AsyncSession, *objetos: Any) -> None:
    """Agrega objetos dentro de un savepoint y exige que la DB los rechace (IntegrityError)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objetos)
            await session.flush()


async def test_esquema_tablas_liquidacion_os_y_detalle(session: AsyncSession) -> None:
    """Verifica columnas e índices de `liquidacion_os` y `liquidacion_detalle` (§04)."""
    conn = await session.connection()

    def _inspeccionar(sync_conn: Any) -> dict[str, Any]:
        insp = inspect(sync_conn)
        return {
            "cabecera": {c["name"] for c in insp.get_columns("liquidacion_os")},
            "detalle": {c["name"] for c in insp.get_columns("liquidacion_detalle")},
            "idx_cabecera": {i["name"] for i in insp.get_indexes("liquidacion_os")},
            "idx_detalle": {i["name"] for i in insp.get_indexes("liquidacion_detalle")},
            "uq_detalle": {c["name"] for c in insp.get_unique_constraints("liquidacion_detalle")},
        }

    info = await conn.run_sync(_inspeccionar)

    assert {
        "id",
        "tenant_id",
        "obra_social",
        "periodo",
        "estado",
        "total",
        "total_reconocido",
        "observaciones",
        "presentada_por",
        "presentada_at",
        "resuelta_por",
        "resuelta_at",
        "anulada_motivo",
        "created_by",
        "created_at",
        "updated_at",
    }.issubset(info["cabecera"])
    assert {
        "id",
        "tenant_id",
        "liquidacion_id",
        "turno_id",
        "obra_social",
        "periodo",
        "monto_reclamado",
        "monto_reconocido",
        "debito_motivo",
        "arancel_vencido",
        "vigente",
        "created_at",
        "updated_at",
    }.issubset(info["detalle"])

    assert "uq_liquidacion_os_borrador" in info["idx_cabecera"]
    assert "ix_liquidacion_os_tenant_os_periodo" in info["idx_cabecera"]
    assert "ix_liquidacion_os_tenant_estado" in info["idx_cabecera"]
    assert "uq_liquidacion_detalle_turno_abierto" in info["idx_detalle"]
    assert "ix_liquidacion_detalle_liquidacion_id" in info["idx_detalle"]
    assert "ix_liquidacion_detalle_tenant_turno" in info["idx_detalle"]
    assert "uq_liquidacion_detalle_turno" in info["uq_detalle"]


async def test_cabecera_rechaza_estado_periodo_y_totales_invalidos(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D4/D6: enum de estado cerrado, período de 6 caracteres y reconocido <= total."""
    esc = await _escenario(session, tenant_a)
    session.add(_liquidacion(tenant_a, esc))
    await session.flush()

    await _flush_rechazado(
        session,
        _liquidacion(tenant_a, esc, obra_social="SWISS", estado="conciliando"),
    )
    await _flush_rechazado(
        session,
        _liquidacion(tenant_a, esc, obra_social="IOMA", periodo="20261"),
    )
    await _flush_rechazado(
        session,
        _liquidacion(
            tenant_a,
            esc,
            obra_social="MEDIFE",
            total=Decimal("10000.00"),
            total_reconocido=Decimal("20000.00"),
        ),
    )
    await _flush_rechazado(
        session,
        _liquidacion(tenant_a, esc, obra_social="AVALIAN", total=Decimal("-1.00")),
    )


async def test_cabecera_exige_presentacion_y_motivo_de_anulacion(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D4/R7: `presentada` exige actor y fecha; `anulada` exige motivo no vacío."""
    esc = await _escenario(session, tenant_a)

    await _flush_rechazado(
        session, _liquidacion(tenant_a, esc, estado=EstadoLiquidacionOS.PRESENTADA.value)
    )
    await _flush_rechazado(
        session,
        _liquidacion(
            tenant_a,
            esc,
            obra_social="OSDE-B",
            estado=EstadoLiquidacionOS.ANULADA.value,
            anulada_motivo="   ",
        ),
    )
    await _flush_rechazado(
        session,
        _liquidacion(
            tenant_a,
            esc,
            obra_social="OSDE-C",
            estado=EstadoLiquidacionOS.PAGADA.value,
            presentada_por=esc["usuario"].id,
            presentada_at=datetime(2026, 11, 30, 12, 0, tzinfo=UTC),
        ),
    )

    presentada = _presentada(tenant_a, esc, obra_social="OSDE-D")
    session.add(presentada)
    await session.flush()
    assert presentada.estado == EstadoLiquidacionOS.PRESENTADA.value


async def test_detalle_rechaza_montos_invertidos_y_debito_sin_motivo(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D2/US-041: reconocido <= reclamado y todo recorte exige `debito_motivo`."""
    esc = await _escenario(session, tenant_a)
    liquidacion = _liquidacion(tenant_a, esc)
    otra = _liquidacion(tenant_a, esc, obra_social="IOMA")
    session.add_all([liquidacion, otra])
    await session.flush()
    turno_uno, turno_dos = esc["turnos"]

    session.add(_detalle(tenant_a, liquidacion, turno_uno.id))
    await session.flush()

    await _flush_rechazado(
        session,
        _detalle(tenant_a, otra, turno_dos.id, monto_reconocido=Decimal("60000.00")),
    )
    await _flush_rechazado(
        session,
        _detalle(
            tenant_a,
            otra,
            turno_dos.id,
            monto_reconocido=Decimal("40000.00"),
            debito_motivo="   ",
        ),
    )
    await _flush_rechazado(session, _detalle(tenant_a, otra, turno_dos.id, periodo="2026"))

    con_motivo = _detalle(
        tenant_a,
        otra,
        turno_dos.id,
        monto_reconocido=Decimal("40000.00"),
        debito_motivo="Arancel fuera de nomenclador",
    )
    session.add(con_motivo)
    await session.flush()
    assert con_motivo.monto_reconocido == Decimal("40000.00")


async def test_un_solo_borrador_por_os_y_periodo_sin_bloquear_complementarias(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D6: el índice parcial bloquea el segundo borrador y deja libres las complementarias."""
    esc = await _escenario(session, tenant_a)
    session.add(_liquidacion(tenant_a, esc))
    await session.flush()

    await _flush_rechazado(session, _liquidacion(tenant_a, esc))

    session.add(_liquidacion(tenant_a, esc, obra_social="IOMA"))
    session.add(_liquidacion(tenant_a, esc, obra_social="OSDE", periodo="202610"))
    session.add(_presentada(tenant_a, esc, obra_social="MEDIFE"))
    await session.flush()

    del_mismo_borrador = (
        (
            await session.execute(
                select(LiquidacionOS).where(
                    LiquidacionOS.tenant_id == tenant_a.id,
                    LiquidacionOS.obra_social == "OSDE",
                    LiquidacionOS.periodo == "202611",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(del_mismo_borrador) == 1


async def test_turno_no_se_duplica_abierto_y_se_libera_al_anular(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """RN-OS-02 / D3: dos filas abiertas del mismo turno chocan; con `vigente = false` conviven."""
    esc = await _escenario(session, tenant_a)
    primera = _liquidacion(tenant_a, esc)
    segunda = _presentada(tenant_a, esc)
    session.add_all([primera, segunda])
    await session.flush()
    turno_uno, turno_dos = esc["turnos"]

    session.add(_detalle(tenant_a, primera, turno_uno.id))
    await session.flush()

    await _flush_rechazado(session, _detalle(tenant_a, segunda, turno_uno.id))

    cerrada = _detalle(
        tenant_a,
        segunda,
        turno_uno.id,
        monto_reconocido=CERO,
        debito_motivo="Turno liquidado dos veces",
        vigente=False,
    )
    session.add(cerrada)
    await session.flush()
    assert cerrada.vigente is False

    # Baja lógica: anular libera el turno de la liquidación anulada.
    anulada = _liquidacion(tenant_a, esc, obra_social="IOMA", periodo="202611")
    session.add(anulada)
    await session.flush()
    fila_anulada = _detalle(tenant_a, anulada, turno_dos.id)
    session.add(fila_anulada)
    await session.flush()
    anulada.estado = EstadoLiquidacionOS.ANULADA.value
    anulada.anulada_motivo = "Se liquidó por error"
    fila_anulada.vigente = False
    await session.flush()

    nueva = _liquidacion(tenant_a, esc, obra_social="IOMA", periodo="202611")
    session.add(nueva)
    await session.flush()
    session.add(_detalle(tenant_a, nueva, turno_dos.id))
    await session.flush()

    abiertos = (
        (
            await session.execute(
                select(LiquidacionOSDetalle).where(
                    LiquidacionOSDetalle.tenant_id == tenant_a.id,
                    LiquidacionOSDetalle.turno_id == turno_dos.id,
                    LiquidacionOSDetalle.vigente.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(abiertos) == 1
    assert abiertos[0].liquidacion_id == nueva.id


def test_migracion_012_encadenada_con_grants_y_modelos() -> None:
    """La migración encadena con 011, otorga permisos a `turnos_app` y registra los modelos."""
    ruta_mig = (
        RAIZ / "src" / "backend" / "alembic" / "versions" / "012_obras_sociales_liquidacion.py"
    )
    assert ruta_mig.exists()
    contenido = ruta_mig.read_text(encoding="utf-8")
    assert 'revision: str = "012_obras_sociales_liquidacion"' in contenido
    assert 'down_revision: str | None = "011_mercadopago_webhooks"' in contenido
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in contenido
    assert "liquidacion_os, liquidacion_detalle TO turnos_app" in contenido
    assert "REVOKE ALL PRIVILEGES ON TABLE" in contenido
    assert "liquidacion_os, liquidacion_detalle FROM turnos_app" in contenido

    contenido_env = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    for simbolo in ("LiquidacionOS", "LiquidacionOSDetalle"):
        assert simbolo in contenido_env

    contenido_conftest = (RAIZ / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "app.domain.liquidacion_os" in contenido_conftest
    assert '"liquidacion_detalle"' in contenido_conftest
    assert '"liquidacion_os"' in contenido_conftest


def _tablas_sqlite(ruta_db: Path) -> set[str]:
    """Lee el catálogo de una DB SQLite sin abrir el event loop de los tests async."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {fila[0] for fila in filas}


def _indices_sqlite(ruta_db: Path) -> set[str]:
    """Índices del catálogo SQLite (incluye los únicos parciales de D3/D6)."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    return {fila[0] for fila in filas}


def test_migracion_012_upgrade_y_downgrade_reversibles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R11: `upgrade head` crea tablas e índices y `downgrade 011` los elimina sin residuos."""
    from alembic import command
    from alembic.config import Config

    ruta_db = tmp_path / "liquidacion_migracion.db"
    monkeypatch.delenv("DATABASE_URL_OWNER", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{ruta_db.as_posix()}")

    cfg = Config(str(RAIZ / "src" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "src" / "backend" / "alembic"))

    tablas_nuevas = {"liquidacion_os", "liquidacion_detalle"}
    indices_nuevos = {
        "uq_liquidacion_os_borrador",
        "ix_liquidacion_os_tenant_os_periodo",
        "ix_liquidacion_os_tenant_estado",
        "uq_liquidacion_detalle_turno_abierto",
        "ix_liquidacion_detalle_liquidacion_id",
        "ix_liquidacion_detalle_tenant_turno",
    }

    command.upgrade(cfg, "head")
    assert tablas_nuevas.issubset(_tablas_sqlite(ruta_db))
    assert indices_nuevos.issubset(_indices_sqlite(ruta_db))

    command.downgrade(cfg, "011_mercadopago_webhooks")
    assert not (tablas_nuevas & _tablas_sqlite(ruta_db))
    assert not (indices_nuevos & _indices_sqlite(ruta_db))

    command.upgrade(cfg, "head")
    assert tablas_nuevas.issubset(_tablas_sqlite(ruta_db))
    assert indices_nuevos.issubset(_indices_sqlite(ruta_db))
