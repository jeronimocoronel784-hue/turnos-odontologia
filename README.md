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

- [x] C-01 `foundation-setup` + C-02 `core-models-multitenant` (ciclo 1,
  archivado en `openspec/changes/archive/2026-10-03-c-01-foundation-core-models/`,
  copia de entrega en `docs/changes/`).
- [ ] Próximo: C-03 `auth-rbac-tokens` (`/opsx:propose C-03-auth-rbac-tokens`).

Roadmap completo en `CHANGES.md`; dominio en `knowledge-base/`;
competencia en `discovery/discovery.md`.
