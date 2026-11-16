# Guía de defensa oral — Turnos Odontología

**Basada en:** auditoría del 2026-10-20 (commit `ac56510`).
**Formato asumido:** 15 minutos, 4 integrantes (3 + 4 + 4 + 4).
**Regla de oro:** defender lo que el repo prueba, no lo que el PDF promete.

---

## 1. Cómo usar esta guía

1. Leer el **pitch de 3 minutos** (§2) hasta poder decirlo sin leer.
2. Asignarse los bloques de §3.
3. Memorizar los **números** de §4 (son los que el jurado pregunta).
4. Repasar el **glosario** de §5: si no podés explicar un término en una frase, no lo nombres.
5. Practicar el **banco de preguntas** (§6) de a dos: uno pregunta, otro responde en 30–45 segundos.
6. Leer las **preguntas trampa** (§7) y los **claims prohibidos** (§8). Ahí se pierde la defensa.
7. Probar la **demo** (§9) en la máquina que se va a usar.
8. Imprimir la **chuleta** (§10).

---

## 2. Pitch de 3 minutos (texto literal)

> "Turnos Odontología es un SaaS multi-tenant para consultorios odontológicos de Argentina y Uruguay. Resuelve un problema concreto: el consultorio pierde plata y tiempo por ausentismo, por reservas telefónicas en horario de atención y por información dispersa entre agenda, historia clínica, caja y obras sociales.
>
> La propuesta es una PWA: el paciente reserva online 24/7, deja una seña por Mercado Pago, y el consultorio recibe el turno confirmado, el recordatorio por WhatsApp y el registro en caja. Del lado interno, recepción maneja agenda y pacientes, el odontólogo carga historia clínica y odontograma, y el dueño ve caja, obras sociales y auditoría.
>
> Decidimos construirlo como monolito modular en FastAPI, con PostgreSQL, Redis y React, porque el primer cliente es un consultorio: no necesitamos microservicios, necesitamos abaratar la operación y poder desplegar todo con Docker Compose. El aislamiento multi-tenant es lógico: un `tenant_id` en toda tabla de negocio, un repositorio que falla cerrado si falta tenant y permisos de base de datos para que la auditoría sea append-only.
>
> Metodológicamente usamos Spec-Driven Development con OpenSpec: cada cambio es atómico, tiene propuesta, escenarios, diseño y tasks; se implementa, se verifica y se archiva. Planificamos 17 changes en 7 fases, con un camino crítico de 9 que termina en la reserva pública con seña.
>
> Hoy está implementada y verificada la fundación: los 3 modelos core, la migración reversible, el seed idempotente, el aislamiento por repositorio, la PWA base, Docker Compose, CI y 24 tests. Lo que sigue es auth y RBAC, y después pacientes, agenda, historia clínica, caja y pagos. No vamos a decir que el producto está terminado: está terminada la base, con deuda de verificación en PostgreSQL que tenemos identificada y acotada."

---

## 3. Estructura de 15 minutos (4 integrantes)

| Bloque | Tiempo | Contenido | Quién |
|---|---|---|---|
| 1 | 3 min | Problema, discovery, propuesta de valor, alcance v1 vs v2 | Integrante 1 |
| 2 | 4 min | Arquitectura, stack, multi-tenant, modelos y auditoría | Integrante 2 |
| 3 | 4 min | Metodología SDD/OPSX, roadmap, agentes, governance, TDD | Integrante 3 |
| 4 | 4 min | Estado real, calidad, demo, riesgos y próximos pasos | Integrante 4 |

### Guion sugerido por bloque

**Bloque 1 — Problema y producto**
- Ausentismo, reserva telefónica, dispersión de datos.
- 18 sistemas relevados; diferenciación: reserva + seña + WhatsApp + multi-tenant + PWA.
- 4 roles; 7 flujos; 18 entidades; alcance v1 y fuera de alcance.
- Cierre: "el corte del MVP es C-15: reserva pública con seña cobrada".

**Bloque 2 — Arquitectura**
- Diagrama: PWA → FastAPI → PostgreSQL/Redis.
- Monolito modular, capas, por qué no microservicios.
- Multi-tenant: `tenant_id`, `TenantMixin`, `BaseRepository`, falla cerrado.
- Modelos: Tenant, Usuario, Auditoria; constraints; migración 001.
- Auditoría append-only por GRANT.
- Honestidad: `application/` vacía, sin JWT todavía.

**Bloque 3 — Método**
- Qué es SDD y qué es OpenSpec; change, delta spec, archive.
- Flujo explore → propose → apply → verify → archive.
- 17 changes, 9 gates, camino crítico, 3 agentes.
- Skills, registry, governance por dominio, Engram.
- TDD: qué se hizo y qué no se evidencia.

**Bloque 4 — Estado y cierre**
- Qué está implementado (tabla de 6.1 de la auditoría).
- Gates: 22 passed, 2 skipped; ruff/mypy/tsc/build.
- Lo que no está: auth, agenda, HC, pagos, frontend de negocio.
- Riesgos principales y próximos pasos.
- Cierre: "la base está; el producto es el roadmap".

---

## 4. Números que hay que saber

| Dato | Valor |
|---|---|
| Changes planificados | **17** en **7 fases** |
| Gates de sincronización | **9** (GATE 0 a 8) |
| Camino crítico | **9 changes**: C-01→C-02→C-03→C-05→C-06→C-09→C-11→C-12→C-15 |
| Agentes planificados | **3** (Backend Core, Backend Aux, Dinero+Frontend) |
| Documentos de KB | **11** + README |
| Sistemas relevados en discovery | **18** |
| Roles | **4** (Dueño, Recepción, Odontólogo, Paciente) |
| Entidades del modelo | **18**; implementadas **3** |
| Flujos principales | **7** |
| Escenarios del ciclo 1 | **18** (7 foundation + 11 core) |
| Escenarios delta de C-02 | **8** (5 auditoría + 3 paridad) |
| Tasks C-01 original | **10/14** |
| Tasks c-01-solo-setup | **11/13** |
| Tasks c-02-modelos-core | **0/11** |
| Tests | **24** colectados: **22 passed, 2 skipped, 0 failed** |
| Commits | **13** en `main` |
| Skills | **14**, versionadas en `.agents/skills/` |
| Reglas duras | **13** (R1–R13) |
| Versiones | Python 3.12.10, FastAPI 0.111.0, SQLAlchemy 2.0.54, PostgreSQL 15.10, React 18.3.1, Vite 5.4.9 |

**Frases para usar:**
- "18 escenarios, 24 tests, 22 verdes y 2 skips que requieren PostgreSQL real."
- "C-02 está planificado y validado, pero 0 de 11 tasks: no está implementado."
- "El camino crítico son 9 changes, no 17."

---

## 5. Glosario en una frase

| Término | Explicación |
|---|---|
| **SDD** | Desarrollo guiado por especificaciones: el contrato se escribe antes que el código. |
| **OpenSpec** | Herramienta que estructura changes, specs, tasks y archives en el repo. |
| **OPSX** | Workflow fluido de OpenSpec: cualquier acción se puede repetir, sin gates rígidos. |
| **Change** | Unidad atómica de trabajo con propuesta, diseño, specs y tasks. |
| **Delta spec** | Escenarios que un change agrega, modifica o elimina respecto de la spec principal. |
| **Archive** | Cierre del change: sincroniza specs y lo mueve a `changes/archive/`. |
| **Multi-tenant lógico** | Una sola base y esquema; cada fila lleva `tenant_id`. |
| **RLS** | Row Level Security: política de PostgreSQL que filtra filas por usuario. No implementada. |
| **Repositorio** | Clase que encapsula el acceso a datos y aplica el filtro de tenant. |
| **UoW** | Unit of Work: agrupa operaciones y hace commit/rollback como una unidad. |
| **Append-only** | Solo INSERT y SELECT; sin UPDATE ni DELETE. Se aplica con permisos de DB. |
| **Soft delete** | Marcar como borrado sin eliminar la fila. No implementado aún. |
| **JWT** | Token firmado con identidad y tenant; access corto + refresh rotativo. Pendiente C-03. |
| **RBAC** | Control de acceso por rol. Matriz documentada, no enforceada aún. |
| **Idempotencia** | Repetir la misma operación no duplica el efecto; clave en pagos y webhooks. |
| **Outbox** | Tabla de eventos pendientes para publicar en cola sin doble escritura. Diseñado, no implementado. |
| **PWA** | Web app instalable con manifest y service worker. |
| **FDI** | Notación dental de dos dígitos: cuadrante + diente. Usada en el odontograma. |
| **PHI** | Información de salud protegida. En Argentina aplica Ley 25.326 y HCE. |
| **Governance** | Nivel de autonomía del agente según criticidad del dominio. |
| **Skill** | Paquete de instrucciones y reglas compactas que el agente carga para una tarea. |
| **Engram** | Memoria persistente entre sesiones y compactaciones. |
| **TDD** | Red-green-refactor: test que falla, código mínimo, refactor. |

---

## 6. Banco de preguntas (con respuesta)

### A. Producto y negocio

**1. ¿Qué problema resuelve?**
Ausentismo, reserva telefónica limitada al horario del consultorio y datos dispersos entre agenda, HC, caja y obras sociales. La PWA permite reservar 24/7 con seña y el back-office centraliza la operación.

**2. ¿Quién es el cliente y quién paga?**
El consultorio (dueño) paga la suscripción. El paciente usa la reserva pública sin cuenta. El modelo de precio está abierto (PO-04); el supuesto es suscripción mensual por consultorio, no comisión por turno.

**3. ¿Por qué odontología y no medicina general?**
El odontograma, las prestaciones por pieza y las obras sociales odontológicas son un dominio específico con reglas propias (FDI, copagos, liquidaciones). Un sistema genérico no las modela bien.

**4. ¿Qué diferencia su producto de los 18 sistemas relevados?**
Integración de reserva pública + seña por Mercado Pago + WhatsApp + multi-tenant en una sola PWA, con foco en consultorios chicos. Muchos competidores son sistemas de escritorio o no tienen reserva online con pago.

**5. ¿Qué está dentro y qué fuera del alcance v1?**
Dentro: agenda, pacientes, HC/odontograma, presupuestos, caja/señas, MP, reserva pública, mensajería, OS, auditoría/exportación. Fuera: app nativa, AFIP nativa, facturación fiscal, push, IA clínica.

**6. ¿Cómo se cobra la seña y qué pasa si el paciente cancela?**
La seña se ata al turno; el pago es idempotente por event-id; al cancelar, la política del tenant define devolución o retención, y todo movimiento concilia en caja (RN-PA). C-12 lo implementa.

**7. ¿Qué pasa si el consultorio no tiene internet?**
La PWA cachea el shell y permite tolerar red inestable (SU-06). La operación crítica de escritura requiere conexión; no prometemos offline completo en v1.

**8. ¿Cómo manejan la privacidad?**
Datos sintéticos en desarrollo (R13), sin PHI en logs/errores/URLs (R9), acceso por rol (RBAC), auditoría append-only. La normativa aplicable es Ley 25.326 y HCE; HIPAA no aplica legalmente en Argentina, usamos la skill solo como catálogo de buenas prácticas.

### B. Arquitectura y stack

**9. ¿Por qué monolito modular y no microservicios?**
DD-02: un solo deploy, menos infraestructura, un equipo chico. Los módulos tienen límites claros (`api`, `domain`, `infrastructure`). Microservicios sería costo operativo sin beneficio para 1 consultorio.

**10. ¿Por qué FastAPI?**
Async nativo, Pydantic para validación y contratos, OpenAPI automático y tipado fuerte. Encaja con Python y con el equipo.

**11. ¿Por qué PostgreSQL?**
Transacciones, constraints, JSONB para configuración por tenant, integridad referencial y camino a RLS. Es la base estándar para datos de salud.

**12. ¿Por qué Redis?**
Cola/caché para mensajería, vencimientos y reintentos (DD-06). Hoy solo se usa en el health y hay un esqueleto de worker.

**13. ¿Cómo escala?**
Primero vertical: API stateless detrás de un proxy, Postgres y Redis. Si crece: réplicas de lectura, particionado por tenant, RLS, workers separados. No está implementado el escalado; es el camino.

**14. ¿Por qué PWA y no app nativa?**
DD-01: un solo código, instalable, sin tiendas, ideal para paciente ocasional. Push queda fuera de v1.

**15. ¿Qué hace el worker?**
Hoy es un esqueleto (`workers/main.py`) sin jobs. Está previsto para WhatsApp, emails, vencimientos y reintentos.

**16. ¿Por qué TanStack Query?**
Maneja estado de servidor: cache, reintentos, invalidación. Evita reinventar loading/error/data.

**17. ¿Qué capas tiene el backend?**
`api` (routers/schemas), `domain` (modelos), `application` (vacía), `infrastructure` (DB/seed), `shared` (config/log/errores). La capa de casos de uso es la deuda principal.

**18. ¿Por qué los modelos están en `domain` si son SQLAlchemy?**
Decisión pragmática para C-02: el dominio importa `Base` de infraestructura. Es una inversión de dependencia consciente; se puede separar cuando haya casos de uso.

### C. Multi-tenant y seguridad

**19. ¿Cómo aíslan los datos entre consultorios?**
Cada tabla de negocio lleva `tenant_id` vía `TenantMixin`. `BaseRepository` exige tenant en el constructor, filtra todas las consultas y rechaza agregar una entidad con tenant ajeno. Si falta tenant, lanza `TenantContextoRequerido`.

**20. ¿Qué pasa si un programador consulta directo con `session.execute`?**
Ve todos los tenants. El aislamiento depende de pasar por el repositorio. No hay RLS. Es el riesgo de A-04 y la razón para evaluar RLS como defensa en profundidad.

**21. ¿Por qué no usaron RLS?**
DD-07: multi-tenant lógico desde el día 1, RLS opcional a futuro. Se priorizó simplicidad y portabilidad; el guard de aplicación falla cerrado. Es una decisión documentada, no un olvido.

**22. ¿Cómo evitan IDOR (acceder a un recurso de otro tenant)?**
El repositorio busca por `id` **y** `tenant_id`; si el recurso es de otro tenant, devuelve `None`. Además, los schemas de input no aceptan `tenant_id` (`extra='forbid'`).

**23. ¿De dónde sale el `tenant_id` en un request real?**
Hoy de ningún lado: no hay auth. En C-03 sale del JWT y se inyecta en el UoW. R4 prohíbe tomarlo del body o query.

**24. ¿Cómo evitan que recepción vea la historia clínica?**
La matriz RBAC lo prohíbe (`03_actores_y_roles.md`), pero **todavía no está enforceada**. C-03 implementa los permisos; C-09 los aplica a HC.

**25. ¿Cómo protegen los secretos?**
`.env` gitignored, `.env.example` solo placeholders, Compose exige variables con `${VAR:?}`, no hay secretos en imágenes. `JWT_SECRET` todavía no valida longitud mínima (deuda).

**26. ¿Cómo evitan PHI en logs?**
Regla R9 y logger sin payloads; el 500 es genérico. No hay filtro automático de PHI ni logging estructurado: deuda M-10.

**27. ¿La auditoría es inmutable?**
Parcialmente. El rol app solo tiene SELECT/INSERT sobre `auditoria`, pero el owner puede modificarla y un `DELETE` sobre `tenant` la borra en cascada. Es el hallazgo CRITICAL A-01; el fix es `RESTRICT` + revocar DELETE.

**28. ¿Qué pasa si roban un token?**
El access token es corto (15 min) y el refresh rota (30 días). La revocación efectiva se implementa en C-03 con rotación y lista de revocados en Redis.

### D. Datos, agenda y clínica

**29. ¿Por qué UUID guardado como CHAR(32)?**
Para que SQLite y PostgreSQL generen el mismo DDL y los tests corran en ambos. Costo: se pierde el tipo nativo UUID y sus índices. Es un tradeoff de portabilidad.

**30. ¿Por qué `politicas` es JSONB?**
Cada consultorio configura anticipación, duración, recordatorios y retención sin migrar el esquema. Se valida en la capa de aplicación.

**31. ¿Cómo evitan doble turno?**
Regla RN-AG-01. La implementación correcta es una restricción de exclusión en PostgreSQL por profesional/sillón y rango de tiempo, dentro de una transacción. **Todavía no está implementada** (C-06).

**32. ¿Cómo modelarían el odontograma?**
Notación FDI: 32 piezas permanentes y 20 temporales, con estados por cara/superficie y evolución histórica. Es parte de C-09; no está implementado.

**33. ¿Por qué soft delete?**
R7: en HC, turnos y caja no se borra; se marca y se audita. Hoy no hay soft delete; `activo` es desactivación, no borrado lógico.

**34. ¿Cómo se calcula el copago de obra social?**
Con el padrón y arancel del tenant: copago = arancel − cobertura. Solo los turnos finalizados liquidan (RN-OS). C-13 lo implementa.

**35. ¿Cómo garantizan idempotencia en pagos?**
Dedup por event-id del webhook, outbox transaccional y conciliación contra Mercado Pago. No hay doble efecto si el webhook se repite (R8, C-12).

**36. ¿Qué pasa si se cae el worker?**
Redis pierde la cola porque no tiene persistencia configurada (M-16). El outbox en DB permite reprocesar; el diseño lo prevé, la implementación no.

### E. Metodología SDD/OPSX

**37. ¿Qué es SDD?**
Spec-Driven Development: se escribe la especificación (qué y por qué), el diseño (cómo) y los tasks antes de codificar. El código es consecuencia del contrato.

**38. ¿Qué aporta OpenSpec?**
Estado verificable: `openspec status` dice qué artefactos existen; `validate` chequea coherencia; `archive` sincroniza specs. Evita que el agente improvise y que el humano adivine el estado.

**39. ¿Qué es un change y qué es un delta spec?**
Un change es la unidad atómica de trabajo. El delta spec son los escenarios que ese change agrega/modifica/elimina; al archivar se fusionan en la spec principal.

**40. ¿Por qué 17 changes y no uno grande?**
Atomicidad: cada change se puede implementar en una sesión, revisar y archivar por separado. Permite paralelizar y aislar el riesgo.

**41. ¿Cómo se paraleliza con 3 agentes?**
Los gates marcan sincronización. En el GATE 5 corren 4 changes en paralelo (lista de espera, mensajería, HC, caja); en el GATE 6, tres. Cada agente tiene un dominio.

**42. ¿Qué es el camino crítico y por qué termina en C-15?**
La secuencia mínima que no se puede paralelizar. Termina en C-15 porque el corte del MVP es reserva pública con seña: sin C-15 no hay captura 24/7; sin C-12 no hay seña.

**43. ¿Qué es governance por dominio?**
Nivel de autonomía según criticidad: CRÍTICO (auth, pagos, salud, auditoría) requiere análisis y aprobación humana; BAJO (CRUD, layout) permite autonomía si los tests pasan. Ejemplo: 2.4 se movió de C-01 a C-02 por ser CRÍTICO.

**44. ¿Qué son las skills y el registry?**
Paquetes de instrucciones y reglas compactas (Postgres, FastAPI, TDD, Docker, HIPAA, etc.). El registry mapea cada change a las skills que debe cargar.

**45. ¿Qué es Engram y para qué lo usaron?**
Memoria persistente entre sesiones. Guardaron decisiones, progreso y hallazgos para no perder contexto tras compactaciones. No es telemetría: es traza de decisiones.

**46. ¿Cómo evitan que el agente alucine?**
Specs como contrato, CLI como fuente de estado, tests y gates como verificación, changes chicos, revisión humana en CRÍTICO. No es infalible; la evidencia muestra que la documentación se desincronizó.

**47. ¿Qué rol tiene el humano?**
Define producto y alcance, aprueba cambios CRÍTICOS, revisa y decide. El agente ejecuta, propone y verifica; no decide solo en auth, pagos o salud.

### F. Calidad, TDD e infraestructura

**48. ¿Qué tests tienen y qué prueban?**
24: modelos (5), aislamiento (3), seed (2), health (3), settings (3), auditoría (3) y cobertura de verificación (5). Cubren alta, duplicados, tenant cruzado, matrícula, idempotencia, 503 y placeholders.

**49. ¿Por qué hay 2 tests skipped?**
Requieren PostgreSQL real y el rol restringido `turnos_app`; sin Docker local, `conftest.py` cae a SQLite y no puede probar permisos. En CI, con Postgres, corren.

**50. ¿Hicieron TDD estricto?**
Parcialmente. Hay tests y casos borde, pero no hay commits RED separados: el commit principal mezcla código y tests, y 5 tests se agregaron en Verify. La disciplina está; la trazabilidad rojo-verde no está evidenciada.

**51. ¿Qué corre el CI?**
Backend con PostgreSQL 15.10 y Redis 7.4.1: migración, ruff, formato, mypy y pytest. Frontend: `npm ci` y `npm run build` (tsc + Vite).

**52. ¿Qué NO prueba el CI?**
Build de imágenes, `compose up`, nginx, proxy `/api`, CORS, tests de frontend, e2e, accesibilidad, downgrade, `alembic check`, worker, health real, cobertura y deploy.

**53. ¿Cómo se levanta el sistema?**
`cp .env.example .env`, completar passwords y JWT; `docker compose up --build`; `docker compose --profile tools run --rm migrar`; seed; `GET /api/health`; frontend con `npm ci && npm run dev`.

**54. ¿Por qué el health puede dar 200 sin tablas?**
Porque solo hace `SELECT 1`. No valida esquema ni versión de Alembic. Es una trampa operativa: `compose up` no migra automáticamente.

**55. ¿Los Dockerfiles están listos para producción?**
Tienen multi-stage, non-root, tags exactos y healthchecks. No están listos: falta `.dockerignore` en frontend, proxy nginx, HTTPS, secrets management, pinning por digest y build en CI.

### G. Estado real y cierre

**56. ¿Qué está terminado hoy?**
Fundación: layout, FastAPI, 3 modelos, migración 001, seed, repositorio/UoW, auditoría por permisos, PWA base, Compose, CI, 22 tests verdes. C-01 archivado; C-02 planificado.

**57. ¿Qué NO está terminado?**
Auth/JWT/RBAC, pacientes, agenda, HC/odontograma, caja, Mercado Pago, reserva pública, frontend de negocio, verificación en PostgreSQL real, CI verde evidenciado y documentación al día.

**58. ¿Cuál es el mayor riesgo técnico?**
La cascada que puede borrar la auditoría desde `tenant` (A-01). Después, la ausencia de auth y el aislamiento sin RLS.

**59. ¿Cuál es el mayor riesgo de proceso?**
La desincronización entre documentos y repo: README, CHANGES, design de C-02 y PDF afirman cosas que ya no son ciertas. Un jurado que los contraste lo va a ver.

**60. ¿Qué harían distinto?**
Tres cosas: Docker/Postgres desde el día 1 para no diferir R11; commits atómicos por move/rewiring/tests para que la historia sea auditable; no marcar `[x]` ni "completo" hasta cerrar la verificación real.

**61. ¿Qué falta para el MVP?**
C-03 auth/RBAC, C-05 pacientes, C-06 agenda, C-09 HC/odontograma, C-11 caja/señas, C-12 Mercado Pago y C-15 reserva pública. Y cerrar C-02 en Docker/Postgres.

**62. ¿Qué aprendieron?**
Que el método sirve para ordenar el trabajo del agente, pero no reemplaza la verificación: sin Docker, sin CI observado y sin documentación sincronizada, el "estado" que declara la herramienta puede no ser el real.

---

## 7. Preguntas trampa y cómo responder

| Trampa | Mala respuesta | Buena respuesta |
|---|---|---|
| "¿Entonces el proyecto está terminado?" | "Sí, C-01 y C-02 están listos." | "Está terminada la fundación y el primer vertical. C-02 está planificado, 0/11. El producto completo es el roadmap de 17 changes." |
| "¿C-02 está completo?" | "Sí, `openspec status` dice complete." | "`status` habla de artefactos de planificación. El progreso real es 0/11 según `instructions apply`." |
| "¿Usan RLS?" | "Sí, somos multi-tenant seguros." | "No. Usamos aislamiento de aplicación con repositorio; RLS es defensa en profundidad futura." |
| "¿JWT implementado?" | "Sí." | "No. Está diseñado y es C-03. Hoy no hay endpoints de negocio expuestos." |
| "¿Cumplen HIPAA?" | "Sí, usamos la skill." | "HIPAA no aplica legalmente en Argentina. Usamos la skill como catálogo; la normativa es Ley 25.326 y HCE." |
| "¿La auditoría es inmutable?" | "Sí, append-only." | "Parcialmente: el rol app no puede UPDATE/DELETE, pero el owner sí y la cascada desde tenant la borra. Está identificado como CRÍTICO." |
| "¿Hicieron TDD estricto?" | "Sí, siempre." | "La disciplina y la cobertura están; la secuencia rojo-verde no está evidenciada en commits. Es una deuda de proceso." |
| "¿Docker funciona?" | "Sí, todo levantado." | "En esta máquina no hay Docker. El Compose está escrito y validado por YAML; la verificación real está pendiente." |
| "¿El frontend está deployado?" | "Sí." | "No end-to-end: no hay servicio en Compose ni proxy `/api`; en dev funciona por el proxy de Vite." |
| "¿Por qué el PDF dice otra cosa?" | "El PDF es la verdad." | "El PDF es un guion de defensa desactualizado. La fuente de verdad es el repo y esta auditoría." |
| "¿Por qué un commit de 262 archivos?" | "Fue un error." | "Sí, fue un error de granularidad. El design prometía commits por tanda; la historia no lo refleja." |
| "¿Cómo sé que el agente no inventó el código?" | "Porque usamos IA buena." | "Porque hay specs, tests, gates y revisión humana. Aun así, la trazabilidad no es perfecta: lo que no está verificado lo decimos." |

---

## 8. Claims prohibidos (no decir nunca)

| No decir | Decir |
|---|---|
| "C-02 está terminado" | "C-02 está planificado y validado; 0/11 tasks" |
| "El producto está terminado" | "La fundación está; el producto es el roadmap" |
| "Tenemos auth" | "Auth es C-03; hoy no hay endpoints de negocio" |
| "Tenemos RBAC enforceado" | "La matriz está documentada; el enforcement es C-03" |
| "Usamos RLS" | "Aislamiento de aplicación; RLS futuro" |
| "La auditoría es inmutable" | "Append-only por permisos, con un riesgo de cascade identificado" |
| "Tests contra Postgres siempre" | "CI sí; local cae a SQLite y 2 skips" |
| "CI verde comprobado" | "El workflow está configurado; no hay evidencia guardada del run" |
| "Todo está dockerizado" | "Backend, DB, Redis y worker sí; frontend corre aparte" |
| "45 observaciones en Engram" | "Engram se usó como traza; las métricas globales no son del proyecto" |

---

## 9. Demo en vivo

### Ruta A — con Docker (ideal)

```bash
# 1. Preparar entorno
cp .env.example .env
# completar POSTGRES_PASSWORD, APP_DB_PASSWORD, JWT_SECRET

# 2. Levantar
docker compose up --build -d

# 3. Migrar y sembrar
docker compose --profile tools run --rm migrar
cd src/backend && python -m app.infrastructure.seed && cd ../..

# 4. Verificar salud
curl http://localhost:8000/api/health

# 5. Frontend
cd src/frontend && npm ci && npm run dev
# abrir http://localhost:5173 → "Conectado"

# 6. OpenAPI
# abrir http://localhost:8000/docs

# 7. Mostrar tablas
docker compose exec db psql -U postgres -d turnos -c "\dt"
```

**Qué narrar mientras tanto:**
- "El health consulta DB y Redis; si uno falla, devuelve 503 con mensaje en rioplatense."
- "La migración crea tenant, usuario y auditoría, y da al rol app solo SELECT/INSERT en auditoría."
- "El seed es idempotente: correrlo dos veces no duplica."

### Ruta B — sin Docker (fallback)

```bash
pytest -q
ruff check --config src/backend/pyproject.toml src/backend tests
ruff format --check --config src/backend/pyproject.toml src/backend tests
mypy src/backend
cd src/frontend && npm run build
cd ../..
openspec list --json
openspec status --change "c-02-modelos-core" --json
openspec instructions apply --change "c-02-modelos-core" --json
```

**Qué mostrar en código:**
1. `BaseRepository`: el guard de tenant y el filtro.
2. Migración 001: constraints + GRANT de auditoría.
3. `seed.py`: idempotencia y datos ficticios.
4. `test_repository_isolation.py`: A no ve B.
5. Archive de C-01: proposal, design, tasks, specs.

**Si el health devuelve 503 sin DB:** explicar que es el comportamiento diseñado y que el mensaje nombra el servicio caído. No intentar ocultarlo.

---

## 10. Chuleta de una página (imprimible)

```text
┌─────────────────────────────────────────────────────────────┐
│ TURNOS ODONTOLOGÍA — DEFENSA                                │
├─────────────────────────────────────────────────────────────┤
│ QUÉ ES: SaaS multi-tenant para consultorios odontológicos.  │
│ PWA paciente + back-office. Reserva 24/7 + seña MP + WA.     │
│                                                             │
│ MVP: C-15 reserva pública + C-12 seña. Camino crítico 9:     │
│ C-01→C-02→C-03→C-05→C-06→C-09→C-11→C-12→C-15                 │
│                                                             │
│ NÚMEROS: 17 changes / 7 fases / 9 gates / 3 agentes          │
│ 11 docs KB / 18 sistemas / 4 roles / 18 entidades (3 impl.) │
│ 18 escenarios ciclo 1 / 24 tests (22 pass, 2 skip)           │
│ C-01 10/14 · c-01-solo-setup 11/13 · C-02 0/11               │
│                                                             │
│ STACK: Python 3.12 + FastAPI + SQLAlchemy + Postgres 15      │
│ React 18 + TS 5 + Vite + TanStack Query + PWA               │
│ Redis 7 + Docker Compose + GitHub Actions                   │
│                                                             │
│ MULTI-TENANT: tenant_id en toda tabla; BaseRepository        │
│ falla cerrado; sin RLS (decisión DD-07).                    │
│                                                             │
│ AUDITORÍA: append-only por GRANT SELECT/INSERT;              │
│ RIESGO: cascade desde tenant (CRÍTICO, A-01).               │
│                                                             │
│ SDD: explore→propose→apply→verify→archive.                   │
│ Change = proposal + design + specs + tasks.                 │
│ status "complete" = planificación, NO implementación.        │
│                                                             │
│ TERMINADO: fundación + 3 modelos + migración + seed +        │
│ repo/UoW + PWA base + Compose + CI + 22 tests.              │
│ NO TERMINADO: auth/JWT/RBAC, pacientes, agenda, HC,          │
│ odontograma, caja, MP, reserva pública, frontend negocio.   │
│                                                             │
│ DEUDA CLAVE: Docker/Postgres no verificado; 2 skips;         │
│ SQLite local; CI sin evidencia; docs desactualizados;        │
│ TDD sin commits RED; frontend sin tests.                    │
│                                                             │
│ FRASE DE CIERRE: "La base está verificada; el producto      │
│ es el roadmap. Lo que falta está identificado, no oculto."  │
└─────────────────────────────────────────────────────────────┘
```

---

## 11. Reparto sugerido y transiciones

| Integrante | Preguntas que debería poder responder |
|---|---|
| 1 | Producto, problema, competencia, alcance, pricing, privacidad |
| 2 | Stack, arquitectura, modelos, multi-tenant, auditoría, migración |
| 3 | SDD, OpenSpec, roadmap, gates, skills, governance, TDD, Engram |
| 4 | Estado real, tests, CI, Docker, riesgos, próximos pasos, demo |

**Transiciones ensayadas:**
- 1 → 2: "Si el problema y el alcance están claros, veamos cómo se traduce en arquitectura."
- 2 → 3: "Con el modelo definido, el siguiente problema es cómo construir 17 changes sin perder el control: ahí entra SDD."
- 3 → 4: "El método define el camino; ahora veamos qué parte del camino está realmente recorrida."
- 4 → cierre: "La base está verificada; el producto es el roadmap. Lo que falta está identificado, no oculto."

---

## Anexo — Respuestas de 15 segundos para preguntas de pasillo

- **¿Qué es OpenSpec?** Un sistema de artefactos y estado para desarrollar por especificaciones.
- **¿Qué es un tenant?** Cada consultorio; sus datos se filtran por `tenant_id`.
- **¿Qué es append-only?** Solo se inserta y lee; no se modifica ni borra.
- **¿Qué es el outbox?** Una tabla de eventos para publicar en cola sin doble escritura.
- **¿Qué es governance?** Cuánta autonomía tiene el agente según la criticidad del dominio.
- **¿Qué es TDD?** Test que falla, código mínimo, refactor.
- **¿Qué falta?** Auth, agenda, HC, caja, pagos y reserva pública; y cerrar la verificación en Postgres.
- **¿Qué está más flojo?** La sincronización entre documentos y estado real.
- **¿Qué está más fuerte?** El método, la KB, el roadmap y el primer vertical con tests.
- **¿Qué harías distinto?** Docker desde el día 1 y commits atómicos.
