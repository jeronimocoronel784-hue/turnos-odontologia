# Tasks

## 1. Modelos de dominio, regla RN-CO-01 y migración Alembic 004 (TDD)

- [x] 1.1 Crear modelos de dominio `Paciente` y `FichaClinica` en `src/backend/app/domain/` (`paciente.py`, `ficha_clinica.py`) con `TenantMixin`, `AuditMixin`, constraints de unicidad (`uq_paciente_tenant_dni`, `uq_ficha_clinica_paciente_id`), índices de búsqueda y la función pura `puede_enviar_whatsapp(paciente)` para la regla RN-CO-01; implementar la migración `004_pacientes_ficha_clinica.py` y verificar con tests en `tests/test_migracion_004_pacientes.py` el ciclo `upgrade` / `downgrade` y los constraints en DB
  - Evidencia: Modelos Paciente y FichaClinica con constraints de unicidad y relación 1:1, función RN-CO-01 y migración 004 encadenada con 003; 7 tests pasando en `tests/test_migracion_004_pacientes.py`.
- [x] 1.2 Crear schemas Pydantic estrictos (`extra='forbid'`, R1) en `src/backend/app/api/schemas_pacientes.py` para creación, actualización, opt-in y respuesta de pacientes y fichas clínicas con normalización de DNI/teléfono y rechazo de `tenant_id` en body; verificar con tests en `tests/test_schemas_pacientes.py`
  - Evidencia: Schemas con extra='forbid', normalización de DNI y teléfono, mensajes en rioplatense y rechazo de campos extra; 9 tests pasando en `tests/test_schemas_pacientes.py`.

## 2. Endpoints CRUD, opt-in WA, get_or_create y gates de calidad (TDD)

- [x] 2.1 Implementar endpoints CRUD y opt-in en `src/backend/app/api/routers/pacientes.py` (`GET /api/pacientes`, `GET /:id`, `POST /`, `PATCH /:id`, `DELETE /:id` baja lógica, `PATCH /:id/optin`) protegidos por RBAC (`Recurso.PACIENTES`) y con registro en `auditoria`; verificar en `tests/test_pacientes_api.py` alta, listado, filtros, baja lógica y control 403 para odontólogo en escrituras
  - Evidencia: CRUD completo de pacientes y endpoint PATCH opt-in con RBAC, soft delete y auditoría; 6 tests pasando en `tests/test_pacientes_api.py`.
- [x] 2.2 Implementar la lógica `get_or_create_paciente` para reserva pública sin login y la validación de envíos automáticos según RN-CO-01; verificar en `tests/test_pacientes_negocio.py` la unicidad de DNI por consultorio, el alta implícita, el bloqueo de WhatsApp sin opt-in y el corte de envíos ante baja STOP
  - Evidencia: Servicio get_or_create_paciente con deduplicación por DNI y creación atómica de ficha clínica, función RN-CO-01 y procesar_baja_stop con auditoría; 4 tests pasando en `tests/test_pacientes_negocio.py`.
- [x] 2.3 Registrar el router en `src/backend/app/main.py`, documentar endpoints en `README.md`, actualizar `CHANGES.md` a `[x]` y ejecutar la suite completa de tests (`pytest`), `ruff check` y `mypy`
  - Evidencia: Router registrado en main.py y conftest.py, README.md y CHANGES.md actualizados, linters limpios y suite de tests ejecutada.

## Workflow follow-up

- Archivar el change con `openspec archive c-05-pacientes` y sincronizar specs.
- Versionar en git (`git commit` y `git push`) según R10 y R12.
