# Tasks

## 1. Persistencia de sesiones y tokens públicos (migración 002)

- [ ] 1.1 Crear modelos `RefreshToken` y `TokenGestion` en `app/domain/` (hash, familia, vencimiento, revocación, `tenant_id`) y migración `002` con sus índices; verificar `alembic upgrade head` + `downgrade -1` + `upgrade head` contra Postgres real y que los índices/constraints aparezcan en `pg_indexes`/`information_schema`
- [ ] 1.2 Agregar los GRANT CRUD del rol app sobre `refresh_token` y `token_gestion` en la migración (y su REVOKE en `downgrade`); verificar como `turnos_app` con `psql` que INSERT/SELECT/UPDATE/DELETE funcionan, y que el `downgrade -1` deja las tablas y los GRANTs sin rastro

## 2. Primitivas de seguridad (TDD)

- [ ] 2.1 Implementar hash y verificación de passwords con bcrypt y rounds configurables (`BCRYPT_ROUNDS`, 4 en tests / 12 por defecto); verificar tests de password correcto, incorrecto y que el hash nunca aparezca en la respuesta
- [ ] 2.2 Implementar emisión y validación de access token JWT (claims `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`, leeway 30 s); verificar tests de token válido, vencido, firma inválida, `type` distinto de access y expiración según `JWT_ACCESS_MIN`
- [ ] 2.3 Implementar el servicio de tokens públicos de gestión (generación con `secrets`, guardado SHA-256, validación por token + `recurso` + `recurso_id` + `vence_at` + `revocado_at` con comparación en tiempo constante); verificar tests de token vigente, vencido, revocado, de otro recurso, de otro tenant y que en DB solo se guarda el hash
- [ ] 2.4 Implementar el rate limiter de login en Redis (clave `login:{ip}:{sha256(email normalizado)}`, 5/60 s, fail-closed si Redis no responde); verificar tests del sexto intento → 429, ventana expirada, normalización de mayúsculas y que el email no queda en claro en la clave ni en logs

## 3. Casos de uso de sesión y endpoints `/api/auth`

- [ ] 3.1 Implementar `POST /api/auth/login`: valida credenciales, emite access + refresh, devuelve 401 genérico para email inexistente/password incorrecto/usuario inactivo y audita `auth.login` / `auth.login_fallido`; verificar los 4 tests de login y la fila de auditoría sin credenciales
- [ ] 3.2 Implementar `POST /api/auth/refresh` con rotación y detección de reúso (revoca toda la familia y audita `auth.refresh_reuso`); verificar tests de refresh normal, reúso, refresh vencido y refresh revocado por logout, comprobando que el token viejo deja de servir
- [ ] 3.3 Implementar `POST /api/auth/logout` (revoca sesión, borra cookie, 204 idempotente) y `GET /api/auth/me` (id, email, nombre, roles, tenant, sin `password_hash`); verificar tests de logout con sesión, logout sin cookie y contenido exacto de `/me`
- [ ] 3.4 Configurar la cookie del refresh (`HttpOnly`, `Secure` según `COOKIE_SECURE`, `SameSite=Lax`, `Path=/api/auth`, `max_age=JWT_REFRESH_DAYS`); verificar test de flags de la cookie y que el refresh no viaje en el body
- [ ] 3.5 Documentar los endpoints de auth (login, refresh, logout, me, códigos de error y manejo de la cookie) en `README.md`; verificar que los ejemplos documentados coinciden con los tests de contrato

## 4. RBAC enforced en la API

- [ ] 4.1 Definir la matriz declarativa `RECURSOS × ROLES → acciones` en `app/domain/rbac.py` espejando `03_actores_y_roles.md` y la dependency `ActorAutenticado` (usuario, tenant, roles, email) construida solo desde el token; verificar tests de matriz completa (cada rol × recurso esperado) y de `tenant_id` tomado del token
- [ ] 4.2 Implementar los guards `requiere(recurso, accion)` con 403 rioplatense sin filtrar existencia del recurso; verificar tests de recepción editando clínica → 403, odontólogo reabriendo cierre de caja → 403, recepción leyendo configuración → 200 y Dueño con doble rol operativo → 200 en acción administrativa y clínica
- [ ] 4.3 Implementar `GET /api/usuarios` (R para los 3 roles), `POST /api/usuarios` y `PATCH /api/usuarios/:id/rol` (solo Dueño) usando los guards y el `tenant_id` del token; verificar tests de 200/403 por rol, de que el body con `tenant_id` ajeno se rechaza y de que un usuario no puede leer usuarios de otro tenant
- [ ] 4.4 Integrar los guards en `GET /api/auth/me` y en los endpoints de usuarios, y registrar en auditoría los cambios de rol; verificar que toda ruta interna nueva responde 401 sin token y que el cambio de rol deja rastro en `auditoria`

## 5. Integración y gates de calidad

- [ ] 5.1 Correr la suite completa contra Postgres real (`DATABASE_URL_TEST` + `APP_ROLE_URL_TEST`) sin skips nuevos y verificar verde junto con `ruff check`, `ruff format --check` y `mypy --config-file src/backend/pyproject.toml` estricto
- [ ] 5.2 Verificar `openspec validate c-03-auth-rbac-tokens --strict` sin warnings, actualizar el estado de C-03 en `CHANGES.md` con lo entregado y dejar constancia de los pendientes que correspondan a changes posteriores (rutas públicas cableadas en C-06/C-09/C-12/C-15)

## Workflow follow-up

- Archivar el change con `openspec archive c-03-auth-rbac-tokens` cuando la revisión esté aprobada.
- Pushear a GitHub (R12) con commits convencionales y sin secretos (R10).
