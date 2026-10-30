# Proposal

## Why

El sistema ya tiene usuarios con rol y `tenant_id` en el modelo, pero **nadie puede autenticarse ni autorizarse todavía**: no hay login, no hay tokens, y la matriz RBAC de `03_actores_y_roles.md` no está enforced en la API. Además, el paciente —que no tiene cuenta— necesita operar sobre sus turnos, pagos y consentimientos mediante tokens públicos vencibles (RN-SE-03). Sin C-03 no hay forma de saber quién hace cada request, así que todos los changes de dominio que vienen después (pacientes, agenda, HC, caja) quedarían sin control de acceso.

## What Changes

- **Autenticación JWT para staff interno**:
  - `POST /api/auth/login` con email + password (bcrypt) y rate limiting de 5 intentos/60s por IP+email.
  - Access token corto (`JWT_ACCESS_MIN`, default 15 min) + refresh token con **rotación**: cada refresh emite uno nuevo e invalida el anterior; el **reúso** de un refresh ya rotado revoca toda la familia de sesión.
  - Refresh entregado en **cookie HttpOnly** (`secure`, `samesite=lax`); access token en body para el cliente.
  - `POST /api/auth/refresh`, `POST /api/auth/logout` (revoca la sesión activa) y `GET /api/auth/me`.
  - Claims del access token: `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.
- **RBAC enforced en API, no solo en UI**:
  - `PermissionContext` con `require_role()` + guards por recurso según la matriz de `03_actores_y_roles.md`.
  - El `tenant_id` efectivo sale **siempre** del token (R4), nunca del body/query.
  - Dueño con doble rol operativo (ej. dueño + odontólogo) resuelto por lista de roles, no por un único enum.
  - Los rechazos devuelven 403 con mensaje accionable en rioplatense (RN-GL-02), sin filtrar si el recurso existe.
- **Tokens públicos para el paciente sin login** (RN-SE-03):
  - Entidad `TokenGestion` (token con entropía alta, guardado hasheado, `vence_at`, `usado_at`) y servicio de creación/validación.
  - Un token vencido, revocado o de otro recurso **no** expone datos de terceros ni permite operar.
  - Las rutas públicas concretas (`/reservar`, `/mis-turnos`, `/pagar`, `/firmar`, `/lista-espera`) se cablean en C-06/C-09/C-12/C-15; este change entrega la primitiva y sus garantías.
- **Persistencia de sesiones**: migración 002 con `refresh_token` (hash, familia, `revocado_at`) y `token_gestion`, con los GRANTs correspondientes al rol app.
- **BREAKING**: ninguno para el contrato actual (no hay endpoints de negocio todavía); sí introduce la obligación de mandar `Authorization: Bearer` en todo endpoint interno a partir de acá.

## Capabilities

### New Capabilities

- `auth-rbac-tokens`: autenticación JWT con rotación de refresh, autorización por matriz de roles enforced en API, y tokens públicos vencibles para el paciente sin login.

### Modified Capabilities

- Ninguna. `core-models-multitenant` no cambia sus requirements: las tablas nuevas (`refresh_token`, `token_gestion`) son parte del comportamiento de acceso, no del modelo core.

## Impact

- **Afecta**: `src/backend/app/{domain,application,infrastructure,api}/` (auth, sesiones, tokens, guards), `src/backend/alembic/versions/002_*`, `src/backend/app/shared/{settings,exceptions}`, `tests/`.
- **Dependencias**: `python-jose` y `passlib[bcrypt]` ya están en `pyproject.toml`; Redis ya está en el stack para el rate limiting.
- **Desbloquea**: C-04, C-05 y todo el resto del roadmap, que necesitan `tenant_id` confiable y guards por rol.
- **No toca**: layout de directorios, frontend (los guards de UI llegan en C-16/C-17), Mercado Pago, WhatsApp, datos reales (R13: solo fixtures sintéticos).
- **Riesgos**: rate limiting con Redis caído no debe bloquear el login de forma insegura (fail-closed en producción, degradación explícita en dev); rotación de refresh mal implementada puede dejar sesiones zombis (se cubre con tests de reúso).
