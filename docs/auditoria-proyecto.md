# Auditoría integral — Turnos Odontología

**Fecha de corte:** 2026-10-20
**Commit auditado:** `ac56510` (main = origin/main, sin cambios sin commitear)
**Alcance:** estado real del repositorio, cronología de sesiones, fases SDD/OPSX, changes, roadmap, calidad, riesgos y brechas documentales.
**Método:** lectura de código y artefactos + ejecución de gates + contraste con git, OpenSpec y Engram. Todo hallazgo tiene evidencia. Lo que no se pudo verificar se marca explícitamente.

---

## 0. Veredicto en 10 líneas

1. El proyecto tiene **fundación metodológica completa y verificable**: Discovery, Knowledge Base, roadmap de 17 changes, skills versionadas, governance y reglas duras.
2. El **Ciclo 1 de implementación existió y se archivó**: FastAPI mínima, 3 modelos multi-tenant, migración Alembic reversible, seed idempotente, repositorio con aislamiento, PWA base, Docker Compose, CI y 24 tests.
3. Ese ciclo se archivó como `2026-10-03-c-01-foundation-core-models` cubriendo **C-01 + C-02 juntos**, con 10/14 tasks.
4. El 2026-10-15 se detectó que el layout `src/` estaba mal y se separó: `c-01-solo-setup` (refactor puro) se archivó con **11/13**.
5. **C-02 está planificado y validado, pero 0/11 tasks ejecutadas.** No hay que presentarlo como terminado.
6. Lo implementado es un **esqueleto vertical de fundación**, no el producto: no hay auth, pacientes, agenda, HC, odontograma, caja, pagos ni reserva pública.
7. Gates locales en verde: **22 passed, 2 skipped, 0 failed**, `ruff`, `ruff format --check`, `mypy`, `tsc --noEmit` y `vite build`.
8. Los 2 skips son los tests de auditoría append-only que requieren PostgreSQL real + rol restringido; **Docker no está instalado en esta máquina**.
9. Hay riesgos reales que hay que reconocer: **la auditoría puede borrarse en cascada desde `tenant`**, la app no valida configuración al arrancar, no hay JWT/RBAC todavía y el frontend no está desplegado end-to-end.
10. La documentación de estado (`README`, `CHANGES.md`, `design.md` de C-02, PDF) está **desactualizada en varios puntos**. La defensa debe apoyarse en el estado real, no en esos documentos.

---

## 1. El proyecto en una página

### 1.1 Qué es

SaaS multi-tenant para gestión de consultorios odontológicos en Argentina/Uruguay. Cubre agenda, pacientes, historia clínica y odontograma, presupuestos, caja y señas, obras sociales, cobros por Mercado Pago y comunicación por WhatsApp, con una PWA pública para que el paciente reserve 24/7.

**Alcance v1:** agenda + pacientes + HC/odontograma + caja/señas + Mercado Pago + reserva pública + mensajería + obras sociales + auditoría/exportación.
**Fuera de alcance v1:** app nativa, AFIP nativa, facturación fiscal, push notifications, múltiples sucursales avanzadas, IA clínica.

### 1.2 Actores y RBAC

| Rol | Alcance |
|---|---|
| Dueño | Administración total del consultorio, configuración, usuarios, reportes |
| Recepción | Agenda, pacientes, caja; **no** edita historia clínica |
| Odontólogo | Agenda propia, HC, odontograma, presupuestos |
| Paciente | Reserva pública, sus turnos; sin acceso al back-office |

La matriz RBAC vive en `knowledge-base/03_actores_y_roles.md`. En código **todavía no está enforceada** (C-03).

### 1.3 Modelo de datos

18 entidades documentadas en `knowledge-base/04_modelo_de_datos.md`. Implementadas hoy: **3** (`tenant`, `usuario`, `auditoria`). Todas las tablas de negocio llevan `tenant_id`; el `tenant` es la raíz y no lo lleva.

### 1.4 Stack real (versiones verificadas)

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | Python / FastAPI | 3.12.10 / 0.111.0 |
| ORM | SQLAlchemy async | 2.0.54 |
| Validación | Pydantic / pydantic-settings | 2.13.5 / 2.15.0 |
| Migraciones | Alembic | 1.13.2 |
| DB | PostgreSQL | 15.10 |
| Cola/caché | Redis | 7.4.1 |
| Frontend | React / TypeScript / Vite | 18.3.1 / 5.6.3 / 5.4.9 |
| Datos front | TanStack Query / React Router | 5.59.20 / 6.26.2 |
| Estilos | Tailwind CSS | 3.4.13 |
| PWA | vite-plugin-pwa | 0.20.5 |
| Infra | Docker Compose | db, redis, api, worker, migrar, mailhog |
| CI | GitHub Actions | backend + frontend en paralelo |

### 1.5 Arquitectura real

```text
Navegador
   │  (dev: proxy Vite / prod: pendiente)
   ▼
React SPA ──► GET /api/health
   │
   ▼
FastAPI (monolito modular)
   ├── api/          routers + schemas Pydantic + deps
   ├── domain/       modelos SQLAlchemy (Tenant, Usuario, Auditoria)
   ├── application/  VACÍA (casos de uso pendientes)
   ├── infrastructure/db/  BaseRepository + UnitOfWork
   ├── infrastructure/seed.py
   ├── shared/       settings, logging, exceptions, database
   └── workers/      esqueleto Redis (sin jobs)
   │
   ├──► PostgreSQL 15 (3 tablas)
   └──► Redis 7 (health + esqueleto)
```

**Lectura honesta:** es una arquitectura objetivo bien documentada con **solo el primer segmento vertical implementado**. `application/` está vacía y ningún endpoint usa todavía repositorio/UoW.

---

## 2. Cronología: qué se hizo en cada sesión

> Engram no guarda transcripciones literales; guarda observaciones con timestamp. La cronología se reconstruye con git + artefactos + observaciones. Hay 5 bloques operativos de trabajo y esta auditoría como sexto.

### Sesión 1 — 2026-10-01: Discovery / investigación

**Objetivo:** entender el mercado antes de definir el producto.

**Qué se hizo**
- Relevamiento de **18 sistemas** de gestión odontológica y turnos.
- 5 casos de uso principales, 5 preguntas abiertas, análisis de funcionalidades y precios.
- Documento `discovery/discovery.md` con fuentes y fecha de extracción.

**Por qué importa en la defensa:** justifica que el alcance no se inventó; surge de evidencia de mercado. También explica por qué el producto se diferencia en reserva pública + seña + WhatsApp + multi-tenant.

**Evidencia:** `discovery/discovery.md` (`sources_fetched_at: 2026-10-01`), `.active-orchestrator-state.json`.

---

### Sesión 2 — 2026-10-02: Fundación metodológica

**Objetivo:** convertir el discovery en una base ejecutable por agentes.

**Qué se hizo**
1. `openspec init` y estructura de changes.
2. **Knowledge Base** de 11 documentos + README (`knowledge-base/`): visión, descripción, actores, modelo de datos, reglas de negocio, funcionalidades, flujos, arquitectura, decisiones, preguntas abiertas, pagos MP.
3. **Roadmap** `CHANGES.md`: 17 changes, dependencias, 9 gates, camino crítico de 9, plan de 3 agentes.
4. **Skills:** 14 recomendadas e instaladas; registry con compact rules.
5. **Instrucciones de agente** (`AGENTS.md` + `CLAUDE.md`) con 13 reglas duras R1–R13.
6. Push inicial `48bf10c` (31 archivos) + README `b71193f`.

**Decisiones clave**
- Monolito modular FastAPI + SPA desacoplada (DD-02), no microservicios.
- Multi-tenant lógico desde el día 1 (DD-07), RLS opcional a futuro.
- PWA, no app nativa (DD-01).
- JWT access corto + refresh rotativo (DD-03), a implementar en C-03.
- Redis + outbox + idempotencia para mensajería y pagos (DD-06).

**Evidencia:** `48bf10c`, `knowledge-base/`, `CHANGES.md`, `.agents/skill-registry.md`, `.active-orchestrator-state.json`.

**Deuda:** la inicialización de OpenSpec no tiene commit propio; el primer commit ya contiene todo. La fase `init` no es auditable por separado.

---

### Sesión 3 — 2026-10-03: Reglas de agente + Ciclo OPSX 1 + entregables

**Objetivo:** ejecutar el primer ciclo completo de implementación y cerrar entregables del TP.

**Qué se hizo**

*Mañana:*
- `AGENTS.md`/`CLAUDE.md` (`072e380`) con stack, skills por agente, roadmap y reglas R1–R13.

*Tarde: Ciclo 1 completo*
| Fase | Resultado |
|---|---|
| Explore | Se decide cubrir **C-01 + C-02 juntos** para tener reglas verificables desde el inicio |
| Propose | 4/4 artefactos; 18 escenarios (7 foundation + 11 core); 14 tasks |
| Apply | 10/14: FastAPI, modelos, repo, UoW, migración 001, seed, PWA, Compose, CI |
| Verify | 22 passed + 2 skipped; se agregan 5 tests de cobertura; ruff/mypy/tsc/build verdes |
| Archive | `2026-10-03-c-01-foundation-core-models`; 2 specs sincronizadas; validate 2/2 |
| Push | `09cd116` (78 archivos) |

*Cierre del TP:*
- Reordenamiento del repo a `src/`, `tests/`, `docs/` (`fca9bd0`).
- Informe de Discovery de 256 líneas, 18 sistemas, 8 secciones (`f202e2f`).
- Plantilla de reflexión (`9dca044`).

**Decisiones clave**
- Posponer RLS; aislamiento por `BaseRepository` + GRANT de auditoría (D3/D4).
- `tenant_id` obligatorio y falla cerrado si falta.
- Auditoría append-only por permisos de DB, no por trigger.
- Seed sintético idempotente.

**Deuda generada**
- 4 tasks sin cerrar (Compose up, GRANT real, CI verde, verificación integral).
- La suite local cae a SQLite si no hay `DATABASE_URL_TEST` (tensión con R11).
- El commit `09cd116` mezcla implementación y tests: no hay trazabilidad RED/GREEN.

**Evidencia:** `09cd116`, `fca9bd0`, `f202e2f`, `9dca044`, archives y specs.

---

### Sesión 4 — 2026-10-14: Reflexión, video y guion de defensa

**Objetivo:** cerrar entregables académicos.

**Qué se hizo**
- `reflexion.md` completado (por otra integrante, `sabrinagimenez98`) y corregido (`c029acd`, `fd8d371`).
- Video presentación agregado al README (`e21495e`, `e86b099`).
- Guion de defensa de 15 minutos para 4 integrantes (3+4+4+4) exportado a PDF.

**Deuda**
- El guion fuente `.md` no está versionado; solo el PDF.
- El PDF quedó desactualizado en varios datos (registry, reflexión, métricas de Engram, tasks).
- `reflexion.md` narra un change de agenda (C-06), no el ciclo 1 real.

**Evidencia:** commits del 2026-10-14, `reflexion.md`, `docs/guion-defensa-adaptado.pdf`.

---

### Sesión 5 — 2026-10-15: Reauditoría y split C-01/C-02

**Objetivo:** corregir el layout y separar responsabilidades.

**Problema detectado**
- `src/` estaba plano-mezclado: backend y frontend en la misma raíz, con `src/src/` anidado.
- C-01 y C-02 estaban fusionados; 2.4 (GRANT de auditoría) es CRÍTICO y no debía vivir en un change BAJO.

**Qué se hizo**
1. `c-01-solo-setup`: refactor puro de layout `backend/` + `frontend/` → `src/backend/` + `src/frontend/`, con `git mv` (historia preservada), rewiring de pytest/conftest/pyproject/compose/CI y `skip_specs: true`.
2. `c-02-modelos-core`: gap-closure para cerrar 2.4 y verificar paridad post-move. Delta de 8 escenarios (5 de auditoría + 3 de paridad).
3. Apply de C-01: 11/13; bloqueadas 3.3 y 5.1 por falta de Docker.
4. Archive de C-01 (`2026-10-15-c-01-solo-setup`, validate 3/3).
5. Push `6196a3a` (262 archivos) + merge `ac56510`.

**Resultado**
- Layout correcto y árbol de dependencias restaurado.
- **C-02 quedó propuesto y sin aplicar (0/11).**

**Deuda**
- El design prometía commits separados; la historia muestra un único commit de 262 archivos.
- `CHANGES.md` marca C-01 `[x]` con 3.3/5.1 abiertas.
- El `design.md` de C-02 sigue describiendo el layout viejo y bloqueos ya vencidos.

**Evidencia:** `6196a3a`, `ac56510`, archives, `openspec status`.

---

### Sesión 6 — 2026-10-20: Auditoría integral (esta sesión)

**Objetivo:** reconstruir el estado real y preparar la defensa oral.

**Qué se hizo**
- Auditoría de backend, tests, migración y DB.
- Auditoría de frontend, Docker, CI y configuración.
- Reconstrucción documental de sesiones, fases y changes.
- Ejecución de gates: pytest, ruff, mypy, tsc, build, Alembic sobre SQLite.
- Este documento + guía de defensa.

**Resultado**
- Estado real medido, riesgos priorizados y brechas documentales identificadas.

---

## 3. Fases SDD/OPSX: qué son y cómo se aplicaron

### 3.1 Qué es SDD (Spec-Driven Development)

En SDD, **la especificación es la fuente de verdad**, no el código. El flujo es:

```text
idea → explorar → proponer (spec + diseño + tasks) → implementar → verificar → archivar
```

Cada cambio produce artefactos revisables antes de escribir código. La ventaja: el agente no improvisa; ejecuta un contrato. La desventaja: si los artefactos se desactualizan, la "fuente de verdad" miente. Eso pasó parcialmente acá.

### 3.2 OpenSpec / OPSX

OpenSpec es la herramienta que materializa SDD en el repo. OPSX es el workflow fluido (sin gates rígidos) que usa:

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

**Importante para la defensa:** `openspec status` puede decir `isComplete: true` refiriéndose a **artefactos de planificación**, no a implementación. El progreso real se lee con `openspec instructions apply`. En C-02 eso da **0/11**.

### 3.3 El flujo de fundación usado

Antes del primer change se ejecutó el flujo de fundación (skill `active-orchestrator`):

```text
openspec init → discovery → kb-creator → roadmap-generator
→ find-skill → skill-registry → agent-instruction
```

| Fase | Producto | Evidencia |
|---|---|---|
| Discovery | `discovery/discovery.md` | 18 sistemas, fuentes 2026-10-01 |
| KB | 11 docs + README | `knowledge-base/` |
| Roadmap | 17 changes, gates, camino crítico | `CHANGES.md` |
| Find-skill | 14 skills | state `skills.installed` |
| Registry | Compact rules por change | `.agents/skill-registry.md` |
| Agent-instruction | `AGENTS.md` + `CLAUDE.md`, R1–R13 | `072e380` |

### 3.4 El ciclo aplicado al change

| Fase | Qué produce | Evidencia en este repo | Estado |
|---|---|---|---|
| Explore | Entendimiento y alcance; sin código | Observaciones Engram #13, #54 | Hecho |
| Propose | Proposal + design + specs + tasks | `openspec/changes/...` | Hecho |
| Apply | Código + tests por task | Commits `09cd116`, `6196a3a` | Parcial |
| Verify | Gates y cobertura de escenarios | 22 passed + 2 skipped; ruff/mypy/tsc | Parcial |
| Archive | Sync de specs + cierre | 2 archives | Hecho |

### 3.5 Evaluación honesta del método

**Fortalezas**
- Alcance trazable: cada change tiene propuesta, escenarios y tasks.
- Governance explícito: lo CRÍTICO se separa de lo BAJO.
- Calidad automatizada: gates reales, no declarativos.
- Memoria persistente: decisiones y sesiones quedan en Engram.

**Debilidades**
- Los artefactos de C-02 no se actualizaron tras el move → describen un estado inexistente.
- El `[x]` de C-01 convive con verificaciones abiertas.
- TDD estricto no está evidenciado en la secuencia de commits.
- La documentación de estado (README/PDF) se desincronizó del repo.

---

## 4. Los changes, uno por uno

### 4.1 C-01 original — `2026-10-03-c-01-foundation-core-models`

**Objetivo:** fundación técnica + modelos core en un solo ciclo.
**Alcance:** scaffolding, FastAPI, settings, logging, errores, SQLAlchemy/Alembic, 3 modelos, repo/UoW, seed, PWA, Compose, CI.
**Specs:** `foundation-setup` (7 escenarios) + `core-models-multitenant` (11 escenarios) = **18**.
**Tasks:** 10/14.
**Pendientes:** 1.4 Compose up + health; 2.4 GRANT de auditoría en Postgres real; 4.2 CI verde; 4.3 verificación integral.
**Resultado:** archivado, 2 specs sincronizadas, validate 2/2.
**Lectura:** es el cambio más grande y el que más código dejó. Su deuda es de verificación, no de diseño.

### 4.2 C-01 `solo-setup` — `2026-10-15-c-01-solo-setup`

**Objetivo:** corregir layout sin cambiar comportamiento.
**Alcance:** `git mv` a `src/backend` + `src/frontend`; rewiring de 6 paths en CI, pytest, compose y pyproject.
**Specs:** ninguna (`skip_specs: true`) porque es refactor puro.
**Tasks:** 11/13; pendientes 3.3 (migración reversible en contenedor) y 5.1 (stack limpio + health).
**Resultado:** archivado, validate 3/3.
**Lectura:** cierra la deuda estructural, no la de verificación.

### 4.3 C-02 `core-models-multitenant` — activo

**Objetivo:** gap-closure. Cerrar 2.4 (GRANT de auditoría) y verificar paridad post-move.
**Alcance:** 3 grupos de tasks:
1. Aislamiento multi-tenant + constraints contra Postgres real.
2. GRANT de auditoría: diagnóstico → propuesta de SQL → aprobación humana → test TDD → reversibilidad.
3. Migración + seed + gates R1/R2/R9 + paridad post-move.
**Delta spec:** 8 escenarios (5 de auditoría + 3 de paridad).
**Tasks:** **0/11**.
**Estado:** planificación completa y validada; implementación no iniciada.
**Bloqueos:** Docker/Postgres no disponible localmente; tasks 5.x marcadas como bloqueadas por C-01 aunque C-01 ya se archivó.
**Lectura:** no es un change de features nuevas; es un change de **cierre de verificación**. No inflarlo.

### 4.4 C-03 en adelante

No iniciados. **C-03 `auth-rbac-tokens`** es el próximo crítico: habilita R4 (tenant desde JWT), RBAC y todos los endpoints de negocio. Sin C-03 no se puede avanzar a C-04/C-05.

---

## 5. Roadmap completo

### 5.1 Las 7 fases y los 9 gates

```text
GATE 0: C-01
GATE 1: C-02
GATE 2: C-03  ← desbloquea todo
GATE 3: C-04 + C-05 (paralelo)
GATE 4: C-06 (une ambas ramas)
GATE 5: C-07 + C-08 + C-09 + C-11 (4 paralelos)
GATE 6: C-10 + C-12 + C-13 (3 paralelos)
GATE 7: C-14 + C-15 + C-16 (3 paralelos)
GATE 8: C-17
```

### 5.2 Camino crítico (9 changes)

```text
C-01 → C-02 → C-03 → C-05 → C-06 → C-09 → C-11 → C-12 → C-15
```

**Por qué termina en C-15:** el corte del MVP es que el paciente pueda reservar online y pagar la seña por Mercado Pago. Sin C-15 no hay captura 24/7; sin C-12 no hay seña. C-16 y C-17 completan la operación interna pero no el corte mínimo.

### 5.3 Los 17 changes

| # | Change | Fase | Governance | Depende de | Estado |
|---|---|---|---|---|---|
| C-01 | foundation-setup | 0 | BAJO | — | Archivado con deuda |
| C-02 | core-models-multitenant | 0 | CRÍTICO | C-01 | Activo 0/11 |
| C-03 | auth-rbac-tokens | 1 | CRÍTICO | C-02 | Pendiente |
| C-04 | catalogo-configuracion | 2 | BAJO | C-03 | Pendiente |
| C-05 | pacientes | 2 | BAJO | C-03 | Pendiente |
| C-06 | agenda-turnos | 2 | CRÍTICO | C-04, C-05 | Pendiente |
| C-07 | lista-espera | 3 | MEDIO | C-06 | Pendiente |
| C-08 | comunicaciones-mensajeria | 3 | ALTO | C-06 | Pendiente |
| C-09 | historia-clinica-odontograma | 3 | CRÍTICO | C-05, C-06 | Pendiente |
| C-10 | presupuestos-planes | 3 | MEDIO | C-04, C-06, C-09 | Pendiente |
| C-11 | caja-senas | 4 | CRÍTICO | C-06 | Pendiente |
| C-12 | mercadopago-webhooks | 4 | CRÍTICO | C-11 | Pendiente |
| C-13 | obras-sociales-liquidacion | 4 | MEDIO | C-04, C-06 | Pendiente |
| C-14 | auditoria-exportacion | 5 | CRÍTICO | C-11, C-13 | Pendiente |
| C-15 | reserva-publica-pwa | 6 | MEDIO | C-09, C-12 | Pendiente |
| C-16 | frontend-agenda-clinica | 6 | MEDIO | C-08, C-10 | Pendiente |
| C-17 | frontend-caja-os-admin | 6 | MEDIO | C-13, C-14 | Pendiente |

**Distribución:** 3 BAJO, 7 CRÍTICO, 1 ALTO, 6 MEDIO.
**Agentes:** A = Backend Core; B = Backend Aux; C = Dinero + Frontend.

### 5.4 Por qué este orden

- Primero **identidad y aislamiento** (C-01/02/03): sin tenant y auth no hay negocio seguro.
- Luego **datos maestros en paralelo** (C-04 catálogo, C-05 pacientes).
- Después **agenda** (C-06), que es el corazón operativo y depende de ambos.
- En el fork grande, **clínica y caja** avanzan en paralelo porque son dominios distintos.
- Pagos (C-12) depende de caja (C-11) porque la seña nace de un cobro.
- La reserva pública (C-15) va al final porque integra HC + pagos + PWA.

---

## 6. Qué está implementado vs. qué no

### 6.1 Matriz de estado real

| Área | Implementado | Evidencia | Brecha |
|---|---|---|---|
| Health check | `GET /api/health` 200/503 con DB+Redis | `api/routers/health.py` | Sin timeout DB; engine por request; no valida esquema |
| Configuración | Pydantic Settings, `.env.example` con placeholders | `shared/settings.py` | No valida al arrancar; `JWT_SECRET` sin mínimo |
| Logging | Logger a stdout, sin PHI explícita | `shared/logging.py` | Sin redacción automática ni request ID |
| Errores | `AppError`, 500 genérico, mensajes rioplatenses | `shared/exceptions.py` | No loguea el 500; integrity errors sin cablear |
| Modelos | Tenant, Usuario, Auditoria | `domain/*.py` | `rol` sin CHECK/ENUM; `actor_id` sin FK; sin relaciones |
| Multi-tenant | `TenantMixin` + `BaseRepository` falla cerrado | `mixins.py`, `repository.py` | Sin RLS; depende de disciplina de uso; sin JWT |
| UoW | Commit/rollback + repos por tenant | `unit_of_work.py` | Sin transacción explícita, savepoints ni retry |
| Auditoría | Tabla + GRANT SELECT/INSERT + tests | `auditoria.py`, migración 001 | **Cascade desde tenant**; sin helper de registro; sin tamper-evidence |
| Migración | 001 reversible (SQLite verificada) | `alembic/versions/001...` | GRANTs no verificados en Postgres |
| Seed | Idempotente secuencial, datos ficticios | `infrastructure/seed.py` | No concurrente; password descartada; permisos no persistidos |
| API negocio | **Nada** | — | Sin auth, tenant, usuario, pacientes, agenda, HC, caja, pagos |
| Frontend | Ruta `/` + estado de API; PWA base | `main.tsx`, `ApiStatus.tsx` | Sin login, dashboard ni pantallas de negocio |
| PWA | Manifest + SW + iconos 192/512 | `vite.config.ts` | `lang:en`, iconos placeholder, sin offline real |
| Docker | Compose con 6 servicios + Dockerfiles multi-stage | `docker-compose.yml` | Frontend fuera de compose; sin proxy `/api`; sin HTTPS |
| CI | Backend con Postgres/Redis real + frontend build | `.github/workflows/ci.yml` | Sin Docker, e2e, frontend tests, downgrade, cobertura |
| Tests | 24 colectados: 22 pass, 2 skip | `tests/` | 2 skips de auditoría; 5 tests son estáticos |
| Docs | KB, discovery, roadmap, 2 archives, specs | `knowledge-base/`, `openspec/` | README/CHANGES/PDF desactualizados |

### 6.2 Qué puede hacer el sistema hoy (demo real)

1. Levantar API, DB, Redis, worker y Mailhog con Compose.
2. Ejecutar migración 001 y seed.
3. Responder `GET /api/health` con estado de DB y Redis.
4. Servir una PWA mínima que muestra si la API está conectada.
5. Pasar 22 tests locales y los gates de lint/tipos/build.
6. Ejecutar `alembic upgrade/downgrade` sobre SQLite.
7. **Nada más.** No hay login, ni pacientes, ni turnos.

---

## 7. Evidencia de calidad

### 7.1 Gates ejecutados en esta auditoría

| Gate | Resultado | Exit |
|---|---|---|
| `pytest -q` | 22 passed, 2 skipped, 0 failed | 0 |
| `pytest` desde `src/backend` | 22 passed, 2 skipped | 0 |
| `ruff check` | All checks passed | 0 |
| `ruff format --check` | 38 files already formatted | 0 |
| `mypy` | Success: 29 source files | 0 |
| `tsc --noEmit` | Sin errores | 0 |
| `npm run build` | 81 módulos; JS 239.95 kB (77.31 gzip); CSS 5.50 kB | 0 |
| `alembic upgrade head` (SQLite) | Tablas + índices creados | 0 |
| `alembic downgrade base` (SQLite) | Solo `alembic_version` | 0 |
| `docker --version` | **No instalado** | N/A |

### 7.2 Inventario de tests

| Archivo | Tests | Qué cubre |
|---|---|---|
| `test_auditoria_appendonly.py` | 3 | INSERT deja rastro; UPDATE/DELETE rechazados (2 skip sin Postgres) |
| `test_core_models.py` | 5 | Alta feliz, email duplicado mismo tenant, mismo email otro tenant, matrícula, slug duplicado |
| `test_repository_isolation.py` | 3 | A no ve B, falta tenant falla, tenant ajeno rechazado |
| `test_seed.py` | 2 | Seed en base vacía, doble ejecución no duplica |
| `test_health.py` | 3 | 200 OK, DB caída 503, Redis caído 503 (con mocks) |
| `test_settings.py` | 3 | Falta JWT falla, mínimos construyen, `.env.example` sin secretos |
| `test_cobertura_verify.py` | 5 | 3 son checks estáticos de archivos (PWA, shell, CI) |

### 7.3 Lo que el CI sí y no prueba

**Sí:** lint, formato, tipos, migración 001, pytest contra PostgreSQL/Redis reales, build frontend, rol restringido para append-only.

**No:** build de imágenes, `compose up`, nginx, proxy `/api`, CORS, tests de frontend, e2e, accesibilidad, downgrade, `alembic check`, worker, Mailhog, health real, cobertura, seguridad, deploy.

**Conclusión:** CI verde es necesario pero **no garantiza que el stack despliegue**.

### 7.4 Evaluación de TDD

**A favor:** 24 tests para 18 escenarios; casos borde reales (mismo email en otro tenant, tenant ajeno, doble seed); tests de DB y de schema.

**En contra:** no hay commits RED; el commit principal mezcla código y tests; los 5 tests de `test_cobertura_verify` se agregaron en Verify (test-after); 3 de esos 5 son checks de strings; la suite local usa SQLite por fallback.

**Frase honesta para la defensa:** "Aplicamos TDD como disciplina de cobertura y casos borde, pero la historia de commits no evidencia la secuencia rojo-verde. Es una de las cosas que mejoraríamos."

---

## 8. Hallazgos priorizados

### 8.1 CRITICAL

#### A-01. La auditoría append-only se puede borrar en cascada desde `tenant`

- `GRANT DELETE ON tenant TO turnos_app` (migración 001, línea 91).
- `auditoria.tenant_id` FK `ON DELETE CASCADE` (línea 72).
- El rol app no tiene DELETE directo sobre `auditoria`, pero un `DELETE FROM tenant` dispara la cascada.
- **Impacto:** se destruye el trail que la ley y RN-SE-01 exigen conservar 5 años.
- **Respuesta de defensa:** reconocerlo como el hallazgo más grave, explicar que el fix es `ON DELETE RESTRICT` + revocar DELETE + desactivación lógica, y que C-02 lo tiene en alcance (2.1–2.3).

### 8.2 HIGH

| ID | Hallazgo | Evidencia | Respuesta esperada |
|---|---|---|---|
| A-02 | La app no falla al arrancar sin config requerida; el primer request da 500 opaco | `main.py` no instancia Settings; probe real 500 | "Falta lifespan de validación; está en la deuda de C-01" |
| A-03 | No hay auth/JWT/RBAC; el `tenant_id` no viene del token | No hay router auth; repo recibe tenant por parámetro | "R4 se implementa en C-03; hoy no hay endpoints de negocio expuestos" |
| A-04 | Aislamiento multi-tenant solo de aplicación; sin RLS | `repository.py`; sin RLS en migración | "Decisión DD-07: RLS opcional a futuro; el guard falla cerrado, pero depende de usar el repo" |
| A-05 | `deps.sesion_db` crea engine/pool por request sin `dispose` | `deps.py`, `database.py` | "Debe ser singleton por proceso con dispose en shutdown" |
| A-06 | `docker compose up` no migra y el health da 200 sin tablas | `migrar` en perfil tools; health solo `SELECT 1` | "Es una trampa operativa; el fix es migración one-shot con `service_completed_successfully`" |
| A-07 | `rol` es `String(20)` sin CHECK/ENUM y se lee como `str` | `usuario.py`, migración | "El tipado promete enum y el runtime no lo entrega; hay que agregar constraint/TypeDecorator" |
| A-08 | Frontend no desplegable end-to-end: sin servicio en Compose, nginx sin proxy `/api`, sin CORS | `docker-compose.yml`, `nginx.conf`, `main.py` | "Dev funciona por proxy de Vite; prod requiere proxy o CORS + `VITE_API_URL`" |
| A-09 | Puertos 5432/6379/1025/8025 expuestos, Redis y Mailhog sin auth, sin TLS | `docker-compose.yml` | "Es local-first; no debe exponerse a Internet sin TLS, auth y bind a 127.0.0.1" |
| A-10 | Sin tests de frontend ni lint; CI no valida Docker | `package.json`, `ci.yml` | "El TDD se aplicó al backend; el frontend es deuda declarada" |

### 8.3 MEDIUM (selección)

| ID | Hallazgo |
|---|---|
| M-01 | "Matriz de permisos" solo es un dict Python; no se persiste ni se enforce |
| M-02 | Seed usa rol app, commitea internamente, password aleatoria descartada, no concurrente |
| M-03 | `.env.example` usa `usuario_app` pero el rol real es `turnos_app`; `APP_DB_ROLE` desalineado |
| M-04 | Índices duplicados (`slug unique` + `ix_tenant_slug`; unique compuesto + índice) |
| M-05 | `actor_id` sin FK; `entidad_id` con formato inconsistente; sin tamper-evidence |
| M-06 | Soft delete no implementado; DELETE permitido a nivel DB |
| M-07 | Cobertura insuficiente: append-only local, cascade, rollback UoW, seed concurrente, `alembic check` |
| M-08 | Health sin timeout DB y engine por request |
| M-09 | `JWT_SECRET` sin `SecretStr` ni longitud mínima |
| M-10 | Sin redacción de PHI ni logging de excepciones inesperadas |
| M-11 | `application/` vacía; dominio importa infraestructura (inversión de dependencias) |
| M-12 | Test de settings con tautología `or True` y dependencia de ausencia de `.env` |
| M-13 | PWA con `lang:en`, iconos placeholder, sin offline real |
| M-14 | Flujo local documentado roto (Alembic no carga `.env`, host `db` fuera de Compose) |
| M-15 | Healthcheck del backend acepta 503 como sano |
| M-16 | Redis sin persistencia ni password; Mailhog sin perfil dev |
| M-17 | CI sin `permissions`, `concurrency`, `timeout`, paths, cache pip, matrix |

---

## 9. Método de trabajo: agentes, skills, governance y memoria

### 9.1 Active Stack + OpenCode + OpenSpec

El proyecto usa tres capas:
- **OpenCode** como runtime de agentes.
- **Active Stack** como metodología (orquestador + subagentes + skills + governance).
- **OpenSpec** como sistema de artefactos y estado.

### 9.2 Roles de agente

`AGENTS.md` define 7 roles: Backend Core, Backend Aux, Frontend, Clínico, Infra, Diagnóstico y Calidad. Cada uno tiene skills asignadas. El orquestador delega y no implementa.

### 9.3 Skills y registry

- 14 skills versionadas en `.agents/skills/`.
- Registry canónico: `.agents/skill-registry.md` (`.atl/skill-registry.md` es un shim).
- Tabla Change → Skills, por ejemplo:
  - C-01: `multi-stage-dockerfile`, `python-fastapi-development`, `tdd`, `code-review`.
  - C-02: `supabase-postgres-best-practices`, `python-fastapi-development`, `tdd`.
  - C-03: `auth-implementation-patterns`, `python-fastapi-development`, `supabase-postgres-best-practices`, `tdd`, `code-review`.
  - C-09: `healthcare-emr-patterns`, `hipaa-compliance`, `frontend-design`, `supabase-postgres-best-practices`, `tdd`.
  - C-12: `stripe-integration` (plantilla), `clerk-webhooks` (patrón), `upstash-redis-js`, `tdd`, `code-review`.

**Límite honesto:** no hay telemetría de invocación por skill; el uso está documentado y planificado, no probado skill por skill.

### 9.4 Governance por dominio

| Nivel | Dominios | Comportamiento |
|---|---|---|
| CRÍTICO | Auth, pagos, salud, auditoría | Análisis primero; sin escritura sin aprobación humana |
| ALTO | Config sensible, backups | Proponer y esperar revisión |
| MEDIO | Lógica de negocio, adaptadores | Implementar con checkpoints |
| BAJO | CRUDs, catálogos, layout | Autonomía si los tests pasan |

**Evidencia clara:** 2.4 (GRANT de auditoría) se sacó de C-01 (BAJO) y se movió a C-02 (CRÍTICO), con la regla de proponer el SQL y esperar aprobación antes de escribirlo.

### 9.5 Engram

Se usó como traza de decisiones y progreso (`opsx/ciclo-1/apply`, `opsx/ciclo-1/verify`, split C-01/C-02, entregables). **No** conviene citar el número exacto de observaciones como métrica del proyecto: `mem_stats` es global y mezcla proyectos.

### 9.6 Reglas R1–R13: cumplimiento

| Regla | Estado real |
|---|---|
| R1 Pydantic sin ORM, `extra='forbid'` | Cumplida en lo implementado |
| R2 type hints + ruff/mypy | Cumplida (gates verdes) |
| R3 async end-to-end | Cumplida en lo implementado |
| R4 tenant desde JWT | **No implementada** (C-03) |
| R5 sin `any`, TS estricto | Cumplida (sin `any`; strict on) |
| R6 datos clínicos fuera de localStorage | No aplicable aún (no hay features clínicas) |
| R7 no hard delete | Parcial: auditoría append-only; cascade lo contradice |
| R8 montos en servidor + webhooks idempotentes | No aplicable aún (C-12) |
| R9 sin PHI en logs/errores/URLs | Cumplida por ausencia de PHI; sin filtro automático |
| R10 commits convencionales + sin secretos | Parcial: hay commits sin prefijo; no hay secretos |
| R11 tests contra DB real | Parcial: CI sí; local cae a SQLite y 2 skips |
| R12 push por change | Parcial: push por ciclo/entrega, no por task |
| R13 datos ficticios | Cumplida |

---

## 10. Discrepancias documentales (qué NO afirmar)

| # | Documento dice | Realidad |
|---|---|---|
| D-01 | `openspec status` de C-02: `isComplete: true` | Es planificación; implementación 0/11 |
| D-02 | README: C-01 + C-02 terminados y archivados | C-02 tiene change activo 0/11 |
| D-03 | README: `docs/discovery/` vacía | Ya existe `informe-discovery.md` |
| D-04 | CHANGES: backend en `src/app/` y frontend en `src/` | Layout real `src/backend/` + `src/frontend/` |
| D-05 | CHANGES: C-02 "no aplicar hasta archivar C-01" | C-01 ya está archivado |
| D-06 | CHANGES: C-02 "4 tasks" | Tiene 11 |
| D-07 | CHANGES: "11 variables" | KB-08 lista 13 y se agregó `DATABASE_URL_OWNER` |
| D-08 | `.env.example`: rol `usuario_app` | Rol real `turnos_app` |
| D-09 | PDF: registry canónico `.atl` | Canónico `.agents` |
| D-10 | PDF: reflexión es plantilla | Está completa |
| D-11 | PDF: 45 observaciones / 4 sesiones | Métrica global, no del proyecto |
| D-12 | C-02 design: layout `src/app`, C-01 no aplicado | Estado previo al 2026-10-15 |
| D-13 | C-02 tasks 5.x "bloqueadas por C-01" | C-01 ya archivado |
| D-14 | `docs/changes/` copia completa | Solo el archive del 2026-10-03 |
| D-15 | Guion fuente `docs/guion-defensa-adaptado.md` | Solo existe el PDF |

**Regla de oro para la defensa:** si citás un número, que salga de esta auditoría o del repo, no del PDF.

---

## 11. Conclusión y próximos pasos

### 11.1 Lo que se puede defender con orgullo

1. **Método**: SDD con artefactos, 17 changes atómicos, gates de paralelismo y camino crítico.
2. **Fundación**: KB de 11 documentos, discovery con 18 sistemas, reglas R1–R13.
3. **Primer vertical**: 3 modelos, migración reversible, seed idempotente, repo con guard de tenant, auditoría por permisos, PWA, Compose, CI.
4. **Calidad medida**: 22 tests verdes, ruff/mypy/tsc/build verdes.
5. **Honestidad**: los pendientes están documentados y acotados, no ocultos.

### 11.2 Lo que hay que cerrar antes de “terminar” C-02

1. Levantar Postgres real (Docker) y correr la suite completa sin skips.
2. Diagnosticar y corregir el GRANT de auditoría (2.1–2.3) con aprobación humana.
3. Corregir `ON DELETE CASCADE` de `auditoria` → `RESTRICT`.
4. Validar configuración al arranque (lifespan).
5. Verificar `upgrade/downgrade/upgrade` en contenedor fresco.
6. Verificar CI verde y guardar evidencia.
7. Actualizar `CHANGES.md`, README y `c-02/design.md` al layout real.

### 11.3 Deuda estructural para después

- C-03: JWT, RBAC, tenant desde token, rate limiting.
- Engine singleton + dispose.
- RLS como defensa en profundidad.
- Frontend en Compose + proxy nginx + CORS + HTTPS.
- Tests de frontend y e2e.
- Soft delete y helper de auditoría.
- Tamper-evidence de auditoría (hash chain/firma).

---

## Anexo A — Comandos útiles para verificar en vivo

```bash
# Estado de changes
openspec list --json
openspec status --change "c-02-modelos-core" --json
openspec instructions apply --change "c-02-modelos-core" --json
openspec validate --change "c-02-modelos-core"

# Gates backend (desde la raíz)
pytest -q
ruff check --config src/backend/pyproject.toml src/backend tests
ruff format --check --config src/backend/pyproject.toml src/backend tests
mypy src/backend

# Gates frontend
cd src/frontend
npm run build
npx tsc --noEmit

# Stack (si Docker está disponible)
docker compose up --build -d
docker compose --profile tools run --rm migrar
cd src/backend && python -m app.infrastructure.seed
curl http://localhost:8000/api/health

# Migración reversible (SQLite, sin Docker)
cd src/backend
alembic upgrade head
alembic downgrade base
```

## Anexo B — Estructura del repo

```text
turnos-odontologia/
├── .agents/                 # 14 skills + registry canónico
├── .atl/                    # shim del registry
├── .github/workflows/ci.yml # backend + frontend
├── db/init/                 # roles de PostgreSQL
├── discovery/               # investigación de mercado
├── docs/
│   ├── discovery/informe-discovery.md
│   ├── changes/             # copia del archive 2026-10-03
│   ├── guion-defensa-adaptado.pdf
│   ├── auditoria-proyecto.md        ← este documento
│   └── defensa-oral-guia.md         ← guía de defensa
├── knowledge-base/          # 11 docs + README
├── openspec/
│   ├── config.yaml
│   ├── specs/               # 2 specs main
│   └── changes/
│       ├── archive/2026-10-03-c-01-foundation-core-models/
│       ├── archive/2026-10-15-c-01-solo-setup/
│       └── c-02-modelos-core/   ← activo, 0/11
├── src/
│   ├── backend/             # app, alembic, Dockerfile
│   └── frontend/            # React + Vite + PWA
├── tests/                   # 24 tests
├── CHANGES.md               # roadmap de 17 changes
├── AGENTS.md / CLAUDE.md    # reglas R1–R13
├── docker-compose.yml
└── README.md
```
