# Proposal

## Why
El `docker-compose.yml` del proyecto **no declara el servicio `frontend`** (solo `api`, `db`, `redis`, `worker`, `migrar` y `mailhog`), tal como lo admite el propio `README.md` (sección "Estado del frontend"). Hoy la única forma de ver la UI es `npm run dev` en el 5173 con el proxy de Vite o un build estático sin `/api`, y la consigna del trabajo práctico exige mostrar en el video "frontend y backend levantados con el flujo implementado". La imagen nginx no-root ya existe y funciona (`src/frontend/Dockerfile.frontend` + `src/frontend/nginx.conf`, con `npm run build` en verde): falta cablearla al stack y darle el reverse proxy hacia `api:8000`.

## What Changes
- **Servicio `frontend` en `docker-compose.yml`**: build desde `src/frontend/Dockerfile.frontend` (nginx no-root con healthcheck propio), publicación de su puerto en el host, `depends_on` de `api`, sin tocar el resto de servicios.
- **Reverse proxy `/api` en `src/frontend/nginx.conf`**: `location /api/` → `proxy_pass http://api:8000` dentro de la red de compose (mismo origen, sin CORS), preservando método, path, headers y código de estado; el SPA fallback (`try_files ... /index.html`) sigue cubriendo el resto de las rutas.
- **Documentación**: actualizar la nota de estado del frontend en `README.md` y dejar el comando de levantamiento/verificación de la demo.
- **Verificación end-to-end**: con el stack completo levantado, comprobar el flujo público de reserva (`/reservar/{slug}`) y el login contra el backend **a través del proxy del frontend**, con tests de integración contra la API real (R11).
- **`CHANGES.md`**: nueva entrada C-18 con propósito, alcance, exclusiones, dependencias y "Leer antes".

## Capabilities

### New Capabilities
<!-- Ninguna: el comportamiento nuevo pertenece a la infraestructura base ya cubierta por foundation-setup -->

### Modified Capabilities
- `foundation-setup`: el requisito "Stack completo levantable con un comando" ahora incluye el servicio `frontend` además de api, postgres, redis, worker y mailhog; se agregan requisitos de proxy inverso `/api` hacia `api:8000` y de verificación end-to-end de la demo (reserva pública + login) sobre el stack levantado.

## Impact
- **Infraestructura**: `docker-compose.yml` (+servicio `frontend` y `FRONT_URL` alineado a `http://localhost:8080`), `src/frontend/nginx.conf` (+bloque `location /api/`), `README.md` (estado y verificación), `CHANGES.md` (entrada C-18).
- **Backend / API**: **sin cambios** — ni lógica de negocio, ni endpoints, ni migraciones, ni modelos (R1, R4, R8 intactos). Los webhooks de Mercado Pago/WhatsApp siguen llegando directo a `api:8000` (puerto publicado), no pasan por el frontend.
- **Frontend**: sin pantallas nuevas ni cambios de componentes React; solo la configuración de nginx (mismo origen para `fetch` de `/api`, por lo que `VITE_API_URL` queda vacío como hoy).
- **Tests**: nuevo(s) test(s) de integración que ejercitan el stack levantado contra API + PostgreSQL reales (R11), con al menos 2 casos por comportamiento.
- **Exclusiones**: no implementa pantallas nuevas (C-16 `frontend-agenda-clinica` y C-17 `frontend-caja-os-admin` siguen pendientes), no toca auditoría/exportación (C-14), ni lógica de negocio backend, ni seeds, ni migraciones.
