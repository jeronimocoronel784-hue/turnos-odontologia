# Revisión SDD — c-18-frontend-compose-demo

**Fecha**: 2026-11-12 · **Artefactos**: proposal.md, design.md, specs/foundation-setup/spec.md, tasks.md
**KB consultada**: `05_reglas_de_negocio.md` (completo) + `03_actores_y_roles.md` §Rutas públicas, `07_flujos_principales.md` §Flujo 1, `08_arquitectura_propuesta.md` §Estructura/§Variables de entorno, `10_preguntas_abiertas.md` (PO-01..PO-04) · **Reglas duras**: R1–R13 (`AGENTS.md`) · **Índice**: `CHANGES.md` §[C-18] "Leer antes"

> Revisión hecha con la skill `sdd-change-review` (gate previo a `/opsx:apply`). Este reporte refleja el estado de los artefactos al momento del gate; los fixes fueron aplicados después por instrucción del orquestador (ver `evidencia-sdd-review-y-mcp.md`).

## Veredicto

**APROBAR CON CAMBIOS** — sin hallazgos CRITICAL ni HIGH: los 4 hallazgos son casos de borde faltantes y una config desalineada, todos con sugerencia accionable; ninguna regla RN-* fue violada por los artefactos (R6, R8, R9, RN-SE-04 respetados).

## Hallazgos

| # | Tipo | Severidad | Regla | Evidencia (artefacto:línea) | Problema | Sugerencia |
|---|------|-----------|-------|-----------------------------|----------|------------|
| 1 | caso-borde-faltante | MEDIUM | R11, RN-AG-01, RN-GL-02 | `specs/foundation-setup/spec.md:73` (único escenario del POST de reserva) | La verificación e2e solo cubre el alta exitosa; falta el rechazo de doble reserva (409 con alternativas) a través del proxy | Agregar escenario "Slot tomado concurrentemente" → 409 + alternativas en rioplatense, y su caso de test (tasks 2.5) |
| 2 | caso-borde-faltante | MEDIUM | RN-GL-02, R11 | `specs/foundation-setup/spec.md:23-49` (Requirement del proxy) | Sin escenario de upstream caído: en el video el `502` crudo de nginx podría confundirse con una falla del producto | Agregar escenario "API caída tras el arranque" → 502/504 sin `index.html` ni stack traces + smoke manual (task 2.6) |
| 3 | regla-ausente | LOW | RN-PA-02, R8 | `specs/foundation-setup/spec.md:73` y `tasks.md:26` (el 4.2 solo chequeaba el monto) | No se verificaba que la reserva de prestación con seña cree la Seña `pendiente` con `monto_sena` devuelto por el servidor | Ampliar escenario/task: respuesta `201` con `requiere_sena`, `monto_sena` y seña `pendiente` (tasks 4.1/4.2) |
| 4 | regla-contradictoria | LOW | KB `08_arquitectura_propuesta.md:62` (§Variables de entorno — `FRONT_URL` = URL pública del front) | `docker-compose.yml:43` (`FRONT_URL: http://localhost:5173`) vs `design.md:31` (servicio frontend en `8080`) | `FRONT_URL` seguiría apuntando al dev server de Vite una vez que el front corre en compose :8080 (hoy sin impacto: `Settings.front_url` no se lee desde el código, `settings.py:40`) | Actualizar `FRONT_URL` a `http://localhost:8080` en compose (task 1.1) |

## Cobertura de reglas (matriz RN ↔ artefactos)

Dominios involucrados: Seguridad (RN-SE), Excepciones globales (RN-GL) + los ejercitados por la demo de reserva (RN-AG, RN-PA).

| RN | Estado | Dónde se cubre / por qué falta |
|----|--------|--------------------------------|
| RN-AG-01 | PARCIAL | Spec cubre catálogo/slots y alta (spec.md:55, 73) pero faltaba el 409 de doble reserva → hallazgo #1 |
| RN-AG-02 | CUBIERTA (no tocada) | `fin = inicio + duración` lo calcula el backend; el cambio solo lo verifica vía proxy (spec.md:55) |
| RN-AG-03 | CUBIERTA (no tocada) | Bloqueos no reservables siguen garantizados por C-06; sin cambios en el change |
| RN-AG-04 | CUBIERTA (no tocada) | El POST de demo usa `sobreturno=False` (`reserva_publica.py:260`); sin cambios |
| RN-AG-05 | CUBIERTA (no tocada) | Cancelación/reprogramación fuera del alcance (C-15/C-16); no se modifica |
| RN-AG-06 | CUBIERTA (no tocada) | Reprogramación fuera del alcance; no se modifica |
| RN-AG-07 | CUBIERTA (no tocada) | El change no mueve estados de turno; solo verifica la reserva `pendiente` inicial |
| RN-AG-08 | CUBIERTA (no tocada) | Confirmación WA/webhooks fuera del alcance; webhooks no se enrutan por el proxy (proposal Impact) |
| RN-PA-01 | CUBIERTA (no tocada) | Seña `pendiente` se crea en C-06/C-11; sin cambios |
| RN-PA-02 | PARCIAL | Faltaba verificar la seña `pendiente` con monto del servidor en la demo → hallazgo #3 |
| RN-PA-03 | CUBIERTA (excluida) | Exclusión explícita en proposal: los webhooks de MP siguen directo a `api:8000`, el proxy solo cubre `/api/` |
| RN-PA-04 | CUBIERTA (no tocada) | Retención/devolución de seña fuera del alcance; no se modifica |
| RN-PA-05 | CUBIERTA (no tocada) | Caja/conciliación fuera del alcance; no se modifica |
| RN-SE-01 | CUBIERTA (no tocada) | El login sigue escribiendo `auth.login` en auditoría (`sesiones.py:87-94`); sin cambios |
| RN-SE-02 | CUBIERTA | Artefactos y evidencia sin PHI ni datos reales (R9, R13); solo IDs y datos ficticios del seed |
| RN-SE-03 | CUBIERTA (no tocada) | `token_gestion` viaja por el proxy tal cual; el conf no loguea bodies (spec.md:23-27: preserva headers) |
| RN-SE-04 | CUBIERTA | `DEMO_PASSWORD` solo por env con placeholder en `.env.example`, sin imprimir el valor (design.md:39-41, tasks.md:18) |
| RN-GL-01 | CUBIERTA | Sin conflictos entre reglas en los artefactos (no hay reglas de menor precedencia pisando SE/CL/PA) |
| RN-GL-02 | PARCIAL | Rechazos 401/404 en rioplatense cubiertos (spec.md:33, 67); faltaba el caso de upstream caído → hallazgo #2 |
| RN-GL-03 | CUBIERTA | No se proponen atajos en RN-SE/RN-CL/RN-PA-03: sin cambios de negocio |

## Casos borde faltantes

- **POST /reservar (e2e)** — solo happy path; falta escenario de slot tomado concurrentemente → 409 + alternativas (R11, hallazgo #1).
- **Proxy `/api/`** — sin escenario de API caída (502/504 sin `index.html` ni stack traces) (R11, RN-GL-02, hallazgo #2).
- **Reserva con seña** — sin escenario de Seña `pendiente` con `monto_sena` del servidor (RN-PA-02, R8, hallazgo #3).
- Requisitos auditados contra R11 post-fix: "Stack completo" 2 escenarios, "Proxy inverso" 4, "Verificación e2e" 5 → todos ≥2.

## Consultas al PO

- Ninguna bloqueante: PO-01 (hosting), PO-02 (costo WA), PO-03 (retención legal) y PO-04 (pricing) no condicionan este change (Docker local primero, decisión ya tomada en `10_preguntas_abiertas.md:15-16`).
- El puerto/URL pública definitiva del front (hoy `http://localhost:8080` en local) queda para PO-01 cuando se decida el deploy.

## Fuera de alcance

- Dominios **RN-LE**, **RN-OS**, **RN-CL** y **RN-CO** completos: no se modifican ni se ejercitan en la demo de reserva/login (sin lista de espera, liquidación, HC ni envíos); el opt-in WA del formulario ya está testeado en C-15/C-08.
- **R5** (TS estricto): sin cambios de componentes React (solo `nginx.conf`); **R7** (soft delete): sin borrados nuevos; **R1**/**R4**: sin tocar schemas ni el manejo de `tenant_id`.
- C-14 (auditoría/exportación), C-16 y C-17 (pantallas nuevas): fuera del alcance por diseño del change.
