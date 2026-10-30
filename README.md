# Turnos Consultorio Odontología

SaaS multi-tenant de gestión odontológica para consultorios y clínicas de
Argentina y Latinoamérica: agenda multi-profesional con anti-solapamiento,
reserva online 24/7, historia clínica + odontograma FDI, caja/señas con
Mercado Pago, obras sociales y recordatorios por WhatsApp.

Video explicativo:
https://youtu.be/sK8yQHpTE8E

## Clonar

```bash
git clone https://github.com/jeronimocoronel784-hue/turnos-odontologia
cd turnos-odontologia
```

## Prerrequisitos

| Herramienta | Versión mínima |
|---|---|
| Docker + Docker Compose | Docker 24 / Compose v2 |
| Python | 3.12 |
| Node | 22 |

## Configurar entorno

```bash
cp .env.example .env
```

Completá en `.env` las variables obligatorias (el compose no arranca sin
ellas): `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` y `JWT_SECRET`. El resto tiene
valores de ejemplo en `.env.example`. NUNCA commitees `.env` con secretos
(R10).

## Levantar stack

```bash
docker compose up --build
```

Servicios:

| Servicio | Qué es | Puerto |
|---|---|---|
| `api` | FastAPI | :8000 |
| `db` | PostgreSQL 15 | :5432 |
| `redis` | Redis 7 (colas/caché) | :6379 |
| `worker` | Worker de colas | — |
| `mailhog` | Email transaccional en dev | :8025 (UI) / :1025 (SMTP) |

> Estado del frontend: la PWA tiene imagen nginx lista en
> `src/frontend/Dockerfile.frontend` (+ `src/frontend/nginx.conf`), pero el compose todavía no
> declara ese servicio. Para desarrollo del front: `cd src/frontend && npm ci &&
> npm run dev`.

## Migraciones y seed

```bash
# Migraciones (servicio `migrar`, perfil tools)
docker compose --profile tools run --rm migrar
# Equivalente local:
cd src/backend && alembic upgrade head
```

La migración `001` crea `tenant`, `usuario` y `auditoria` (+ rol `turnos_app`
restringido: solo INSERT+SELECT en auditoría). El seed piloto es 100%
ficticio (1 tenant + 1 Dueño + matriz de permisos base, idempotente):

```bash
cd src/backend && python -m app.infrastructure.seed
```

## Correr tests

Backend con **DB real en contenedor, sin mocks de DB** (R11):

```bash
python -m pytest tests -q
```

Frontend (tipos + build, desde `src/frontend/`):

```bash
cd src/frontend && npm ci && npm run build
```

Lint + tipos (mismos comandos que CI):

```bash
ruff check --config src/backend/pyproject.toml src/backend tests
ruff format --check --config src/backend/pyproject.toml src/backend tests
mypy src/backend/app src/backend/alembic
```

## Health check

```bash
curl http://localhost:8000/api/health
```

- `200` con `{"estado":"ok",...}` si API + PostgreSQL + Redis responden.
- `503` con `detalle` en rioplatense indicando qué servicio está caído
  (sin stack traces ni datos sensibles).

## Autenticación (C-03)

Todo endpoint interno exige `Authorization: Bearer <access_token>`. El access
token es un JWT HS256 de vida corta (`JWT_ACCESS_MIN`, 15 min por defecto) con
los claims `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.
El `tenant_id` efectivo sale **siempre** del token (R4): un `tenant_id` en body,
query o path se ignora o se rechaza con 422.

| Endpoint | Body | Éxito | Errores |
|---|---|---|---|
| `POST /api/auth/login` | `{"email","password","tenant_slug"?}` | `200` access + cookie | `400` email en 2 consultorios, `401` credenciales, `429` rate limit, `503` Redis caído |
| `POST /api/auth/refresh` | — (cookie) | `200` access nuevo + cookie rotada | `401` sin cookie / vencido / revocado / reúso |
| `POST /api/auth/logout` | — (cookie) | `204` siempre, cookie borrada | — |
| `GET /api/auth/me` | — | `200` identidad | `401` sin token o inválido |

`tenant_slug` solo hace falta si el mismo email existe en más de un
consultorio; sin él, el login responde `400` pidiendo el consultorio. Cualquier
input que intente mandar `tenant_id` o que no valide el schema responde `422`.

Ejemplo de login:

```bash
curl -i -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"duena.piloto@example.com","password":"<password>"}'
```

<!-- contrato-login -->
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.firma",
  "token_type": "bearer",
  "expira_en_segundos": 900,
  "usuario": {
    "id": "6f1c8a3e-4b2d-4f5a-9c7e-1a2b3c4d5e6f",
    "tenant_id": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
    "tenant_slug": "consultorio-piloto",
    "email": "duena.piloto@example.com",
    "nombre": "Dueña Piloto Ficticia",
    "roles": ["dueno"]
  }
}
```

El **refresh token nunca viaja en el body**: se entrega en la cookie
`refresh_token`, que siempre es `HttpOnly` + `SameSite=Lax` + `Path=/api/auth`,
lleva `Secure` cuando `COOKIE_SECURE=true` (default; `false` solo en dev sobre
`http://localhost`) y dura `JWT_REFRESH_DAYS` días. Cada refresh rota el token:
el anterior queda revocado y, si se reutiliza, se revoca toda la familia de la
sesión y se audita `auth.refresh_reuso`.

Todos los rechazos usan mensajes rioplatenses accionables y nunca revelan si un
recurso o un usuario existe (RN-GL-02, R9).

## Catálogo y configuración (C-04)

Endpoints administrativos multi-tenant protegidos por `Recurso.CONFIGURACION` (`dueno`: CRUD; `recepcion` y `odontologo`: solo lectura `GET`). Bajas lógicas con `activo=False` / `activa=False` (R7) y trazabilidad completa en `auditoria`:

| Método | Endpoint | Roles permitidos | Descripción |
|---|---|---|---|
| `GET /api/admin/sillones` | Listar sillones | Dueño, Recepción, Odontólogo | Lista sillones del consultorio (filtros `?solo_activos=true`, `?sucursal=...`). |
| `POST /api/admin/sillones` | Crear sillón | Dueño | Alta de box (nombre único por tenant+sucursal). Audita `sillon.crear`. |
| `PATCH /api/admin/sillones/{sillon_id}` | Actualizar sillón | Dueño | Actualización parcial. Audita `sillon.actualizar`. |
| `DELETE /api/admin/sillones/{sillon_id}` | Desactivar sillón | Dueño | Baja lógica (`activo=False`). Audita `sillon.desactivar`. |
| `GET /api/admin/prestaciones` | Listar prestaciones | Dueño, Recepción, Odontólogo | Lista servicios del consultorio (filtro `?solo_activas=true`). |
| `POST /api/admin/prestaciones` | Crear prestación | Dueño | Alta con duración, precio particular, seña e invasiva. Audita `prestacion.crear`. |
| `PATCH /api/admin/prestaciones/{prestacion_id}` | Actualizar prestación | Dueño | Actualización parcial con revalidación de seña. Audita `prestacion.actualizar`. |
| `DELETE /api/admin/prestaciones/{prestacion_id}` | Desactivar prestación | Dueño | Baja lógica (`activa=False`). Audita `prestacion.desactivar`. |
| `GET /api/admin/coberturas` | Listar coberturas | Dueño, Recepción, Odontólogo | Lista convenios OS con filtro `?vigente_en=...`, `?obra_social=...`, `?prestacion_id=...`. |
| `POST /api/admin/coberturas` | Crear cobertura | Dueño | Alta de arancel/copago para prestación del consultorio. Audita `cobertura_os.crear`. |
| `PATCH /api/admin/coberturas/{cobertura_id}` | Actualizar cobertura | Dueño | Actualización parcial y fechas de vigencia. Audita `cobertura_os.actualizar`. |
| `DELETE /api/admin/coberturas/{cobertura_id}` | Desactivar cobertura | Dueño | Baja lógica (`activa=False`). Audita `cobertura_os.desactivar`. |
| `GET /api/admin/tenant/politicas` | Consultar políticas | Dueño, Recepción, Odontólogo | Retorna anticipación mínima, porcentaje de seña default y horas de cancelación. |
| `PATCH /api/admin/tenant/politicas` | Modificar políticas | Dueño | Merge parcial de políticas operativas. Audita `tenant.actualizar_politicas`. |

Seed piloto base: Sillón "Box 1" (sucursal central) y 5 prestaciones base (`Limpieza` 30', `Consulta` 20', `Arreglo` 45', `Endodoncia` 60', `Extracción` 45').

## Pacientes y consentimiento WhatsApp (C-05)

Endpoints protegidos por Recurso.PACIENTES (dueno y 
ecepcion: CRUD; odontologo: solo lectura GET). Bajas lógicas con ctivo=False (R7), ficha clínica 1:1 inicializada en el alta, regla RN-CO-01 de opt-in WA y servicio get_or_create_paciente para reserva pública sin login:

| Método | Endpoint | Roles permitidos | Descripción |
|---|---|---|---|
| GET /api/pacientes | Listar / buscar pacientes | Dueño, Recepción, Odontólogo | Lista pacientes del consultorio con filtros ?dni=..., ?telefono=..., ?q=... y ?solo_activos=true. |
| GET /api/pacientes/{paciente_id} | Detalle de paciente | Dueño, Recepción, Odontólogo | Consulta paciente con su ficha clínica 1:1 vinculada. |
| POST /api/pacientes | Crear paciente | Dueño, Recepción | Alta con validación de DNI único por consultorio (409 en colisión) e inicialización de ficha clínica. Audita paciente.crear. |
| PATCH /api/pacientes/{paciente_id} | Actualizar paciente | Dueño, Recepción | Modificación parcial de contacto o cobertura. Audita paciente.actualizar. |
| DELETE /api/pacientes/{paciente_id} | Desactivar paciente | Dueño, Recepción | Baja lógica (ctivo=False, R7). Audita paciente.baja. |
| PATCH /api/pacientes/{paciente_id}/optin | Consentimiento WhatsApp | Dueño, Recepción | Actualiza optin_wa (alta o STOP según RN-CO-01). Audita paciente.optin. |

## Estructura del repo

```text
src/                  Código (backend + frontend)
  backend/            FastAPI: app/ (api/ routers+schemas, domain/ Tenant, Usuario,
                      Auditoria, mixins, application/, infrastructure/ db+seed,
                      shared/ settings+db session+logging+exceptions, workers/),
                      alembic/ (001: tenant, usuario, auditoria),
                      pyproject.toml / alembic.ini / Dockerfile / .dockerignore
  frontend/           React + TS PWA (src/: features/, shared/, pages/),
                      public/ (assets PWA: manifest, íconos),
                      Dockerfile.frontend / nginx.conf,
                      package.json / vite.config.ts / tsconfig.json / tailwind.config.js /
                      postcss.config.js / index.html
tests/                Suite pytest contra DB real (conftest + 8 módulos test_*)
db/init/              Rol `turnos_app` restringido (init de Postgres)
docker-compose.yml    api + postgres + redis + worker + migrar + mailhog
docs/                 Documentación adicional e informes de discovery
knowledge-base/       Fuente de verdad del dominio (visión, datos, reglas, flujos…)
openspec/             Specs y changes de OpenSpec (fuente del CLI)
.agents/              Skills y configuración de agentes IA
.opencode/            Comandos y configuración de OpenCode
CHANGES.md            Índice operativo de implementación (17 changes, 7 fases)
AGENTS.md / CLAUDE.md Reglas del proyecto para agentes
pytest.ini / .env.example / .github/workflows/ci.yml
```

> **Nota de equivalencia:** layout vigente `src/backend/` + `src/frontend/` (tras
> `c-01-solo-setup`). Si un doc viejo menciona `backend/` o `frontend/` en raíz,
> leé `src/backend/` / `src/frontend/`; si menciona `src/app` plano, leé
> `src/backend/app/`; si menciona `backend/app/tests`, leé `tests/`.

## Nota CI

`.github/workflows/ci.yml` corre backend (pytest contra Postgres/Redis de
servicio) y frontend (`tsc` + build) en paralelo. Las credenciales que usa
(`postgres:postgres`, `turnos_app_ci`, JWT de ejemplo) son **dummies
efímeros que solo existen dentro del runner**, práctica estándar: ningún
secreto real vive en el repo.

## Troubleshooting

- **Puertos ocupados** (`5432`, `6379`, `8000`, `8025`/`1025`): otro Postgres,
  Redis o Mailhog local colisiona. Bajá el servicio local o liberá el puerto
  antes de `docker compose up`.
- **Error `Falta POSTGRES_PASSWORD / APP_DB_PASSWORD / JWT_SECRET en .env`**:
  no copiaste el entorno. Corré `cp .env.example .env` y completá esas tres
  variables.
- **Docker daemon apagado**: `docker compose` falla con error de conexión.
  Abrí Docker Desktop (o `sudo systemctl start docker`) y reintentá.
- **`/api/health` en 503**: revisá que `db` y `redis` estén `healthy`
  (`docker compose ps`) antes de mirar la API.

## Estado

- [x] C-01 `foundation-setup` (`openspec/changes/archive/2026-10-15-c-01-solo-setup/`).
- [x] C-02 `core-models-multitenant` (`openspec/changes/archive/2026-10-29-c-02-modelos-core/`).
- [x] C-03 `auth-rbac-tokens` (`openspec/changes/archive/2026-10-30-c-03-auth-rbac-tokens/`).
- [x] C-04 `catalogo-configuracion` (`openspec/changes/archive/2026-10-30-c-04-catalogo-configuracion/`).
- [ ] Próximo: C-05 `pacientes` (`/opsx:propose c-05-pacientes`).

Roadmap completo en `CHANGES.md`; dominio en `knowledge-base/`;
competencia en `discovery/discovery.md`.
