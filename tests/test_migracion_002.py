"""Migración 002: tablas, índices y constraints de sesiones y tokens públicos (tarea 1.1).

Verifica el esquema realmente desplegado (alembic upgrade head + create_all) y
que los modelos ORM no hayan derivado del DDL.
"""

from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.refresh_token import RefreshToken
from app.domain.token_gestion import TokenGestion

RAIZ = Path(__file__).resolve().parents[1]


def _unicos(insp, tabla: str) -> set[tuple[str, ...]]:  # type: ignore[no-untyped-def]
    """Unique constraints + unique indexes (SQLite expone la unicidad como índice)."""
    columnas = {tuple(u["column_names"]) for u in (insp.get_unique_constraints(tabla) or [])}
    columnas |= {
        tuple(i["column_names"])
        for i in (insp.get_indexes(tabla) or [])
        if i.get("unique") and i.get("column_names")
    }
    return columnas


def _leer(conn) -> dict[str, object]:  # type: ignore[no-untyped-def]
    insp = inspect(conn.connection())
    return {
        "refresh_indexes": {i["name"] for i in insp.get_indexes("refresh_token")},
        "gestion_indexes": {i["name"] for i in insp.get_indexes("token_gestion")},
        "refresh_unique": _unicos(insp, "refresh_token"),
        "gestion_unique": _unicos(insp, "token_gestion"),
        "refresh_fks": {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in insp.get_foreign_keys("refresh_token")
        },
        "gestion_fks": {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in insp.get_foreign_keys("token_gestion")
        },
        "refresh_columns": {c["name"]: c["nullable"] for c in insp.get_columns("refresh_token")},
        "gestion_columns": {c["name"]: c["nullable"] for c in insp.get_columns("token_gestion")},
    }


async def _esquema(session: AsyncSession) -> dict[str, object]:
    return await session.run_sync(_leer)  # type: ignore[no-any-return]


async def test_002_crea_indices_de_consulta_por_tenant_y_familia(session: AsyncSession) -> None:
    esquema = await _esquema(session)

    assert {"ix_refresh_token_tenant_usuario", "ix_refresh_token_familia"} <= esquema[
        "refresh_indexes"
    ]
    assert "ix_token_gestion_tenant_recurso" in esquema["gestion_indexes"]


async def test_002_token_hash_es_unico_y_las_fks_apuntan_al_dueno(
    session: AsyncSession,
) -> None:
    esquema = await _esquema(session)

    assert ("token_hash",) in esquema["refresh_unique"]
    assert ("token_hash",) in esquema["gestion_unique"]
    assert ("tenant_id", "tenant") in esquema["refresh_fks"]
    assert ("usuario_id", "usuario") in esquema["refresh_fks"]
    assert ("tenant_id", "tenant") in esquema["gestion_fks"]


async def test_002_columnas_obligatorias_y_opcionales(session: AsyncSession) -> None:
    esquema = await _esquema(session)
    refresh = esquema["refresh_columns"]
    gestion = esquema["gestion_columns"]

    for columna in ("token_hash", "familia_id", "vence_at", "tenant_id", "usuario_id"):
        assert refresh[columna] is False, columna
    assert refresh["revocado_at"] is True
    assert refresh["reemplazado_por_id"] is True

    for columna in ("token_hash", "recurso", "recurso_id", "vence_at", "tenant_id"):
        assert gestion[columna] is False, columna
    assert gestion["revocado_at"] is True
    assert gestion["usado_at"] is True


async def test_los_modelos_orm_coinciden_con_el_ddl(session: AsyncSession) -> None:
    esquema = await _esquema(session)

    assert set(esquema["refresh_columns"]) == set(RefreshToken.__table__.columns.keys())
    assert set(esquema["gestion_columns"]) == set(TokenGestion.__table__.columns.keys())


def test_alembic_env_importa_los_modelos_de_sesiones() -> None:
    # Sin estos imports, un `alembic revision --autogenerate` futuro borraría las
    # tablas de C-03 al no verlas en `Base.metadata`.
    env = (RAIZ / "src" / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "app.domain.refresh_token" in env
    assert "app.domain.token_gestion" in env
