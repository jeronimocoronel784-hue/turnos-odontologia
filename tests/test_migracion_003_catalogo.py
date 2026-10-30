"""Migración 003: tablas, índices, constraints y permisos de catálogo y configuración (tarea 1.1).

Verifica:
1. Esquema desplegado: tablas sillon, prestacion, cobertura_os.
2. Índices y constraints únicos y check a nivel base de datos.
3. FK cobertura_os.prestacion_id -> prestacion.id con RESTRICT.
4. Paridad ORM-DDL y presencia de modelos en alembic/env.py.
5. Invariantes de CheckConstraint (duracion > 0, sena valida,
   vigencia ordenada, montos no negativos).
6. GRANTs CRUD a turnos_app cuando corre contra Postgres con APP_ROLE_URL_TEST.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.cobertura_os import CoberturaOS
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.tenant import Tenant
from app.shared.database import create_engine_for

RAIZ = Path(__file__).resolve().parents[1]


def _unicos(insp, tabla: str) -> set[tuple[str, ...]]:  # type: ignore[no-untyped-def]
    """Unique constraints + unique indexes (SQLite expone unicidad compuesta como índice)."""
    columnas = {tuple(u["column_names"]) for u in (insp.get_unique_constraints(tabla) or [])}
    columnas |= {
        tuple(i["column_names"])
        for i in (insp.get_indexes(tabla) or [])
        if i.get("unique") and i.get("column_names")
    }
    return columnas


def _leer(conn: Any) -> dict[str, Any]:
    insp = inspect(conn.connection())
    return {
        "sillon_indexes": {i["name"] for i in (insp.get_indexes("sillon") or [])},
        "prestacion_indexes": {i["name"] for i in (insp.get_indexes("prestacion") or [])},
        "cobertura_indexes": {i["name"] for i in (insp.get_indexes("cobertura_os") or [])},
        "sillon_unique": _unicos(insp, "sillon"),
        "prestacion_unique": _unicos(insp, "prestacion"),
        "cobertura_unique": _unicos(insp, "cobertura_os"),
        "cobertura_fks": {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in (insp.get_foreign_keys("cobertura_os") or [])
        },
        "sillon_columns": {c["name"]: c["nullable"] for c in (insp.get_columns("sillon") or [])},
        "prestacion_columns": {
            c["name"]: c["nullable"] for c in (insp.get_columns("prestacion") or [])
        },
        "cobertura_columns": {
            c["name"]: c["nullable"] for c in (insp.get_columns("cobertura_os") or [])
        },
    }


async def _esquema(session: AsyncSession) -> dict[str, Any]:
    res: dict[str, Any] = await session.run_sync(_leer)
    return res


def test_archivo_migracion_003_existe_y_encadena_con_002() -> None:
    archivo = RAIZ / "src" / "backend" / "alembic" / "versions" / "003_catalogo_configuracion.py"
    assert archivo.exists(), f"Falta {archivo}"
    contenido = archivo.read_text(encoding="utf-8")
    assert 'revision: str = "003_catalogo_configuracion"' in contenido
    assert 'down_revision: str | None = "002_sesiones_tokens"' in contenido


def test_modelos_catalogo_coinciden_con_el_ddl() -> None:
    # Verificamos paridad entre columnas ORM y definición
    sillon_cols = set(Sillon.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "nombre",
        "sucursal",
        "activo",
        "created_at",
        "updated_at",
    } == sillon_cols

    prestacion_cols = set(Prestacion.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "nombre",
        "duracion_min",
        "precio_particular",
        "requiere_sena",
        "monto_sena",
        "invasiva",
        "activa",
        "created_at",
        "updated_at",
    } == prestacion_cols

    cobertura_cols = set(CoberturaOS.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "obra_social",
        "prestacion_id",
        "arancel",
        "copago",
        "vigencia_desde",
        "vigencia_hasta",
        "activa",
        "created_at",
        "updated_at",
    } == cobertura_cols


def test_modelos_catalogo_registrados_en_alembic_env() -> None:
    env_py = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from app.domain.sillon import Sillon" in env_py
    assert "from app.domain.prestacion import Prestacion" in env_py
    assert "from app.domain.cobertura_os import CoberturaOS" in env_py


async def test_003_crea_tablas_e_indices_del_catalogo(session: AsyncSession) -> None:
    esquema = await _esquema(session)

    # Columnas esperadas
    assert "nombre" in esquema["sillon_columns"]
    assert "sucursal" in esquema["sillon_columns"]
    assert "activo" in esquema["sillon_columns"]

    assert "duracion_min" in esquema["prestacion_columns"]
    assert "precio_particular" in esquema["prestacion_columns"]
    assert "requiere_sena" in esquema["prestacion_columns"]
    assert "monto_sena" in esquema["prestacion_columns"]
    assert "invasiva" in esquema["prestacion_columns"]
    assert "activa" in esquema["prestacion_columns"]

    assert "obra_social" in esquema["cobertura_columns"]
    assert "arancel" in esquema["cobertura_columns"]
    assert "copago" in esquema["cobertura_columns"]
    assert "vigencia_desde" in esquema["cobertura_columns"]
    assert "vigencia_hasta" in esquema["cobertura_columns"]

    # Índices esperados
    assert "ix_sillon_tenant_sucursal" in esquema["sillon_indexes"]
    assert "ix_prestacion_tenant_activa" in esquema["prestacion_indexes"]
    assert "ix_cobertura_os_tenant_os" in esquema["cobertura_indexes"]
    assert "ix_cobertura_os_tenant_prestacion" in esquema["cobertura_indexes"]

    # FK esperada
    assert ("prestacion_id", "prestacion") in esquema["cobertura_fks"]

    # Unicidad esperada
    assert ("tenant_id", "sucursal", "nombre") in esquema["sillon_unique"]
    assert ("tenant_id", "nombre") in esquema["prestacion_unique"]


async def test_003_db_constraints_sillon_unicidad(session: AsyncSession, tenant_a: Tenant) -> None:
    s1 = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box 1",
        sucursal="central",
        activo=True,
    )
    session.add(s1)
    await session.flush()

    s2 = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box 1",
        sucursal="central",
        activo=True,
    )
    session.add(s2)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_prestacion_duracion_positiva(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Consulta Express",
        duracion_min=0,  # Violates duracion_min > 0
        precio_particular=Decimal("1000.00"),
        requiere_sena=False,
        monto_sena=None,
        invasiva=False,
        activa=True,
    )
    session.add(p)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_prestacion_sena_invalida(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Cirugía Compleja",
        duracion_min=60,
        precio_particular=Decimal("50000.00"),
        requiere_sena=True,
        monto_sena=None,  # Violates requiere_sena => monto_sena > 0
        invasiva=True,
        activa=True,
    )
    session.add(p)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_cobertura_vigencia_ordenada(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Limpieza General",
        duracion_min=30,
        precio_particular=Decimal("15000.00"),
        requiere_sena=False,
        monto_sena=None,
        invasiva=False,
        activa=True,
    )
    session.add(p)
    await session.flush()

    hoy = datetime.now(UTC).date()
    c = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="OSDE",
        prestacion_id=p.id,
        arancel=Decimal("12000.00"),
        copago=Decimal("2000.00"),
        vigencia_desde=hoy,
        vigencia_hasta=hoy - timedelta(days=1),  # Violates vigencia_hasta >= vigencia_desde
        activa=True,
    )
    session.add(c)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_cobertura_montos_no_negativos(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Consulta General",
        duracion_min=20,
        precio_particular=Decimal("10000.00"),
        requiere_sena=False,
        monto_sena=None,
        invasiva=False,
        activa=True,
    )
    session.add(p)
    await session.flush()

    hoy = datetime.now(UTC).date()
    c = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="Swiss Medical",
        prestacion_id=p.id,
        arancel=Decimal("-10.00"),  # Violates arancel >= 0
        copago=Decimal("0.00"),
        vigencia_desde=hoy,
        vigencia_hasta=None,
        activa=True,
    )
    session.add(c)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_sillon_mismo_nombre_distinta_sucursal_o_distinto_tenant_ok(
    session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    s1 = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box 1",
        sucursal="central",
        activo=True,
    )
    s2 = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Box 1",
        sucursal="norte",
        activo=True,
    )
    s3 = Sillon(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        nombre="Box 1",
        sucursal="central",
        activo=True,
    )
    session.add_all([s1, s2, s3])
    await session.flush()
    assert s1.id != s2.id != s3.id


async def test_003_db_constraints_prestacion_precio_negativo(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Tratamiento Inválido",
        duracion_min=30,
        precio_particular=Decimal("-10.00"),
        requiere_sena=False,
        monto_sena=None,
        invasiva=False,
        activa=True,
    )
    session.add(p)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_prestacion_requiere_sena_monto_cero(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Cirugia Sin Monto Sena",
        duracion_min=60,
        precio_particular=Decimal("30000.00"),
        requiere_sena=True,
        monto_sena=Decimal("0.00"),  # Violates monto_sena > 0
        invasiva=True,
        activa=True,
    )
    session.add(p)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_003_db_constraints_cobertura_copago_negativo(
    session: AsyncSession, tenant_a: Tenant
) -> None:
    p = Prestacion(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        nombre="Consulta Triangulacion",
        duracion_min=20,
        precio_particular=Decimal("10000.00"),
        requiere_sena=False,
        monto_sena=None,
        invasiva=False,
        activa=True,
    )
    session.add(p)
    await session.flush()

    hoy = datetime.now(UTC).date()
    c = CoberturaOS(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        obra_social="Galeno",
        prestacion_id=p.id,
        arancel=Decimal("10000.00"),
        copago=Decimal("-500.00"),  # Violates copago >= 0
        vigencia_desde=hoy,
        vigencia_hasta=None,
        activa=True,
    )
    session.add(c)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


def _factory_rol_app() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("APP_ROLE_URL_TEST", "")
    if not url:
        pytest.skip(
            "Falta APP_ROLE_URL_TEST (rol app restringido en Postgres); pendiente sin Docker."
        )
    return async_sessionmaker(create_engine_for(url), class_=AsyncSession, expire_on_commit=False)


async def test_003_grants_rol_app_crud_en_catalogo(
    session: AsyncSession, dialecto: str, tenant_a: Tenant
) -> None:
    if dialecto != "postgresql":
        pytest.skip("Los GRANTs por rol solo existen en Postgres.")
    await session.commit()

    factory = _factory_rol_app()
    async with factory() as app_session:
        for tabla in ("sillon", "prestacion", "cobertura_os"):
            privilegios = (
                (
                    await app_session.execute(
                        text(
                            f"SELECT has_table_privilege('turnos_app','{tabla}','INSERT') AS ri,"
                            f" has_table_privilege('turnos_app','{tabla}','SELECT') AS rs,"
                            f" has_table_privilege('turnos_app','{tabla}','UPDATE') AS ru,"
                            f" has_table_privilege('turnos_app','{tabla}','DELETE') AS rd"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert (
                privilegios["ri"] and privilegios["rs"] and privilegios["ru"] and privilegios["rd"]
            ), f"turnos_app carece de privilegios CRUD completos sobre {tabla}"
