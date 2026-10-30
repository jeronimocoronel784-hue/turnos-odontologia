# Tasks

## 1. Modelos de dominio y migración `003_catalogo_configuracion` (TDD)

- [x] 1.1 Crear modelos `Sillon`, `Prestacion` y `CoberturaOS` en `app/domain/` (`sillon.py`, `prestacion.py`, `cobertura_os.py`) y migración reversible `003_catalogo_configuracion.py` con constraints (`UNIQUE`, `CHECK`, `FOREIGN KEY`), índices y `GRANT`/`REVOKE` para `turnos_app`; verificar con tests en `tests/test_migracion_003_catalogo.py` el ciclo `upgrade head` → `downgrade -1` → `upgrade head`, los constraints en DB (duración > 0, seña > 0 cuando `requiere_sena`, vigencia ordenada, unicidad por tenant) y los permisos CRUD de `turnos_app`
  - Evidencia: Modelos Sillon, Prestacion y CoberturaOS con constraints (UNIQUE, CHECK, FK RESTRICT) e índices por tenant; migración 003_catalogo_configuracion encadenada a 002 con GRANTs condicionales a turnos_app; 13 tests pasando en `tests/test_migracion_003_catalogo.py`.
- [x] 1.2 Crear schemas Pydantic estrictos (`extra='forbid'`, R1) en `app/api/schemas_catalogo.py` para `Sillon`, `Prestacion`, `CoberturaOS` y `PoliticasUpdate`/`PoliticasRead` con validaciones de negocio en rioplatense; verificar con tests unitarios en `tests/test_schemas_catalogo.py` los casos felices y rechazos (duración <= 0, `requiere_sena` sin `monto_sena`, `vigencia_hasta < vigencia_desde`, porcentajes/horas fuera de rango y `tenant_id` infiltrado en el body)
  - Evidencia: Schemas con extra='forbid', tipos Decimal y validaciones de negocio en rioplatense; 17 tests pasando en `tests/test_schemas_catalogo.py` cubriendo casos válidos, rechazos por rango/duración/seña y rechazo de campos extra.

## 2. Endpoints CRUD administrativos y políticas del consultorio (TDD)

- [x] 2.1 Implementar `/api/admin/sillones` (`GET`, `POST`, `PATCH /:id`, `DELETE /:id` baja lógica) en `app/api/routers/admin_catalogo.py` con `requiere(Recurso.CONFIGURACION, ...)`, `BaseRepository` y `registrar_auditoria`; verificar en `tests/test_admin_sillones.py` alta, listado por rol (`dueno`, `recepcion`, `odontologo`), 403 en escritura para no-dueños, 409 por nombre duplicado en la misma sucursal, baja lógica auditada y aislamiento entre tenants
  - Evidencia: CRUD completo de sillones con RBAC Recurso.CONFIGURACION, soft delete y registro en auditoria; 8 tests pasando en `tests/test_admin_sillones.py`.
- [x] 2.2 Implementar `/api/admin/prestaciones` (`GET`, `POST`, `PATCH /:id`, `DELETE /:id` baja lógica) con validación de `duracion_min > 0` y `requiere_sena ⇒ monto_sena > 0`, más auditoría; verificar en `tests/test_admin_prestaciones.py` CRUD por rol, normalización de `monto_sena` cuando `requiere_sena = false`, rechazo 422 con mensaje rioplatense, 409 por nombre duplicado en el tenant y baja lógica
  - Evidencia: CRUD completo de prestaciones con validación de seña/duración, normalización a null de monto_sena, 409 por colisión de nombre, soft delete y auditoría; 9 tests pasando en `tests/test_admin_prestaciones.py`.
- [x] 2.3 Implementar `/api/admin/coberturas` (`GET` con filtro `vigente_en`, `obra_social` y `prestacion_id`, `POST`, `PATCH /:id`, `DELETE /:id` baja lógica) validando que `prestacion_id` pertenezca al consultorio del token; verificar en `tests/test_admin_coberturas.py` alta, filtro de vigencia por fecha (cobertura vigente vs vencida), rechazo 404 si la prestación es de otro tenant y control RBAC
  - Evidencia: CRUD de coberturas de obras sociales con filtro por fecha de vigencia, validación de pertenencia de prestación al tenant, soft delete y auditoría; 6 tests pasando en `tests/test_admin_coberturas.py`.
- [x] 2.4 Implementar `GET /api/admin/tenant/politicas` y `PATCH /api/admin/tenant/politicas` con actualización parcial sobre `Tenant.politicas` y registro en `auditoria` (`antes`/`despues`); verificar en `tests/test_admin_politicas.py` lectura por los 3 roles, actualización parcial solo por `dueno`, rechazo 422 de valores inválidos y fila de auditoría
  - Evidencia: Endpoints GET y PATCH /api/admin/tenant/politicas con defaults seguros, merge parcial y registro en auditoría con antes/después; 6 tests pasando en `tests/test_admin_politicas.py`.
- [x] 2.5 Documentar la sección `## Catálogo y configuración (C-04)` y actualizar el estado del proyecto en `README.md` y `CHANGES.md`; verificar con test de contrato en `tests/test_catalogo_documentacion.py` que todas las rutas documentadas existen en la app
  - Evidencia: README.md con tabla completa de 14 endpoints de /api/admin, estado C-04 en README y CHANGES.md, y 4 tests pasando en `tests/test_catalogo_documentacion.py`.

## 3. Seed del catálogo base y gates de calidad

- [x] 3.1 Extender `ejecutar_seed` en `app/infrastructure/seed.py` para poblar de forma idempotente el sillón `"Box 1"` (sucursal `"central"`) y las 5 prestaciones base (`Limpieza` 30', `Consulta` 20', `Arreglo` 45', `Endodoncia` 60', `Extracción` 45') con precios y flags `requiere_sena`/`invasiva`; verificar en `tests/test_seed.py` que dos ejecuciones consecutivas dejan exactamente 1 sillón y 5 prestaciones sin duplicar
  - Evidencia: Seed extendido con SILLON_SEED y PRESTACIONES_SEED 100% idempotente; 3 tests pasando en `tests/test_seed.py`.
- [x] 3.2 Ejecutar la suite completa (`pytest`), `ruff check`, `ruff format --check`, `mypy --config-file src/backend/pyproject.toml` y `openspec validate c-04-catalogo-configuracion --strict`, verificando 0 errores y 0 warnings
  - Evidencia: pytest 186 passed (4 skipped condicionales de Postgres en local), ruff check limpio (0 errors), ruff format limpio (81 files formatted), mypy estricto limpio en app, alembic y tests nuevos (59 source files), openspec validate c-04-catalogo-configuracion --strict exitoso.

## Workflow follow-up

- Archivar el change con `/opsx:archive c-04-catalogo-configuracion` y sincronizar la spec en `openspec/specs/catalogo-configuracion/spec.md`.
- Hacer commit y push a GitHub (`origin main`) con nombres de commits simples y explicativos (R10, R12).
