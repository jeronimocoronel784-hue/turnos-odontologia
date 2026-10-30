# Tasks

## 1. Persistencia de sesiones y tokens públicos (migración 002)

- [x] 1.1 Crear modelos `RefreshToken` y `TokenGestion` en `app/domain/` (hash, familia, vencimiento, revocación, `tenant_id`) y migración `002` con sus índices; verificar `alembic upgrade head` + `downgrade -1` + `upgrade head` contra Postgres real y que los índices/constraints aparezcan en `pg_indexes`/`information_schema`
  - Evidencia: `app/domain/refresh_token.py`, `app/domain/token_gestion.py`, `alembic/versions/002_sesiones_tokens_publicos.py`. Ciclo `downgrade -1` → `to_regclass` NULL → `upgrade head` → tablas restauradas contra PostgreSQL 18. `pg_indexes`: `ix_refresh_token_familia`, `ix_refresh_token_tenant_usuario`, `ix_token_gestion_tenant_recurso`; únicos `refresh_token_token_hash_key`, `token_gestion_token_hash_key`; FKs `refresh_token_usuario_id_fkey` / `refresh_token_tenant_id_fkey` / `token_gestion_tenant_id_fkey`. Tests: `tests/test_migracion_002.py` (5).
- [x] 1.2 Agregar los GRANT CRUD del rol app sobre `refresh_token` y `token_gestion` en la migración (y su REVOKE en `downgrade`); verificar como `turnos_app` con `psql` que INSERT/SELECT/UPDATE/DELETE funcionan, y que el `downgrade -1` deja las tablas y los GRANTs sin rastro
  - Evidencia: `GRANT`/`REVOKE` en la migración 002 (solo dialecto Postgres). `psql` como `turnos_app`: INSERT/UPDATE/DELETE en `refresh_token` y en `token_gestion` OK; tras `downgrade -1` las tablas y sus privilegios desaparecen. Test: `tests/test_grants_sesiones.py` (CRUD real con el rol restringido, sin skip contra PG).

## 2. Primitivas de seguridad (TDD)

- [x] 2.1 Implementar hash y verificación de passwords con bcrypt y rounds configurables (`BCRYPT_ROUNDS`, 4 en tests / 12 por defecto); verificar tests de password correcto, incorrecto y que el hash nunca aparezca en la respuesta
  - Evidencia: `app/infrastructure/security/passwords.py` (bcrypt directo, límite de 72 bytes, `PasswordInvalido`). `tests/test_seguridad_passwords.py` (7): correcto/incorrecto, salts distintos, `$2b$04$` vs `$2b$12$`, rechazo >72 bytes, hash nunca en respuesta ni en logs.
- [x] 2.2 Implementar emisión y validación de access token JWT (claims `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`, leeway 30 s); verificar tests de token válido, vencido, firma inválida, `type` distinto de access y expiración según `JWT_ACCESS_MIN`
  - Evidencia: `app/infrastructure/security/jwt.py` (`HS256`, leeway 30 s). `tests/test_seguridad_jwt.py` (8): claims exactos, vigencia según `JWT_ACCESS_MIN`, vencido, firma inválida, `type` distinto, `sub`/`tenant_id` inválidos.
- [x] 2.3 Implementar el servicio de tokens públicos de gestión (generación con `secrets`, guardado SHA-256, validación por token + `recurso` + `recurso_id` + `vence_at` + `revocado_at` con comparación en tiempo constante); verificar tests de token vigente, vencido, revocado, de otro recurso, de otro tenant y que en DB solo se guarda el hash
  - Evidencia: `app/infrastructure/security/tokens_publicos.py` (`secrets.token_urlsafe(32)`, SHA-256, `hmac.compare_digest`, `tenant_id` obligatorio en la validación). `tests/test_tokens_publicos.py` (10): vigente, vencido, revocado, usado, otro recurso, otro `recurso_id`, otro tenant, hash en reposo y entropía.
- [x] 2.4 Implementar el rate limiter de login en Redis (clave `login:{ip}:{sha256(email normalizado)}`, 5/60 s, fail-closed si Redis no responde); verificar tests del sexto intento → 429, ventana expirada, normalización de mayúsculas y que el email no queda en claro en la clave ni en logs
  - Evidencia: `app/infrastructure/security/rate_limit.py` (fail-closed 503, `expire` en el primer hit, log con IP + huella, nunca email). `tests/test_rate_limit_login.py` (7) con `fakeredis`: 6º intento → 429, ventana expirada, `Ana@X.com` = `ana@x.com`, clave sin email en claro, log sin email, Redis caído → 503.

## 3. Casos de uso de sesión y endpoints `/api/auth`

- [x] 3.1 Implementar `POST /api/auth/login`: valida credenciales, emite access + refresh, devuelve 401 genérico para email inexistente/password incorrecto/usuario inactivo y audita `auth.login` / `auth.login_fallido`; verificar los 4 tests de login y la fila de auditoría sin credenciales
  - Evidencia: `app/api/routers/auth.py` + `app/application/auth/sesiones.py`. `tests/test_auth_login.py` (10): éxito con access + cookie, 401 genérico en email inexistente / password incorrecta / usuario inactivo, `tenant_slug` obligatorio si el email está repetido en 2 consultorios, extra fields → 422, auditoría `auth.login` / `auth.login_fallido` sin credenciales ni PHI.
- [x] 3.2 Implementar `POST /api/auth/refresh` con rotación y detección de reúso (revoca toda la familia y audita `auth.refresh_reuso`); verificar tests de refresh normal, reúso, refresh vencido y refresh revocado por logout, comprobando que el token viejo deja de servir
  - Evidencia: `rotar_refresh` en `sesiones.py` (revoca familia completa en reúso, `reemplazado_por_id`, auditoría). `tests/test_auth_refresh.py` (7): rotación normal, token viejo inválido, reúso revoca la familia + audita, refresh vencido, revocado por logout, usuario desactivado, access nuevo con identidad del usuario.
- [x] 3.3 Implementar `POST /api/auth/logout` (revoca sesión, borra cookie, 204 idempotente) y `GET /api/auth/me` (id, email, nombre, roles, tenant, sin `password_hash`); verificar tests de logout con sesión, logout sin cookie y contenido exacto de `/me`
  - Evidencia: `tests/test_auth_logout_me.py` (6): logout revoca + audita + borra cookie, logout sin cookie/duplicado → 204, `/me` con identidad exacta sin `password_hash` ni PHI, `/me` sin token → 401, token vencido → 401.
- [x] 3.4 Configurar la cookie del refresh (`HttpOnly`, `Secure` según `COOKIE_SECURE`, `SameSite=Lax`, `Path=/api/auth`, `max_age=JWT_REFRESH_DAYS`); verificar test de flags de la cookie y que el refresh no viaje en el body
  - Evidencia: `tests/test_auth_cookie.py` (5): flags en dev (`HttpOnly`, `SameSite=Lax`, `Path=/api/auth`, sin `Secure`), flags en prod (`Secure`), `max_age` = `JWT_REFRESH_DAYS`, rotación con los mismos flags, refresh nunca en el body (solo `access_token`).
- [x] 3.5 Documentar los endpoints de auth (login, refresh, logout, me, códigos de error y manejo de la cookie) en `README.md`; verificar que los ejemplos documentados coinciden con los tests de contrato
  - Evidencia: sección `## Autenticación (C-03)` en `README.md` (claims, tabla de endpoints, 400/401/429/503, cookie). `tests/test_auth_documentacion.py` (3): las rutas documentadas existen en la app, los códigos de error documentados coinciden con el contrato y la cookie documentada coincide con los flags reales.

## 4. RBAC enforced en la API

- [x] 4.1 Definir la matriz declarativa `RECURSOS × ROLES → acciones` en `app/domain/rbac.py` espejando `03_actores_y_roles.md` y la dependency `ActorAutenticado` (usuario, tenant, roles, email) construida solo desde el token; verificar tests de matriz completa (cada rol × recurso esperado) y de `tenant_id` tomado del token
  - Evidencia: `app/domain/rbac.py` (14 recursos × 3 roles) + `app/api/security.py`. `tests/test_rbac_matriz.py` (6): matriz completa contra una copia explícita de §03, `tenant_id` del token manda sobre body/query, rol desconocido rechazado.
- [x] 4.2 Implementar los guards `requiere(recurso, accion)` con 403 rioplatense sin filtrar existencia del recurso; verificar tests de recepción editando clínica → 403, odontólogo reabriendo cierre de caja → 403, recepción leyendo configuración → 200 y Dueño con doble rol operativo → 200 en acción administrativa y clínica
  - Evidencia: `requiere()` en `app/api/security.py` (403 con mensaje rioplatense, sin revelar existencia). `tests/test_rbac_guards.py` (6): recepción edita clínica → 403, odontólogo reabre caja → 403, recepción lee configuración → 200, Dueño con rol operativo → 200 admin y clínico, sin token → 401.
- [x] 4.3 Implementar `GET /api/usuarios` (R para los 3 roles), `POST /api/usuarios` y `PATCH /api/usuarios/:id/rol` (solo Dueño) usando los guards y el `tenant_id` del token; verificar tests de 200/403 por rol, de que el body con `tenant_id` ajeno se rechaza y de que un usuario no puede leer usuarios de otro tenant
  - Evidencia: `app/api/routers/usuarios.py`. `tests/test_usuarios_api.py` (10): listado solo del tenant del token, 200/403 por rol en alta y cambio de rol, `tenant_id` en body → 422 (`extra=forbid`), usuario de otro tenant no visible, password >72 bytes → 422, email repetido → 409.
- [x] 4.4 Integrar los guards en `GET /api/auth/me` y en los endpoints de usuarios, y registrar en auditoría los cambios de rol; verificar que toda ruta interna nueva responde 401 sin token y que el cambio de rol deja rastro en `auditoria`
  - Evidencia: guards en `auth.py` y `usuarios.py`; `registrar_auditoria` en alta y cambio de rol. Tests: `tests/test_auth_logout_me.py` (`/me` 401 sin token), `tests/test_rbac_guards.py` (toda sonda 401 sin token), `tests/test_usuarios_api.py` (fila de auditoría por cambio de rol con actor y antes/después).

## 5. Integración y gates de calidad

- [x] 5.1 Correr la suite completa contra Postgres real (`DATABASE_URL_TEST` + `APP_ROLE_URL_TEST`) sin skips nuevos y verificar verde junto con `ruff check`, `ruff format --check` y `mypy --config-file src/backend/pyproject.toml` estricto
  - Evidencia: **125 passed, 0 skipped** contra PostgreSQL 18.6 real (`turnos_test` migrada 001+002, rol `turnos_app`). Fallback SQLite: 122 passed, 3 skipped (solo los casos que exigen Postgres: GRANTs). `ruff check` → All checks passed; `ruff format --check` → 68 files already formatted; `mypy` → Success en 45 archivos.
- [x] 5.2 Verificar `openspec validate c-03-auth-rbac-tokens --strict` sin warnings, actualizar el estado de C-03 en `CHANGES.md` con lo entregado y dejar constancia de los pendientes que correspondan a changes posteriores (rutas públicas cableadas en C-06/C-09/C-12/C-15)
  - Evidencia: `openspec validate c-03-auth-rbac-tokens --strict` → `Change 'c-03-auth-rbac-tokens' is valid`. `CHANGES.md` §[C-03] actualizado con estado y entregables; pendientes de cableado de rutas públicas asignados a C-06/C-09/C-12/C-15.

## Workflow follow-up

- Archivar el change con `openspec archive c-03-auth-rbac-tokens` cuando la revisión esté aprobada.
- Pushear a GitHub (R12) con commits convencionales y sin secretos (R10).
