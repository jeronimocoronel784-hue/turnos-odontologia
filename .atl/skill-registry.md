# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

Project: turnos-odontologia — SaaS multi-tenant odontológico (FastAPI + SQLAlchemy + PostgreSQL + Redis + React + TS + Vite + Docker Compose). PWA pública 24/7 + agenda recepción + HC/odontograma + cobros/OS + WhatsApp.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| React components, Next.js pages, data fetching, bundle optimization, performance improvements | vercel-react-best-practices | C:\Users\jeron\.agents\skills\vercel-react-best-practices\SKILL.md |
| Building new UI or reshaping existing one; aesthetic direction, typography, non-templated visual identity | frontend-design | C:\Users\jeron\.agents\skills\frontend-design\SKILL.md |
| BEFORE writing/changing anything in Postgres: tables/columns, schema, migrations, RLS, indexes, triggers, functions, queues (pg_cron/pgmq), pgvector, slow queries, connection exhaustion, locking | supabase-postgres-best-practices | C:\Users\jeron\.agents\skills\supabase-postgres-best-practices\SKILL.md |
| Python FastAPI backend: async patterns, SQLAlchemy, Pydantic, auth, production API patterns, microservices | python-fastapi-development | C:\Users\jeron\.agents\skills\python-fastapi-development\SKILL.md |
| Implementing auth systems, securing APIs, OAuth2/social login, RBAC, session management, SSO, multi-tenancy | auth-implementation-patterns | C:\Users\jeron\.agents\skills\auth-implementation-patterns\SKILL.md |
| Redis cache, KV/session store, serverless Redis, rate-limit, queues, locks, leaderboards, streams, search | upstash-redis-js | C:\Users\jeron\.agents\skills\upstash-redis-js\SKILL.md |
| Build features or fix bugs test-first; red-green-refactor; integration tests | tdd | C:\Users\jeron\.agents\skills\tdd\SKILL.md |
| Review a branch, PR, or work-in-progress changes ("review since X") | code-review | C:\Users\jeron\.agents\skills\code-review\SKILL.md |
| Integrating payments, subscriptions, secure checkout, refunds, payment webhooks (Stripe pattern → plantilla para Mercado Pago C-07) | stripe-integration | C:\Users\jeron\.agents\skills\stripe-integration\SKILL.md |
| Webhook verification + event-driven sync DB/notifications (Clerk verifyWebhook pattern → plantilla para webhooks MP C-07) | clerk-webhooks | C:\Users\jeron\.agents\skills\clerk-webhooks\SKILL.md |
| WhatsApp production issues, message failures, workflow behavior, webhook delivery (Kapso CLI + Logs search) | observe-whatsapp | C:\Users\jeron\.agents\skills\observe-whatsapp\SKILL.md |
| EMR/EHR features: encounter workflows, prescriptions, clinical data entry UI (plantilla para HC + odontograma FDI C-05) | healthcare-emr-patterns | C:\Users\jeron\.agents\skills\healthcare-emr-patterns\SKILL.md |
| PHI handling, covered entities, BAAs, minimum-necessary, auditabilidad (base para Ley 25.326 + HCE AR) | hipaa-compliance | C:\Users\jeron\.agents\skills\hipaa-compliance\SKILL.md |
| Optimized multi-stage Dockerfiles, any language/framework (foundation C-01) | multi-stage-dockerfile | C:\Users\jeron\.agents\skills\multi-stage-dockerfile\SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### vercel-react-best-practices (PWA paciente + agenda — C-08/C-09 aprox.)
- Elimina waterfalls: `Promise.all()` para fetches independientes; inicia promesas temprano, haz `await` tarde; usa Suspense boundaries para streaming
- Nunca importes de barrel files — importa directo del módulo; `next/dynamic` para componentes pesados; carga analytics/logging después de hidratación
- Server: `React.cache()` para dedup por request; LRU para cross-request; minimiza datos serializados a Client Components; nunca estado mutable a nivel módulo en RSC/SSR
- No `useMemo`/`useCallback` especulativos; deriva estado durante el render, no en effects; dependencias primitivas en effects; `startTransition`/`useDeferredValue` para updates no urgentes
- Nunca definas componentes dentro de componentes; ternario en vez de `&&` para render condicional; preload en hover/focus para velocidad percibida
- Gotcha: props duplicadas serializadas en RSC y listeners globales duplicados son las regresiones más comunes — verifica ambos en review

### frontend-design (PWA móvil-first paciente + pantallas agenda/HC)
- Diseña desde la materia del brief (odontología: clínica, calma, confianza) — nunca defaults genéricos (fondo crema + serif + terracota, dark + verde ácido, SaaS-card-kit con todo redondeado y misma sombra)
- Tipografía con intención: 1-2 familias deliberadas, escala clara, líneas <80 caracteres; nunca ALL-CAPS para labels ni acentuar una sola palabra del titular
- Estructura visual = información: sin numeración 01/02/03 salvo secuencia real; sin dividers/labels decorativos
- Motion: un solo momento orquestado (no fade-slide en cada sección); el motion responde a acciones del usuario; respeta `prefers-reduced-motion`
- Copy desde el usuario ("Gestionar notificaciones", no "webhook config"); CTA dice qué pasa ("Guardar cambios"); errores explican qué pasó + cómo arreglarlo, sin disculpas vagas; pantallas vacías invitan a actuar
- Plan en dos pasadas (tokens color/tipo/layout + principios → revisar contra el brief → recién codear); audacia concentrada en un elemento memorable

### supabase-postgres-best-practices (core-models multi-tenant C-02, anti-solapamiento)
- Carga esta skill ANTES de cualquier cambio de schema, migración, RLS, índice o query lenta — incluso un cambio de una columna
- Multi-tenant: aísla por tenant con RLS policies + tests que verifiquen visibilidad (filas visibles para el tenant equivocado = bug CRITICAL)
- Anti-solapamiento agenda: prefiere constraints de exclusión/rangos en DB sobre validación solo en app (la app valida UX, la DB garantiza)
- Indexa lo que filtras/ordenas/joineas; parciales donde el filtro es selectivo; verifica con EXPLAIN antes de asumir
- Nunca N+1: batch/dataloader o joins agregados; pagina con keyset (no OFFSET profundo en listados grandes)
- Conexiones: pool obligatorio (PgBouncer/Supavisor); nunca conexión nueva por request en serverless/edge
- Migraciones: declarativas/reversibles, sin downtime (expand-then-contract); `pg_restore`/imports con verificación post-carga

### python-fastapi-development (backend foundation C-01, core-models C-02)
- Stack: Python 3.11+, FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic + pytest; gestión con uv; lint ruff + format black + mypy
- Estructura: routers por dominio, schemas Pydantic separados de modelos SQLAlchemy (request/response explícitos, nunca exponer el ORM crudo)
- Async end-to-end (endpoints + session); session por request con cierre garantizado; nunca bloquear el loop con I/O sync
- Errores: excepciones custom + handlers globales con formato uniforme; loguea con request-id; nunca stack traces al cliente
- Auth: delega a `auth-implementation-patterns` (JWT + RBAC); hashing argon2/bcrypt; validación Pydantic en borde
- Quality gates por change: tests >80%, mypy + ruff limpios, OpenAPI completo, sin secretos en imagen/config
- Gotcha: esta skill invoca sub-skills `@...` que NO existen localmente — ignora los "Copy-Paste Prompts" con `@`, aplica solo los patrones

### auth-implementation-patterns (JWT + RBAC recepcion/odontologo/admin — C-03)
- Separa AuthN (quién eres) de AuthZ (qué puedes hacer); RBAC por rol + verificación de ownership del recurso/tenant en servidor
- Access tokens cortos (15-30 min) + refresh rotado; nunca JWT en localStorage (XSS) — httpOnly + secure + sameSite
- Passwords solo con argon2/bcrypt; login con rate limit anti-brute-force; reseteo con tokens seguros y expiración
- Toda verificación auth en servidor — nunca solo checks de cliente; HTTPS siempre; rota secretos regularmente
- Loguea eventos de seguridad (intentos, fallos) sin PHI ni credenciales; ofrece MFA donde sea viable
- OAuth2/OIDC para login social/SSO; sesiones stateful solo si hay razón (escala peor que JWT stateless)
- Multi-tenant: el tenant del token manda — nunca confíes en `tenant_id` del body/query sin contrastar con el token

### upstash-redis-js (cola WA/email, recordatorios, lista de espera)
- Cliente serverless HTTP (`Redis.fromEnv()` con `UPSTASH_REDIS_REST_URL/TOKEN`); sin pooling — apto para serverless/edge donde TCP no va
- Caché: cache-aside por defecto, write-through solo si la frescura lo exige; toda entrada con TTL explícito y estrategia de invalidación
- Sesiones/estado usuario en hashes con expiración; rate-limit con `@upstash/ratelimit`, no casero
- Colas recordatorios WA: lists/streams + consumer groups (entrega at-least-once → consumidores idempotentes); locks distribuidos con expiración anti-deadlock
- Batch con pipeline/auto-pipeline para N operaciones; MULTI/EXEC solo para atomicidad real; Lua (EVAL) para lógica servidor que evita round-trips
- Datos: sorted sets para rankings/lista de espera ordenada; JSON + JSONPath para documentos; vector index solo para búsqueda semántica real
- Proyecto usa Redis propio en Compose, no Upstash cloud — aplica los patrones, adapta el cliente/env a la infra del repo

### tdd (transversal C-01..C-17, Strict TDD activo)
- Rojo antes que verde: test que falla primero, luego mínimo código para pasar; nada de features especulativas
- Tests contra interfaces públicas/seams acordados — nunca internos, métodos privados ni mocks de colaboradores internos
- Un slice vertical por ciclo (un seam, un test, una implementación mínima); nunca "todos los tests primero, todo el código después"
- Valores esperados de fuente independiente (literal conocido, ejemplo trabajado, spec) — nunca recomputados como el código (tautología)
- Nombres como especificación ("paciente puede reservar turno válido") alineados al glosario del dominio (KB); respeta ADRs del área
- Refactor NO es parte del loop rojo-verde — va en etapa de review (ver `code-review`)
- Mínimo 2 casos por comportamiento (happy path + un edge); lee `tests.md`/`mocking.md` de la skill ante duda

### code-review (calidad HIGH/CRITICAL: auth, caja, HC, auditoría)
- Dos ejes separados, nunca mezclados: Standards (¿sigue los estándares del repo?) vs Spec (¿implementa lo pedido?)
- Fija el punto base primero: `git diff <fixed-point>...HEAD` (tres puntos, contra merge-base) + `git log <fixed-point>..HEAD --oneline`; diff vacío o ref inválida = falla acá
- Spec: busca origen en este orden — refs en commits (#123) → path pasado por usuario → `docs/`/`specs/`/`.scratch/` por nombre de rama → si no hay, eje Spec reporta "no spec available"
- Standards: el estándar documentado del repo siempre gana sobre el baseline de smells Fowler; cada smell es juicio ("posible Feature Envy"), nunca violación dura; omite lo que el tooling ya exige
- Reporte <400 palabras por eje con citas (archivo+línea, línea de spec); cierra con totales por eje + peor issue de cada eje, sin re-rankear entre ejes

### stripe-integration (PLANTILLA para Mercado Pago C-07 — no existe skill nativa MP)
- Prefiere Checkout/hosted (menor carga PCI y mantenimiento) sobre Payment Intents custom; Setup Intents para guardar medios futuros
- Webhooks: escucha `payment.succeeded/failed`, `subscription.updated/deleted`, `charge.refunded`, `invoice.payment_succeeded`; verifica firma SIEMPRE, responde 200 rápido, procesa async
- Idempotencia en creación de cobros y en handlers (clave de idempotencia + dedup por event-id) — reintentos del proveedor llegan duplicados
- Nunca montos calculados en cliente: el servidor calcula total (impuestos, descuentos, seña); concilia estado local contra eventos, no contra redirects
- Test mode + tarjetas de prueba (4242… éxito, …0002 rechazo, 3DS, fondos insuficientes); cada flujo con test automatizado
- Adapta a MP: Checkout Pro + notificaciones IPN/Webhook con validación, conciliación de señas contra reserva, estados pendientes/expirados

### clerk-webhooks (PATRÓN para verificación/conciliación webhooks MP C-07)
- Verifica firma en CADA handler con `verifyWebhook(req)` + secreto (`*_WEBHOOK_SIGNING_SECRET`) — nunca omitir, ni en handlers solo-notificación; falla = 400
- Ruta webhook PÚBLICA: excluida del middleware auth (si no, 401); responde 200 de inmediato tras verificar, trabajo pesado async
- Webhooks son async/eventual-consistent: nunca como parte de flujo sync (onboarding lee del token/API directo, no de tu DB)
- Sync a DB por tipo de evento (created/updated/deleted + memberships); handlers idempotentes (reintentos Svix/Meta duplican)
- Notificaciones (email/Slack) también verifican firma primero; mismo patrón vale para IPN MP: verificar → 200 → conciliar → notificar
- Gotcha: ejemplos Clerk/Next.js —移植 el patrón (verificar→ack→idempotente→conciliar), no el SDK

### observe-whatsapp (confirmación automática WA con opt-in y log)
- Diagnóstico = Logs search primero: `kapso logs search --query "<id>" --period 24h --source all --limit 20 --output json`; si vacío, reintenta `--period 7d` antes de concluir
- Fuentes: `external_api_log`, `whatsapp_webhook_event`, `flow_event`, `webhook_delivery`; `--problems-only` para barridos, sin él para timelines exactas
- Delivery: busca por WAMID/teléfono → resuelve número (`numbers resolve`) → lista mensajes → inspecciona mensaje + conversación; prefiere `phone_number_id` canónico
- Errores: `kapso status` → health del número → logs con `--problems-only` → plantillas si aplica; correlaciona mensaje↔workflow↔API↔webhook-delivery
- Setup webhooks/flujos: eso es `integrate-whatsapp`/`automate-whatsapp` (NO instaladas) — esta skill solo observa/debuguea
- Proyecto: requiere `kapso login` o env (`KAPSO_API_BASE_URL` sin `/platform/v1` + `KAPSO_API_KEY`); si Kapso no aplica, usa el método (WAMID-first, timelines, health) sobre Meta Cloud API

### healthcare-emr-patterns (PLANTILLA para ficha clínica + odontograma FDI C-05)
- Seguridad paciente primero: interacciones/focos/valores críticos ALERTAN (no-dismissable, nunca toast) y bloquean hasta override documentado en auditoría
- Encounter en single-page vertical (header sticky + flujo 1 Queja → … → 9 Firma/Bloqueo); nunca tabs que fragmenten el workflow clínico
- Firma = lock: sin ediciones post-firma, solo addendum vinculado; ambos en timeline; auditoría quién/cuándo/qué
- Templates con chips clicables + campos requeridos + red flags (alerta visible) + sugerencias ICD; vitals/labs con rangos (verde/amarillo/rojo) + tendencias + scoring (NEWS2/qSOFA)
- Accesibilidad clínica: contraste 4.5:1, targets 44×44, teclado completo, nunca solo-color (texto+icono), labels para lector, sin auto-dismiss en alertas
- Anti-patrones: datos clínicos en localStorage, `any` en estructuras clínicas, edición de encounters firmados, datos sin audit trail
- Adapta a odonto: FDI de 2 dígitos por pieza, superficies/estados por pieza, presupuesto vinculado a plan, evolución por cita

### hipaa-compliance (BASE para auditoría/trazabilidad — adaptar a Ley 25.326 + HCE AR)
- Overlay, no implementación: lo concreto va en `healthcare-phi-compliance`/`healthcare-reviewer`/`security-review` (NO instaladas) — aplica sus gates aquí
- Gates por tarea: ¿es PHI? → ¿actor cubierto/asociado? → ¿el vendor/LLM tiene BAA? → ¿mínimo necesario? → ¿lectura/escritura/export auditable?
- Nunca PHI en logs, analytics, crash reports, prompts LLM, URLs, browser storage, errores visibles al cliente ni payloads de ejemplo
- Terceros (SaaS, observabilidad, soporte, LLM) bloqueados por defecto hasta BAA + límites de datos claros; prefiere IDs internos opacos sobre DNI/teléfono/dirección
- Acceso mínimo necesario + authN/authZ + audit trail en todo read/write/export de PHI; AR: mapear a Ley 25.326, consentimiento, HCE y secreto profesional
- Duda regulatoria en HIGH/CRITICAL → escalar a revisión humana antes de codear (gobernanza CRITICAL/HIGH)

### multi-stage-dockerfile (foundation C-01 con Docker Compose)
- Builder (deps/compilación/test) separado de runtime (solo lo necesario); copia solo artefactos; stages con nombre (`AS builder`)
- Base oficial mínima con tag exacto (`python:3.11-slim`, no `latest`); Alpine si compatible; distroless en runtime donde aplique
- Capas: lo estable primero (deps), lo cambiante último (código); combina `RUN` con `&&`; `.dockerignore` siempre; `COPY --chown` en un paso
- Seguridad: nunca root (`USER` no-root); sin build-tools/secretos en imagen final; permisos restrictivos; escanea vulnerabilidades
- Prod: `NODE_ENV=production`, `HEALTHCHECK` por tipo de app, build-args para config entre entornos, aprovecha caché ordenando de menos a más cambiante

## Change → Skills (delegación rápida)

| Change | Skills a inyectar |
|--------|-------------------|
| C-01 foundation/infra | multi-stage-dockerfile, python-fastapi-development, tdd, code-review |
| C-02 core-models multi-tenant | supabase-postgres-best-practices, python-fastapi-development, tdd |
| C-03 auth JWT + RBAC | auth-implementation-patterns, python-fastapi-development, supabase-postgres-best-practices (RLS), tdd, code-review |
| C-05 HC + odontograma | healthcare-emr-patterns, hipaa-compliance, frontend-design, supabase-postgres-best-practices, tdd |
| C-07 pagos Mercado Pago | stripe-integration (plantilla), clerk-webhooks (patrón webhook), python-fastapi-development, upstash-redis-js (colas), tdd, code-review |
| Agenda/turnos + anti-solapamiento | supabase-postgres-best-practices (exclusión), upstash-redis-js (lista espera), tdd |
| WhatsApp confirmación/recordatorios | observe-whatsapp, upstash-redis-js (colas/retry), hipaa-compliance (opt-in/log), tdd |
| PWA paciente / pantallas recep. | vercel-react-best-practices, frontend-design, tdd |
| Auditoría/trazabilidad | hipaa-compliance, supabase-postgres-best-practices (audit trail), code-review |
| Cualquier branch/PR | code-review (dos ejes), tdd (rojo-verde fuera del loop de refactor) |

## Project Conventions

| File | Path | Notes |
|------|------|-------|
| (vacío — primer pass) | — | CLAUDE.md/AGENTS.md aún no existen; agent-instruction los generará. Re-correr skill-registry después. |

Sin archivos de convención en raíz al momento del build (solo CHANGES.md, knowledge-base/, openspec/, discovery/). Estándares vivos: Strict TDD + gobernanza por dominio (CRITICAL: auth/salud/pagos/auditoría → análisis primero; HIGH: config/datos → proponer y esperar; MEDIUM: lógica negocio con checkpoints; LOW: CRUDs autonomía con tests verdes).
