"""Alembic async (SQLAlchemy 2.0). URL desde DATABASE_URL_OWNER (DDL/seed, D4) o DATABASE_URL.

Corre con el rol owner: crea tablas + GRANTs al rol app (ver migración 001).
En SQLite (dev local sin Docker) el DDL de roles se saltea solo.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.domain.auditoria import Auditoria  # noqa: F401
from app.domain.tenant import Tenant  # noqa: F401
from app.domain.usuario import Usuario  # noqa: F401
from app.infrastructure.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = os.getenv("DATABASE_URL_OWNER") or os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Che, falta DATABASE_URL_OWNER (o DATABASE_URL) para migrar.")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _hacer(engine_config: dict) -> None:  # type: ignore[type-arg]
    async def _run() -> None:
        engine = async_engine_from_config(
            engine_config, prefix="sqlalchemy.", poolclass=pool.NullPool
        )
        async with engine.connect() as connection:
            await connection.run_sync(_migrar)
        await engine.dispose()

    asyncio.run(_run())


def _migrar(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    seccion = config.get_section(config.config_ini_section, {})
    seccion["sqlalchemy.url"] = _url()
    _hacer(dict(seccion))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
