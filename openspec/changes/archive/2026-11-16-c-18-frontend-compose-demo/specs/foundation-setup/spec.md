# Spec Delta

## MODIFIED Requirements

### Requirement: Stack completo levantable con un comando

El sistema SHALL proveer un `docker-compose.yml` con api, postgres, redis, worker, frontend y mailhog (dev) que levanta el stack completo con un solo comando; el servicio `frontend` SHALL construirse desde `src/frontend/Dockerfile.frontend` (nginx no-root con healthcheck propio) y depende de `api`.

#### Scenario: Levantar el stack piloto

- **GIVEN** una máquina con Docker Compose y el `.env` configurado
- **WHEN** se ejecuta `docker compose up`
- **THEN** los servicios api, postgres, redis, worker, frontend y mailhog quedan corriendo y `GET /api/health` responde 200

#### Scenario: Frontend sirve la PWA sin herramientas de build en el host

- **GIVEN** el stack completo levantado con `docker compose up --build`
- **WHEN** un navegador pide `http://localhost:8080/`
- **THEN** el contenedor `frontend` responde 200 con el shell de la PWA y su healthcheck reporta `healthy`, sin que el host necesite `node` ni `npm`

## ADDED Requirements

### Requirement: Proxy inverso de la API en el frontend servido por compose

El sistema SHALL servir la PWA desde el nginx del servicio `frontend` y hacer proxy inverso de `/api/` hacia `http://api:8000` en la red interna de compose, preservando método, path, cuerpo, headers y código de estado, de modo que la PWA consuma la API en mismo origen y sin CORS.

#### Scenario: Health de la API a través del proxy

- **GIVEN** el stack completo levantado
- **WHEN** se hace `GET http://localhost:8080/api/health`
- **THEN** el frontend devuelve el JSON de `api:8000` con status 200, en mismo origen y sin redirección

#### Scenario: Login con credenciales inválidas conserva el error de negocio

- **GIVEN** el stack completo levantado
- **WHEN** se hace `POST http://localhost:8080/api/auth/login` con un password incorrecto
- **THEN** la respuesta es 401 con el `detail` en rioplatense de la API, sin stack traces, y el proxy no la reemplaza por el shell de la SPA

#### Scenario: Rutas de SPA y de API no se pisan

- **GIVEN** el stack completo levantado
- **WHEN** se pide `http://localhost:8080/reservar/consultorio-fantasma` y después `http://localhost:8080/api/ruta-inexistente`
- **THEN** la primera responde 200 con `index.html` (fallback SPA) y la segunda responde 404 en JSON de FastAPI, nunca `index.html`

#### Scenario: API caída tras el arranque

- **GIVEN** el stack levantado y el servicio `api` detenido o sin responder
- **WHEN** el navegador pide `http://localhost:8080/api/health`
- **THEN** el proxy devuelve el error del upstream (502/504) sin stack traces y sin servir `index.html`, y la PWA muestra un aviso de servicio caído en rioplatense

### Requirement: Verificación end-to-end de la demo de reserva y login

El sistema SHALL permitir verificar con el stack levantado el flujo público de reserva y el login del staff a través del frontend servido por compose, contra la API y PostgreSQL reales (R11), con datos 100% ficticios del seed.

#### Scenario: Catálogo y slots del consultorio seed

- **GIVEN** el stack levantado con migraciones y seed (`consultorio-piloto`)
- **WHEN** se hace `GET http://localhost:8080/api/reservar/consultorio-piloto`
- **THEN** responde 200 con las 5 prestaciones activas del seed, sus profesionales y sillones, y los slots calculados sin solapamientos

#### Scenario: Login del staff a través del proxy

- **GIVEN** el stack levantado y un usuario demo de prueba creado con credenciales conocidas (ficticias)
- **WHEN** se hace `POST http://localhost:8080/api/auth/login` con esas credenciales
- **THEN** responde 200 con `access_token`, `expira_en_segundos` y la identidad del usuario, y la cookie `refresh_token` llega `HttpOnly`

#### Scenario: Consultorio inexistente

- **GIVEN** el stack levantado
- **WHEN** se hace `GET http://localhost:8080/api/reservar/consultorio-fantasma`
- **THEN** responde 404 con el mensaje rioplatense de la API indicando que el consultorio no existe o no está activo

#### Scenario: Reserva pública confirmada desde el navegador

- **GIVEN** el stack levantado y `http://localhost:8080/reservar/consultorio-piloto` abierto en el navegador
- **WHEN** un paciente completa datos ficticios válidos y envía la reserva de un slot disponible
- **THEN** el navegador recibe el `token_gestion` desde el servidor y ve la confirmación, con los montos provistos por la API (R8) y sin persistir datos clínicos en `localStorage` (R6)

#### Scenario: Reserva de prestación con seña

- **GIVEN** el stack levantado y la prestación "Endodoncia" (`requiere_sena: true`) elegida en `/reservar/consultorio-piloto`
- **WHEN** el paciente envía la reserva de un slot libre
- **THEN** la respuesta `201` del servidor incluye `requiere_sena: true`, `monto_sena` exacto (15000) y `token_gestion`, con la Seña creada en estado `pendiente` (RN-PA-02) y sin montos calculados en el navegador (R8)

#### Scenario: Slot tomado concurrentemente

- **GIVEN** el stack levantado y un slot reservado hace instantes por otro paciente
- **WHEN** un segundo paciente envía la reserva del mismo slot para el mismo profesional y sillón
- **THEN** la API responde 409 con slots alternativos y mensaje en rioplatense (RN-AG-01, RN-GL-02), sin crear un segundo turno
