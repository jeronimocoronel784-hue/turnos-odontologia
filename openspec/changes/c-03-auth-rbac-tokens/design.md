# Design

## Context

Ver `proposal.md` — Why. Estado actual relevante:

- `Usuario` ya tiene `rol` (`dueno`/`recepcion`/`odontologo`), `password_hash` y `tenant_id`; no existe nada que emita ni valide credenciales.
- `Auditoria` es append-only con GRANT `INSERT+SELECT` para el rol app (C-02), lista para recibir eventos de auth.
- `Settings` ya expone `jwt_secret`, `jwt_access_min` y `jwt_refresh_days`; `python-jose`, `passlib[bcrypt]` y `redis` ya son dependencias.
- `BaseRepository`/`UnitOfWork` exigen `tenant_id` explícito y fallan si falta: el token es la única fuente válida de ese dato (R4).
- El seed crea el Dueño con un `password_hash` derivado de un secreto aleatorio, así que hoy no hay credenciales conocidas para probar login.

## Goals / Non-Goals

**Goals:**

- Que todo endpoint interno tenga identidad verificable y permiso explícito por recurso.
- Que un refresh robado tenga ventana de uso acotada y que su reúso sea detectable y catastrófico para el atacante (revoca la familia).
- Que el paciente opere sin cuenta sin poder ver ni tocar datos de terceros.
- Que el rate limiting no se pueda evadir variando el email en mayúsculas ni dejando el email en claro en Redis.

**Non-Goals:**

- Multi-rol persistido (`usuario_rol`) para un mismo usuario: v1 mantiene un rol por usuario y el rol Dueño cubre la matriz administrativa y clínica.
- Blacklist de access tokens: el access es corto y stateless; el logout revoca el refresh.
- MFA, recuperación de password por email, login social, SSO.
- Guards de UI (C-16/C-17) y endpoints públicos concretos de reserva/pago/firma (C-06/C-09/C-12/C-15).

## Decisions

### D1 — JWT HS256 con `python-jose`

Access token firmado con `JWT_SECRET` (HS256). **Alternativa considerada:** PyJWT (más mantenido) — se descarta para no sumar una dependencia que hace lo mismo que una ya instalada. Si más adelante se necesita rotación de claves, se migra a RS256 sin cambiar el contrato.

Claims: `sub` (id de usuario), `tenant_id`, `roles` (lista), `email`, `jti`, `type` (`access`), `iat`, `exp`. `leeway` de 30 s para tolerar skew de reloj entre contenedores.

### D2 — Refresh token opaco persistido, no JWT

El refresh es un valor aleatorio (`secrets.token_urlsafe(48)`) guardado **hasheado** (SHA-256) en `refresh_token`. **Alternativa considerada:** refresh JWT stateless — se descarta porque sin estado no hay revocación real ni detección de reúso, que son requisitos del spec.

Tabla `refresh_token`:

| Columna | Rol |
|---|---|
| `id` | PK |
| `tenant_id`, `usuario_id` | dueño de la sesión |
| `token_hash` (unique) | SHA-256 del valor entregado |
| `familia_id` | agrupa la cadena de rotaciones |
| `vence_at` | `JWT_REFRESH_DAYS` |
| `revocado_at` | null si está vivo |
| `reemplazado_por_id` | apunta al refresh que lo rotó |
| `created_at` | auditoría básica |

**Rotación:** cada refresh válido marca `revocado_at` + `reemplazado_por_id` y crea el siguiente con el mismo `familia_id`. **Reúso:** si llega un token con `revocado_at` no nulo, se revoca toda la familia (`UPDATE ... WHERE familia_id = ?`) y se audita. La comparación se hace por hash con `hmac.compare_digest`.

### D3 — Cookie HttpOnly configurable por entorno

`HttpOnly` + `SameSite=Lax` + `Path=/api/auth` siempre. `Secure` se controla con `COOKIE_SECURE` (default `true`), porque en desarrollo local sobre `http://localhost` una cookie `Secure` no se envía y bloquearía el flujo. Los tests corren con `COOKIE_SECURE=false` explícito y el default de producción queda seguro.

### D4 — Rate limiting en Redis con clave derivada

Clave `login:{ip}:{sha256(email_normalizado)}` con `INCR` + `EXPIRE 60`; el email nunca aparece en claro en Redis ni en logs (R9) y se normaliza a minúsculas para que `Ana@x.com` y `ana@x.com` compartan balde. **Alternativa considerada:** límite solo por IP — se descarta porque un atacante rota IPs contra un mismo usuario. **Si Redis no responde, el login falla cerrado (503)**: es un control de seguridad, no un adorno.

### D5 — Matriz RBAC declarativa en código

`app/domain/rbac.py` define `RECURSOS × ROLES → acciones` como tabla pura, espejo de `03_actores_y_roles.md`, con una dependency `requiere(recurso, accion)` para FastAPI. **Alternativa considerada:** permisos en DB por tenant — más flexible, pero agrega superficie de configuración y auditoría que el v1 no pide; el enum de roles ya está fijado en la KB.

El claim `roles` es una lista desde el día uno para no romper el contrato cuando aparezca multi-rol real; en v1 tiene un elemento.

### D6 — `tenant_id` solo desde el token

La dependency de autenticación construye un `ActorAutenticado` (`usuario_id`, `tenant_id`, `roles`, `email`) y los routers reciben ese objeto; ningún schema de request acepta `tenant_id`. Los repositorios se instancian con `actor.tenant_id`, cerrando el bypass por body/query que prohíbe R4.

### D7 — Token público opaco con hash y vencimiento obligatorio

`secrets.token_urlsafe(32)` (~256 bits) → se entrega una vez y se guarda SHA-256 en `token_gestion` junto a `tenant_id`, `recurso`, `recurso_id`, `vence_at`, `revocado_at`, `usado_at`. **Alternativa considerada:** JWT firmado para links públicos — se descarta porque el link circula por WhatsApp/email y tiene que poder revocarse y vencer de verdad; un JWT sin estado no se revoca sin lista negra.

La validación exige coincidencia de `recurso` y `recurso_id` además del token, de modo que un token de un turno no sirva para otro (RN-SE-03).

### D8 — Estructura de código

- `app/domain/` — `refresh_token.py`, `token_gestion.py`, `rbac.py`.
- `app/application/auth/` — `login.py`, `refresh.py`, `logout.py` (casos de uso puros sobre repos).
- `app/infrastructure/security/` — `jwt.py`, `passwords.py`, `rate_limit.py`, `tokens_publicos.py`.
- `app/api/` — `routers/auth.py`, `security.py` (dependencies de actor + guards), `schemas_auth.py`.

### D9 — Auditoría de auth con helper compartido

`registrar_auditoria(session, tenant_id, actor_id, accion, entidad, entidad_id, antes, despues)` en `app/application/auditoria.py`. Acciones: `auth.login`, `auth.login_fallido`, `auth.logout`, `auth.refresh_reuso`. Nunca guarda password, tokens ni email completo (se guarda el id del usuario).

## Risks / Trade-offs

- **[Redis caído bloquea login]** → fail-closed documentado y `/api/health` ya reporta Redis caído; el operador ve la causa.
- **[Cookie `Secure` en dev rompe el flujo]** → `COOKIE_SECURE=false` solo en `.env` local y tests; el default es seguro.
- **[bcrypt encarece la suite]** → rounds configurables (4 en tests, 12 en producción) vía `BCRYPT_ROUNDS`.
- **[Rotación mal implementada deja sesiones zombis]** → tests explícitos de reúso, refresh vencido y logout; cada caso verifica que el refresh viejo deja de servir.
- **[Access token no revocable antes de expirar]** → ventana máxima de 15 min asumida; el logout corta el refresh, no el access.
- **[Migración 002 con sesiones activas]** → `downgrade -1` borra `refresh_token` y `token_gestion` (todas las sesiones se pierden: aceptable en v1).

## Migration Plan

1. Migración `002` crea `refresh_token` y `token_gestion` con índices (`token_hash` único, (`tenant_id`,`usuario_id`), (`recurso`,`recurso_id`)) y GRANT CRUD al rol app.
2. Deploy con `JWT_SECRET` y `COOKIE_SECURE` definidos; sin secretos hardcodeados (R10).
3. Rollback: `alembic downgrade -1` + volver al build anterior; los usuarios vuelven a loguearse.
4. Sin datos a migrar: el login se estrena con el seed (Dueño ficticio) y fixtures sintéticos (R13).

## Open Questions

- ¿Multi-rol real (`usuario_rol`) para el futuro? No cambia el contrato: el claim `roles` ya es lista. Se decide cuando aparezca el primer caso que el rol Dueño no cubra.
