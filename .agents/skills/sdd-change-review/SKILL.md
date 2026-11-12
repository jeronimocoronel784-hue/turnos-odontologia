---
name: sdd-change-review
description: "Revisa los artefactos SDD de un change de OpenSpec (proposal.md, design.md, specs/*.md y tasks.md) contra la knowledge-base del proyecto para detectar reglas de negocio ambiguas, ausentes o contradictorias (RN-AG/LE/PA/OS/CL/CO/SE/GL) y casos de borde faltantes en los escenarios verificables, antes de aprobar la propuesta. Usala siempre que haya que revisar, validar, auditar o aprobar un change o sus artefactos, justo antes de /opsx:propose, /opsx:apply o de arrancar la implementación, y cuando el usuario diga 'revisar contra la KB', 'chequear reglas de negocio', 'faltan casos borde' o 'aprobar la propuesta'. Gate de calidad obligatorio para cualquier change del roadmap CHANGES.md."
---

# sdd-change-review — Revisión de artefactos SDD contra la Knowledge Base

## Propósito

Un change de OpenSpec puede estar perfectamente escrito y aun así contradecir la fuente de verdad del dominio. Esta skill fuerza el cruce sistemático **artefactos del change ↔ knowledge-base** antes de aprobar una propuesta, para encontrar los tres problemas que más caros salen después de implementar:

1. **Reglas de negocio ausentes** — la KB dice algo (`RN-AG-05`, anticipación mínima de cancelación) y ninguno de los cuatro artefactos lo menciona.
2. **Reglas ambiguas o contradictorias** — el artefacto la reinterpreta, la debilita ("según corresponda", sin umbral) o la viola (p. ej. montos calculados en cliente = R8, o un UPDATE sobre auditoría = RN-SE-01).
3. **Casos de borde faltantes** — los escenarios solo cubren el happy path cuando R11 exige mínimo 2 casos por comportamiento, o se omiten los rechazos que la KB ya define (RN-GL-02: todo rechazo con mensaje accionable).

Detectar esto en la propuesta cuesta minutos; detectarlo en `/opsx:apply` cuesta un rework.

## Cuándo se activa (triggers)

Activala cuando:

- Vayas a **aprobar, validar o revisar** la proposal de un change (`openspec/changes/<name>/proposal.md`).
- Se pida expresamente: "revisar contra la KB", "chequear reglas de negocio", "validar el change", "¿falta algún caso borde?", "revisar los specs/tasks".
- Se complete un `/opsx:propose` y antes de pasar a `/opsx:apply` (gate previo a implementar).
- `CHANGES.md` liste el change y su sección `Leer antes` incluya revisar artefactos.
- Un cambio de diseño (design.md) proponga tocar reglas RN-* existentes o flujos de `knowledge-base/07_flujos_principales.md`.

NO la uses para: revisar código implementado (eso es `code-review`), refactorear specs ya archivados, ni proponer cambios nuevos a la KB sin que haya un change abierto (eso es materia de `/opsx:propose`).

## Entradas necesarias

| Entrada | Ruta | Para qué |
|---|---|---|
| Artefactos del change | `openspec/changes/<name>/{proposal.md, design.md, tasks.md}` + `specs/<capability>/spec.md` | Objeto de la revisión |
| Reglas de negocio | `knowledge-base/05_reglas_de_negocio.md` | Fuente de verdad de RN-* |
| Dominio y flujos | `knowledge-base/03_actores_y_roles.md`, `04_modelo_de_datos.md`, `06_funcionalidades.md`, `07_flujos_principales.md` | Contexto de rol/entidad/flujo |
| Decisiones y huecos | `knowledge-base/09_decisiones_y_supuestos.md`, `10_preguntas_abiertas.md` | Para no marcar como "ausente" lo que está abierto (PO-*) |
| Reglas duras | `AGENTS.md` / `CLAUDE.md` (R1–R13) | Cruce transversal |
| Índice del change | `CHANGES.md` (sección `Leer antes` del change) | Alcance y dependencias |

Si falta algún artefacto (p. ej. no existe `design.md`), repórtalo como hallazgo de severidad HIGH y continúa con lo disponible.

**Límites de datos**: esta revisión trabaja solo con texto de specs/reglas. Nunca adjuntes credenciales, `.env` ni datos reales de pacientes (R9, R13) en el reporte ni en los ejemplos — referenciar entidades por ID opaco o por código RN-*.

## Procedimiento paso a paso

### Paso 0 — Inventario de artefactos
Lista los archivos del change y confirma presencia de proposal, design, specs (delta) y tasks. Faltantes → hallazgo HIGH, seguir con lo que hay.

### Paso 1 — Entender el alcance
Lee `proposal.md` completo (Why / What Changes / Capabilities / Impact) y `tasks.md`. Anota:
- **Dominios RN involucrados**: Agenda (RN-AG), Lista de espera (RN-LE), Señas/cobros (RN-PA), Obra social (RN-OS), Clínica (RN-CL), Comunicación (RN-CO), Seguridad (RN-SE).
- **Roles/actores** que toca (de `03_actores_y_roles.md`) y **entidades** del `04_modelo_de_datos.md`.

### Paso 2 — Cargar la fuente de verdad
Lee `05_reglas_de_negocio.md` **completo** (es corto: ~60 líneas) y las secciones relevantes de los demás archivos de la KB. Lee también la sección `Leer antes` del change en `CHANGES.md` y R1–R13 en `AGENTS.md`. No trabajes de memoria: toda regla que cites debe salir de un archivo leído en este paso.

### Paso 3 — Matriz de trazabilidad RN ↔ artefactos
Para cada RN de los dominios del Paso 1, ubica dónde se cubre (proposal / design / spec / tasks) y asígnale un estado:

| Estado | Significado |
|---|---|
| `CUBIERTA` | Algún artefacto la implementa de forma explícita y correcta |
| `PARCIAL` | Se menciona pero omite un matiz (excepción, umbral, rol, estado) |
| `AUSENTE` | Ningún artefacto la contempla |
| `CONTRADICTORIA` | El artefacto la viola o la opone a otra regla |
| `AMBIGUA` | Se menciona con lenguaje sin umbral/condición verificable |

Reglas de lectura:
- **Contradicciones**: aplica el orden de precedencia `RN-GL-01` (SE > CL > PA > AG > CO). Si dos reglas chocan, manda la de mayor precedencia y el artefacto que sigue la menor está mal.
- **Ambigüedad**: frases como "según corresponda", "de forma oportuna", "apropiadamente", "cuando sea necesario" sin umbral configurable = AMBIGUA. La KB casi siempre da el umbral (p. ej. RN-AG-05: default 24 h).
- **No inventes reglas**: si el tema no está en la KB, clasifícalo como `AUSENTE EN KB` y verificá si es una pregunta abierta `PO-*` de `10_preguntas_abiertas.md` → va a "Consultas al PO", no se inventa la respuesta.

### Paso 4 — Casos de borde en los escenarios verificables
Por cada `### Requirement:` de los specs delta, auditá sus `#### Scenario:`:

1. **Mínimo 2 casos por comportamiento (R11)**: al menos un happy path y un edge/rechazo. Un Requirement con un solo escenario → hallazgo "caso borde faltante".
2. **Rechazo con mensaje accionable (RN-GL-02)**: si la regla puede rechazar algo, debe haber escenario del rechazo con mensaje en rioplatense.
3. **Idempotencia/duplicados (R8, RN-AG-08, RN-PA-03, RN-CO-02, RN-LE-02)**: si el flujo recibe webhooks, confirmaciones o reintentos, debe existir escenario de evento repetido.
4. **Aislamiento multi-tenant (R4)**: todo flujo que lea/escriba recursos debe tener escenario de tenant equivocado (o quedar explícito que el token manda).
5. **Máquina de estados (RN-AG-07)**: si el change mueve estados de turno, verificá que solo aparezcan transiciones del grafo cerrado.
6. **Casos borde del dominio típicos**: solapamiento concurrente (409), bloqueos/feriados (RN-AG-03), fuera de término (RN-AG-05), seña impaga (RN-PA-01), sin cobertura de OS (RN-OS-01), opt-in WA ausente/STOP (RN-CO-01), consentimiento sin firma (RN-CL-02), token vencido/inválido (RN-SE-03).

### Paso 5 — Cruce con reglas duras R1–R13
Filtrá solo las aplicables al alcance (no cites R5 en un change puramente backend). Las más frecuentes en revisión de artefactos: R4 (tenant del token), R6 (nada clínico en localStorage), R7 (soft delete, nunca hard delete), R8 (montos nunca en cliente; idempotencia de cobros/webhooks), R9 (PHI fuera de logs/URLs/errores), R11 (2 casos por comportamiento).

### Paso 6 — Clasificar hallazgos
A cada hallazgo asignal:
- **Tipo**: `regla-ausente` | `regla-ambigua` | `regla-contradictoria` | `caso-borde-faltante` | `artefacto-faltante`.
- **Severidad** (gobierno del proyecto):
  - `CRITICAL` — toca auth/salud/pagos/auditoría (RN-SE, RN-CL, RN-PA) o viola R7/R8/R9 → bloquea la aprobación.
  - `HIGH` — config, datos multi-tenant, reglas RN-AG/LE/CO con impacto en flujo.
  - `MEDIUM` — lógica de negocio con huecos verificables.
  - `LOW` — cosmético/claridad sin riesgo funcional.
- **Evidencia**: `archivo:línea` en el artefacto Y código `RN-*` / `R*` en la KB.
- **Sugerencia**: una acción concreta sobre el artefacto (qué agregar, dónde, con qué umbral).

### Paso 7 — Emitir el reporte y el veredicto
Usá el template de "Resultado esperado" sin alterar sus secciones. El veredicto se deriva de los hallazgos:
- `APROBAR` — sin hallazgos CRITICAL/HIGH.
- `APROBAR CON CAMBIOS` — hay MEDIUM/LOW (y HIGH no bloqueantes) con sugerencias accionables.
- `RECHAZAR` — cualquier CRITICAL, o HIGH que afecte reglas RN-* sin definición.

## Resultado esperado

Un reporte en markdown con **exactamente estas secciones** (guardarlo como archivo si el usuario lo pide; en caso contrario devolverlo inline):

```markdown
# Revisión SDD — <nombre-del-change>

**Fecha**: <AAAA-MM-DD> · **Artefactos**: proposal.md, design.md, specs/<cap>/spec.md, tasks.md
**KB consultada**: 05_reglas_de_negocio.md (+ <secciones leídas>) · **Reglas duras**: R1–R13

## Veredicto
APROBAR | APROBAR CON CAMBIOS | RECHAZAR — <justificación en una línea>

## Hallazgos
| # | Tipo | Severidad | Regla | Evidencia (artefacto:línea) | Problema | Sugerencia |
|---|------|-----------|-------|-----------------------------|----------|------------|
| 1 | regla-ausente | HIGH | RN-AG-05 | proposal.md:14 | No define anticipación mínima de cancelación | Agregar umbral (default 24 h, configurable por tenant) en Requirement de cancelación |

## Cobertura de reglas (matriz RN ↔ artefactos)
| RN | Estado | Dónde se cubre / por qué falta |
|----|--------|--------------------------------|
| RN-AG-05 | AUSENTE | — |

## Casos borde faltantes
- <Requirement> — falta escenario de <borde> (R11: mínimo 2 casos por comportamiento)

## Consultas al PO (KB abierta / ausente en KB)
- <tema> → ¿corresponde a PO-0x o hay que agregar la regla a la KB?

## Fuera de alcance
- <lo que no se revisó y por qué>
```

Reglas del reporte:
- Cada hallazgo cita **evidencia con archivo:línea** y **código RN-*/R***; sin evidencia, no es hallazgo.
- Todo texto del reporte en **español rioplatense** (RN-GL-02 aplica también acá) y sin PHI ni credenciales (R9, R13).
- La matriz debe cubrir **todas** las RN de los dominios del Paso 1, no solo las problemáticas.

## Criterios de revisión

Checklist para que el orquestador (o el usuario) valide el resultado de la skill:

- [ ] **Completitud**: matriz con todas las RN de los dominios involucrados (no solo hallazgos sueltos).
- [ ] **Trazabilidad**: cada hallazgo tiene `archivo:línea` + código `RN-*`/`R*` verificable en la KB.
- [ ] **Los 3 tipos cubiertos**: el reporte evalúa explícitamente ausentes, ambiguas/contradictorias y casos de borde.
- [ ] **Severidad coherente con el gobierno**: CRITICAL solo para auth/salud/pagos/auditoría; CRITICAL ⇒ veredicto RECHAZAR.
- [ ] **Veredicto presente** y consistente con la tabla de hallazgos.
- [ ] **Escenarios auditados contra R11**: cada Requirement con ≥2 casos (happy + edge).
- [ ] **Multi-tenant y reglas duras**: R4, R7, R8, R9 revisadas cuando el alcance aplica.
- [ ] **Sin datos prohibidos**: cero PHI, credenciales o `.env` en el reporte (R9, R13).
- [ ] **No se inventó regla**: los temas sin KB van a "Consultas al PO", no a "Hallazgos".
- [ ] **No se modificaron los artefactos**: la skill solo reporta; los fixes los aplica `/opsx:update-change` o el usuario.

## Ejemplo mínimo

**Entrada** (fragmento de un spec con un Requirement de cancelación):

```markdown
#### Scenario: Cancelación del turno
- **WHEN** el paciente cancela su turno
- **THEN** el sistema libera el horario y confirma la acción.
```

**Salida** (hallazgo que emitiría esta skill):

| # | Tipo | Severidad | Regla | Evidencia | Problema | Sugerencia |
|---|------|-----------|-------|-----------|----------|------------|
| 1 | regla-ambigua | HIGH | RN-AG-05 | spec.md:45 | No se valida la anticipación mínima (default 24 h); cancelar 5 min antes pasaría igual | Agregar Requirement de rechazo fuera de término → estado `ausente` o cargo, con mensaje en rioplatense (RN-GL-02) |
| 2 | caso-borde-faltante | MEDIUM | R11 | spec.md:44 | Un solo escenario (happy path) | Agregar escenario de cancelación fuera de plazo + escenario con token vencido (RN-SE-03) |
