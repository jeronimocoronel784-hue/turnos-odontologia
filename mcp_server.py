"""Servidor MCP para turnos-odontologia compatible con mcp 2.x en Windows (stdio)."""

import json
import os
import sys
from typing import Any

import asyncpg
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

# Fuerza salida sin buffer en Windows para evitar timeouts de stdio en MCP Inspector
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)

load_dotenv()

server = MCPServer("turnos-odontologia")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL_MCP",
    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/turnos"),
)


async def get_connection() -> asyncpg.Connection:
    """Abre una conexión asíncrona a PostgreSQL adaptando el DSN para ejecución local."""
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    if "@db:" in dsn:
        dsn = dsn.replace("@db:", "@localhost:")
    return await asyncpg.connect(dsn, timeout=5.0)


@server.tool()
async def consultar_prestaciones() -> str:
    """Devuelve el listado de prestaciones odontológicas registradas y activas."""
    try:
        conn = await get_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT id, nombre, duracion_min, precio_particular,
                       requiere_sena, monto_sena, invasiva, activa
                FROM prestacion
                WHERE activa = TRUE
                ORDER BY nombre ASC;
                """
            )
            data: list[dict[str, Any]] = [dict(r) for r in rows]
            return json.dumps(data, ensure_ascii=False, default=str, indent=2)
        finally:
            await conn.close()
    except Exception as exc:
        return json.dumps(
            {"error": f"Error al consultar prestaciones: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


@server.tool()
async def buscar_paciente_por_dni(dni: str) -> str:
    """Busca los datos de un paciente por su número de DNI."""
    dni_limpio = dni.replace(".", "").replace("-", "").strip()
    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, nombre, dni, email, telefono, optin_wa, activo
                FROM paciente
                WHERE dni = $1
                LIMIT 1;
                """,
                dni_limpio,
            )
            if not row:
                return json.dumps(
                    {"encontrado": False, "mensaje": f"No se encontró ningún paciente con DNI {dni_limpio}."},
                    ensure_ascii=False,
                )
            return json.dumps(dict(row), ensure_ascii=False, default=str, indent=2)
        finally:
            await conn.close()
    except Exception as exc:
        return json.dumps(
            {"error": f"Error al buscar paciente: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


if __name__ == '__main__':
    server.run(transport='stdio')
