# Tasks

## 1. Servicio `frontend` en docker-compose

- [x] 1.1 Agregar el bloque `service frontend` en `docker-compose.yml` (build `context: ./src/frontend` + `dockerfile: Dockerfile.frontend`, puerto `8080:80`, `depends_on: api` con `condition: service_healthy`) y alinear `FRONT_URL` del servicio `api` a `http://localhost:8080` (hoy apunta al dev server de Vite); verificar con `docker compose config --services` que el servicio aparece y con `docker compose config` que el YAML sigue válido y `FRONT_URL` quedó actualizado.
- [ ] 1.2 Verificar el build de la imagen con `docker compose build frontend` en verde (capa `npm ci` + `npm run build` + nginx no-root) y con `docker inspect --format '{{json .Config.Healthcheck}}' <imagen>` comprobar que el healthcheck `wget http://127.0.0.1:80/` quedó heredado del `Dockerfile.frontend`.
- [ ] 1.3 Verificar el escenario "Frontend sirve la PWA sin herramientas de build en el host": con el stack arriba, `curl -i http://localhost:8080/` responde `200` con `text/html` (shell de la SPA) y `docker compose ps` muestra el contenedor `frontend` `healthy` sin haber instalado `node`/`npm` en el host.

## 2. Reverse proxy `/api` en nginx + tests de integración

- [x] 2.1 Agregar el bloque `location /api/` en `src/frontend/nginx.conf` con `proxy_pass http://api:8000;` (sin URI), `proxy_http_version 1.1`, headers `Host`/`X-Real-IP`/`X-Forwarded-For`/`X-Forwarded-Proto`, sin `proxy_cache` y sin romper el `try_files ... /index.html`; verificar con `docker compose build frontend` y luego `docker run --rm <imagen> nginx -t` (config test en verde).
- [ ] 2.2 Crear `tests/test_demo_frontend.py` (httpx contra `DEMO_BASE_URL`, default `http://localhost:8080`, skip con mensaje de cómo levantar el stack si no responde) con los 2 casos del proxy: `GET /api/health` → `200` con JSON de estado de la API, y `POST /api/auth/login` con password incorrecto → `401` con `detail` rioplatense (nunca `index.html`); verificar con `pytest tests/test_demo_frontend.py -q` contra el stack levantado (API + PostgreSQL reales, sin mocks de DB — R11).
- [ ] 2.3 Sumar al mismo archivo los 2 casos de reserva pública: `GET /api/reservar/consultorio-piloto` → `200` con las 5 prestaciones activas del seed (Limpieza, Consulta, Arreglo, Endodoncia, Extracción) y `GET /api/reservar/consultorio-fantasma` → `404` con mensaje de negocio en rioplatense; verificar con `pytest tests/test_demo_frontend.py -q`.
- [ ] 2.4 Sumar los 2 casos de frontera SPA/API: `GET /reservar/consultorio-fantasma` → `200` `text/html` con el shell de la SPA, y `GET /api/ruta-inexistente` → `404` en JSON de FastAPI (nunca `index.html`); verificar con `pytest tests/test_demo_frontend.py -q`.
- [ ] 2.5 Sumar el caso de doble reserva a través del proxy: dos `POST /api/reservar/consultorio-piloto` sobre el mismo slot → el segundo responde `409` con slots alternativos y mensaje rioplatense (RN-AG-01) sin crear un segundo turno; verificar con `pytest tests/test_demo_frontend.py -q`.
- [ ] 2.6 Verificar el caso de upstream caído: `docker compose stop api` y pedir `GET http://localhost:8080/api/health` → error del proxy `502`/`504` sin `index.html` ni stack traces, y `docker compose start api` devuelve todo a `200` (RN-GL-02); dejarlo registrado como smoke manual en el reporte de verificación.

## 3. Usuario demo con credenciales utilizables (login)

- [ ] 3.1 Crear la utilería dev `src/backend/app/scripts/usuario_demo.py` (`python -m app.scripts.usuario_demo`) que con el DSN owner hace upsert del usuario ficticio `demo.piloto@example.com` (tenant `consultorio-piloto`, rol `recepcion`) usando `hashear_password` (bcrypt) y `DEMO_PASSWORD` del entorno (si falta, falla con mensaje rioplatense que nombra la variable, sin imprimir el password); verificar ejecutándola **dos veces seguidas** (idempotente:1 sola fila) y comprobando en la DB que `password_hash` empieza con `$2b$`, más `ruff check` + `mypy --config-file src/backend/pyproject.toml src/backend/app/scripts` limpios (R2).
- [ ] 3.2 Verificar el login exitoso a través del proxy: `curl -i -X POST http://localhost:8080/api/auth/login -H "Content-Type: application/json" -d '{"email":"demo.piloto@example.com","password":"<DEMO_PASSWORD>"}'` → `200` con `access_token`, `expira_en_segundos` y `usuario`, y la cookie `refresh_token` llega `HttpOnly`; usando como máximo1 intento fallido por caso para no disparar el rate limit (5/60 s por IP+email).

## 4. Verificación end-to-end de la demo + documentación

- [ ] 4.1 Verificar el flujo completo de reserva pública en el navegador: abrir `http://localhost:8080/reservar/consultorio-piloto`, elegir prestación (Endodoncia), slot disponible y datos **ficticios**, enviar y comprobar que aparece la confirmación con `token_gestion` devuelto por el servidor; registrar el resultado como smoke del video del TP.
- [ ] 4.2 Verificar las reglas de dinero y de datos en el flujo: la respuesta `201` de la reserva trae `requiere_sena: true`, `monto_sena` = 15000 y la Seña en estado `pendiente` (RN-PA-02), el monto mostrado sale de la respuesta de la API y no de cálculos del cliente (R8), y en DevTools no hay datos clínicos ni DNI en `localStorage` (R6, R9).
- [ ] 4.3 Verificar el levantamiento desde cero siguiendo el README: `docker compose down` → `docker compose up --build -d` → `docker compose run --rm migrar` → seed → usuario demo → `pytest tests/test_demo_frontend.py -q` en verde (R11) y `GET http://localhost:8080/api/health` en `200`.
- [ ] 4.4 Actualizar `README.md`: reemplazar la nota "el compose todavía no declara ese servicio" por la sección de demo (comandos + URL `http://localhost:8080` + usuario demo) y verificar que los comandos documentados corren tal cual están escritos.

## 5. Cierre de calidad

- [ ] 5.1 Correr `openspec validate c-18-frontend-compose-demo --strict` en verde, la suite completa del backend (`pytest -q` con `DATABASE_URL_TEST` contra PostgreSQL real, R11) sin regresiones y `ruff check` + `mypy` limpios.
- [ ] 5.2 Confirmar que el diff no toca lógica de negocio, endpoints, migraciones ni seeds de prestaciones (alcance del proposal) y que `git status` no muestra `.env` ni secretos (R10); verificar con `git diff --stat` que los archivos cambiados son los previstos en Impact.

## Workflow follow-up

- Aplicar el change con `/opsx:apply c-18-frontend-compose-demo` (TDD estricto) y archivarlo con `/opsx:archive` cuando esté verificado.
- Pushear a GitHub en el cambio (R12), sin commitear `.env`/secretos.
