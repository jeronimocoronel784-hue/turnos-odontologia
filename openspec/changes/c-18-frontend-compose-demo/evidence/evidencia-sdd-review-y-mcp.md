# Evidencia — gate SDD + MCP (c-18-frontend-compose-demo)

**Fecha**: 2026-11-12 · **Change**: `openspec/changes/c-18-frontend-compose-demo/`
Ambas evidencias son de la fase de **preparación** (propose); no se modificó código de negocio.

## 1. Skill `sdd-change-review` — revisión de artefactos vs knowledge-base

- **Solicitud**: invocada con el Skill tool (`sdd-change-review`) una vez generados los 4 artefactos; procedimiento aplicado paso a paso:
  - Paso 0 — inventario: `proposal.md`, `design.md`, `specs/foundation-setup/spec.md`, `tasks.md` (los 4 presentes, sin artefacto faltante).
  - Paso 1 — alcance: dominios SE/GL + flujos ejercitados AG/PA; actores paciente (ruta pública) y staff (login); entidades Tenant, Prestacion, Turno, Usuario.
  - Paso 2 — fuente de verdad leída: `knowledge-base/05_reglas_de_negocio.md` completo, `03` §Rutas públicas, `07` §Flujo 1, `08` §Variables de entorno (`FRONT_URL`), `10` (PO-01..04), `CHANGES.md` §[C-18] "Leer antes" y R1–R13 de `AGENTS.md`.
  - Pasos 3-6 — matriz de trazabilidad RN ↔ artefactos (20 RN: RN-AG 1-8, RN-PA 1-5, RN-SE 1-4, RN-GL 1-3), auditoría de escenarios contra R11 (≥2 por comportamiento) y cruce con reglas duras.
- **Resultado**: reporte completo en `reporte-sdd-change-review.md` con **veredicto: APROBAR CON CAMBIOS** (sin CRITICAL/HIGH; 4 hallazgos: 2 MEDIUM + 2 LOW).
- **Aporte al change** (fixes aplicados a los artefactos después del gate, por instrucción del orquestador):
  1. Escenario nuevo "Slot tomado concurrentemente" (409 + alternativas, RN-AG-01/RN-GL-02) + task de test 2.5.
  2. Escenario nuevo "API caída tras el arranque" (502/504 sin `index.html` ni stack traces) + task de smoke 2.6.
  3. Escenario nuevo "Reserva de prestación con seña" (respuesta `201` con `requiere_sena`, `monto_sena`, seña `pendiente` — RN-PA-02/R8) + task 4.2 ampliado.
  4. `FRONT_URL` del servicio `api` alineado a `http://localhost:8080` en `docker-compose.yml` (task 1.1 + design Decisión 1 + proposal Impact).
  - Re-validación posterior: `openspec validate c-18-frontend-compose-demo --strict` → **válido** (exit 0).

## 2. MCP `turnos-odontologia` — llamada real a una tool

- **Disponibilidad**: el servidor no estaba conectado en esta sesión (sin tools MCP en el catálogo). Se replicó la configuración de `.mcp.json` con un **cliente MCP real por stdio** (`mcp>=2,<3`, command `python -u mcp_server.py`, cwd = raíz del repo), que hace `initialize` + `tools/list` + `tools/call` contra el server del repo.
- **Contexto de la DB**: PostgreSQL 15.10 real en contenedor efímero de verificación (puerto 5433, credenciales dummy locales — no son secretos del repo) con rol `turnos_app` (replicando `db/init/01-roles.sh`), `alembic upgrade head` (migraciones 001..013) y `python -m app.infrastructure.seed` → `{'tenants': 1, 'duenos': 1, 'sillones': 1, 'prestaciones': 5}`. Detalle completo y salida literal en `llamada-real-mcp.md`; el contenedor se eliminó al terminar.
- **Solicitud**: `tools/list` → `['consultar_prestaciones', 'buscar_paciente_por_dni']`; después `tools/call "consultar_prestaciones" {}`.
- **Resultado** (resumen del JSON devuelto — catálogo activo, datos 100% ficticios del seed):

  | prestación | duración | precio particular | requiere seña | monto seña | invasiva |
  |---|---|---|---|---|---|
  | Arreglo | 45' | 25000.00 | no | — | no |
  | Consulta | 20' | 10000.00 | no | — | no |
  | Endodoncia | 60' | 50000.00 | **sí** | 15000.00 | sí |
  | Extracción | 45' | 35000.00 | **sí** | 10000.00 | sí |
  | Limpieza | 30' | 15000.00 | no | — | no |

- **Aporte al change**:
  - Confirmó el **catálogo real con el que se prueba la demo**: los escenarios del spec usan `consultorio-piloto` y la prestación "Endodoncia" con `monto_sena` 15000 — valores que coinciden con la salida real de la tool (y con `PRESTACIONES_SEED` de `src/backend/app/infrastructure/seed.py`).
  - Validó que el DSN default del server (`localhost:5432/turnos`, `mcp_server.py:24`) necesita una Postgres accesible y que, con DB real, la tool responde JSON limpio (sin stack traces, sin PHI).
  - **Límites respetados (R9, R13)**: solo se usó `consultar_prestaciones` (catálogo, sin datos de pacientes); no se invocó `buscar_paciente_por_dni`; sin credenciales, `.env` ni datos reales en esta evidencia.

## Estado final de los artefactos

- `openspec validate c-18-frontend-compose-demo --strict` → verde.
- `openspec status --change c-18-frontend-compose-demo --json` → proposal/specs/design/tasks en `done`.
