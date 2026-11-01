# Tasks

## 1. Modelos de dominio, máquina de estados y migración Alembic 005 (Strict TDD)

- [ ] 1.1 Crear los modelos `Turno` (`EstadoTurno`, `OrigenTurno`, función `validar_transicion_turno`, cálculo de `fin`) y `Bloqueo` (`MotivoBloqueo`) en `src/backend/app/domain/turno.py` y `src/backend/app/domain/bloqueo.py` junto con la migración reversible `src/backend/alembic/versions/005_agenda_turnos.py` (tablas `turno` y `bloqueo`, constraints, índices y `GRANT`/`REVOKE` para `turnos_app`), verificando con `pytest tests/test_migracion_005_agenda.py` el ciclo `upgrade` / `downgrade`, constraints e índices.
- [ ] 1.2 Crear los schemas Pydantic estrictos (`extra='forbid'`, R1) en `src/backend/app/api/schemas_agenda.py` para creación/respuesta de turnos, transición de estado, reprogramación, bloqueos, vista de agenda y reserva/autogestión pública, verificando validaciones y mensajes en rioplatense con `pytest tests/test_schemas_agenda.py`.

## 2. Reglas de negocio de agenda: anti-solapamiento, bloqueos, estados y reprogramación (Strict TDD)

- [ ] 2.1 Implementar en `src/backend/app/application/agenda.py` la verificación de anti-solapamiento por profesional y sillón (RN-AG-01), el respeto de bloqueos (RN-AG-03), el cálculo de slots disponibles/alternativos (409 con `slots_alternativos`, RN-GL-02), el alta de turno con `sobreturno` explícito auditado (RN-AG-04), las transiciones de estado con bloqueo por seña impaga (RN-AG-07, RN-PA-01) y la reprogramación 1-clic con `turno_origen_id` y política `cancelacion_hs` (RN-AG-05, RN-AG-06), verificando cada caso con `pytest tests/test_agenda_negocio.py`.

## 3. Endpoints internos de agenda/bloqueos y endpoints públicos de reserva/autogestión (Strict TDD)

- [ ] 3.1 Implementar el router interno `src/backend/app/api/routers/agenda.py` (`GET /api/agenda`, `POST /api/turnos`, `GET /api/turnos/{id}`, `PATCH /api/turnos/{id}/estado`, `POST /api/turnos/{id}/reprogramar`, `GET /api/bloqueos`, `POST /api/bloqueos`, `DELETE /api/bloqueos/{id}`) con RBAC (`Recurso.AGENDA`, `Recurso.BLOQUEOS`), aislamiento por `tenant_id` del JWT (R4) y auditoría append-only (RN-SE-01), verificando permisos por rol y casos de conflicto con `pytest tests/test_agenda_api.py`.
- [ ] 3.2 Implementar el helper `resolver_token_gestion_recurso` en `src/backend/app/infrastructure/security/tokens_publicos.py` y el router público `src/backend/app/api/routers/reserva_publica.py` (`GET /reservar/{slug}`, `POST /reservar/{slug}`, `GET /mis-turnos/{token}`, `POST /mis-turnos/{token}/confirmar`, `POST /mis-turnos/{token}/cancelar`, `POST /mis-turnos/{token}/reprogramar`), verificando el Flujo 1 completo, idempotencia de confirmación y aislamiento de token con `pytest tests/test_reserva_publica_api.py`.
- [ ] 3.3 Registrar los routers en `src/backend/app/main.py` y `tests/conftest.py`, documentar la sección `## Agenda y turnos (C-06)` en `README.md`, actualizar `CHANGES.md` y verificar toda la suite (`pytest`, `ruff check`, `ruff format --check`, `mypy`).

## Workflow follow-up

- Archivar el change con `openspec archive c-06-agenda-turnos --yes` y validar specs con `openspec validate --specs --strict`.
- Commitear y pushear a GitHub según R10 y R12.
