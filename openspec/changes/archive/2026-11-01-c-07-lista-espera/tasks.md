# Tasks: C-07 Lista de Espera y Oferta de Huecos (`c-07-lista-espera`)

## Phase 1: Dominio, Migración 006 y Contratos Pydantic

- [x] 1.1 Crear `src/backend/app/domain/lista_espera.py` (`ListaEspera`, `EstadoListaEspera`, `CanalAviso`, `generar_idempotency_key_hueco`) y la migración reversible `src/backend/alembic/versions/006_lista_espera.py` con constraints, índice `(tenant_id, estado, prioridad, created_at)` y permisos `GRANT`/`REVOKE` para `turnos_app`. Registrar `ListaEspera` en `alembic/env.py` y `tests/conftest.py`. Verificar con `tests/test_migracion_006_lista_espera.py`.
- [x] 1.2 Crear `src/backend/app/api/schemas_lista_espera.py` (`ListaEsperaCreate`, `ListaEsperaUpdate`, `ListaEsperaRead`, `OfrecerHuecoRequest`, `ListaEsperaPublicaCreate`, `ListaEsperaPublicaRead` con `extra="forbid"`) y verificar validaciones con `tests/test_schemas_lista_espera.py`.

## Phase 2: Motor de Lista de Espera, Oferta de Huecos y Rotación

- [x] 2.1 Implementar `src/backend/app/application/lista_espera.py` (`crear_entrada_lista_espera`, `ofrecer_hueco_lista_espera`, `aceptar_oferta_lista_espera`, `dar_baja_lista_espera`) e integrar el disparo automático al liberar slot en `src/backend/app/application/agenda.py` (`cambiar_estado_turno` y `reprogramar_turno`). Verificar orden `(prioridad, created_at)`, idempotencia por hueco (`RN-LE-02`), rotación por ventana vencida (`RN-LE-01`), colocación (`RN-LE-03`) y conflicto por doble aceptación con `tests/test_lista_espera_api.py` y `tests/test_lista_espera_negocio.py`.

## Phase 3: Endpoints Internos y Públicos + Cierre de Calidad

- [x] 3.1 Implementar `src/backend/app/api/routers/lista_espera.py` con rutas autenticadas (`/api/lista-espera`, `/api/lista-espera/{id}`, `/api/lista-espera/ofrecer-hueco` bajo RBAC `Recurso.LISTA_ESPERA`) y rutas públicas (`/reservar/{slug}/lista-espera`, `/lista-espera/{token}`, `/lista-espera/{token}/aceptar`, `/lista-espera/{token}/baja`), registrándolas en `src/backend/app/main.py` y `tests/conftest.py`. Verificar con `tests/test_lista_espera_api.py`.
- [x] 3.2 Actualizar `README.md` y `CHANGES.md` (`[x]` en C-07), y ejecutar `ruff check`, `ruff format --check`, `mypy` y `pytest` completos en verde.
