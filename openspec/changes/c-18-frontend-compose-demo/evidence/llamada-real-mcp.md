# Evidencia — llamada real al servidor MCP `turnos-odontologia`

- **Fecha**: 2026-11-12
- **Contexto**: verificación del servidor MCP propio del repo (`mcp_server.py`, stdio,
  documentado en `AGENTS.md` → "Servidor MCP: `turnos-odontologia`") con una llamada
  real `tools/list` + `tools/call`, usando el SDK `mcp` (`mcp>=2,<3`) instalado en el host.
- **Script cliente**: stdio client mínimo (`mcp.client.stdio` + `ClientSession`) que
  spawnea `python -u mcp_server.py` con `cwd` en la raíz del repo.

## Entorno de verificación (efímero)

- Contenedor temporal `mcp-verify-db` con `postgres:15.10` en el puerto **5433**
  (el Postgres nativo del host ocupa el 5432; ver `design.md` → riesgo R-1 del apply).
- Rol `turnos_app` creado manualmente replicando `db/init/01-roles.sh`
  (LOGIN + `GRANT CONNECT/USAGE`; `GRANT CREATE ON SCHEMA public` necesario en PG15).
- Migraciones `001..013` aplicadas con `alembic upgrade head` y seed ejecutado:
  `{"tenants": 1, "duenos": 1, "sillones": 1, "prestaciones": 5}`.
- El contenedor fue **eliminado** después de la verificación (DB 100% ficticia del seed, R13).

## Resultado 1 — `tools/list`

```text
TOOLS: ['consultar_prestaciones', 'buscar_paciente_por_dni']
```

## Resultado 2 — `tools/call` → `consultar_prestaciones` (sin argumentos)

Salida real del servidor (JSON), verificando el catálogo seed:

```json
[
  {"nombre": "Arreglo",     "duracion_min": 45, "precio_particular": "25000.00", "requiere_sena": false, "monto_sena": null,    "invasiva": false, "activa": true},
  {"nombre": "Consulta",    "duracion_min": 20, "precio_particular": "10000.00", "requiere_sena": false, "monto_sena": null,    "invasiva": false, "activa": true},
  {"nombre": "Endodoncia",  "duracion_min": 60, "precio_particular": "50000.00", "requiere_sena": true,  "monto_sena": "15000.00", "invasiva": true, "activa": true},
  {"nombre": "Extracción",  "duracion_min": 45, "precio_particular": "35000.00", "requiere_sena": true,  "monto_sena": "10000.00", "invasiva": true, "activa": true},
  {"nombre": "Limpieza",    "duracion_min": 30, "precio_particular": "15000.00", "requiere_sena": false, "monto_sena": null,    "invasiva": false, "activa": true}
]
```

Coincide con el seed piloto documentado en `README.md` (Limpieza 30', Consulta 20',
Arreglo 45', Endodoncia 60', Extracción 45'). Los `id` son UUIDs generados por el seed.

> Nota: en la consola de Windows la `ó` de "Extracción" puede mostrarse como `?`
> (encoding de la terminal, artefacto de display — el JSON se emitió en UTF-8).

## Qué demuestra esto

1. El servidor MCP del repo arranca, hace handshake `initialize` y lista sus 2 tools.
2. La tool `consultar_prestaciones` conecta a Postgres vía `DATABASE_URL(_MCP)`,
   aplica el `@db:` → `@localhost:` del DSN y devuelve datos reales de la DB.
3. Con esto queda cubierto el paso "usar el MCP" del pedido, con evidencia reproducible.
