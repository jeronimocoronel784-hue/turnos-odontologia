# Auditoría integral — Turnos Odontología

**Fecha de corte:** 2026-11-17
**Commit auditado:** `e81f8ae` (`feat(c-14): cierra auditoria-exportacion y completa el roadmap`). `main` = `origin/main` en el mismo SHA (verificado con `git ls-remote origin main` → `e81f8ae316049246de704b9f27cd9796372f1ca0`). Al iniciar la auditoría el árbol estaba limpio (`git status -sb` → solo `## main...origin/main`); al cierre quedan dos archivos modificados sin commitear: este documento y `docs/guion-video-TPI.pdf`, que se actualiza en paralelo (§10).
**Alcance:** estado real del repositorio, cronología, fases SDD/OPSX, los 19 changes del roadmap (20 archives), calidad medida, riesgos y brechas documentales.
**Método:** lectura de código y artefactos + ejecución de gates + contraste con git, OpenSpec y los `tasks.md` de cada archive. Todo hallazgo tiene evidencia (`archivo:línea` o comando → resultado). Lo que no se pudo verificar se marca explícitamente.

---

## 0. Veredicto en 10 líneas

1. El **roadmap está completo**: 19 changes planificados (C-01..C-19) ejecutados y archivados, **20 carpetas** en `openspec/changes/archive/` (C-01 tiene dos: el ciclo original y el split de layout) y **0 changes activos** (`openspec list` → "No active changes found.").
2. **20 specs main válidas**: `openspec validate --all --strict` → **20 passed, 0 failed (20 items)**, una por capability en `openspec/specs/`.
3. Se entregó el **MVP** (agenda + pacientes + HC/odontograma + caja/señas + Mercado Pago + reserva pública PWA) **más** las pantallas internas (C-16/C-17), la demo con Compose (C-18) y auditoría/exportación (C-14). No es un esqueleto: hay **29 tablas**, **13 migraciones** y **110 rutas** en los routers.
4. **C-02 ya no es una deuda**: se archivó el 2026-10-29 con **11/11 tareas** y 24 tests contra PostgreSQL real (`CHANGES.md:135`). La frase "C-02 0/11" de la auditoría anterior quedó vencida.
5. La **calidad medida al corte** es: backend **687 passed / 2 failed / 8 skipped** (los 2 failed son ambientales y preexistentes), frontend **18 archivos / 90 tests** en verde, `ruff`, `ruff format --check` y `mypy` limpios, `npm run build` OK y `openspec validate` 20/20.
6. Los **2 fallos de pytest no son regresiones**: `test_settings` falla porque hay un `.env` local con `JWT_SECRET` y `test_comunicaciones_api` hace una llamada HTTP real a WhatsApp con credenciales dummy (401). Se reportan como fallos de entorno; no se tocaron.
7. La **deuda de verificación está acotada a Docker**: 3 tareas de C-14 (3.3, 10.1, 10.3) y 2 de C-01 solo-setup (3.3, 5.1). El CLI de Docker existe (`29.9.2`) pero el **daemon no responde**, así que las verificaciones siguen bloqueadas.
8. **Riesgo real que sigue abierto (heredado de la auditoría anterior):** la auditoría append-only todavía se puede borrar en cascada desde `tenant` (`001_...py:72` FK `ON DELETE CASCADE` + `:91` `GRANT DELETE ON tenant`). C-02 no tocó permisos y ningún test cubre la cascada.
9. **Otras deudas vigentes, todas documentadas en los artefactos**: exportaciones en disco local del nodo, índices de auditoría diferidos, lecturas de HC sin auditar, retención legal exacta pendiente (PO-03) y desvío consciente de RBAC en C-14 (solo Dueño exporta, consulta al PO abierta).
10. **La documentación de estado ya está mayormente alineada** (README §Estado, `CHANGES.md`, AGENTS con R1–R13, guion del video con "veinte changes"/687/90), pero quedan tres cosas a mantener a mano: `docs/defensa-oral-guia.md` sigue anclada al 2026-10-20, `CHANGES.md` conserva dos notas del 2026-11-16 que dicen que C-14 sigue pendiente, y el guion es un PDF sin fuente `.md` versionada.

---

## 1. El proyecto en una página

### 1.1 Qué es

SaaS multi-tenant para gestión de consultorios odontológicos en Argentina/Uruguay. Cubre agenda, pacientes, historia clínica y odontograma FDI, presupuestos, caja y señas, obras sociales, cobros por Mercado Pago y comunicación por WhatsApp, con una PWA pública para que el paciente reserve 24/7.

**Alcance v1 (entregado):** agenda + pacientes + HC/odontograma + caja/señas + Mercado Pago + reserva pública + mensajería + obras sociales + auditoría/exportación.
**Fuera de alcance v1:** app nativa, AFIP nativa, facturación fiscal, push notifications, múltiples sucursales avanzadas, IA clínica.

### 1.2 Actores y RBAC

| Rol | Alcance |
|---|---|
| Dueño | Administración total del consultorio, configuración, usuarios, reportes, auditoría y exportación |
| Recepción | Agenda, pacientes, caja; **no** edita historia clínica |
| Odontólogo | Agenda propia, HC, odontograma, presupuestos |
| Paciente | Reserva pública, sus turnos, firma de consentimiento; sin acceso al back-office |

La matriz vive en `knowledge-base/03_actores_y_roles.md` y **ya está enforceada en la API** desde C-03: `requiere(recurso, accion)` sobre 14 recursos × 3 roles (`src/backend/app/domain/rbac.py`), con `ActorAutenticado.tenant_id` tomado **solo** del token (`src/backend/app/api/security.py:26,57`). La UI espeja la matriz en `src/frontend/src/shared/rbac.ts`.

**Desvío consciente de C-14:** el trail, los cuatro datasets y el paquete del paciente quedan **solo Dueño**, mientras la KB da exportación parcial a Recepción y Odontólogo (`knowledge-base/03_actores_y_roles.md:31-32`). Está justificado en `openspec/changes/archive/2026-11-17-c-14-auditoria-exportacion/design.md:41-55` y queda como consulta al PO (`proposal.md:38`).

### 1.3 Modelo de datos

18 entidades documentadas en `knowledge-base/04_modelo_de_datos.md` (20 subsecciones: "Profesional" no es tabla propia y "Sobreturno" es un flag de `Turno`). A nivel de esquema, las **13 migraciones** (`001`..`013`) crean **29 tablas** (`op.create_table(` en `src/backend/alembic/versions/`: 3+2+3+2+2+1+2+5+3+3+1+2). Todas las tablas de negocio llevan `tenant_id`; `tenant` es la raíz.

Modelos de dominio en `src/backend/app/domain/`: `tenant`, `usuario`, `auditoria`, `refresh_token`, `token_gestion`, `sillon`, `prestacion`, `cobertura_os`, `paciente`, `ficha_clinica`, `turno`, `bloqueo`, `lista_espera`, `plantilla`, `mensaje`, `clinica` (evolución/odontograma/pieza/adjunto/consentimiento), `presupuesto`, `caja`, `mercadopago`, `liquidacion_os`, más `rbac`, `mixins` y `textos_libres`.

### 1.4 Stack real (versiones verificadas en esta máquina)

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | Python / FastAPI | 3.13.6 local (`requires-python >=3.12`) / 0.162.0 |
| ORM | SQLAlchemy async | 2.1.8 |
| Validación | Pydantic / pydantic-settings | 2.14.2 / `>=2.2` |
| Migraciones | Alembic | 1.20.1 (13 revisiones) |
| DB | PostgreSQL | 15.10 (`postgres:15.10-bookworm`) |
| Cola/caché | Redis | 7.4.1 (`redis:7.4.1-bookworm`) |
| Frontend | React / TypeScript / Vite | 18.3.1 / 5.6.3 / 5.4.9 |
| Datos front | TanStack Query / React Router | 5.59.20 / 6.26.2 |
| Estilos | Tailwind CSS | 3.4.13 |
| PWA | vite-plugin-pwa | 0.20.5 |
| Tests front | Vitest + Testing Library | 2.x / 16.x |
| Infra | Docker Compose | `db`, `redis`, `api`, `frontend`, `worker`, `migrar`, `mailhog` (7 servicios) |
| CI | GitHub Actions | backend + frontend + `openspec validate --all --strict` |

### 1.5 Arquitectura real

```text
Navegador
   │  dev: proxy Vite / prod: nginx del servicio frontend (:8080) con /api → api:8000
   ▼
React SPA/PWA (17 archivos `*Page.tsx`: públicas + `/app` interno)
   │
   ▼
FastAPI (monolito modular, 16 módulos de router, 110 rutas)
   ├── api/            routers + schemas Pydantic + deps + security
   ├── domain/         modelos SQLAlchemy + rbac
   ├── application/    casos de uso por dominio (12 módulos)
   ├── infrastructure/ repository, UoW, security (JWT/passwords/rate limit), seed, mailer, wa_client
   ├── shared/         settings, logging, exceptions, database, montos, zonas, sanitizar_phi
   ├── workers/        worker de outbox + jobs de exportación (Redis)
   └── scripts/        usuario demo
   │
   ├──► PostgreSQL 15 (29 tablas)
   └──► Redis 7 (rate limiting + colas + jobs)
```

**Lectura honesta:** ya no es "solo el primer segmento vertical". La capa `application/` tiene 12 módulos, la API expone negocio real y el frontend cubre las pantallas internas. Lo que falta es **verificación de infraestructura** (3 tareas Docker) y las deudas transversales de §8, no features del roadmap.

Adicional fuera del roadmap: servidor MCP propio (`mcp_server.py`, transporte stdio, 2 tools de **solo lectura**: `consultar_prestaciones` y `buscar_paciente_por_dni`) documentado en `README.md:131`.

---

## 2. Cronología: qué se hizo en cada bloque

> Engram no guarda transcripciones literales; guarda observaciones con timestamp. La cronología se reconstruye con `git log --date=short` + artefactos + observaciones. Hay 20 fechas con commits entre 2026-10-02 y 2026-11-17.

### Bloque 1 — 2026-10-01/02: Discovery y fundación

**Objetivo:** entender el mercado y convertirlo en una base ejecutable por agentes.

**Qué se hizo**
- Relevamiento de **18 sistemas** de gestión odontológica y turnos (`discovery/discovery.md`, `sources_fetched_at: 2026-10-01`).
- `openspec init`, **Knowledge Base** de 11 documentos + README, **roadmap** de 17 changes (después ampliado), 14 skills + registry y `AGENTS.md`/`CLAUDE.md` con R1–R13.
- Push inicial `48bf10c` (31 archivos) + README `b71193f`.

**Evidencia:** `48bf10c`, `b71193f`, `knowledge-base/`, `docs/discovery/informe-discovery.md`.

**Deuda heredada:** la inicialización de OpenSpec no tiene commit propio; el primer commit ya contiene todo. La fase `init` no es auditable por separado.

---

### Bloque 2 — 2026-10-03: Reglas de agente + Ciclo OPSX 1

**Qué se hizo**
- `AGENTS.md`/`CLAUDE.md` (`072e380`).
- Ciclo 1 completo: 4/4 artefactos, 18 escenarios (7 foundation + 11 core), 14 tasks, **10/14** ejecutadas; 22 passed + 2 skipped en ese momento; archive `2026-10-03-c-01-foundation-core-models`; push `09cd116` (78 archivos).
- Reordenamiento a `src/`, `tests/`, `docs/` (`fca9bd0`), informe de discovery de 256 líneas (`f202e2f`) y plantilla de reflexión (`9dca044`).

**Decisión clave:** C-01 y C-02 se ejecutaron juntos para tener reglas verificables desde el inicio.

**Deuda generada:** 4 tasks sin cerrar (1.4 Compose up, 2.4 GRANT, 4.2 CI, 4.3 verificación integral); la suite local cae a SQLite si no hay `DATABASE_URL_TEST` (tensión con R11); el commit `09cd116` mezcla implementación y tests.

---

### Bloque 3 — 2026-10-14/15: Entregables académicos + split C-01/C-02

**Qué se hizo**
- `reflexion.md` completo (`c029acd`, `fd8d371`) y video en el README (`e21495e`, `e86b099`).
- Detección del layout plano (`src/src/` anidado) y separación en `src/backend/` + `src/frontend/` con `git mv` (`6196a3a`).
- Archive `2026-10-15-c-01-solo-setup` con **11/13** (pendientes 3.3 y 5.1 por falta de Docker) y merge `ac56510`.

**Resultado:** layout correcto y C-02 separado como gap-closure CRÍTICO.

---

### Bloque 4 — 2026-10-16/22: Correcciones de entrega

**Qué se hizo**
- Ajustes finales y limpieza de `docs/changes/` (`ee3a2c0`, `60ba6d5`, `c139538`, `4259d25`).
- Baja del PDF viejo de defensa (`b62af89`) y merge con el remoto (`abb5a0c`).

**Lectura:** bloque administrativo, sin cambio de alcance. La auditoría anterior tiene fecha de corte 2026-10-20, pero se versionó recién en `c751f24` (2026-11-16) con datos del ciclo 1.

---

### Bloque 5 — 2026-10-29/30: C-02, C-03 y C-04

**Qué se hizo**
- **C-02** cerrado contra PostgreSQL real: encontró y corrigió 3 defectos reales (GUID→hex en asyncpg, stubs de Redis pisando tipos, `mypy` sin `strict` en CI) y el test de auditoría pasó a validar `SQLSTATE 42501`. Se archivó el 2026-10-29 (`11/11`, 24 tests).
- **C-03** auth/RBAC: migración `002`, login/refresh/logout/me, cookie `HttpOnly` con rotación y revocación por reúso, bcrypt, rate limiting 5/60 s, RBAC declarativo de 14 recursos × 3 roles y CRUD de usuarios. `17/17`, 125 tests contra PostgreSQL real (`3933745`).
- **C-04** catálogo: sillones, prestaciones, coberturas y políticas del tenant; migración `003`; `9/9`, 61 tests nuevos.

**Evidencia:** archives `2026-10-29..`, `2026-10-30..`; `CHANGES.md:135,157,189`.

---

### Bloque 6 — 2026-11-01: C-05 a C-11 (15 commits)

**Qué se hizo, en un día**
- **C-05** pacientes + consentimiento WhatsApp (5/5, 26 tests).
- **C-06** agenda con máquina de estados y anti-solapamiento (6/6, 22 tests).
- **C-07** lista de espera con oferta proactiva por token (5/5).
- **C-08** comunicaciones: plantillas versionadas + outbox (5/5).
- **C-09** HC, odontograma FDI 11–48/51–85, adjuntos y consentimiento con hash (5/5).
- **C-10** presupuestos con cálculo en servidor y guardia de consentimiento (5/5).
- **C-11** caja y señas con grafo de estados y cierre (5/5).

**Evidencia:** 15 commits del 2026-11-01; archives `2026-11-01-c-05..c-11`; `CHANGES.md:213-331`.

---

### Bloque 7 — 2026-11-02/05: C-12 y C-13

**Qué se hizo**
- **C-12** Mercado Pago: `CobroMP`, preferencia atada a la seña, webhook firmado e idempotente por `mp_payment_id`, conciliación y discrepancias; migración `011`.
- **C-13** obras sociales: liquidación por OS/período con débitos, reclamo único, migraciones `012` y `013`, endpoints `/api/os/cobertura` y `/api/liquidaciones*` con export CSV/JSON; 28/28 tareas.
- Fixes de infraestructura en el camino: healthchecks de api/worker, worker tolerante a Redis inactivo, nginx no-root (`aa8470b`, `2c0cccc`, `56c1553`, `4f4c0fd`, `510bd1b`).

**Evidencia:** `fa68066`, `ab34702`; `CHANGES.md:351,371`.

---

### Bloque 8 — 2026-11-10/12: MCP, skills y C-15

**Qué se hizo**
- Servidor MCP con 2 tools de solo lectura (`91132b7`).
- Skills básicas del agente (`f7e14e7`) y merge del remoto (`e40a811`).
- **C-15** reserva pública PWA: `/reservar/:slug`, `/mis-turnos/:token`, seña guiada, `/firmar/:token`, shell offline; 15/15 tareas.

**Evidencia:** `f17ec8b`; archive `2026-11-12-c-15-reserva-publica-pwa`.

---

### Bloque 9 — 2026-11-16: C-16, C-17, C-18 y C-19

**Qué se hizo**
- **C-16** shell interno + agenda clínica (37/37; 12 archivos / 63 tests Vitest al momento del cierre).
- **C-17** caja/OS/admin + dashboards + polish (43/43; 18 archivos / 89 tests).
- **C-18** frontend en Compose con proxy `/api` y usuario demo (17/17).
- **C-19** fix CRÍTICO de persistencia: commit en los 28 endpoints mutantes (22/22; spec `persistencia-sesiones` con 5 requisitos / 17 escenarios).
- CI suma `openspec validate --all --strict` (`11ca173`) y se escribe esta auditoría + la guía de defensa (`c751f24`).

**Evidencia:** `3e25e21`, `5325296`, `0222889`, `ba7f74d`, `7afb7a1`, `6e6f602`, `53bb7f6`, `a1251e0`.

---

### Bloque 10 — 2026-11-17: C-14 y esta reauditoría

**Qué se hizo**
- **C-14** auditoría/exportación: `GET /api/auditoria` con filtros y keyset, exportación 1 clic (sync ≤ 5000 filas, async con job + descarga sobre el umbral), paquete de datos del paciente (RN-SE-02), `/privacidad`, enmascarado de PHI, volumen `exportaciones`; 46/49 tareas.
- Reauditoría integral: se ejecutan todos los gates y se reescribe este documento al estado real.

**Evidencia:** `968e6d6`, `e81f8ae`, archive `2026-11-17-c-14-auditoria-exportacion`.

---

## 3. Fases SDD/OPSX: qué son y cómo se aplicaron

### 3.1 Qué es SDD (Spec-Driven Development)

En SDD, **la especificación es la fuente de verdad**, no el código. El flujo es:

```text
idea → explorar → proponer (spec + diseño + tasks) → implementar → verificar → archivar
```

Cada cambio produce artefactos revisables antes de escribir código. La ventaja: el agente no improvisa; ejecuta un contrato. La desventaja: si los artefactos se desactualizan, la "fuente de verdad" miente. En este repo pasó en C-02 (2026-10-15, ya corregido) y vuelve a pasar en C-14 con dos tests de frontend que los `tasks.md` dan por hechos y no existen (§8.2 R-10, §10 D-03).

### 3.2 OpenSpec / OPSX

OpenSpec es la herramienta que materializa SDD en el repo. OPSX es el workflow fluido que usa:

```bash
openspec new change "<nombre>"
openspec status --change "<nombre>" --json
openspec instructions <artefacto> --change "<nombre>" --json
openspec instructions apply --change "<nombre>" --json
openspec validate --change "<nombre>"
openspec archive "<nombre>"
```

**Conceptos clave**

| Concepto | Qué es | Dónde vive |
|---|---|---|
| Change | Unidad atómica de trabajo con propuesta, diseño, specs y tasks | `openspec/changes/<nombre>/` |
| Proposal | Qué y por qué | `proposal.md` |
| Design | Cómo y con qué decisiones | `design.md` |
| Delta spec | Escenarios que agrega/modifica/elimina el change | `specs/<capability>/spec.md` |
| Tasks | Checklist de implementación | `tasks.md` |
| Main spec | Verdad consolidada de una capability | `openspec/specs/<capability>/spec.md` |
| Archive | Cierre: sincroniza specs y mueve el change | `openspec/changes/archive/AAAA-MM-DD-<nombre>/` |
| Validate | Verifica coherencia de artefactos | CLI |

**Importante para la defensa:** `openspec status` puede decir `isComplete: true` refiriéndose a **artefactos de planificación**, no a implementación. El progreso real se lee en el `tasks.md` del archive. Al corte no quedan changes activos, así que la trampa ya no aplica, pero la lección queda: **el número que se cita sale del `tasks.md` contado a mano, no del status**.

### 3.3 El flujo de fundación usado

```text
openspec init → discovery → kb-creator → roadmap-generator
→ find-skill → skill-registry → agent-instruction
```

| Fase | Producto | Evidencia |
|---|---|---|
| Discovery | `discovery/discovery.md` | 18 sistemas, fuentes 2026-10-01 |
| KB | 11 docs + README | `knowledge-base/` (12 archivos) |
| Roadmap | 19 changes, 9 gates, camino crítico | `CHANGES.md` |
| Find-skill | 21 skills en `.agents/skills/` | `Get-ChildItem .agents/skills -Directory` → 21 |
| Registry | Compact rules por change | `.agents/skill-registry.md` |
| Agent-instruction | `AGENTS.md` + `CLAUDE.md`, R1–R13 | `AGENTS.md:79-97` |

### 3.4 El ciclo aplicado al change

| Fase | Qué produce | Evidencia en este repo | Estado |
|---|---|---|---|
| Explore | Entendimiento y alcance; sin código | Observaciones Engram | Hecho en los changes grandes |
| Propose | Proposal + design + specs + tasks | 20 archives con 4 artefactos | Hecho |
| Apply | Código + tests por task | 19 changes implementados | Hecho, salvo 5 tareas Docker |
| Verify | Gates y cobertura de escenarios | 687 passed / 2 failed ambientales / 8 skipped; 90 Vitest | Hecho con deuda de entorno |
| Archive | Sync de specs + cierre | 20 archives, 20 specs main | Hecho |

### 3.5 Evaluación honesta del método

**Fortalezas**
- Alcance trazable: cada change tiene propuesta, escenarios, tasks y carpeta de archive.
- Governance explícito: lo CRÍTICO se separa y C-19 se propuso como fix CRÍTICO con su propia spec.
- Calidad automatizada: CI corre backend contra PostgreSQL real, frontend con Vitest y `openspec validate --all --strict`.
- Memoria persistente: decisiones y sesiones quedan en Engram.

**Debilidades**
- Algunos `tasks.md` marcan `[x]` tareas cuya evidencia no está en el repo (C-14, 8.1/8.2: tests de frontend inexistentes).
- El TDD está documentado como "Strict TDD" desde C-04, pero en casi todos los changes la secuencia rojo-verde se ve dentro del mismo commit. La excepción parcial es C-14: `968e6d6` agrega los tests de auditoría antes de `e81f8ae`, aunque también suma schemas y `zonas.py`.
- `CHANGES.md` acumula notas de realidad fechadas que quedan vencidas cuando el change se cierra (dos notas del 2026-11-16 sobre C-14).
- El guion del video es un PDF: no se puede diffear en un review, aunque sus números grandes están alineados al corte.

---

## 4. Los changes, uno por uno

> Los 20 archives se leyeron carpeta por carpeta. Tareas = `[x]`/total contadas en el `tasks.md` del archive (comando: `Select-String '\[x\]'` vs `'\[ \]'`).

### 4.1 FASE 0 — Cimientos

**C-01 original — `2026-10-03-c-01-foundation-core-models`**
**Objetivo:** fundación técnica + modelos core en un solo ciclo.
**Alcance:** scaffolding, FastAPI, settings, logging, errores, SQLAlchemy/Alembic, 3 modelos, repo/UoW, seed, PWA, Compose, CI.
**Specs:** `foundation-setup` (7 escenarios) + `core-models-multitenant` (11) = 18.
**Tasks:** **10/14**. Abiertas: 1.4 (Compose up + health), 2.4 (GRANT de auditoría; cerrada luego por C-02), 4.2 (CI verde), 4.3 (verificación integral) — `tasks.md:8,15,26,27`.
**Resultado:** archivado; 2 specs sincronizadas. Su deuda es de verificación, no de diseño, y 2.4 quedó saldada en C-02.

**C-01 solo-setup — `2026-10-15-c-01-solo-setup`**
**Objetivo:** corregir layout sin cambiar comportamiento.
**Alcance:** `git mv` a `src/backend` + `src/frontend`; rewiring de pytest/conftest/pyproject/compose/CI.
**Specs:** ninguna (`skip_specs: true`, refactor puro).
**Tasks:** **11/13**. Abiertas: 3.3 (Alembic `upgrade head` + `downgrade -1` + `upgrade head` en contenedor fresco) y 5.1 (stack limpio + health) — `tasks.md:17,28`.
**Resultado:** archivado, validate 3/3. Es la deuda del split; el archive original conserva además 1.4 (Compose up) y 4.3 (verificación integral), más 4.2 (CI verde) — `CHANGES.md:117`.

**C-02 — `2026-10-29-c-02-modelos-core`**
**Objetivo:** gap-closure de verificación (GRANT de auditoría + paridad post-move).
**Entrega real:** además de cerrar 2.4, corrigió el `GUID` asyncpg (UUID→hex), sacó `types-redis` y alineó `mypy` con el `strict` del proyecto; el test de rechazo de auditoría ahora valida `SQLSTATE 42501` (`CHANGES.md:136`).
**Tasks:** **11/11**. **Tests:** 24 passed / 0 skipped contra PostgreSQL real. **Spec:** `core-models-multitenant`.
**Lectura:** es el change que convirtió la "deuda de C-02" en evidencia; la auditoría del 2026-10-20 quedó desactualizada justo acá.

### 4.2 FASE 1 — Acceso

**C-03 — `2026-10-30-c-03-auth-rbac-tokens`**
**Entrega:** JWT access corto + refresh opaco en cookie `HttpOnly` con rotación y revocación por reúso; logout idempotente; `GET /api/auth/me`; bcrypt directo; rate limiting 5/60 s en Redis fail-closed; RBAC de 14 recursos × 3 roles enforced en la API; CRUD `/api/usuarios` con auditoría de cambios de rol; migración `002`.
**Tasks:** **17/17**. **Tests:** 125 passed contra PostgreSQL real; 122 + 3 skips sin Docker. **Spec:** `auth-rbac-tokens`.
**Lectura:** acá se materializa R4 (`tenant_id` desde el token, `security.py:26,57`).

### 4.3 FASE 2 — Dominio base

**C-04 — `2026-10-30-c-04-catalogo-configuracion`**: sillones, prestaciones, coberturas OS y políticas del tenant; migración `003`; **9/9**, 61 tests nuevos (186 al cierre).
**C-05 — `2026-11-01-c-05-pacientes`**: pacientes + consentimiento WhatsApp; migración `004`; **5/5**, 26 tests nuevos (212 al cierre).
**C-06 — `2026-11-01-c-06-agenda-turnos`**: turnos por profesional y sillón, anti-solapamiento `[inicio, fin)` con `409` + `slots_alternativos`, bloqueos y reprogramación; migración `005`; **6/6**, 22 tests nuevos (234 al cierre).
**Lectura:** C-04 y C-05 corrieron en paralelo y C-06 los unió, como preveía el roadmap.

### 4.4 FASE 3 — Flujos asistenciales

**C-07 — `2026-11-01-c-07-lista-espera`**: `ListaEspera`, migración `006`, oferta y rotación de huecos idempotente, aceptación en 1 clic por token y enganche al cancelar/reprogramar; **5/5**.
**C-08 — `2026-11-01-c-08-comunicaciones-mensajeria`**: `Plantilla` versionada + `Mensaje` outbox, migración `007`, seed de 5 plantillas, `optin_wa`, dedup, reintentos con backoff y webhook de WhatsApp; **5/5**.
**C-09 — `2026-11-01-c-09-historia-clinica-odontograma`**: `Evolucion` append-only con enmienda aditiva, `Odontograma`, `PiezaEvento` FDI 11–48/51–85, `AdjuntoClinico` y `Consentimiento` con `firma_hash`; migración `008`; **5/5**.
**C-10 — `2026-11-01-c-10-presupuestos-planes`**: `Presupuesto`, items y vínculo N-N con turnos, cálculo OS/particular en servidor y guardia de consentimiento para prestaciones invasivas; migración `009`; **5/5**.

### 4.5 FASE 4 — Dinero

**C-11 — `2026-11-01-c-11-caja-senas`**: `Sena`, `MovimientoCaja`, `CierreCaja`; migración `010`; auto-generación de seña al reservar, grafo `pendiente → cobrada → aplicada | devuelta | vencida`, `saldo = precio - cobertura - seña`; **5/5**.
**C-12 — `2026-11-02-c-12-mercadopago-webhooks`**: `CobroMP` + migración `011`, preferencia atada a la seña, webhook HMAC-SHA256 idempotente por `mp_payment_id`, conciliación y discrepancias; **6/6**.
**C-13 — `2026-11-05-c-13-obras-sociales-liquidacion`**: cobertura compartida, migraciones `012` y `013`, liquidación por OS/período con débitos y reclamo único, export CSV/JSON; **28/28**, 173 tests del bloque y suite de 552 al cierre.

### 4.6 FASE 5 — Transversal

**C-19 — `2026-11-16-c-19-fix-commit-persistencia`** (CRÍTICO): commit explícito en los 28 endpoints mutantes de pacientes/HC/caja/presupuestos; spec nueva `persistencia-sesiones` (5 requisitos / 17 escenarios); **22/22**. Desbloqueó la firma E2E de C-16/C-17.
**C-14 — `2026-11-17-c-14-auditoria-exportacion`** (CRÍTICO): `GET /api/auditoria` con filtros, orden descendente y keyset sin `OFFSET`; exportación 1 clic de `agenda`/`pacientes`/`caja`/`liquidaciones` en CSV/JSON (sync ≤ 5000 filas, async con job + descarga sobre el umbral, TTL fijo 24 h); paquete JSON del paciente (RN-SE-02); `/privacidad` pública (Ley 25.326 y 26.529); enmascarado de PHI en textos libres; volumen `exportaciones` en Compose; **46/49** (3 bloqueadas por Docker). Specs: `auditoria-exportacion` (nueva, 410 líneas) + delta `pacientes`.

### 4.7 FASE 6 — Frontend PWA

**C-15 — `2026-11-12-c-15-reserva-publica-pwa`**: `/reservar/:slug`, `/mis-turnos/:token`, seña guiada con montos del servidor, `/firmar/:token`, shell offline con service worker; **15/15**.
**C-16 — `2026-11-16-c-16-frontend-agenda-clinica`**: shell interno + agenda, pacientes, clínica y comunicaciones con guards de rol en UI; capabilities `frontend-shell-interno` y `frontend-agenda-clinica`; **37/37**; 12 archivos / 63 tests Vitest al cierre.
**C-17 — `2026-11-16-c-17-frontend-caja-os-admin`**: caja, OS, admin, dashboards y polish visual; capabilities `frontend-caja-os` y `frontend-admin-tenant`; **43/43**; 18 archivos / 89 tests al cierre.

### 4.8 FASE 7 — Demo compose

**C-18 — `2026-11-16-c-18-frontend-compose-demo`**: servicio `frontend` en `:8080` con nginx y proxy `/api/`, utilería idempotente `app.scripts.usuario_demo`, `tests/test_demo_frontend.py` y documentación; **17/17**.

---

## 5. Roadmap completo

### 5.1 Las 8 fases y los 9 gates

`CHANGES.md` define FASE 0 a FASE 7 (`CHANGES.md:114,154,184,249,326,391,427,485`) y GATE 0 a GATE 8. **Todos los gates están en `✓`**: no queda ningún change pendiente.

```text
GATE 0: ninguna
GATE 1: C-01 ✓
GATE 2: C-02 ✓
GATE 3: C-03 ✓            ← desbloqueó todo
GATE 4: C-04 + C-05 ✓
GATE 5: C-06 ✓
GATE 6: C-09 + C-11 ✓
GATE 7: C-14 + C-15 + C-16 ✓
GATE 8: C-14 ✓ → C-17 ✓
```

### 5.2 Camino crítico (9 changes)

```text
C-01 → C-02 → C-03 → C-05 → C-06 → C-09 → C-11 → C-12 → C-15
```

**Por qué termina en C-15:** el corte del MVP es que el paciente pueda reservar online y pagar la seña por Mercado Pago. Sin C-15 no hay captura 24/7; sin C-12 no hay seña. C-16 y C-17 completan la operación interna; C-14 cierra la obligación legal de consulta y portabilidad.

### 5.3 Los 19 changes

| # | Change | Fase | Governance | Archive | Tareas |
|---|---|---|---|---|---|
| C-01 | foundation-setup | 0 | BAJO | `2026-10-03-...` (10/14) + `2026-10-15-c-01-solo-setup` (11/13) | Con deuda Docker |
| C-02 | core-models-multitenant | 0 | CRÍTICO | `2026-10-29` | 11/11 |
| C-03 | auth-rbac-tokens | 1 | CRÍTICO | `2026-10-30` | 17/17 |
| C-04 | catalogo-configuracion | 2 | BAJO | `2026-10-30` | 9/9 |
| C-05 | pacientes | 2 | BAJO | `2026-11-01` | 5/5 |
| C-06 | agenda-turnos | 2 | CRÍTICO | `2026-11-01` | 6/6 |
| C-07 | lista-espera | 3 | MEDIO | `2026-11-01` | 5/5 |
| C-08 | comunicaciones-mensajeria | 3 | ALTO | `2026-11-01` | 5/5 |
| C-09 | historia-clinica-odontograma | 3 | CRÍTICO | `2026-11-01` | 5/5 |
| C-10 | presupuestos-planes | 3 | MEDIO | `2026-11-01` | 5/5 |
| C-11 | caja-senas | 4 | CRÍTICO | `2026-11-01` | 5/5 |
| C-12 | mercadopago-webhooks | 4 | CRÍTICO | `2026-11-02` | 6/6 |
| C-13 | obras-sociales-liquidacion | 4 | MEDIO | `2026-11-05` | 28/28 |
| C-19 | fix-commit-persistencia | 5 | CRÍTICO | `2026-11-16` | 22/22 |
| C-14 | auditoria-exportacion | 5 | CRÍTICO | `2026-11-17` | 46/49 |
| C-15 | reserva-publica-pwa | 6 | MEDIO | `2026-11-12` | 15/15 |
| C-16 | frontend-agenda-clinica | 6 | MEDIO | `2026-11-16` | 37/37 |
| C-17 | frontend-caja-os-admin | 6 | MEDIO | `2026-11-16` | 43/43 |
| C-18 | frontend-compose-demo | 7 | BAJO | `2026-11-16` | 17/17 |

**Distribución:** 4 BAJO, 8 CRÍTICO, 1 ALTO, 6 MEDIO (evidencia: `Governance` en `CHANGES.md:126..500`).
**Agentes:** A = Backend Core; B = Backend Aux; C = Dinero + Frontend.

### 5.4 Por qué este orden (y qué mostró la ejecución)

- Primero **identidad y aislamiento** (C-01/02/03): sin tenant y auth no hay negocio seguro. La ejecución lo confirmó: los primeros CRUD de negocio (C-04/C-05) llegaron después de C-03.
- Luego **datos maestros en paralelo** (C-04 catálogo, C-05 pacientes) y **agenda** (C-06) como corazón operativo.
- En el fork grande, **clínica y caja** avanzaron en paralelo porque son dominios distintos; **pagos** (C-12) dependió de caja (C-11) porque la seña nace de un cobro.
- La **reserva pública** (C-15) llegó después de HC + pagos + PWA, como estaba previsto.
- **Desvío real:** C-17 se cerró antes que C-14 (dependencia declarada como deuda, `CHANGES.md:42,85`). Cuando C-14 se archivó el 2026-11-17 la deuda quedó saldada, pero las dos notas no se actualizaron.
- **Agregado no planificado:** C-18 (demo compose) y C-19 (fix de persistencia) surgieron de necesidades de la demo y de un bug CRÍTICO de sesión; el roadmap los incorporó como changes formales.

---

## 6. Qué está implementado vs. qué no

### 6.1 Matriz de estado real

| Área | Implementado | Evidencia | Brecha |
|---|---|---|---|
| Health check | `GET /api/health` 200/503 con DB+Redis | `api/routers/health.py` | Sin timeout de DB; engine por request (§8.3) |
| Configuración | Pydantic Settings + `.env.example`; sin secretos | `shared/settings.py` | No hay lifespan que valide al arrancar: se valida en la primera dependencia (`deps.py:14-17`, `main.py:25`) |
| Logging | Logger a stdout, sin PHI explícita | `shared/logging.py` | Sin redacción automática ni request ID |
| Errores | `AppError`, handlers globales, mensajes rioplatenses | `shared/exceptions.py` | — |
| Auth | Login, refresh rotativo, logout, me, rate limit | `routers/auth.py`, `infrastructure/security/` | — |
| RBAC | 14 recursos × 3 roles + recurso nuevo de exportación | `domain/rbac.py`, `api/security.py` | Desvío C-14 (solo Dueño exporta), consulta al PO |
| Modelos | 29 tablas, 13 migraciones reversibles | `alembic/versions/001..013` | Cascada de auditoría desde `tenant` (§8.1) |
| Multi-tenant | `TenantMixin` + repo que falla cerrado + `tenant_id` del token | `domain/mixins.py`, `infrastructure/db/repository.py` | Sin RLS (DD-07: opcional a futuro) |
| UoW | Commit/rollback; C-19 fija el commit explícito en 28 endpoints | `infrastructure/db/unit_of_work.py` | El patrón depende de que cada caso de uso commitee |
| Auditoría | Trail consultable con filtros y keyset; append-only por permisos; exportaciones auditadas | `application/auditoria.py`, `routers/auditoria.py`, migración `001` | Lecturas de HC sin auditar; índices diferidos; cascada |
| Pagos | Preferencia MP, webhook firmado idempotente, conciliación | `routers/webhooks_mercadopago.py`, `application/mercadopago.py` | Credenciales reales no probadas (dummy en tests) |
| Mensajería | Plantillas versionadas, outbox, opt-in, backoff, webhook WA | `application/comunicaciones.py`, `worker` | El test de API hace HTTP real y falla con 401 dummy (§8.1 R-03) |
| Exportación | 4 datasets CSV/JSON + jobs + paquete del paciente + `/privacidad` | `routers/exportacion.py`, `application/exportacion.py` | Archivos en disco local; sin object storage |
| API negocio | 110 rutas en 16 módulos de router | `api/routers/` | — |
| Frontend | 17 archivos `*Page.tsx` (públicas + `/app`), guards de rol, PWA | `src/frontend/src/features/` | 2 tests de C-14 citados en tasks no existen (R-10) |
| PWA | Manifest + SW + offline shell + precache 10 entradas | `vite.config.ts`, build | Bundle JS >500 kB (warning de Vite) |
| Docker | 7 servicios + volumen `exportaciones` + frontend nginx | `docker-compose.yml` | Daemon no disponible en esta máquina para verificaciones |
| CI | Backend con PostgreSQL/Redis + frontend Vitest/build + OpenSpec strict | `.github/workflows/ci.yml` | No valida `compose up`, e2e ni imágenes |
| Tests | 90 archivos / 687 passed / 8 skipped; 90 Vitest | `tests/`, `src/frontend/test/` | 2 fallos ambientales; 8 skips (7 de DB + 1 de stack Compose) |
| Docs | KB, discovery, roadmap completo, 20 archives, 20 specs | `knowledge-base/`, `openspec/` | `defensa-oral-guia.md` viejo; notas de CHANGES |

### 6.2 Qué puede hacer el sistema hoy (demo real)

1. Levantar API, DB, Redis, worker, Mailhog y frontend con `docker compose up --build` (`:8080`).
2. Ejecutar las 13 migraciones y el seed idempotente.
3. Loguearse con el usuario demo y recibir access JWT + refresh en cookie.
4. Gestionar catálogo (sillones, prestaciones, coberturas, políticas) y usuarios con RBAC.
5. Dar de alta pacientes, turnos con anti-solapamiento, bloqueos y reprogramación.
6. Cargar HC con evoluciones append-only, odontograma FDI, adjuntos y consentimiento firmado.
7. Armar presupuestos con cobertura OS y guardia de consentimiento.
8. Cobrar señas, mover caja y cerrar el día.
9. Recibir el webhook de Mercado Pago y conciliar cobros.
10. Liquidar obras sociales por período y exportar CSV/JSON.
11. Reservar online desde la PWA pública, pagar la seña y firmar el consentimiento por token.
12. Consultar `/mis-turnos/:token` y la página pública `/privacidad`.
13. Auditar el trail con filtros y exportar datasets o el paquete de un paciente (solo Dueño).
14. Pasar 687 tests de backend y 90 de frontend, y los gates de lint/tipos/build.

---

## 7. Evidencia de calidad

### 7.1 Gates ejecutados en esta auditoría

| Gate | Resultado | Exit |
|---|---|---|
| `openspec list` | "No active changes found." | 0 |
| `openspec validate --all --strict` | **20 passed, 0 failed (20 items)** | 0 |
| `pytest tests -q` | **687 passed, 2 failed, 8 skipped** en 106.98 s | 1 |
| `ruff check --config src/backend/pyproject.toml src/backend tests` | All checks passed! | 0 |
| `ruff format --check ...` | 212 files already formatted | 0 |
| `mypy --config-file src/backend/pyproject.toml src/backend` | Success: no issues found in 120 source files | 0 |
| `npm run test:run` (frontend) | **18 archivos / 90 tests passed** (19.92 s) | 0 |
| `npm run build` (frontend) | `tsc --noEmit` + vite build + SW; JS 502.39 kB (131.51 gzip), CSS 35.11 kB (6.25 gzip), precache 10 entradas | 0 |
| `git status -sb` | limpio al iniciar; `main` = `origin/main` sin adelantos ni atrasos | 0 |
| `docker --version` | 29.9.2 (cliente) | 0 |
| `docker info` | **daemon no responde** (pipe `dockerDesktopLinuxEngine` no encontrado) | 1 |

**Los 2 fallos de pytest (ambientales, preexistentes, NO se tocaron):**

| Test | Síntoma | Causa |
|---|---|---|
| `tests/test_settings.py::test_arrancar_sin_jwt_secret_falla_nombrando_la_variable` | `Failed: DID NOT RAISE ValidationError` (`tests/test_settings.py:24`) | `Settings` declara `model_config = SettingsConfigDict(env_file=".env", ...)` (`src/backend/app/shared/settings.py:10`) y hay un `.env` local con `JWT_SECRET`: borrar las variables de entorno no evita que Pydantic lea el archivo. En un clon limpio (sin `.env`) pasa. |
| `tests/test_comunicaciones_api.py::test_api_mensajes_y_plantillas_rbac_y_multitenant` | `assert 'pendiente' == 'enviado'` (`tests/test_comunicaciones_api.py:109`) | El reenvío llama al cliente de WhatsApp real y recibe **401** con credenciales dummy (`wa_client.py:45` → `Fallo HTTP WhatsApp Cloud API status=401`); el mensaje queda `pendiente` en vez de `enviado`. No hay mock de red. |

**Los 8 skips, verificados con `pytest -rs` sobre los archivos que los declaran:** 7 exigen PostgreSQL real — append-only con rol restringido (`test_auditoria_appendonly.py:80,103`), GRANTs de sesiones (`test_grants_sesiones.py:33`), GRANTs de catálogo (`test_migracion_003_catalogo.py:418`), locks pesimistas de liquidación (`test_liquidaciones_estados.py:678`, `test_liquidaciones_negocio.py:767`) y carrera contra índice único (`test_liquidaciones_unicidad.py:453`) — y **1 es el smoke contra el stack Compose en vivo** (`test_demo_frontend.py:260`: "Stack compose no está escuchando en http://localhost:8080"). Es la tensión conocida con R11: en local sin contenedor hay 8 casos que no corren.

### 7.2 Inventario de tests

**Backend:** 90 archivos `test_*.py` en `tests/` (`Get-ChildItem tests -File -Filter test_*.py` → 90); 687 tests colectados.

| Grupo | Archivos | Qué cubre |
|---|---|---|
| Auth y seguridad | 11 | login, refresh, cookie, logout/me, usuarios, documentación; JWT, passwords, rate limit, tokens públicos, GRANTs |
| Auditoría | 4 | append-only (API + DB), consulta/keyset, documentación, schemas |
| Exportación | 7 | datasets, jobs, purga, seguridad, paquete del paciente, schemas, documentación |
| Liquidaciones y OS | 12 | dominio, API, estados, unicidad, export, cobertura, schemas |
| Mercado Pago | 5 | API, cliente, webhook, conciliación, schemas |
| Migraciones | 12 | `002` a `013` (aplicación, índices, constraints) |
| Catálogo | 6 | CRUD por recurso, políticas, documentación, schemas |
| Caja / Pacientes / Agenda / Clínica / Presupuestos / Comunicaciones / Lista de espera | 3 cada uno | API, negocio y schemas por dominio |
| Core y transversales | 12 | modelos core, aislamiento, seed, health, settings, montos, RBAC, persistencia, reserva pública, PHI, demo |

**Frontend:** **18 archivos de test** en `src/frontend/test/` (más `render.tsx` y `setup.ts` de infraestructura: 20 archivos en la carpeta) y **90 tests** Vitest: admin, agenda, API client, caja, componentes UI, comunicaciones, ficha clínica, formatters, liquidaciones, login, pacientes, panel/polish, RBAC, sesión, shell y smoke.

### 7.3 Lo que el CI sí y no prueba

**Sí:** instala backend y frontend, crea el rol `turnos_app`, corre `alembic upgrade head`, lint + tipos, `pytest` contra PostgreSQL/Redis reales, Vitest, `tsc` + build y `openspec validate --all --strict` (`.github/workflows/ci.yml`).

**No:** build de imágenes, `compose up`, nginx/proxy `/api` real, e2e con navegador, accesibilidad, downgrade de migraciones, `alembic check`, worker/Mailhog, health end-to-end, cobertura, seguridad de dependencias ni deploy.

**Conclusión:** el CI verde prueba el código y los artefactos; **no prueba que el stack levante**. Eso es exactamente lo que quedó pendiente en las 5 tareas Docker.

### 7.4 Evaluación de TDD

**A favor:** 687 tests para 19 changes; casos borde reales (mismo email en otro tenant, tenant ajeno, doble seed, keyset con `created_at` empatados, cursor corrupto, umbral 5000/5001, job vencido, PHI en nombre de archivo). Varios `tasks.md` (C-04, C-05, C-06, C-13, C-14) dicen "Strict TDD" y C-14 arranca cada bloque con "Escribir primero los tests que fallan".

**En contra:** en la mayoría de los changes el commit principal mezcla código y tests (la secuencia rojo-verde no se separa); C-14 sí tiene un commit previo con tests (`968e6d6`), pero también con schemas; C-14 marca `[x]` dos tareas de frontend cuyos archivos de test no existen (D-03); 3 tests de `test_cobertura_verify` son checks de strings; y en local la suite cae a SQLite para los casos que no exigen Postgres.

**Frase honesta para la defensa:** "Aplicamos TDD como disciplina de cobertura y casos borde en todos los changes; la historia de commits no separa rojo de verde, y en C-14 la cobertura de frontend quedó declarada pero no está en el repo. Es una de las cosas que corregiríamos."

---

## 8. Riesgos y deudas vigentes

> Solo lo que sigue abierto al 2026-11-17. Lo que la auditoría anterior marcaba como grave y ya se cerró (C-02 0/11, falta de auth/RBAC, ausencia de endpoints de negocio, frontend sin pantallas) **no aparece acá**.

### 8.1 Alto

#### R-01. La auditoría append-only todavía se puede borrar en cascada desde `tenant`

- `auditoria.tenant_id` es FK con `ON DELETE CASCADE` (`src/backend/alembic/versions/001_initial_tenant_usuario_auditoria.py:72`).
- El rol de la app tiene `GRANT DELETE ON tenant` (`001_...py:91`), y el trail solo tiene `GRANT SELECT, INSERT` (`:93`).
- C-02 verificó que los GRANT de auditoría eran correctos y **no tocó ningún permiso** (`CHANGES.md:136`); no hay migración posterior que cambie la FK.
- Los tests cubren `UPDATE`/`DELETE` directos sobre `auditoria` (`tests/test_auditoria_appendonly.py:76,99`), **no** el `DELETE FROM tenant`.
- **Impacto:** un borrado del tenant se lleva el trail que RN-SE-01 y la retención de 5 años exigen conservar.
- **Fix esperado:** migración con `ON DELETE RESTRICT` + `REVOKE DELETE ON tenant` + baja lógica del tenant. Es un change nuevo, no una task suelta.
- **Respuesta de defensa:** reconocerlo como el hallazgo más grave que queda, decir que ya estaba identificado en la auditoría con corte 2026-10-20 y que la corrección requiere migración con aprobación humana (governance CRÍTICO).

#### R-02. 3 tareas de C-14 bloqueadas por Docker

- 3.3: correr los casos de DB de append-only contra Postgres real (`tasks.md:22`).
- 10.1: suite backend completa contra Postgres real, sin regresiones (`tasks.md:77`).
- 10.3: smoke end-to-end con `docker compose up --build` (`tasks.md:79`).
- **Estado del entorno:** el CLI existe (`docker --version` → 29.9.2) pero el daemon no responde (`docker info` → pipe no encontrado). No es "Docker no instalado" como decía la auditoría anterior.
- **Comandos documentados en el propio `tasks.md`:** `docker compose up -d db redis && pytest tests/test_auditoria_appendonly.py`; `docker compose up -d db redis && pytest tests`; `docker compose up --build`.

#### R-03. Los 2 fallos ambientales ensucian el gate local

- No son regresiones ni deuda de producto, pero cualquier persona que corra `pytest` ve `2 failed` y tiene que saber por qué.
- `test_settings` depende de que **no** exista `.env` (`tests/test_settings.py:17-25` + `shared/settings.py:10`); `test_comunicaciones_api` depende de que no haya red o de que WhatsApp responda 2xx (`tests/test_comunicaciones_api.py:109`, `wa_client.py:45`).
- **Fix esperado:** marcar el primero con `pytest.mark.skipif(Path('.env').exists())` o forzar `_env_file=None` en el test; mockear el cliente de WhatsApp en el segundo. Ninguno se tocó en esta auditoría (fuera de alcance).

### 8.2 Medio

| ID | Hallazgo | Evidencia | Deuda / mitigación |
|---|---|---|---|
| R-04 | **Exportaciones en disco local del nodo** | `shared/settings.py:44-46` (`/var/tmp/turnos-exportaciones`) + volumen `exportaciones` en `docker-compose.yml` | Funciona mono-nodo; multi-instancia exige object storage (`design.md:215`) |
| R-05 | **Lecturas de HC sin auditar** | `design.md:34,222`: se auditan mutaciones y exportaciones, no la lectura clínica | Change posterior; no se amplió el alcance de C-14 |
| R-06 | **Índices de auditoría diferidos** | `design.md:57-62`: solo existe `(tenant_id, entidad, entidad_id, created_at)` | Agregar `(tenant_id, created_at DESC)` y `(tenant_id, actor_id, created_at DESC)` si supera ~200k filas o p95 > 300 ms |
| R-07 | **Retención legal exacta pendiente (PO-03)** | `knowledge-base/10_preguntas_abiertas.md:18`; `/privacidad` informa "mínimo 5 años, sujeto a dictamen" | Espera dictamen legal; no se inventa un plazo |
| R-08 | **Desvío RBAC de C-14: solo el Dueño exporta** | `proposal.md:38`, `design.md:41-55` vs `knowledge-base/03_actores_y_roles.md:31-32` | Consulta al PO abierta; si se habilita exportación parcial hay que scopear por actor y reescribir la matriz y sus tests |
| R-09 | **Padrón completo de pacientes sin período** | `proposal.md:39` | Consulta al PO: confirmar volcado total o exigir rango |
| R-10 | **Resuelto (2026-11-17): tests de frontend de C-14 creados** | Se agregaron `src/frontend/test/AuditoriaPage.test.tsx` (13 tests) y `PaginaLegal.test.tsx` (6 tests); la suite pasó de 90 a **109 tests** en 20 archivos. Al escribir los tests aparecieron dos bugs reales en `AuditoriaPage.tsx` (reset de la primera página por el auto-aplicado de filtros y formato horario 12 h) y se corrigieron | Mantener los tests en el gate de CI; el riesgo de "tarea marcada sin test" queda cerrado para C-14 |
| R-11 | **C-01 conserva verificaciones abiertas** | Solo-setup: 3.3 y 5.1 (`archive/2026-10-15-c-01-solo-setup/tasks.md:17,28`); original: 1.4, 4.2 y 4.3 (`archive/2026-10-03-c-01-foundation-core-models/tasks.md:8,26,27`); `CHANGES.md:117` | Cuatro dependen de Docker (1.4, 3.3, 5.1, 4.3); la 4.2 (CI verde) ya está cubierta por el pipeline actual, pero no se marcó en el archive |

### 8.3 Bajo (deudas declaradas, no bloquean)

| ID | Hallazgo | Evidencia |
|---|---|---|
| D-01 | Engine/session factory **por request**, sin `dispose` | `api/deps.py:22` → `session_factory_for()` crea engine por request |
| D-02 | Sin validación de config en lifespan | `main.py:25` no instancia Settings al arrancar |
| D-03 | `tasks.md` de C-14 marcan `[x]` tareas sin artefacto en el repo | ver R-10 |
| D-04 | Purga de exportaciones entre vencimiento y barrido (hasta 24 h + 5 min) | `design.md:224` |
| D-05 | Snapshots de auditoría pueden contener PHI; falta revisar minimización | `design.md:220` |
| D-06 | Worker arma el archivo en memoria; TTL fijo de 24 h sin variable | `design.md:117,216` |
| D-07 | Bundle JS > 500 kB (warning de Vite) | `npm run build` → 502.39 kB |
| D-08 | RLS no implementado (decisión DD-07) | sin RLS en migraciones |
| D-09 | `docs/defensa-oral-guia.md` anclada al 2026-10-20 (17 changes, 24 tests) | `docs/defensa-oral-guia.md:3,30,81,95` |
| D-10 | El guion del video es un PDF sin fuente `.md` versionada | `docs/guion-video-TPI.pdf`, agregado en `e81f8ae` |
| D-11 | CI no valida imágenes, `compose up`, e2e ni downgrade | `.github/workflows/ci.yml` |
| D-12 | MCP requiere `mcp>=2,<3` fuera de `requirements.txt` | `AGENTS.md` §Servidor MCP; `README.md:131` |

---

## 9. Método de trabajo: agentes, skills, governance y memoria

### 9.1 Active Stack + OpenCode + OpenSpec

El proyecto usa tres capas:
- **OpenCode** como runtime de agentes.
- **Active Stack** como metodología (orquestador + subagentes + skills + governance).
- **OpenSpec** como sistema de artefactos y estado.

### 9.2 Roles de agente

`AGENTS.md` define **8 roles**: Backend Core, Backend Aux, Frontend, Clínico, Infra, Diagnóstico, Calidad y Revisor SDD. Cada uno tiene skills asignadas. El orquestador delega y no implementa.

### 9.3 Skills y registry

- **21 skills** versionadas en `.agents/skills/` (verificado con `Get-ChildItem .agents/skills -Directory`).
- Registry canónico: `.agents/skill-registry.md` (`.atl/skill-registry.md` es un shim).
- Tabla Change → Skills, por ejemplo:
  - C-01: `multi-stage-dockerfile`, `python-fastapi-development`, `tdd`, `code-review`.
  - C-02: `supabase-postgres-best-practices`, `python-fastapi-development`, `tdd`.
  - C-03: `auth-implementation-patterns`, `python-fastapi-development`, `supabase-postgres-best-practices`, `tdd`, `code-review`.
  - C-09: `healthcare-emr-patterns`, `hipaa-compliance`, `frontend-design`, `supabase-postgres-best-practices`, `tdd`.
  - C-12: `stripe-integration` (plantilla), `clerk-webhooks` (patrón), `upstash-redis-js`, `tdd`, `code-review`.
  - C-14: `sdd-change-review` antes de aprobar, más `supabase-postgres-best-practices` y `tdd`.

**Límite honesto:** no hay telemetría de invocación por skill; el uso está documentado y planificado, no probado skill por skill.

### 9.4 Governance por dominio

| Nivel | Dominios | Comportamiento |
|---|---|---|
| CRÍTICO | Auth, pagos, salud, auditoría | Análisis primero; sin escritura sin aprobación humana |
| ALTO | Config sensible, backups | Proponer y esperar revisión |
| MEDIO | Lógica de negocio, adaptadores | Implementar con checkpoints |
| BAJO | CRUDs, catálogos, layout | Autonomía si los tests pasan |

**Evidencia clara:** C-14 pasó por `sdd-change-review` antes de aprobar (`evidence/reporte-sdd-change-review.md`) y su desvío de RBAC se documentó en proposal + design + tasks en vez de editar la KB por cuenta propia. C-19 se propuso como fix CRÍTICO con spec nueva en lugar de "arreglar y seguir".

### 9.5 Engram

Se usó como traza de decisiones y progreso (fundación, ciclo 1, split C-01/C-02, cada change, esta auditoría). **No** conviene citar el número exacto de observaciones como métrica del proyecto: `mem_stats` es global y mezcla proyectos.

### 9.6 Reglas R1–R13: cumplimiento

| Regla | Estado real |
|---|---|
| R1 Pydantic sin ORM, `extra='forbid'` | Cumplida: schemas por dominio, sin ORM en responses |
| R2 type hints + ruff/mypy | Cumplida: `ruff` y `mypy` limpios (120 archivos) |
| R3 async end-to-end | Cumplida; deuda de engine por request (D-01) |
| R4 tenant desde JWT | **Cumplida**: `security.py:26,57`; tests de `?tenant_id=` que no amplía alcance |
| R5 sin `any`, TS estricto | Cumplida (`npm run build` con `tsc --noEmit`) |
| R6 datos clínicos fuera de localStorage | Cumplida: HC solo en memoria/API; `/privacidad` tampoco escribe storage |
| R7 no hard delete | **Parcial**: soft delete en catálogos/pacientes y auditoría append-only, pero la cascada desde `tenant` sigue abierta (R-01) |
| R8 montos en servidor + webhooks idempotentes | Cumplida: montos `Decimal` en servidor; MP idempotente por `mp_payment_id` |
| R9 sin PHI en logs/errores/URLs | Cumplida en lo verificable: enmascarado en exportaciones, nombres de archivo opacos; falta revisar snapshots de auditoría (D-05) |
| R10 commits convencionales + sin secretos | Mayormente cumplida: conviven prefijos convencionales y mensajes sueltos ("Continuacion"); no hay secretos versionados |
| R11 tests contra DB real | Cumplida en CI y en los changes con Postgres; **local cae a SQLite y hay 8 skips (7 de DB + 1 de stack Compose)** |
| R12 push por change | Cumplida al corte: `main` = `origin/main`; hubo períodos sin push, hoy saldados |
| R13 datos ficticios | Cumplida: fixtures sintéticos y seed de demo |

---

## 10. Discrepancias documentales (qué NO afirmar)

| # | Documento dice | Realidad |
|---|---|---|
| D-01 | `docs/defensa-oral-guia.md`: "auditoría del 2026-10-20", "17 changes", "24 tests: 22 passed + 2 skipped" | 19 changes en 20 archives, 687 passed / 2 failed / 8 skipped (`defensa-oral-guia.md:3,30,81,95`) |
| D-02 | ~~`CHANGES.md:42,85`: "C-14 sigue `[ ]` / pendiente"~~ | **Corregido el 2026-11-17**: las dos notas ahora aclaran que la deuda se saldó con C-14 archivado |
| D-03 | ~~C-14 `tasks.md:54,64`: existen `src/frontend/test/AuditoriaPage.test.tsx` y `PaginaLegal.test.tsx`~~ | **Corregido el 2026-11-17**: ambos archivos existen y la suite frontend pasó a 109 tests (ver R-10) |
| D-04 | La auditoría anterior: "C-02 0/11, implementación no iniciada" | C-02 archivado 2026-10-29 con 11/11 y 24 tests |
| D-05 | La auditoría anterior: "Docker no está instalado" | El CLI está (29.9.2); el daemon no responde |
| D-06 | La auditoría anterior: "no hay auth, pacientes, agenda, HC, caja, pagos ni reserva" | Todo eso está implementado y con tests |
| D-07 | Guion del video: "63 y 89 pruebas de Vitest" (C-16/C-17) | Son los cierres de esos changes; la suite total al corte es 90 |
| D-08 | `README.md:640` menciona 687/2/8 y 90 — correcto | Verificado; es la referencia de estado más confiable |
| D-09 | `docs/changes/` como copia completa de changes | Solo existe `docs/reviews/` y `docs/discovery/`; los changes viven en `openspec/changes/archive/` |
| D-10 | C-02 `design.md` histórico describe el layout viejo | Es un archive: vale como registro, no como estado actual |

**Regla de oro para la defensa:** si citás un número, que salga de esta auditoría o del repo (`git`, `pytest`, `openspec validate`), no de `defensa-oral-guia.md` ni de memoria.

**Estado del guion del video (verificado por extracción de texto del PDF, 17 páginas):** ya dice "veinte changes", menciona 687 tests de backend, 90 de frontend, "las veinte especificaciones" y `openspec validate --all`, y dice que lo que queda es "verificación, no desarrollo: tres comprobaciones que necesitan Docker". Está alineado en los números grandes, pero **no menciona los 2 fallos ambientales ni los 8 skips**, y su fuente editable no está versionada. No se puede diffear: es un binario.

**Nota de sincronización:** durante esta auditoría `docs/guion-video-TPI.pdf` cambió en el árbol de trabajo (460.215 → 515.820 bytes) por una actualización en paralelo, sin commit. La relectura al cierre confirma los mismos números (veinte changes, 687, 90, 20 specs, 3 verificaciones Docker); el PDF y este documento son los dos artefactos que hay que mantener sincronizados a mano.

---

## 11. Conclusión y próximos pasos

### 11.1 Lo que se puede defender con orgullo

1. **Método completo**: SDD con 20 archives, 20 specs válidas, 9 gates y camino crítico ejecutado de punta a punta.
2. **Producto entregado**: MVP (agenda, pacientes, HC/odontograma, caja/señas, MP, reserva pública) + pantallas internas + auditoría/exportación + demo Compose.
3. **Fundación**: KB de 11 documentos, discovery de 18 sistemas, R1–R13 y 21 skills versionadas.
4. **Calidad medida**: 687 tests de backend, 90 de frontend, lint/tipos/build limpios y `openspec validate` 20/20.
5. **Honestidad**: las 5 verificaciones que faltan y las deudas transversales están documentadas con comando y evidencia, no ocultas.

### 11.2 Lo que hay que cerrar para "terminar" de verdad

1. Levantar el daemon de Docker y correr las 3 verificaciones de C-14 (3.3, 10.1, 10.3) y las 2 de C-01 (3.3, 5.1).
2. Corregir R-01 con una migración aprobada: `ON DELETE RESTRICT` en `auditoria.tenant_id` + `REVOKE DELETE ON tenant` + baja lógica.
3. Sanear los 2 fallos ambientales (mock de WhatsApp; `_env_file=None` en el test de settings) para que `pytest` local dé verde.
4. Agregar la cobertura de frontend que C-14 declara (pantalla de auditoría y `/privacidad`).
5. Actualizar `docs/defensa-oral-guia.md` y quitar las dos notas vencidas de `CHANGES.md`.
6. Resolver las consultas al PO: exportación parcial por rol (R-08), padrón completo de pacientes (R-09) y retención legal (R-06/PO-03).

### 11.3 Deuda estructural para después

- Object storage para exportaciones multi-nodo.
- Auditoría de lecturas de HC.
- Índices de auditoría por fecha/actor cuando el volumen lo pida.
- Engine singleton con `dispose` en shutdown.
- Validación de configuración en lifespan.
- Endurecer CI: imágenes, `compose up`, e2e y downgrade.
- RLS como defensa en profundidad.

---

## Anexo A — Comandos útiles para verificar en vivo

```bash
# Estado de changes y specs
openspec list
openspec validate --all --strict
Get-ChildItem openspec/changes/archive -Directory | Measure-Object   # 20

# Gates backend (desde la raíz)
python -m pytest tests -q
ruff check --config src/backend/pyproject.toml src/backend tests
ruff format --check --config src/backend/pyproject.toml src/backend tests
mypy --config-file src/backend/pyproject.toml src/backend

# Gates frontend
cd src/frontend
npm run test:run
npm run build

# Git
git log --date=short --pretty=format:"%h %ad %s" -20
git status -sb
git ls-remote origin main

# Stack (requiere daemon de Docker)
docker compose up --build -d
docker compose --profile tools run --rm migrar
docker compose exec -e DEMO_PASSWORD=... api python -m app.scripts.usuario_demo
curl http://localhost:8000/api/health
curl http://localhost:8080/privacidad

# Tareas bloqueadas de C-14 (con daemon arriba)
docker compose up -d db redis && python -m pytest tests/test_auditoria_appendonly.py
docker compose up -d db redis && python -m pytest tests
docker compose up --build
```

## Anexo B — Estructura del repo

```text
turnos-odontologia/
├── .agents/                 # 21 skills + registry canónico
├── .atl/                    # shim del registry
├── .github/workflows/ci.yml # backend + frontend + openspec strict
├── db/init/                 # roles de PostgreSQL
├── discovery/               # investigación de mercado
├── docs/
│   ├── auditoria-proyecto.md        ← este documento
│   ├── defensa-oral-guia.md         ← guía vieja (2026-10-20), a actualizar
│   ├── guion-video-TPI.pdf          ← guion del video (binario)
│   ├── mcp-skills.pdf / test.pdf
│   ├── guia_swagger_ui_openapi.html
│   ├── discovery/informe-discovery.md
│   └── reviews/2026-11-04-c-13-*.md
├── knowledge-base/          # 11 docs + README
├── openspec/
│   ├── config.yaml
│   ├── specs/               # 20 specs main
│   └── changes/archive/     # 20 archives (0 activos)
├── src/
│   ├── backend/             # app (api/domain/application/infrastructure/shared/workers/scripts), alembic 001..013
│   └── frontend/            # React 18 + Vite + PWA, 17 archivos *Page.tsx, 18 archivos de test
├── tests/                   # 90 archivos test_*.py
├── CHANGES.md               # roadmap de 19 changes (20 archives)
├── AGENTS.md / CLAUDE.md    # reglas R1–R13
├── mcp_server.py / .mcp.json
├── docker-compose.yml       # 7 servicios + volúmenes pgdata y exportaciones
├── .env.example
└── README.md
```
