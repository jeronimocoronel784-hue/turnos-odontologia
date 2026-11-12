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

## Servidor MCP

Servidor propio en [Model Context Protocol](https://modelcontextprotocol.io)
(`mcp_server.py`, transporte **stdio**) que le da a un cliente MCP (Claude Code,
OpenCode, MCP Inspector, etc.) acceso de **solo lectura** a dos consultas del
consultorio, pensado para desarrollo y demos con datos de seed:

| Tool | Qué hace |
|---|---|
| `consultar_prestaciones` | Devuelve en JSON el catálogo de prestaciones activas (nombre, duración, precio particular, seña, invasiva). |
| `buscar_paciente_por_dni` | Busca un paciente por DNI (ignora puntos y guiones) y devuelve su ficha de contacto; si no existe responde `{"encontrado": false, ...}`. |

Ambas herramientas solo ejecutan `SELECT` y devuelven JSON: los errores llegan
como `{"error": "..."}` (sin stack traces ni datos sensibles).

### Requisitos

| Requisito | Detalle |
|---|---|
| Python | 3.12+ (probado con 3.13) |
| SDK `mcp` 2.x | `pip install "mcp>=2,<3"` — **no está en `requirements.txt`**; el código importa `mcp.server.mcpserver.MCPServer` (`mcp_server.py:10`) |
| Dependencias del repo | `pip install -r requirements.txt` (trae `asyncpg`; `python-dotenv` llega con `pydantic-settings`) |
| PostgreSQL | Con el stack arriba (`docker compose up -d db`) o un Postgres local en `localhost:5432/turnos` |

### Configuración

El repo ya trae `.mcp.json` en la raíz (versionado, **sin secretos**):

```json
{
  "mcpServers": {
    "turnos-odontologia": {
      "command": "python",
      "args": ["-u", "mcp_server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

Para reproducirlo en otro cliente MCP (transporte stdio), usá ese mismo bloque
`command`/`args`/`env` con el **directorio de trabajo = raíz del repo**. El `-u`
más las dos variables de entorno no son secretos: desactivan el buffer de stdout
y fuerzan UTF-8 para que el cliente no se cuelge esperando mensajes en Windows
(`mcp_server.py:13-16`).

#### Variables de entorno

| Variable | Default | Para qué sirve |
|---|---|---|
| `DATABASE_URL_MCP` | — | DSN preferido de PostgreSQL para las tools. Es **opcional** y no figura en `.env.example`; si querés fijarlo, agregalo a tu `.env` local (nunca commiteado, R10). |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/turnos` | Fallback si no hay `DATABASE_URL_MCP`. Funciona también el `.env` del compose: el server adapta `postgresql+asyncpg://` → `postgresql://` y el host `@db:` → `@localhost:` (`mcp_server.py:30-32`). |

Además, `load_dotenv()` (`mcp_server.py:18`) lee el `.env` de la raíz si existe.
Los valores reales de DSN viven solo en tu `.env`: este repo y el `.mcp.json`
nunca llevan credenciales (R10).

### Verificación de conexión

1. Chequeo rápido de dependencias:

   ```powershell
   python -c "from mcp.server.mcpserver import MCPServer; print('mcp ok')"
   ```

2. Listar las tools por stdio (MCP Inspector en modo CLI, sin abrir UI):

   ```powershell
   npx -y @modelcontextprotocol/inspector --cli python -u mcp_server.py --method tools/list
   ```

   Debe imprimir las dos tools: `consultar_prestaciones` y `buscar_paciente_por_dni`.

3. Ejecutar una tool:

   ```powershell
   npx -y @modelcontextprotocol/inspector --cli python -u mcp_server.py --method tools/call --tool-name consultar_prestaciones
   ```

   - Con Postgres arriba: JSON con el catálogo seed (`Limpieza`, `Consulta`,
     `Arreglo`, `Endodoncia`, `Extracción`).
   - Con la DB caída: `{"error": "Error al consultar prestaciones: ..."}` — la
     tool responde igual y la sesión MCP no se rompe.

   Para la UI interactiva (probar las dos tools a mano): `npx -y
   @modelcontextprotocol/inspector python -u mcp_server.py`.

### Troubleshooting

- **`ModuleNotFoundError: No module named 'mcp'` (o el cliente marca el server
  como desconectado al instante)**: falta el SDK del protocolo, que **no está en
  `requirements.txt`**. Solución: `pip install "mcp>=2,<3"` y reiniciar el
  cliente MCP. Es genuino: sin el SDK el import de `mcp_server.py:10` truena
  antes de abrir el canal stdio, por eso el cliente reporta falla de conexión
  en lugar de un error visible.
- **La tool devuelve `{"error": "... ConnectionDoesNotExistError ..."}` (u
  `OSError`)**: PostgreSQL no responde (Docker apagado o servicio `db` caído).
  Levantá el stack (`docker compose up -d db`) y reintentá. `get_connection()`
  usa `asyncpg.connect(..., timeout=5.0)` y el `except` devuelve el error como
  JSON (`mcp_server.py:33` y `55-59`), así que el cliente MCP sigue vivo y el
  motivo queda claro en la respuesta.
- **El cliente se cuelga sin listar tools en Windows**: buffering/encoding de
  stdout. Ya está mitigado con `python -u` + `PYTHONUNBUFFERED=1` +
  `PYTHONIOENCODING=utf-8` en `.mcp.json` y con `stdout.reconfigure(...)`
  (`mcp_server.py:13-16`); si copiás la config a otro cliente, no saques esas
  variables.

### Límites (R9, R13)

- **Solo lectura**: ninguna tool escribe, actualiza ni borra; no reemplaza a la
  API REST autenticada ni a sus reglas de tenant/RBAC.
- **Datos de desarrollo**: el seed es 100% ficticio. NUNCA usarla contra datos
  reales de pacientes ni pegar sus respuestas en logs, errores o prompts
  (R9, R13).
- **Sin credenciales propias**: el DSN sale de tu `.env` local; `.mcp.json` no
  lleva secretos y `.env` nunca se commitea (R10).

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

Endpoints protegidos por `Recurso.PACIENTES` (`dueno` y `recepcion`: CRUD; `odontologo`: solo lectura `GET`). Bajas lógicas con `activo=False` (R7), ficha clínica 1:1 inicializada en el alta, regla RN-CO-01 de opt-in WA y servicio `get_or_create_paciente` para reserva pública sin login:

| Método | Endpoint | Roles permitidos | Descripción |
|---|---|---|---|
| `GET /api/pacientes` | Listar / buscar pacientes | Dueño, Recepción, Odontólogo | Lista pacientes del consultorio con filtros `?dni=...`, `?telefono=...`, `?q=...` y `?solo_activos=true`. |
| `GET /api/pacientes/{paciente_id}` | Detalle de paciente | Dueño, Recepción, Odontólogo | Consulta paciente con su ficha clínica 1:1 vinculada. |
| `POST /api/pacientes` | Crear paciente | Dueño, Recepción | Alta con validación de DNI único por consultorio (409 en colisión) e inicialización de ficha clínica. Audita `paciente.crear`. |
| `PATCH /api/pacientes/{paciente_id}` | Actualizar paciente | Dueño, Recepción | Modificación parcial de contacto o cobertura. Audita `paciente.actualizar`. |
| `DELETE /api/pacientes/{paciente_id}` | Desactivar paciente | Dueño, Recepción | Baja lógica (`activo=False`, R7). Audita `paciente.baja`. |
| `PATCH /api/pacientes/{paciente_id}/optin` | Consentimiento WhatsApp | Dueño, Recepción | Actualiza `optin_wa` (alta o STOP según RN-CO-01). Audita `paciente.optin`. |

## Agenda y turnos (C-06)

Núcleo operativo multi-profesional y por sillón con máquina de estados cerrada (`pendiente → confirmado → presente → finalizado` y ramas `cancelado | ausente | reprogramado`, RN-AG-07), anti-solapamiento de rangos `[inicio, fin)` con respuesta `409 Conflict` + `slots_alternativos` (RN-AG-01, RN-GL-02), bloqueos horarios no reservables (RN-AG-03), reprogramación 1-clic con `turno_origen_id` (RN-AG-06) y reserva/autogestión pública por token opaco (RN-SE-03):

| Método | Endpoint | Acceso | Descripción |
|---|---|---|---|
| `GET /api/agenda` | Vista día/semana | Dueño, Recepción, Odontólogo | Turnos y bloqueos filtrables por `desde`, `hasta`, `profesional_id`, `sillon_id` y `estado`. |
| `POST /api/turnos` | Crear turno | Dueño, Recepción | Calcula `fin = inicio + duracion_min` (RN-AG-02), valida anti-solapamiento/bloqueos (o `sobreturno=true` con motivo, RN-AG-04) y emite `token_gestion`. |
| `GET /api/turnos/{turno_id}` | Detalle de turno | Dueño, Recepción, Odontólogo | Consulta un turno del consultorio. |
| `PATCH /api/turnos/{turno_id}/estado` | Transición de estado | Dueño, Recepción, Odontólogo | Aplica el grafo cerrado (RN-AG-07) y bloquea `confirmado` si exige seña impaga (RN-PA-01). Audita `turno.cambiar_estado`. |
| `POST /api/turnos/{turno_id}/reprogramar` | Reprogramar 1-clic | Dueño, Recepción, Odontólogo | Pasa el turno original a `reprogramado` y crea el nuevo en `pendiente` con `turno_origen_id`. Audita `turno.reprogramar`. |
| `GET /api/bloqueos` | Listar bloqueos | Dueño, Recepción, Odontólogo | Lista bloqueos horarios del consultorio. |
| `POST /api/bloqueos` | Crear bloqueo | Dueño, Recepción | Bloquea rango `[desde, hasta)` para profesional y/o sillón. Audita `bloqueo.crear`. |
| `DELETE /api/bloqueos/{bloqueo_id}` | Eliminar bloqueo | Dueño, Recepción | Elimina bloqueo y audita `bloqueo.eliminar`. |
| `GET /reservar/{slug}` | Disponibilidad pública | Público (sin login) | Catálogo activo del consultorio y cálculo de `slots_disponibles` reales. |
| `POST /reservar/{slug}` | Reserva online 24/7 | Público (sin login) | `get_or_create_paciente` por DNI + turno `pendiente` + `token_gestion` opaco. |
| `GET /mis-turnos/{token}` | Ver mi turno | Público (token opaco) | Consulta del turno propio sin exponer datos de terceros. |
| `POST /mis-turnos/{token}/confirmar` | Confirmar turno | Público (token opaco) | Confirmación idempotente (RN-AG-08); rechaza con `409` si exige seña impaga. |
| `POST /mis-turnos/{token}/cancelar` | Cancelar turno | Público (token opaco) | Cancela respetando `cancelacion_hs` del consultorio (RN-AG-05). |
| `POST /mis-turnos/{token}/reprogramar` | Reprogramar turno | Público (token opaco) | Reprograma en término creando nuevo turno vinculado y nuevo token. |

## Lista de espera y oferta proactiva de huecos (C-07)

Relleno automatizado de cancelaciones y reprogramaciones (**Flujo 6**) respetando orden estricto por `(prioridad ASC, created_at ASC)` (`RN-LE-01`), idempotencia por `(entrada, hueco)` con rotación automática cuando expira la ventana de respuesta (`RN-LE-02`) y colocación en 1 clic por token opaco que crea el `Turno` vinculado (`RN-LE-03`):

| Método | Endpoint | Acceso | Descripción |
|---|---|---|---|
| `GET /api/lista-espera` | Listar lista de espera | Dueño, Recepción, Odontólogo | Lista entradas del consultorio ordenadas por `(prioridad, created_at)` con filtros `?estado=...`, `?prestacion_id=...`, `?profesional_id=...`, `?paciente_id=...`. |
| `POST /api/lista-espera` | Crear entrada | Dueño, Recepción | Alta interna con `prioridad`, `canal_aviso` (`wa`/`email`) y emisión de `token_gestion`. Audita `lista_espera.crear`. |
| `GET /api/lista-espera/{entrada_id}` | Detalle de entrada | Dueño, Recepción, Odontólogo | Consulta una solicitud de lista de espera del consultorio. |
| `PATCH /api/lista-espera/{entrada_id}` | Actualizar / baja | Dueño, Recepción | Modifica `prioridad`, `canal_aviso`, `observaciones` o pasa a `baja` (rotando el hueco si estaba `avisada`). |
| `POST /api/lista-espera/ofrecer-hueco` | Ofrecer / rotar hueco | Dueño, Recepción | Vence ofertas expiradas y avisa al primer candidato compatible sin duplicar (`idempotency_key`). Audita `lista_espera.avisar`. |
| `POST /reservar/{slug}/lista-espera` | Anotarse online | Público (sin login) | `get_or_create_paciente` por DNI + alta en `activa` + `token_gestion` opaco. |
| `GET /lista-espera/{token}` | Consultar estado / oferta | Público (token opaco) | Muestra estado de la solicitud y el hueco ofrecido si está `avisada`. |
| `POST /lista-espera/{token}/aceptar` | Aceptar hueco 1-clic | Público (token opaco) | Crea el `Turno` vinculado, pasa a `colocada` (`RN-LE-03`) o devuelve `409` con `slots_alternativos` si otro ganó la carrera. |
| `POST /lista-espera/{token}/baja` | Darse de baja | Público (token opaco) | Baja idempotente y rotación inmediata del hueco al siguiente en la fila. |

## Comunicaciones, Outbox y Webhook de WhatsApp (C-08)

Sistema de mensajería transaccional y recordatorios (**Flujo 2**) basado en el patrón **Outbox + Worker Redis**, con deduplicación estricta por `idempotency_key` (`RN-CO-02`), respeto obligatorio de `optin_wa` (`RN-CO-01`: omisión auditada si no tiene opt-in y baja inmediata ante `STOP`), reintentos con backoff exponencial (`RN-CO-03`), plantillas versionadas (`RN-CO-04`) y verificación criptográfica `X-Hub-Signature-256` (HMAC-SHA256, `R8`) en el webhook de WhatsApp:

| Método | Endpoint | Acceso | Descripción |
|---|---|---|---|
| `GET /api/mensajes` | Listar outbox | Dueño, Recepción | Lista envíos del consultorio filtrables por `estado`, `turno_id`, `paciente_id`. |
| `POST /api/mensajes` | Encolar mensaje | Dueño | Encola mensaje de forma idempotente renderizando la última versión activa de la plantilla. |
| `POST /api/mensajes/{mensaje_id}/reenviar` | Reenviar mensaje | Dueño, Recepción | Reinicia intentos y despacha de inmediato un mensaje `fallido`/`omitido`. Audita `mensaje.reenviar`. |
| `POST /api/mensajes/procesar-outbox` | Procesar pendientes | Dueño | Ejecuta el ciclo de despacho de mensajes `pendiente` vencidos del consultorio. |
| `GET /api/plantillas` | Listar plantillas | Dueño, Recepción | Lista versiones de plantillas (`confirmacion_reserva`, `recordatorio_24h`, `cancelacion_turno`, `hueco_lista_espera`, `sena_pendiente`). |
| `POST /api/plantillas` | Nueva versión | Dueño | Crea una nueva versión incremental `(codigo, canal, version+1)`. Audita `plantilla.crear_version`. |
| `GET /webhooks/whatsapp` | Challenge Meta | Público (token Meta) | Verificación de suscripción del webhook (`hub.mode=subscribe` + `hub.verify_token`). |
| `POST /webhooks/whatsapp` | Eventos WhatsApp | Público (firma HMAC) | Valida `X-Hub-Signature-256`, deduplica por `event_id`, confirma turnos (`RN-AG-08`) y procesa bajas `STOP` (`RN-CO-01`). |

## Estructura del repo

```text
src/                  Código (backend + frontend)
  backend/            FastAPI: app/ (api/ routers+schemas, domain/ Tenant, Usuario,
                      Auditoria, mixins, application/, infrastructure/ db+seed,
                      shared/ settings+db session+logging+exceptions, workers/),
                      alembic/ (001..013: tenant, usuario, auditoria, auth, catalogo, pacientes,
                      agenda, lista_espera, comunicaciones, clinica, presupuestos, caja/señas,
                      mercadopago, obras sociales),
                      pyproject.toml / alembic.ini / Dockerfile / .dockerignore
  frontend/           React + TS PWA (src/: features/, shared/, pages/),
                      public/ (assets PWA: manifest, íconos),
                      Dockerfile.frontend / nginx.conf,
                      package.json / vite.config.ts / tsconfig.json / tailwind.config.js /
                      postcss.config.js / index.html
tests/                Suite pytest contra DB real (conftest + módulos test_*)
db/init/              Rol `turnos_app` restringido (init de Postgres)
docker-compose.yml    api + postgres + redis + worker + migrar + mailhog
docs/                 Documentación adicional e informes de discovery
knowledge-base/       Fuente de verdad del dominio (visión, datos, reglas, flujos…)
openspec/             Specs y changes de OpenSpec (fuente del CLI)
.agents/              Skills y configuración de agentes IA
.opencode/            Comandos y configuración de OpenCode
CHANGES.md            Índice operativo de implementación (17 changes, 7 fases)
AGENTS.md / CLAUDE.md Reglas del proyecto para agentes
pytest.ini / .env.example / .mcp.json / mcp_server.py / .github/workflows/ci.yml
```

> **Nota de equivalencia:** layout vigente `src/backend/` + `src/frontend/` (tras
> `c-01-solo-setup`). Si un doc viejo menciona `backend/` o `frontend/` en raíz,
> leé `src/backend/` / `src/frontend/`; si menciona `src/app` plano, leé
> `src/backend/app/`; si menciona `backend/app/tests`, leé `tests/`.

## Historia Clínica, Odontograma FDI y Consentimiento Informado (C-09)

- **Migración `008_historia_clinica_odontograma`**: crea las tablas `evolucion`, `odontograma`, `pieza_evento`, `adjunto_clinico` y `consentimiento` con permisos `GRANT/REVOKE` para `turnos_app`.
- **Inmutabilidad Clínica (`R7`, `RN-CL-01`, `RN-CL-03`)**:
  - `GET/PUT /api/pacientes/{id}/ficha`: la edición está restringida a `ODONTOLOGO` y `DUENO` (`Recurso.CLINICA`); cada cambio de anamnesis genera automáticamente una `Evolucion` y un evento en `Auditoria` sin exponer PHI (`R9`). `RECEPCION` posee permiso de solo lectura.
  - `GET/POST /api/pacientes/{id}/evoluciones` y `GET/POST /api/pacientes/{id}/adjuntos`: evoluciones append-only con soporte de enmienda aditiva (`es_correccion_de_id`).
- **Odontograma FDI (`RN-CL-01`)**:
  - `GET /api/odontograma/{paciente_id}`, `POST /api/odontograma/{paciente_id}/eventos` y `GET /api/odontograma/{paciente_id}/piezas/{pieza_fdi}/historial` validan piezas permanentes (`11–48`) y deciduas (`51–85`), proyectando el estado actual por pieza/superficie sin sobrescribir el historial.
- **Consentimiento Informado (`RN-CL-02`, `RN-SE-03`)**:
  - `GET/POST /api/consentimientos`, `POST /api/consentimientos/{id}/firmar`, `POST /api/consentimientos/{id}/revocar` y el canal público sin login `GET/POST /firmar/{token}` registran `firma_hash` SHA-256.
  - Cuando un turno corresponde a una prestación con `invasiva = True`, la transición a `presente` exige un consentimiento firmado y no revocado (`409 Conflict` si falta).

## Presupuestos y Planes de Tratamiento (C-10)

- **Migración `009_presupuestos_planes`**: crea las tablas `presupuesto`, `presupuesto_item` y `presupuesto_turno` con permisos `GRANT/REVOKE` para `turnos_app`.
- **Cálculo en Servidor (`R8`, `RN-OS-01`)**:
  - `POST /api/presupuestos` y `POST /api/presupuestos/{id}/items` calculan `precio_unit`, `cobertura_os` (según convenio activo y vigente en `cobertura_os`) y `a_cargo = precio_unit * cantidad - cobertura_os`; sin convenio vigente se factura como particular (`cobertura_os = 0`).
- **Consentimiento Obligatorio en Invasivas y Vínculo con Turnos (`RN-CL-04`, `US-022`)**:
  - `POST /api/presupuestos/{id}/aceptar` exige consentimiento firmado vigente para toda prestación invasiva incluida (`409 Conflict` si falta).
  - `GET/POST /api/presupuestos/{id}/turnos` asocia las citas al plan y pasa el presupuesto de `aceptado` a `en_curso` hasta cerrarlo en `finalizado`.

## Señas y Caja Diaria (C-11)

- **Migración `010_caja_senas`**: crea las tablas `sena`, `cierre_caja` y `movimiento_caja` con constraints (`monto > 0`, grafo de estados, cierre completo), índices por tenant y permisos `GRANT/REVOKE` para `turnos_app`.
- **Señas atadas al turno (`RN-PA-01/02/04`)**:
  - Reservar un turno de una prestación con `requiere_sena = True` genera automáticamente la seña `pendiente` por `monto_sena` con vencimiento a 24 h; un turno con seña impaga no pasa a `confirmado` (`409`).
  - `POST /api/senas/{id}/cobrar` pasa la seña a `cobrada`, acredita `turno.sena_cobrada` y registra el ingreso en el cierre abierto. Es idempotente: reintentar el cobro no duplica el movimiento.
  - `POST /api/senas/{id}/cancelacion` aplica la política de cancelación: en término (≥ `cancelacion_hs`) → `devuelta`; fuera de término o `ausente` → retenida en `aplicada`.
  - `POST /api/senas/{id}/vencer` vence la seña impaga, cancela el turno, libera el slot y ofrece el hueco a la lista de espera (**Flujo 1 paso 6**).
- **Liquidación del turno (`Flujo 4`, `R8`)**:
  - `GET /api/caja/turnos/{id}/liquidacion?obra_social=OSDE` calcula en servidor `saldo = precio_particular − cobertura_os − sena_cobrada` (con piso en cero), reutilizando el convenio vigente de `cobertura_os`.
  - `POST /api/caja/turnos/{id}/cobrar` registra el `MovimientoCaja` por el saldo y pasa la seña `cobrada` a `aplicada`; un segundo cobro del mismo turno responde `409` (nunca duplica la plata).
- **Caja diaria (`RN-PA-05`, `US-030`)**:
  - `POST /api/caja/cierre` abre el cierre del día (uno por fecha y consultorio) y `POST /api/caja/movimientos` asocia cada ingreso/egreso al cierre abierto vigente (`GET /api/caja/movimientos` lista lo conciliado).
  - `POST /api/caja/cierre/{id}/cerrar` fija `total_sistema = ingresos − egresos` y `diferencia = total_contado − total_sistema`; el cierre cerrado es **inmutable** (`409` al re-cerrarlo o al intentar imputarle movimientos nuevos).
  - `POST /api/caja/cierre/{id}/reabrir` está reservado al rol `DUENO` (`Accion.REABRIR_CIERRE`): recepción recibe `403`; el dueño reabre con motivo obligatorio y deja `antes`/`despues` en `Auditoria` (`RN-SE-01`).

## Mercado Pago (C-12)

- **Migración `011_mercadopago_webhooks`**: crea `cobro_mp` con `mp_payment_id` único, `payload` crudo (`JSONB`/`JSON`), `monto > 0`, estados `estado_mp` y `estado_conciliacion` acotados por `CHECK`, índices por pago y por `(tenant_id, estado_conciliacion)` y permisos `GRANT/REVOKE` para `turnos_app`.
- **Preferencia de pago (`RN-PA-02`)**:
  - `crear_preferencia_para_sena` genera el checkout con `external_reference = sena.id` y `expiration_date_to = sena.vence_at`; sólo se permite sobre señas `pendiente` con vencimiento.
  - Las credenciales salen de `Settings.mp_access_token`; el cliente acepta un `http_client` httpx inyectable y, sin transporte, opera en modo simulado para tests y sandbox offline.
- **Webhook firmado e idempotente (`RN-PA-03`, `RN-SE-04`)**:
  - `POST /webhooks/mercadopago` (también `/api/webhooks/mercadopago`) valida `x-signature` HMAC-SHA256 sobre `data.id`, `x-request-id` y `ts` con ventana de 10 minutos antes de tocar la base; firma inválida responde `401` y no persiste nada.
  - El payload crudo se guarda en `cobro_mp.payload` antes de evaluar la máquina de estados. `mp_payment_id` es único: un reintento idéntico responde `200` sin duplicar movimientos y la carrera de dos requests simultáneos se resuelve por constraint + relectura.
  - El `tenant_id` se deriva de la seña resuelta por `external_reference` (nunca del body, `R4`); si la referencia no resuelve, responde `200` ignorado sin persistir.
- **Mapeo de estados y caja (`RN-PA-05`, `R7`, `R8`)**:
  - `approved` consistente → seña `cobrada`, `turno.sena_cobrada = True` e ingreso `medio=mp` enlazado por `cobro_mp_id`; `pending` queda pendiente de conciliación; `rejected`/`cancelled` no acreditan dinero.
  - `refunded` → seña `devuelta`, `sena_cobrada = False` y egreso compensatorio (el ingreso original nunca se borra). La transición `approved → refunded` se aplica una sola vez.
  - Pagos sobre seña `vencida`, turno `cancelado`/`ausente`, monto distinto o seña ya cobrada por otro medio quedan en `discrepancia` para revisión manual, sin auto-confirmar ni cerrar caja.
- **Conciliación y consulta (`RN-PA-05`)**:
  - `conciliar_cobros` recorre los cobros `pendiente`, consulta MP y aplica el mismo mapeo (con scope opcional por tenant) para el job periódico.
  - `GET /api/pagos/mercadopago/cobros` y `GET /api/pagos/mercadopago/discrepancias` filtran por `sena_id`, `turno_id`, `estado_mp`, `estado_conciliacion`, `limite` y `offset`; el motivo de cada discrepancia se deriva del estado actual de seña/turno/monto.
  - Ambos endpoints usan `Recurso.CAJA` + `Accion.ACTUALIZAR`: Dueño y Recepción operan la conciliación (`200`), el Odontólogo recibe `403`.

## Obras Sociales y Liquidación (C-13)

- **Migraciones `012_obras_sociales_liquidacion` y `013_liquidacion_claim_unico`** (encadenadas sobre la migración de `C-12`): la `012` crea `liquidacion_os` y `liquidacion_detalle` con `CHECK` de estado/período/montos, FK con `RESTRICT` hacia cabecera/turno, índices únicos parciales (`uq_liquidacion_os_borrador`, `uq_liquidacion_detalle_turno_abierto`) y permisos `GRANT/REVOKE` para `turnos_app`; la correctiva `013` **no modifica** la `012` (ya aplicada en bases existentes) y agrega `liquidacion_detalle.reclamado` y `liquidacion_os.turnos_sin_cobertura`, y reemplaza esos índices por versiones con `lower(obra_social)`: `uq_liquidacion_os_borrador` (`tenant_id`, `lower(obra_social)`, `periodo`) donde `estado = 'borrador'` y `uq_liquidacion_detalle_turno_reclamado` (`tenant_id`, `turno_id`, `lower(obra_social)`, `periodo`) donde `reclamado`.
- **Cobertura compartida (`RN-OS-01`, `R8`)**:
  - `domain/cobertura_os.py` implementa la resolución pura (`vigente` → último arancel cargado → particular) y `application/cobertura.py` los loaders async; presupuestos (`C-10`) y caja (`C-11`) delegan ahí sin cambiar su contrato.
  - Sin convenio vigente se factura como particular (`cobertura = 0`); un arancel vencido **avisa** y usa el arancel más reciente en lugar de facturar como particular.
  - `GET /api/os/cobertura` resuelve por `prestacion_id` o por `turno_id` (deriva prestación y fecha del turno) con `obra_social` y `fecha` de referencia opcionales; devuelve `precio_particular`, `cobertura`, `monto_a_cargo`, `estado_arancel` (`vigente|vencido|sin_cobertura`), vigencias, `arancel_vencido` y `advertencia`. Los montos viajan como `Decimal` serializado a string.
- **Liquidación mensual por OS y período (`RN-OS-02`, `US-041`)**:
  - `POST /api/liquidaciones` arma el `borrador` con los turnos `finalizado` cuyo inicio cae en el período `yyyymm` y que tienen convenio con la OS; informa `turnos_sin_cobertura` (persistido en la cabecera) y `advertencias` (incluida la liquidación complementaria si el período ya tiene una `pagada`).
  - Estados: `borrador → presentada → pagada | con_debitos`; `con_debitos → pagada`; `borrador → anulada`. `pagada` y `anulada` son terminales.
  - **Reclamo único por obra social y período** (`RN-OS-02`): un turno se reclama **una sola vez** por OS/período mientras su liquidación no esté `anulada`; una complementaria **no vuelve a reclamar lo ya pagado** (sólo entran en ella los turnos nunca reclamados) y los turnos excluidos se informan en `advertencias`. Si no queda ningún turno nuevo, el alta responde `422`.
  - Un solo `borrador` por OS/período: `409` en la aplicación + índice único parcial `uq_liquidacion_os_borrador` en la base; una **carrera** de dos altas simultáneas también responde `409` (nunca `500`).
  - Los débitos se registran por turno con `monto_reconocido` y `debito_motivo` obligatorio en cada recorte; `total` y `total_reconocido` se recalculan siempre en el servidor, sobre el detalle persistido.
  - **`con_debitos → pagada`**: la obra social puede terminar pagando sólo el saldo reconocido; la transición **conserva** el saldo reconocido y el motivo del débito del detalle, y el pendiente se expone como `saldo_debito` (`total - total_reconocido`, campo derivado, no una columna).
- **Endpoints (`Recurso.LIQUIDACIONES`)**:

| Método | Ruta | Qué hace | Dueño | Recepción | Odontólogo |
|---|---|---|---|---|---|
| `GET` | `/api/os/cobertura` | Lookup de cobertura y monto a cargo | sí | sí | sí |
| `POST` | `/api/liquidaciones` | Genera el borrador del período (`201`; `409` si ya hay borrador o por carrera, `422` si no hay turnos nuevos) | sí | sí | `403` |
| `GET` | `/api/liquidaciones` | Lista filtrable por `obra_social`, `periodo`, `estado` | sí | sí | sí |
| `GET` | `/api/liquidaciones/{id}` | Detalle con una fila por turno | sí | sí | sí |
| `PATCH` | `/api/liquidaciones/{id}` | Registra débitos del borrador (`409` si no es `borrador`) | sí | sí | `403` |
| `POST` | `/api/liquidaciones/{id}/cerrar` | Presenta el borrador (`422` si está vacío) | sí | sí | `403` |
| `POST` | `/api/liquidaciones/{id}/resultado` | Registra `pagada` o `con_debitos` según lo que reconoció la OS | sí | sí | `403` |
| `DELETE` | `/api/liquidaciones/{id}` | Anula por baja lógica con `{motivo}` (`R7`) | sí | sí | `403` |
| `GET` | `/api/liquidaciones/{id}/exportar` | Descarga la liquidación (`?formato=csv\|json`) | sí | sí | `403` |

- **Exportación generada en servidor (`RN-OS-03`, `R9`)**:
  - `GET /api/liquidaciones/{id}/exportar?formato=csv|json` (por defecto `csv`) responde con `Content-Disposition: attachment; filename="liquidacion-<os>-<periodo>.<ext>"`.
  - CSV: UTF-8 con BOM, separador `,`, decimal `.`, quoting y CRLF de RFC 4180. JSON: cabecera (`obra_social`, `periodo`, `estado`, `total`, `total_reconocido`, `saldo_debito`) + lista de `detalles`. El `saldo_debito` derivado (`total - total_reconocido`) acompaña a la exportación en ambos formatos.
  - Una fila por turno con `periodo`, `obra_social`, `estado`, `estado_arancel`, `turno_id`, `fecha_turno`, `prestacion`, `monto_reclamado`, `monto_reconocido` y `debito_motivo`; nunca incluye DNI, teléfono ni otros datos del paciente. Un formato distinto de `csv|json` responde `422` y no genera archivo.
  - v1 no incluye presentación electrónica ni envío del archivo a la obra social.

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
- [x] C-05 `pacientes` (`openspec/changes/archive/2026-11-01-c-05-pacientes/`).
- [x] C-06 `agenda-turnos` (`openspec/changes/archive/2026-11-01-c-06-agenda-turnos/`).
- [x] C-07 `lista-espera` (`openspec/changes/archive/2026-11-01-c-07-lista-espera/`).
- [x] C-08 `comunicaciones-mensajeria` (`openspec/changes/archive/2026-11-01-c-08-comunicaciones-mensajeria/`).
- [x] C-09 `historia-clinica-odontograma` (`openspec/changes/archive/2026-11-01-c-09-historia-clinica-odontograma/`).
- [x] C-10 `presupuestos-planes` (`openspec/changes/archive/2026-11-01-c-10-presupuestos-planes/`).
- [x] C-11 `caja-senas` (implementado en `openspec/changes/c-11-caja-senas/`): modelos + migración `010`, casos de uso de señas/caja, endpoints `/api/senas*` y `/api/caja/*`.
- [x] C-12 `mercadopago-webhooks` (implementado en `openspec/changes/c-12-mercadopago-webhooks/`): modelo `CobroMP` + migración `011`, preferencias MP, webhook firmado e idempotente, conciliación y endpoints `/api/pagos/mercadopago/*`.
- [x] C-13 `obras-sociales-liquidacion` (implementado en `openspec/changes/c-13-obras-sociales-liquidacion/`): cobertura compartida + migraciones `012` y `013`, liquidación por OS/período con débitos y estados `borrador`/`presentada`/`pagada`/`con_debitos`/`anulada`, reclamo único por obra social y período, endpoints `/api/os/cobertura` y `/api/liquidaciones*` con exportación CSV/JSON.
- [x] C-15 `reserva-publica-pwa` (`openspec/changes/archive/2026-11-12-c-15-reserva-publica-pwa/`): PWA pública de reserva online y autogestión de turnos por token opaco (React + TypeScript + Vite PWA): catálogo y slots en `/reservar/:slug`, formulario sin login con validación DNI/teléfono, seña guiada a Mercado Pago con montos del servidor, `/mis-turnos/:token`, firma de consentimiento en `/firmar/:token` y shell offline con service worker.
- [ ] Próximos (Fase 5 / Fase 6): C-14 `auditoria-exportacion`.

Roadmap completo en `CHANGES.md`; dominio en `knowledge-base/`;
competencia en `discovery/discovery.md`.
