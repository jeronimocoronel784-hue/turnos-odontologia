# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **turnos-odontologia** (SaaS multi-tenant de gestión odontológica AR: agenda, HC/odontograma, caja/señas/MP, OS, WA).
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>` (ej. `/opsx:propose C-01-foundation-setup`).
4. Al terminar el change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` en este archivo.

---

## Árbol de dependencias

```
C-01 foundation-setup
└── C-02 core-models-multitenant
    └── C-03 auth-rbac-tokens                     ← desbloquea TODO lo demás
          ├── C-04 catalogo-configuracion          [Agente A]
          ├── C-05 pacientes                       [Agente B]
          │     └── C-06 agenda-turnos ─────────── ← necesita C-04 + C-05
          │           ├── C-07 lista-espera                 [Agente A]
          │           ├── C-08 comunicaciones-mensajeria     [Agente B]
          │           ├── C-09 historia-clinica-odontograma [Agente A]
          │           │     └── C-10 presupuestos-planes (+ C-04)
          │           ├── C-11 caja-senas                   [Agente C]
          │           │     └── C-12 mercadopago-webhooks
          │           └── C-13 obras-sociales-liquidacion (+ C-04)
          │                 └── C-14 auditoria-exportacion (+ C-11)
          │                       └── C-17 frontend-caja-os-admin ← cierre + polish final
          ├── C-15 reserva-publica-pwa (+ C-09, C-12)
          └── C-16 frontend-agenda-clinica (+ C-08, C-10)
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un grupo pueden ejecutarse en paralelo.

```
GATE 0: ninguna
  → C-01 foundation-setup (solo)

GATE 1: C-01 ✓
  → C-02 core-models-multitenant (solo)

GATE 2: C-02 ✓
  → C-03 auth-rbac-tokens (solo)

GATE 3: C-03 ✓                          ← FORK (2 paralelos)
  → C-04 catalogo-configuracion          [Agente A]
  → C-05 pacientes                       [Agente B]

GATE 4: C-04 + C-05 ✓
  → C-06 agenda-turnos (solo — une ambas ramas)

GATE 5: C-06 ✓                          ← PRIMER FORK GRANDE (4 paralelos)
  → C-07 lista-espera                    [Agente A]
  → C-08 comunicaciones-mensajeria       [Agente B]
  → C-09 historia-clinica-odontograma    [Agente A — si C-07 ✓]
  → C-11 caja-senas                      [Agente C]

GATE 6: C-09 + C-11 ✓                   ← FORK (3 paralelos)
  → C-10 presupuestos-planes             [Agente B]
  → C-12 mercadopago-webhooks            [Agente C]
  → C-13 obras-sociales-liquidacion      [Agente A]

GATE 7: GATE 6 completo ✓               ← FORK frontend + transversal
  → C-14 auditoria-exportacion           [Agente A]
  → C-15 reserva-publica-pwa             [Agente C]
  → C-16 frontend-agenda-clinica         [Agente B]

GATE 8: C-14 ✓
  → C-17 frontend-caja-os-admin (solo — cierre + polish visual final)
```

### Camino crítico (9 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-05 → C-06 → C-09 → C-11 → C-12 → C-15
```

> Reserva online con seña cobrada por MP (Flujos 1+4) es el corte del MVP: sin C-15 no hay captura 24/7, sin C-12 no hay seña. C-16/C-17 cierran la operación interna pero van fuera del mínimo.

### Plan óptimo con 3 agentes

```
Paso │ Agente A (Backend Core) │ Agente B (Backend Aux)  │ Agente C (Dinero+Frontend)
─────┼─────────────────────────┼─────────────────────────┼─────────────────────────────
  1  │ C-01 foundation-setup   │            —            │              —
  2  │ C-02 core-models        │            —            │              —
  3  │ C-03 auth-rbac          │            —            │              —
  4  │ C-04 catalogo           │ C-05 pacientes          │              —
  5  │ C-06 agenda-turnos      │            —            │              —
  6  │ C-07 lista-espera       │ C-08 comunicaciones     │ C-11 caja-senas
  7  │ C-09 clinica-odontograma│ C-10 presupuestos       │ C-12 mercadopago
  8  │ C-13 obras-sociales     │ C-16 front-agenda-clin. │ C-15 reserva-publica-pwa
  9  │ C-14 auditoria-export   │            —            │              —
 10  │ C-17 front-caja-os-admin│            —            │              —
```

---

## FASE 0 — Cimientos

### [C-01] `foundation-setup`
- **Estado**: `[ ]` pendiente
- **Scope**: Scaffolding completo del monorepo + infraestructura base
  - Estructura `backend/app/{domain,application,infrastructure,api,workers,tests}` + `frontend/src/{features,shared,pages}` según `08_arquitectura_propuesta.md` §Estructura
  - `backend/`: FastAPI app mínima con `GET /api/health`, SQLAlchemy + Alembic inicializado, `shared/` con settings (Pydantic), logger, db session, exceptions con mensajes en rioplatense (RN-GL-02)
  - `frontend/`: Vite + React + TypeScript + PWA base (manifest + service worker vacío), React Router, TanStack Query, Tailwind
  - `docker-compose.yml`: api + postgres + redis + worker (+ mailhog dev)
  - `.env.example` con las 11 variables de §08 (DATABASE_URL, REDIS_URL, JWT_SECRET, MP_*, WA_*, SMTP_URL, FRONT_URL, TENANT_SLUG_DEFAULT); secretos solo `${VAR}`, jamás hardcodeados (RN-SE-04)
  - CI GitHub Actions: jobs paralelos backend (pytest) y frontend (tsc + build)
- **Dependencias**: ninguna
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios
  - `knowledge-base/08_arquitectura_propuesta.md` §Variables de entorno
  - `knowledge-base/02_descripcion_general.md` §Stack

---

### [C-02] `core-models-multitenant`
- **Estado**: `[ ]` pendiente
- **Scope**: Entidades raíz multi-tenant + auditoría append-only + seed piloto
  - Modelos: `Tenant` (con `politicas` jsonb), `Usuario` (rol enum dueno/recepcion/odontologo, email único por tenant, matrícula obligatoria si odontólogo), `Auditoria` (solo INSERT+SELECT, retención 5 años)
  - `TenantMixin` (`tenant_id` FK en toda tabla de negocio), `AuditMixin` (`created_at/updated_at`), `BaseRepository[T]` + `UnitOfWork`
  - Migración 001: tablas `tenant`, `usuario`, `auditoria` + índices (`slug`, (`tenant_id`,`email`))
  - Seed mínimo: 1 tenant piloto + 1 usuario Dueño + matriz de permisos base
  - Tests: aislamiento multi-tenant (tenant A no ve datos de B), constraint email/tenant, auditoría rechaza UPDATE/DELETE
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Tenant
  - `knowledge-base/04_modelo_de_datos.md` §Usuario
  - `knowledge-base/04_modelo_de_datos.md` §Auditoria
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-01

---

## FASE 1 — Acceso

### [C-03] `auth-rbac-tokens`
- **Estado**: `[ ]` pendiente
- **Scope**: Autenticación JWT + RBAC por matriz + tokens públicos para paciente sin login
  - `POST /api/auth/login` — JWT access corto + refresh con rotación (reúso = revocación), rate limiting 5/60s por IP+email
  - `POST /api/auth/refresh`, `POST /api/auth/logout` (blacklist), `GET /api/auth/me`
  - Refresh en cookie HttpOnly (secure, samesite=lax); claims JWT: `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`
  - `PermissionContext`: `require_role()`, guards por recurso según matriz §03 enforced en API (no solo UI); Dueño con doble rol operativo
  - Tokens públicos `token_gestion` (uuid, entropía + vencimiento) para rutas sin login: `/reservar/:slug`, `/mis-turnos/:token`, `/pagar/:token`, `/firmar/:token`, `/lista-espera/:token` (RN-SE-03)
  - Tests: login/refresh/logout, token expirado, rate limit, matriz RBAC completa (recepción no edita clínica, odontólogo no reabre cierres), token ajeno no expone datos de terceros
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-02
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-03

---

## FASE 2 — Dominio base

> C-04 y C-05 en paralelo (no se referencian). C-06 los une a ambos.

### [C-04] `catalogo-configuracion`
- **Estado**: `[ ]` pendiente
- **Scope**: Catálogo clínico-administrativo que todo turno referencia
  - Modelos: `Sillon` (nombre único por tenant+sucursal), `Prestacion` (`duracion_min>0`, `requiere_sena` ⇒ `monto_sena>0`, flag `invasiva`), `CoberturaOS` (OS × prestación × arancel × copago × vigencia)
  - Endpoints CRUD admin: `/api/admin/sillones`, `/api/admin/prestaciones`, `/api/admin/coberturas`, `PATCH /api/admin/tenant/politicas` (anticipación mínima, seña default, cancelación)
  - Migración 002: tablas `sillon`, `prestacion`, `cobertura_os` + alter `tenant.politicas`
  - Seed: Sillón "Box 1" + 5 prestaciones (limpieza 30', consulta 20', arreglo 45', endodoncia 60', extracción 45') con precios y flags seña/invasiva
  - Tests: CRUD por rol (recepción solo lectura en config), constraints de seña/duración, vigencia de aranceles
- **Dependencias**: C-03
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Sillon
  - `knowledge-base/04_modelo_de_datos.md` §Prestacion
  - `knowledge-base/04_modelo_de_datos.md` §CoberturaOS / Liquidacion
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos

---

### [C-05] `pacientes`
- **Estado**: `[ ]` pendiente
- **Scope**: Registro de pacientes sin login + opt-in WA
  - Modelo `Paciente`: (`tenant_id`,`dni`) único, `optin_wa` default false, `obra_social_id` + `nro_afiliado` nullables
  - Endpoints CRUD: `/api/pacientes` (búsqueda por DNI/teléfono, alta implícita en reserva con `get_or_create` por DNI), `PATCH /api/pacientes/:id/optin`
  - Migración 003: tablas `paciente`, `ficha_clinica` (vacía, 1:1 — contenido clínico en C-09)
  - Tests: unicidad DNI por tenant, WA automático bloqueado sin opt-in (RN-CO-01), baja STOP corta envíos
- **Dependencias**: C-03
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Paciente
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CO-01
  - `knowledge-base/10_preguntas_abiertas.md` (paciente sin login — resuelta)

---

### [C-06] `agenda-turnos`
- **Estado**: `[ ]` pendiente
- **Scope**: Núcleo del sistema — máquina de estados del turno + anti-solapamiento + reserva pública
  - Modelo `Turno` con estados `pendiente → confirmado → presente → finalizado` y ramas `cancelado|ausente|reprogramado`; `token_gestion` único; `sobreturno` bool + motivo; `fin = inicio + duracion_prestacion` (RN-AG-01/02/04/07)
  - Modelo `Bloqueo` (profesional/sillón, desde/hasta, motivo); slots cubiertos no reservables (RN-AG-03)
  - Anti-solapamiento por (`profesional_id`, rango) y (`sillon_id`, rango) con exclusion constraint; 409 con slots alternativos + mensaje rioplatense (RN-GL-02)
  - Endpoints internos: `GET /api/agenda` (día/semana por profesional y sillón), `POST /api/turnos`, reprogramación 1-clic (original → `reprogramado` + nuevo con `turno_origen_id`, RN-AG-06), sobreturno explícito auditado
  - Endpoints públicos (Flujo 1): `GET/POST /reservar/:slug` (slots reales, sin doble reserva), `/mis-turnos/:token` (ver/confirmar/cancelar/reprogramar); crea Paciente + Turno `pendiente` + Seña `pendiente` si exige
  - Migración 004: tablas `turno`, `bloqueo` + índices (`tenant_id`,`profesional_id`,`inicio`), (`tenant_id`,`sillon_id`,`inicio`), `token_gestion`
  - Cada transición escribe en Auditoría (RN-SE-01)
  - Tests: solapamiento profesional y sillón, bloqueo no reservable, grafo de estados cerrado, reprogramación con historial, 409 con alternativas
- **Dependencias**: C-04, C-05
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Turno (Cita)
  - `knowledge-base/04_modelo_de_datos.md` §Bloqueo
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Agenda (RN-AG)
  - `knowledge-base/07_flujos_principales.md` §Flujo 1: Reserva online con seña

---

## FASE 3 — Flujos asistenciales

> C-07, C-08, C-09, C-11 en paralelo tras C-06. C-10 espera a C-09 (consentimiento).

### [C-07] `lista-espera`
- **Estado**: `[ ]` pendiente
- **Scope**: Lista de espera que rellena huecos liberados (Flujo 6)
  - Modelo `ListaEspera`: orden (`prioridad`,`created_at`), estados `activa → avisada → colocada | baja`, `canal_aviso`
  - Al liberarse slot: primera entrada compatible → aviso WA/email con ventana de respuesta → acepta por token crea Turno y marca `colocada`; vence → siguiente (RN-LE-01/02/03)
  - Endpoints: `/api/lista-espera` CRUD + `/lista-espera/:token` (anotarse/darse de baja, público)
  - Migración 005: tabla `lista_espera`; idempotencia un aviso por hueco por entrada (`idempotency_key`)
  - Tests: orden prioridad/antigüedad, doble aceptación simultánea (gana primera), ventana vencida rota al siguiente
- **Dependencias**: C-06
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §ListaEspera
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Lista de espera (RN-LE)
  - `knowledge-base/07_flujos_principales.md` §Flujo 6: Lista de espera

---

### [C-08] `comunicaciones-mensajeria`
- **Estado**: `[ ]` pendiente
- **Scope**: Outbox + worker Redis + WA Business API + email + webhooks (Flujo 2)
  - Modelos `Mensaje` (outbox con `idempotency_key` único, estados `pendiente→enviado→entregado→leido|fallido`, `programado_para`) y `Plantilla` versionada
  - Worker Redis: toma vencidos, verifica `optin_wa`, envía por WA Cloud API, reintentos con backoff, log visible; sin doble recordatorio por (`turno`,plantilla,ventana) (RN-CO-02/03)
  - Webhook `POST /webhooks/whatsapp` (verificación + firma HMAC): botón Confirmar → Turno `confirmado` idempotente (RN-AG-08); STOP = baja opt-in
  - Recordatorio 24h programable por plantilla; email vía SMTP como fallback
  - Migración 006: tablas `mensaje`, `plantilla` + seed 5 plantillas (confirmación, recordatorio 24h, cancelación, hueco lista de espera, seña pendiente)
  - Tests: webhook repetido sin doble transición, sin opt-in no envía (omisión logueada), reintento no duplica, firma inválida rechazada
- **Dependencias**: C-06
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Mensaje / Recordatorio (outbox)
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Comunicación (RN-CO)
  - `knowledge-base/07_flujos_principales.md` §Flujo 2: Confirmación WA
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados (Outbox + Idempotency)

---

### [C-09] `historia-clinica-odontograma`
- **Estado**: `[ ]` pendiente
- **Scope**: Ficha + odontograma FDI inmutable + consentimientos con firma (Flujo 3)
  - `FichaClinica` 1:1 por paciente (edición solo rol clínico genera Evolución + Auditoría; recepción solo lectura, RN-CL-01/03)
  - `Odontograma` cabecera + `PiezaEvento` (FDI 11–48, superficie enum, evento enum, `turno_id` origen); historial inmutable — cambios son nuevos eventos; adjuntos RX/fotos/PDF
  - `Consentimiento`: texto versionado + `firma_hash`, firma presencial o por token (`/firmar/:token`); prestación `invasiva` sin firma bloquea `presente` con mensaje claro (RN-CL-02)
  - Endpoints: `/api/pacientes/:id/ficha`, `/evoluciones`, `/api/odontograma/:pacienteId` (+ eventos, historial por pieza), `/api/consentimientos` (+ firmar)
  - Migración 007: tablas `evolucion`, `odontograma`, `pieza_evento`, `consentimiento`, `adjunto`
  - Tests: edición HC crea evolución (nunca UPDATE destructivo), FDI inválida rechazada, `presente` bloqueado sin consentimiento en invasiva, recepción no edita clínica
- **Dependencias**: C-05, C-06
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §FichaClinica / Anamnesis
  - `knowledge-base/04_modelo_de_datos.md` §Odontograma (FDI)
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Clínica (RN-CL)
  - `knowledge-base/07_flujos_principales.md` §Flujo 3: Atención con HC

---

### [C-10] `presupuestos-planes`
- **Estado**: `[ ]` pendiente
- **Scope**: Presupuestos y planes de tratamiento vinculados a citas
  - Modelos `Presupuesto` (estados `borrador→presentado→aceptado|rechazado→en_curso→finalizado`), `PresupuestoItem` (`a_cargo = precio*cantidad − cobertura_os`), vínculo N–N con Turnos
  - Aceptación con invasiva exige consentimiento firmado (chequea C-09, RN-CL-04); cálculo `a_cargo` con cobertura vigente o particular (RN-OS-01)
  - Endpoints: `/api/presupuestos` CRUD + items + `/aceptar`, `/api/presupuestos/:id/turnos` (próxima cita del plan)
  - Migración 008: tablas `presupuesto`, `presupuesto_item`, `presupuesto_turno`
  - Tests: cálculo a cargo vs OS, aceptar invasiva sin firma rechazado, items vinculados a turnos hasta el alta
- **Dependencias**: C-04, C-06, C-09
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Presupuesto / PlanTratamiento
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CL-04
  - `knowledge-base/05_reglas_de_negocio.md` §RN-OS-01
  - `knowledge-base/06_funcionalidades.md` §US-022

---

## FASE 4 — Dinero

> C-11 corre en paralelo con la FASE 3 (solo necesita C-06). C-12 y C-13 esperan a C-11 y C-04/C-06.

### [C-11] `caja-senas`
- **Estado**: `[ ]` pendiente
- **Scope**: Caja diaria + señas atadas al turno (sin MP — eso es C-12)
  - Modelo `Seña`: 1 activa por turno, estados `pendiente→cobrada→aplicada|devuelta` + `vencida`; turno con seña exigible impaga no confirma (RN-PA-01/02/04)
  - Modelos `MovimientoCaja` (ingreso/egreso, medio efectivo/débito/crédito/transf/mp, vínculo turno/cobro) y `CierreCaja` (total sistema vs contado, diferencia visible, inmutable cerrado; reapertura solo Dueño + Auditoría)
  - Reserva con `requiere_sena` auto-genera Seña `pendiente` con vencimiento; vencida impaga → turno cancelado + slot liberado + aviso a lista de espera (Flujo 1 paso 6)
  - Cálculo al cobrar: `precio − cobertura_OS − seña_cobrada = saldo` (Flujo 4)
  - Endpoints: `/api/senas`, `/api/caja/movimientos`, `/api/caja/cierre` (abrir/cerrar/reabrir)
  - Migración 009: tablas `sena`, `movimiento_caja`, `cierre_caja`
  - Tests: grafo de seña, cancelación en/fuera de término (devuelta vs retenida/aplicada), cierre inmutable, reapertura solo Dueño auditada
- **Dependencias**: C-06
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Sena
  - `knowledge-base/04_modelo_de_datos.md` §Caja / Movimiento
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Señas y cobros (RN-PA)
  - `knowledge-base/07_flujos_principales.md` §Flujo 4: Cobro con seña aplicada

---

### [C-12] `mercadopago-webhooks`
- **Estado**: `[ ]` pendiente
- **Scope**: Cobros Mercado Pago con idempotencia + conciliación diaria
  - Preferencia MP por seña (`external_reference = seña.id`, `expiration_date_to = vence_at`); link/QR expuesto en mensajes (C-08) y `/pagar/:token`
  - Webhook `POST /webhooks/mercadopago`: persistir payload crudo → verificar firma → procesar idempotente por `mp_payment_id` único (repetido = 200 sin efecto, RN-PA-03)
  - Mapeo estados MP → Seña/Cobro (`approved→cobrada`, `pending→pendiente`, `rejected→vencida`, `refunded→devuelta`); discrepancia monto/estado → revisión manual, nunca auto-cierre (RN-PA-05)
  - Job diario de conciliación contra API MP + vista de discrepancias; devoluciones solo vía API con motivo + auditoría
  - Modelo `CobroMP` (`mp_payment_id` único, `estado_conciliacion`); Migración 010: tabla `cobro_mp`
  - Credenciales sandbox por tenant en config (nunca en código, RN-SE-04)
  - Tests: webhook duplicado, pago post-vencimiento (discrepancia + ofrecer aplicar/devolver), firma inválida, conciliación marca discrepancia
- **Dependencias**: C-11
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/11_pagos_mercadopago.md` (completo — modelo, idempotencia, casos borde)
  - `knowledge-base/04_modelo_de_datos.md` §CobroMP
  - `knowledge-base/05_reglas_de_negocio.md` §RN-PA-03
  - `knowledge-base/05_reglas_de_negocio.md` §RN-PA-05

---

### [C-13] `obras-sociales-liquidacion`
- **Estado**: `[ ]` pendiente
- **Scope**: Cobertura calculada en el turno + liquidación exportable con débitos (Flujo 5)
  - Cálculo en agenda/cobro: `a_cargo = precio − cobertura` por arancel vigente; sin cobertura vigente → particular; arancel vencido alerta y usa vigente con aviso (RN-OS-01)
  - Modelos `LiquidacionOS` (`borrador→presentada→pagada|con_debitos`, por OS/período `yyyymm`) + detalle por turno (reclamado/reconocido/motivo débito)
  - Solo turnos `finalizado` entran; un turno en una sola liquidación abierta por OS/período (constraint, RN-OS-02); v1 sin presentación electrónica (RN-OS-03)
  - Endpoints: `/api/os/cobertura` (lookup), `/api/liquidaciones` CRUD + `/cerrar` + `/exportar` (CSV/JSON)
  - Migración 011: tablas `liquidacion_os`, `liquidacion_detalle`
  - Tests: turno no finalizado rechazado, doble liquidación del mismo turno rechazada, export CSV/JSON con débitos
- **Dependencias**: C-04, C-06
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §CoberturaOS / Liquidacion
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Obra social (RN-OS)
  - `knowledge-base/07_flujos_principales.md` §Flujo 5: Liquidación OS
  - `knowledge-base/06_funcionalidades.md` §US-040 / US-041

---

## FASE 5 — Transversal

### [C-14] `auditoria-exportacion`
- **Estado**: `[ ]` pendiente
- **Scope**: Trail consultable + exportación 1-clic + página legal (Flujo 7)
  - `GET /api/auditoria` (filtros entidad/período/actor, solo Dueño) sobre tabla append-only
  - Exportación CSV/JSON de agenda, pacientes, caja, liquidaciones en 1 clic; job asíncrono con descarga si el volumen es grande
  - Intento de borrar auditoría rechazado por permiso + constraint (test explícito)
  - Página legal pública (Ley 25.326 + HCE) + exportación de datos del paciente (RN-SE-02)
  - Sin migración (lee tablas existentes); middleware/interceptor de auditoría si aún no centralizado en changes previos
  - Tests: matriz (recepción/odontólogo sin acceso), export contiene solo datos del tenant, auditoría inmutable
- **Dependencias**: C-11, C-13
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Auditoria (append-only)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-01
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-02
  - `knowledge-base/07_flujos_principales.md` §Flujo 7: Auditoría y exportación

---

## FASE 6 — Frontend PWA

> Backend antes que frontend acoplado: las 3 vistas esperan a sus endpoints. C-15/C-16 en paralelo; C-17 cierra con admin + polish visual final.

### [C-15] `reserva-publica-pwa`
- **Estado**: `[ ]` pendiente
- **Scope**: PWA pública del paciente (móvil-first) + shell offline
  - `features/reserva-publica`: prestaciones → profesionales → slots reales → formulario (nombre+DNI+teléfono+OS) → link/QR MP si exige seña → `token_gestion`
  - Páginas por token: `/mis-turnos/:token`, `/lista-espera/:token`, `/pagar/:token` (redirect MP), `/firmar/:token` (consentimiento)
  - `shared/pwa`: manifest instalable, service worker, cola offline (reserva encolada si internet inestable, US-063) con mensajes rioplatenses de estado
  - Rate-limit y validación estricta espejando backend; español rioplatense en toda la UI
  - Tests: flujo reserva→pago→confirmación (mock MP/WA), token ajeno no muestra datos, offline encola y sincroniza
- **Dependencias**: C-09, C-12
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/07_flujos_principales.md` §Flujo 1: Reserva online con seña
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/06_funcionalidades.md` §US-002
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad (tokens públicos)

---

### [C-16] `frontend-agenda-clinica`
- **Estado**: `[ ]` pendiente
- **Scope**: PWA interna — agenda + pacientes + clínica + comunicaciones
  - `features/agenda`: vista día/semana por profesional y sillón, estados, bloqueos, sobreturnos marcados, reprogramación 1-clic, reflejo en vivo de confirmaciones WA (US-001)
  - `features/pacientes`: ficha, búsqueda DNI/teléfono, opt-in WA; `features/clinica`: anamnesis/evolución, odontograma FDI interactivo, presupuestos del plan, firma de consentimiento en el acto
  - `features/comunicaciones`: log de mensajes por turno, reenvío manual, editor de plantillas (recepción: reenviar; dueño: CRUD)
  - Guards de rol en UI espejando matriz §03 (recepción no ve edición clínica) + política de cancelación configurable (US-011)
  - Tests: guards por rol, agenda renderiza bloqueos/sobreturnos, odontograma marca eventos por pieza/superficie
- **Dependencias**: C-08, C-10
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-001 / US-003
  - `knowledge-base/06_funcionalidades.md` §US-020 / US-021
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos
  - `knowledge-base/07_flujos_principales.md` §Flujo 2 / Flujo 3

---

### [C-17] `frontend-caja-os-admin`
- **Estado**: `[ ]` pendiente
- **Scope**: PWA interna — caja/OS/admin + dashboards + polish visual final del producto
  - `features/caja`: movimientos por medio, cierre con diferencia visible, historial; `features/os`: padrón, cobertura al agendar, liquidación con débitos + export
  - `features/admin`: configuración tenant/prestaciones/precios/horarios/políticas, usuarios/roles, auditoría consultable, exportación 1-clic (US-050/051)
  - Importación Excel de pacientes/prestaciones para onboarding en 1 día (US-063) + cierre de caja y reportes del dueño
  - Restyle/UI polish final sobre producto estable: tokens de diseño, estados vacíos/error en rioplatense, responsive móvil-first verificado
  - Tests: cierre muestra diferencia, reapertura solo Dueño en UI, import Excel mapea pacientes, dashboards leen datos reales
- **Dependencias**: C-13, C-14
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-030 / US-041
  - `knowledge-base/06_funcionalidades.md` §US-050 / US-051
  - `knowledge-base/07_flujos_principales.md` §Flujo 4 / Flujo 5
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios (frontend)

---
