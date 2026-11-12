# Design

## Context

Ver `proposal.md` → Why. Estado actual relevante:

- `docker-compose.yml` declara `db`, `redis`, `api` (publica `8000`, healthcheck propio), `worker`, `migrar` (perfil `tools`) y `mailhog`; **no existe servicio `frontend`** (lo admite `README.md:53-56`).
- `src/frontend/Dockerfile.frontend` ya funciona: build multi-stage (node 22 → nginx 1.27.3 no-root, uid 10001) con `HEALTHCHECK` (`wget http://127.0.0.1:80/`) y `CMD nginx -g "daemon off;"`. `npm run build` del frontend está en verde.
- `src/frontend/nginx.conf` hoy solo sirve la SPA (`try_files $uri $uri/ /index.html`) con los temp paths ya apuntando a `/tmp` (requisito del usuario no-root); **no tiene proxy a la API**.
- El frontend consume la API con rutas **relativas** (`BASE_URL = import.meta.env.VITE_API_URL ?? ""` en `src/frontend/src/shared/api-client.ts:3` y `shared/reserva-api.ts:16`), es decir `/api/...` del mismo origen. En dev ese rol lo juega el proxy de Vite (`vite.config.ts:67` → `localhost:8000`); en compose le corresponde a nginx.
- El backend **no** tiene `CORSMiddleware`: el mismo origen que da el proxy es el camino correcto, no abrir CORS.
- Seed (`src/backend/app/infrastructure/seed.py`): tenant `consultorio-piloto`, 5 prestaciones ficticias, sillón "Box 1" y una Dueña `duena.piloto@example.com` cuyo hash es `pbkdf2_sha256` — `verificar_password` es bcrypt-only y `tests/test_seguridad_passwords.py:60` afirma que ese hash **nunca** autentica. O sea: para verificar el login de la demo hace falta crear un usuario demo con hash bcrypt.
- `FRONT_URL` figura en compose/.env.example pero no se lee desde el backend; no requiere cambios.

## Goals / Non-Goals

**Goals:**
- Que `docker compose up --build` deje **frontend y api levantados y comunicados** (mismo origen), listos para grabar la demo del TP.
- Verificación reproducible del flujo público de reserva (`/reservar/consultorio-piloto`) y del login contra el backend **a través del proxy del frontend**, contra API + PostgreSQL reales (R11).
- Mantener intactos R1 (schemas Pydantic), R4 (`tenant_id` del token), R6 (sin clínicos en `localStorage`), R8 (montos del servidor), R9/R13 (sin PHI ni datos reales).

**Non-Goals:**
- No pantallas nuevas ni componentes React (C-16 y C-17 siguen pendientes); la UI de login de staff no existe y **no** se crea acá: el login se verifica por HTTP contra el proxy.
- No tocar lógica de negocio, endpoints, migraciones, seeds de prestaciones ni el backend más allá de una utilería dev de usuario demo.
- No habilitar CORS, no enrutar webhooks (`/webhooks/*`) por el frontend, no incluir C-14 (auditoría/exportación).

## Decisions

### 1. Servicio `frontend` en `docker-compose.yml`
- `build.context: ./src/frontend`, `dockerfile: Dockerfile.frontend` (imagen existente, sin cambios), puerto **`8080:80`** (el `8000` es de api, el `5173` está reservado al dev server de Vite y el `8025` a mailhog) y `depends_on: api` con `condition: service_healthy` para que el video no arranque con el proxy apuntando a una API caída.
- Alinear `FRONT_URL` del servicio `api` (hoy `http://localhost:5173`, `docker-compose.yml:43`) a `http://localhost:8080`: la KB (`08_arquitectura_propuesta.md`, §Variables de entorno) define `FRONT_URL` como la URL pública del front para armar links; aunque `Settings.front_url` todavía no se lee desde el código (`settings.py:40`), dejar el valor viejo sería un cable suelto que apuntaba al dev server.
- El healthcheck lo hereda del `Dockerfile` (wget a `127.0.0.1:80`): no se duplica en compose.
- **Alternativa descartada**: levantar `npm run dev` (Vite) como servicio — requiere node en el host o una imagen de dev, y no es "el frontend levantado" en el sentido de build de producción del video.

### 2. Reverse proxy `/api/` en `src/frontend/nginx.conf`
- Bloque `location /api/` con `proxy_pass http://api:8000;` (**sin URI** → preserva el path tal cual, evita el clásico doble `/api`), `proxy_http_version 1.1`, `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` y timeouts por defecto. El `try_files ... /index.html` sigue cubriendo todo lo que no sea `/api/` (y el Service Worker ya excluye `^/api/` con `navigateFallbackDenylist`).
- El `proxy_temp_path` ya está en `/tmp` en el conf actual: nginx no-root puede escribir los temporales del proxy sin permisos extra.
- **Alternativas descartadas**: (a) CORS en FastAPI + `VITE_API_URL=http://localhost:8000` — expone el backend en otro origen y el backend hoy no tiene CORS; (b) subir Vite en compose — imagen de dev, no build de producción; (c) tunelar solo `/api/reservar` — el login y `/api/auth/*` también necesitan el proxy.

### 3. Usuario demo con credenciales utilizables (login de la demo)
- Utilería dev idempotente `src/backend/app/scripts/usuario_demo.py` (`python -m app.scripts.usuario_demo`): con el DSN owner hace upsert de un usuario ficticio (`demo.piloto@example.com`, tenant `consultorio-piloto`, rol `recepcion`) usando `hashear_password` (bcrypt) y **`DEMO_PASSWORD` del entorno** (placeholder nuevo en `.env.example`, R10: nunca secretos reales en el repo; si falta, falla con mensaje rioplatense nombrando la variable).
- **Alternativas descartadas**: cambiar `_hash_dev` del seed a bcrypt (rompería el contrato ya testeado de "hash viejo no autentica" y afecta a todos los entornos); crear el usuario vía `POST /api/usuarios` (exige login previo → círculo vicioso); hardcodear el password en el código (R10).

### 4. Verificación end-to-end (R11, ≥2 casos por comportamiento)
- Tests de integración `tests/test_demo_frontend.py` con `httpx` contra `DEMO_BASE_URL` (default `http://localhost:8080`), **sin mocks de DB**: la API real dentro de compose habla con el PostgreSQL del contenedor. Si el stack no está arriba, se skipean con mensaje claro que indica cómo levantarlo (patrón ya usado en el repo).
- Comportamientos y sus casos (≥2 por comportamiento — R11):
  1. *Proxy conserva respuestas de la API*: `GET /api/health` → 200 con JSON de estado; `POST /api/auth/login` con password malo → 401 con `detail` rioplatense (nunca `index.html`).
  2. *Reserva pública (GET)*: `GET /api/reservar/consultorio-piloto` → 200 con las 5 prestaciones del seed; `GET /api/reservar/consultorio-fantasma` → 404 con mensaje de negocio.
  3. *Reserva pública (POST)*: alta 201 con `token_gestion` + seña `pendiente` con `monto_sena` del servidor (RN-PA-02, R8); y un segundo POST del mismo slot → 409 con alternativas y mensaje rioplatense (RN-AG-01, RN-GL-02), sin turno duplicado.
  4. *Frontera SPA/API*: `/reservar/consultorio-fantasma` → 200 `text/html` con el shell; `/api/ruta-inexistente` → 404 JSON de FastAPI.
  5. *Upstream caído*: `docker compose stop api` → `GET /api/health` por el proxy responde 502/504 sin `index.html` ni stack traces (RN-GL-02) y `docker compose start api` restaura el 200.
- Además, verificación manual de login **exitoso** (curl vía proxy con el usuario demo) y del alta de reserva desde el navegador en `http://localhost:8080/reservar/consultorio-piloto` (smoke del video).
- Como el rate limit de login es 5/60 s por IP+email (C-03), los casos usan emails distintos por test y no repiten intentos fallidos.

### 5. Evidencia y docs
- `consultar_prestaciones` (MCP propio) se usa durante la preparación para confirmar el catálogo real del seed con el que se prueba la demo; la evidencia queda en `evidence/` junto a la del gate `sdd-change-review`.
- `README.md`: reemplazar la nota "el compose todavía no declara ese servicio" por los comandos de la demo (`docker compose up --build`, `migrar`, seed, usuario demo, URL `http://localhost:8080`). `CHANGES.md`: entrada C-18 con propósito/alcance/exclusiones/dependencias/"Leer antes".

## Risks / Trade-offs

- [El host ya tiene un Postgres nativo escuchando en `5432` (máquina de esta sesión)] → el servicio `db` de compose no podrá bindear ese puerto. Mitigación: detectarlo en la verificación (`docker compose up` avisa del conflicto) y, si ocurre, documentarlo en README con la salida (`docker compose down` + detener el servicio ajeno, o mapeo temporal distinto **solo** para la verificación); no se cambia el compose por eso.
- [Login rate limit (5/60 s) y Redis `fail-closed` 503] → los tests de login usan un solo intento fallido por caso con emails distintos, y el caso de éxito no repite.
- [Webhooks de MP/WA] → siguen entrando directo a `api:8000` (puerto publicado); el proxy solo cubre `/api/`, así que `/webhooks/*` no se intercepta. Cualquier cambio ahí sería de C-12, no de este change.
- [Service Worker cacheando respuestas de API] → el `runtimeCaching` de `/api/` ya usa `NetworkFirst` (GET) / `NetworkOnly` (POST) y `navigateFallbackDenylist: [/^\/api\//]`; el proxy no agrega `proxy_cache`, así que no se duplica caché.
- [Imágenes y build del frontend en cada `--build`] → capa `npm ci` cacheada por `package-lock.json`; solo se reconstruye si cambian lock/src.
- [Datos de la demo] →100% ficticios del seed (R13); los logs de verificación no contienen DNI ni datos clínicos (R9).

## Migration Plan

1. Editar `src/frontend/nginx.conf` (agregar `location /api/`) y `docker-compose.yml` (servicio `frontend`) + placeholder `DEMO_PASSWORD` en `.env.example`.
2. Levantar: `docker compose up --build -d` → `docker compose run --rm migrar` → seed → `python -m app.scripts.usuario_demo`.
3. Correr `pytest tests/test_demo_frontend.py` + smoke manual (reserva y login en el navegador/curl) y actualizar README/CHANGES.
4. **Rollback**: no hay migraciones ni dependencias de datos; revertir los dos archivos de config y el script deja el repo en el estado anterior (`docker compose down`).
