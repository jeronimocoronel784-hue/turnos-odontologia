"""Migración 013: reclamo único por obra social y período (C-13, tarea E.7, D12).

Verifica:
1. `liquidacion_detalle.reclamado` y `liquidacion_os.turnos_sin_cobertura` con sus defaults
   (y que el metadata del ORM genere el mismo esquema que Alembic).
2. El índice único parcial `uq_liquidacion_detalle_turno_reclamado` rechaza el segundo
   reclamo del mismo turno por obra social/período (incluido `"OSDE"` vs `"osde"`), y sólo
   la anulación lo libera (el pago no).
3. El backfill libera los reclamos de liquidaciones `anulada` y los duplicados
   preexistentes, conservando el más antiguo por `(created_at, id)`.
4. La migración es reversible: `upgrade head` → `downgrade 012_obras_sociales_liquidacion`
   → `upgrade head`.

R11: la migración corre contra una DB real (SQLite temporal en el loop de desarrollo y
Postgres en el entorno de verificación); los datos son sintéticos.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
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
REVISION_012 = "012_obras_sociales_liquidacion"
REVISION_013 = "013_liquidacion_claim_unico"

# (clave, estado, obra_social, período, turno, created_at, vigente, reclamo esperado)
ESCENARIOS_PRE_013 = (
    # El mismo turno reclamado dos veces: la `012` lo permite (la segunda fila está pagada
    # y por eso no es `vigente`); la `013` conserva el reclamo más antiguo.
    ("vieja", "borrador", "OSDE", "202611", "t1", "2026-11-01 09:00:00", 1, 1),
    ("nueva", "presentada", "OSDE", "202611", "t1", "2026-11-02 09:00:00", 0, 0),
    # La anulación libera el reclamo.
    ("anulada", "anulada", "IOMA", "202611", "t2", "2026-11-03 09:00:00", 0, 0),
    # El pago NO libera el reclamo: sigue vigente.
    ("pagada", "pagada", "OSDE", "202611", "t3", "2026-11-04 09:00:00", 0, 1),
    # La anulada es más antigua que la vigente: la vigente conserva el reclamo (si no, el
    # turno quedaría reclamable otra vez).
    ("anulada_vieja", "anulada", "SWISS", "202611", "t4", "2026-11-01 08:00:00", 0, 0),
    ("pagada_nueva", "pagada", "SWISS", "202611", "t4", "2026-11-05 09:00:00", 0, 1),
)


def _config_alembic() -> Any:
    """Config de Alembic apuntando al proyecto (SQLite temporal)."""
    from alembic.config import Config

    cfg = Config(str(RAIZ / "src" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "src" / "backend" / "alembic"))
    return cfg


def _migrar(
    ruta_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
    *,
    abajo: bool = False,
) -> None:
    """Corre `upgrade`/`downgrade` de Alembic sobre el SQLite temporal."""
    from alembic import command

    monkeypatch.delenv("DATABASE_URL_OWNER", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{ruta_db.as_posix()}")
    cfg = _config_alembic()
    if abajo:
        command.downgrade(cfg, revision)
    else:
        command.upgrade(cfg, revision)


def _columnas_sqlite(ruta_db: Path, tabla: str) -> dict[str, dict[str, Any]]:
    """Columnas de una tabla SQLite (`PRAGMA table_info`)."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute(f"PRAGMA table_info({tabla})").fetchall()
    return {
        fila[1]: {"tipo": fila[2], "notnull": fila[3], "dflt_value": fila[4], "pk": fila[5]}
        for fila in filas
    }


def _indices_sqlite(ruta_db: Path) -> dict[str, str]:
    """Índices del catálogo SQLite (nombre → DDL)."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    return {fila[0]: (fila[1] or "") for fila in filas}


def _turno_determinista(clave: str) -> str:
    """`turno_id` estable (CHAR(32) hexadecimal) para las siembras del backfill."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"turno-{clave}").hex


def _sembrar_reclamos_pre_013(ruta_db: Path) -> tuple[str, dict[str, str]]:
    """Siembra los reclamos previos a la `013` sobre el esquema de la `012`.

    Devuelve el `tenant_id` sembrado y el mapa `clave del escenario` → `id` del detalle.
    """
    import sqlite3

    tenant_id = uuid.uuid4().hex
    usuario_id = uuid.uuid4().hex
    liquidacion_ids: dict[str, str] = {}
    detalle_ids: dict[str, str] = {}

    with sqlite3.connect(ruta_db) as conexion:
        for escenario in ESCENARIOS_PRE_013:
            clave, estado, obra_social, periodo, turno, created_at, vigente, _ = escenario
            liquidacion_id = uuid.uuid4().hex
            liquidacion_ids[clave] = liquidacion_id
            presented = estado in {"presentada", "pagada", "con_debitos"}
            resuelta = estado in {"pagada", "con_debitos"}
            conexion.execute(
                """
                INSERT INTO liquidacion_os (
                    id, tenant_id, obra_social, periodo, estado, total, total_reconocido,
                    observaciones, presentada_por, presentada_at, resuelta_por, resuelta_at,
                    anulada_motivo, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    liquidacion_id,
                    tenant_id,
                    obra_social,
                    periodo,
                    estado,
                    1000.00,
                    1000.00 if resuelta else None,
                    usuario_id if presented else None,
                    "2026-11-05 10:00:00" if presented else None,
                    usuario_id if resuelta else None,
                    "2026-11-06 10:00:00" if resuelta else None,
                    "Se liquidó por error" if estado == "anulada" else None,
                    usuario_id,
                    created_at,
                    created_at,
                ),
            )

            detalle_id = uuid.uuid4().hex
            detalle_ids[clave] = detalle_id
            conexion.execute(
                """
                INSERT INTO liquidacion_detalle (
                    id, tenant_id, liquidacion_id, turno_id, obra_social, periodo,
                    monto_reclamado, monto_reconocido, debito_motivo, arancel_vencido,
                    vigente, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?, ?)
                """,
                (
                    detalle_id,
                    tenant_id,
                    liquidacion_id,
                    _turno_determinista(turno),
                    obra_social,
                    periodo,
                    1000.00,
                    vigente,
                    created_at,
                    created_at,
                ),
            )
        conexion.commit()
    return tenant_id, detalle_ids


def _reclamos(ruta_db: Path) -> dict[str, int]:
    """Mapa `detalle_id` → `reclamado` de la base migrada."""
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        filas = conexion.execute("SELECT id, reclamado FROM liquidacion_detalle").fetchall()
    return {fila[0]: fila[1] for fila in filas}


async def _turno_finalizado(session: AsyncSession, tenant: Tenant) -> tuple[uuid.UUID, uuid.UUID]:
    """Alta mínima: profesional, paciente, sillón, prestación y un turno finalizado."""
    usuario = Usuario(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"odonto-013-{tenant.slug}@consultorio.test",
        nombre="Dra. Reclamo",
        password_hash="hash-test",
        rol=RolUsuario.ODONTOLOGO,
        matricula="MP-01300",
        activo=True,
    )
    paciente = Paciente(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Paciente Reclamo",
        dni="30111222",
        telefono="+5491155554444",
        optin_wa=True,
        activo=True,
    )
    sillon = Sillon(id=uuid.uuid4(), tenant_id=tenant.id, nombre="Box Reclamo", activo=True)
    prestacion = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        nombre="Consulta Reclamo",
        duracion_min=30,
        precio_particular=Decimal("50000.00"),
        requiere_sena=False,
        invasiva=False,
        activa=True,
    )
    session.add_all([usuario, paciente, sillon, prestacion])
    await session.flush()

    inicio = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    turno = Turno(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        paciente_id=paciente.id,
        profesional_id=usuario.id,
        sillon_id=sillon.id,
        prestacion_id=prestacion.id,
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        estado=EstadoTurno.FINALIZADO.value,
        origen=OrigenTurno.PRESENCIAL.value,
    )
    session.add(turno)
    await session.flush()
    return turno.id, usuario.id


def _cabecera(
    tenant: Tenant,
    usuario_id: uuid.UUID,
    *,
    obra_social: str,
    periodo: str = "202611",
    estado: EstadoLiquidacionOS = EstadoLiquidacionOS.BORRADOR,
) -> LiquidacionOS:
    """Cabecera de liquidación válida para los constraints de la `012`."""
    datos: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "obra_social": obra_social,
        "periodo": periodo,
        "estado": estado.value,
        "total": Decimal("50000.00"),
        "created_by": usuario_id,
    }
    if estado is not EstadoLiquidacionOS.BORRADOR:
        datos["presentada_por"] = usuario_id
        datos["presentada_at"] = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
    return LiquidacionOS(**datos)


def _detalle(
    tenant: Tenant,
    cabecera: LiquidacionOS,
    turno_id: uuid.UUID,
    **overrides: Any,
) -> LiquidacionOSDetalle:
    """Fila de detalle con el reclamo vigente (`reclamado = true` por default)."""
    datos: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "liquidacion_id": cabecera.id,
        "turno_id": turno_id,
        "obra_social": cabecera.obra_social,
        "periodo": cabecera.periodo,
        "monto_reclamado": Decimal("50000.00"),
        "arancel_vencido": False,
        "vigente": True,
    }
    datos.update(overrides)
    return LiquidacionOSDetalle(**datos)


# ---------------------------------------------------------------------------
# 1. Columnas nuevas
# ---------------------------------------------------------------------------


def test_la_migracion_013_agrega_reclamado_y_turnos_sin_cobertura(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D12: la `013` agrega las dos columnas y el ORM declara el mismo esquema."""
    ruta_db = tmp_path / "liquidacion_013_columnas.db"
    _migrar(ruta_db, monkeypatch, "head")

    detalle = _columnas_sqlite(ruta_db, "liquidacion_detalle")
    assert "reclamado" in detalle
    assert detalle["reclamado"]["notnull"] == 1
    assert detalle["reclamado"]["dflt_value"] is not None

    cabecera = _columnas_sqlite(ruta_db, "liquidacion_os")
    assert "turnos_sin_cobertura" in cabecera
    assert cabecera["turnos_sin_cobertura"]["notnull"] == 1
    assert cabecera["turnos_sin_cobertura"]["dflt_value"] is not None

    # Los índices de la `013` reemplazan a los de la `012` y usan `lower(obra_social)`.
    indices = _indices_sqlite(ruta_db)
    assert "uq_liquidacion_detalle_turno_reclamado" in indices
    assert "uq_liquidacion_detalle_turno_abierto" not in indices
    assert "lower(obra_social)" in indices["uq_liquidacion_detalle_turno_reclamado"]
    assert "lower(obra_social)" in indices["uq_liquidacion_os_borrador"]

    # El metadata del ORM (`Base.metadata.create_all`) declara lo mismo que Alembic.
    columna_reclamado = LiquidacionOSDetalle.__table__.c.reclamado
    assert columna_reclamado.nullable is False
    assert columna_reclamado.default is not None
    assert columna_reclamado.default.arg is True

    columna_sin_cobertura = LiquidacionOS.__table__.c.turnos_sin_cobertura
    assert columna_sin_cobertura.nullable is False
    assert columna_sin_cobertura.default is not None
    assert columna_sin_cobertura.default.arg == 0


# ---------------------------------------------------------------------------
# 2. Índice de reclamo único
# ---------------------------------------------------------------------------


async def test_el_indice_reclamado_rechaza_el_segundo_reclamo(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    """D9/D12: un turno se reclama una sola vez por obra social y período."""
    turno_id, usuario_id = await _turno_finalizado(session, tenant_a)

    primera = _cabecera(tenant_a, usuario_id, obra_social="OSDE")
    session.add(primera)
    await session.flush()
    detalle_primero = _detalle(tenant_a, primera, turno_id)
    session.add(detalle_primero)
    await session.flush()

    # Misma obra social y período, con otra capitalización: el segundo reclamo se rechaza.
    segunda = _cabecera(
        tenant_a,
        usuario_id,
        obra_social="osde",
        estado=EstadoLiquidacionOS.PRESENTADA,
    )
    session.add(segunda)
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(_detalle(tenant_a, segunda, turno_id))
            await session.flush()

    # El pago NO libera el reclamo: el mismo turno sigue sin poder reclamarse.
    detalle_primero.vigente = False
    await session.flush()
    tercera = _cabecera(
        tenant_a,
        usuario_id,
        obra_social="OSDE",
        estado=EstadoLiquidacionOS.PRESENTADA,
    )
    session.add(tercera)
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(_detalle(tenant_a, tercera, turno_id))
            await session.flush()

    # Otra obra social u otro período: el turno se puede liquidar aparte.
    otra_os = _cabecera(tenant_a, usuario_id, obra_social="IOMA")
    session.add(otra_os)
    await session.flush()
    session.add(_detalle(tenant_a, otra_os, turno_id))
    await session.flush()

    otro_periodo = _cabecera(tenant_a, usuario_id, obra_social="OSDE", periodo="202610")
    session.add(otro_periodo)
    await session.flush()
    session.add(_detalle(tenant_a, otro_periodo, turno_id))
    await session.flush()

    # La anulación libera el reclamo: el turno vuelve a ser reclamable.
    primera.estado = EstadoLiquidacionOS.ANULADA.value
    primera.anulada_motivo = "Se liquidó por error"
    detalle_primero.reclamado = False
    await session.flush()

    liberada = _cabecera(tenant_a, usuario_id, obra_social="OSDE")
    session.add(liberada)
    await session.flush()
    session.add(_detalle(tenant_a, liberada, turno_id))
    await session.flush()


# ---------------------------------------------------------------------------
# 3. Backfill
# ---------------------------------------------------------------------------


def test_el_backfill_libera_los_reclamos_anulados_y_duplicados(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D9/D12: la `013` libera anulados y duplicados conservando el más antiguo."""
    import sqlite3

    ruta_db = tmp_path / "liquidacion_013_backfill.db"
    _migrar(ruta_db, monkeypatch, REVISION_012)
    tenant_id, detalle_ids = _sembrar_reclamos_pre_013(ruta_db)

    _migrar(ruta_db, monkeypatch, "head")

    reclamos = _reclamos(ruta_db)
    esperados = {escenario[0]: escenario[-1] for escenario in ESCENARIOS_PRE_013}
    for clave, detalle_id in detalle_ids.items():
        assert reclamos[detalle_id] == esperados[clave], f"reclamo inesperado en {clave}"

    # La garantía de DB quedó activa: el turno ya reclamado no se puede volver a reclamar.
    with sqlite3.connect(ruta_db) as conexion:
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                """
                INSERT INTO liquidacion_detalle (
                    id, tenant_id, liquidacion_id, turno_id, obra_social, periodo,
                    monto_reclamado, monto_reconocido, debito_motivo, arancel_vencido,
                    vigente, reclamado, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, 1, 1, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    tenant_id,
                    uuid.uuid4().hex,
                    _turno_determinista("t1"),
                    "OSDE",
                    "202611",
                    1000.00,
                    "2026-11-07 09:00:00",
                    "2026-11-07 09:00:00",
                ),
            )


# ---------------------------------------------------------------------------
# 4. Reversibilidad
# ---------------------------------------------------------------------------


def test_la_migracion_013_es_reversible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R11: `upgrade head` → `downgrade 012` → `upgrade head` deja el esquema como debe."""
    ruta_db = tmp_path / "liquidacion_013_reversible.db"
    _migrar(ruta_db, monkeypatch, "head")

    assert "reclamado" in _columnas_sqlite(ruta_db, "liquidacion_detalle")
    assert "turnos_sin_cobertura" in _columnas_sqlite(ruta_db, "liquidacion_os")
    assert "uq_liquidacion_detalle_turno_reclamado" in _indices_sqlite(ruta_db)

    _migrar(ruta_db, monkeypatch, REVISION_012, abajo=True)

    assert "reclamado" not in _columnas_sqlite(ruta_db, "liquidacion_detalle")
    assert "turnos_sin_cobertura" not in _columnas_sqlite(ruta_db, "liquidacion_os")
    indices = _indices_sqlite(ruta_db)
    assert "uq_liquidacion_detalle_turno_reclamado" not in indices
    assert "uq_liquidacion_detalle_turno_abierto" in indices
    assert "uq_liquidacion_os_borrador" in indices

    _migrar(ruta_db, monkeypatch, "head")

    assert "reclamado" in _columnas_sqlite(ruta_db, "liquidacion_detalle")
    assert "turnos_sin_cobertura" in _columnas_sqlite(ruta_db, "liquidacion_os")
    assert "uq_liquidacion_detalle_turno_reclamado" in _indices_sqlite(ruta_db)
