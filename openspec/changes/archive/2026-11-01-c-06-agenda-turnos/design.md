# Design

## Context

`C-06 agenda-turnos` une las ramas de catálogo (`C-04`: `Sillon`, `Prestacion`, políticas en `Tenant.politicas`) y pacientes (`C-05`: `Paciente`, `get_or_create_paciente`) sobre la base de autenticación, RBAC y tokens públicos (`C-03`: `TokenGestion`, `crear_token_gestion`, `validar_token_gestion`). Ver `proposal.md` para motivación y `specs/agenda-turnos/spec.md` para el contrato de comportamiento.

## UI Mockups

Decision: no (no UI) — este change es exclusivamente de dominio, persistencia y API REST backend; la UI de agenda y reserva pública corresponde a `C-15` y `C-16`.

## Goals / Non-Goals

**Goals:**
- Garantizar la integridad del grafo cerrado de estados del turno (RN-AG-07) y la auditoría append-only en cada transición (RN-SE-01).
- Impedir dobles reservas sobre el mismo profesional o sillón salvo `sobreturno=True` explícito con motivo (RN-AG-01, RN-AG-04) y bloquear cualquier reserva sobre rangos cubiertos por `Bloqueo` (RN-AG-03).
- Proveer respuestas `409 Conflict` accionables en español rioplatense acompañadas de slots alternativos cercanos cuando un horario no está disponible (RN-GL-02).
- Habilitar el Flujo 1 (reserva online por `slug` y autogestión por `token_gestion` opaco) sin exponer PHI ni permitir acceso cruzado entre turnos o consultorios (RN-SE-03, R9).

**Non-Goals:**
- Tabla `Sena` y movimientos de caja (pertenecen a `C-11`; en `C-06` el turno expone el contrato `sena_requerida` / `sena_cobrada` para hacer cumplir RN-PA-01 sin acoplarse prematuramente a Mercado Pago).
- Envío efectivo por WhatsApp Cloud API o worker Redis (pertenecen a `C-08`).
- Verificación de `Consentimiento` firmado al pasar a `presente` en prestaciones invasivas (se enchufa en `C-09` cuando se introduce el modelo `Consentimiento`).

## Decisions

### D1. Modelos `Turno` y `Bloqueo` y migración `005_agenda_turnos`
- **`Turno` (`turno`)**:
  - `id (GUID PK)`, `tenant_id (GUID FK tenant.id)`, `paciente_id (GUID FK paciente.id)`, `profesional_id (GUID FK usuario.id)`, `sillon_id (GUID FK sillon.id)`, `prestacion_id (GUID FK prestacion.id)`.
  - `inicio (DateTime timezone=True)`, `fin (DateTime timezone=True)`.
  - `estado (String(24))`: enum `EstadoTurno` (`pendiente`, `confirmado`, `presente`, `finalizado`, `cancelado`, `ausente`, `reprogramado`).
  - `origen (String(24))`: enum `OrigenTurno` (`presencial`, `online`, `whatsapp`).
  - `sobreturno (Boolean, default=False)` + `observaciones (Text, nullable)` (obligatorio cuando `sobreturno=True`) + `motivo_cancelacion (Text, nullable)`.
  - `turno_origen_id (GUID FK turno.id, nullable)` para trazabilidad de reprogramación (RN-AG-06).
  - `sena_cobrada (Boolean, default=False)` para hacer cumplir RN-PA-01 (`requiere_sena` impaga bloquea transición a `confirmado`) hasta que `C-11` conecte la entidad `Sena`.
  - Check constraints: `ck_turno_rango_valido` (`fin > inicio`), `ck_turno_sobreturno_motivo` (`(NOT sobreturno) OR (observaciones IS NOT NULL AND length(trim(observaciones)) > 0)`).
- **`Bloqueo` (`bloqueo`)**:
  - `id (GUID PK)`, `tenant_id (GUID FK tenant.id)`, `profesional_id (GUID FK usuario.id, nullable)`, `sillon_id (GUID FK sillon.id, nullable)`, `desde (DateTime timezone=True)`, `hasta (DateTime timezone=True)`, `motivo (String(32))` (`feriado`, `vacaciones`, `manual`, `administrativo`), `descripcion (Text, nullable)`, `created_by (GUID FK usuario.id, nullable)`.
  - Check constraints: `ck_bloqueo_rango_valido` (`hasta > desde`), `ck_bloqueo_objetivo_no_nulo` (`profesional_id IS NOT NULL OR sillon_id IS NOT NULL`).

### D2. Anti-solapamiento portable (PostgreSQL + SQLite de tests) y sugerencia de slots
- **Elección**: Validación transaccional en capa de aplicación (`verificar_disponibilidad`) consultando solapamientos `[inicio, fin)` (`existente.inicio < nuevo_fin AND existente.fin > nuevo_inicio`) sobre:
  1. `Bloqueo` del mismo `tenant_id` que afecte al `profesional_id` o al `sillon_id` (o bloqueos generales si ambos coinciden). Ningún turno —ni siquiera con `sobreturno=True`— puede pisar un `Bloqueo` (RN-AG-03).
  2. `Turno` en estados activos que ocupan agenda (`pendiente`, `confirmado`, `presente`) para el mismo `profesional_id` o el mismo `sillon_id`, salvo que el nuevo turno tenga `sobreturno=True` y motivo explícito (RN-AG-01, RN-AG-04).
- **Alternativas en 409 (`ConflictoDisponibilidad`)**: Cuando hay choque de horario o bloqueo, se calculan hasta 5 slots libres próximos de duración `duracion_min` para ese profesional y sillón dentro de la jornada (`08:00` a `18:00` UTC/local del día solicitado y siguientes) y se devuelven en el body del `409 Conflict` (`{"detail": "...", "slots_alternativos": [...]}`) manteniendo compatibilidad con el contrato general `detail` en rioplatense (RN-GL-02).

### D3. Grafo cerrado de estados (RN-AG-07) y regla de seña (RN-PA-01)
- Mapa declarativo `TRANSICIONES_PERMITIDAS`:
  - `pendiente` → `{confirmado, cancelado, ausente, reprogramado}`
  - `confirmado` → `{presente, cancelado, ausente, reprogramado}`
  - `presente` → `{finalizado}`
  - `finalizado`, `cancelado`, `ausente`, `reprogramado` → `set()` (estados terminales).
- Si el estado destino es `confirmado` y la `Prestacion` asociada tiene `requiere_sena=True` pero `turno.sena_cobrada` es `False`, se rechaza con `409 Conflict` explicando que falta acreditar la seña (RN-PA-01).
- Confirmación repetida sobre un turno ya `confirmado` por canal público/WA es idempotente: devuelve `200 OK` sin duplicar transición ni auditoría (RN-AG-08).

### D4. Reprogramación en 1 clic (RN-AG-06) y política de anticipación (RN-AG-05)
- Reprogramar nunca muta `inicio`/`fin` del turno original:
  1. Verifica que el turno original esté en `pendiente` o `confirmado`.
  2. En canal público (`/mis-turnos/{token}`), verifica que falten al menos `politicas["cancelacion_hs"]` (default 24 h) antes de `turno.inicio`; si está fuera de término, devuelve `409 Conflict` con mensaje rioplatense (RN-AG-05).
  3. Valida disponibilidad del nuevo rango `[nuevo_inicio, nuevo_fin)`.
  4. Cambia el turno original a `reprogramado` y crea el nuevo `Turno` en `pendiente` con `turno_origen_id = original.id` (conservando `sena_cobrada` si ya estaba abonada), emitiendo un nuevo `TokenGestion` para el nuevo turno y auditando ambos cambios en la misma transacción.

### D5. Token público de gestión (RN-SE-03)
- En lugar de exponer un UUID predecible en la URL, `POST /reservar/{slug}` (y `POST /api/turnos`) emite un `TokenGestion` mediante `crear_token_gestion(session, tenant_id=..., recurso="turno", recurso_id=str(turno.id), vence_at=turno.fin + timedelta(days=7))`.
- Para encontrar un turno desde `/mis-turnos/{token}` sin que el cliente envíe `tenant_id` ni `turno_id`, se agrega un helper en `tokens_publicos.py` (`resolver_token_gestion_recurso(session, token=token, recurso="turno")`) que busca por `token_hash` (único con índice), verifica vigencia/revocación en tiempo constante y retorna la fila `TokenGestion` con su `tenant_id` y `recurso_id` verificados.

## Risks / Trade-offs

- **[Risk] Concurrencia en reservas simultáneas para el mismo slot** → **Mitigation**: verificación de solapamiento inmediatamente antes del `flush` dentro de la misma transacción + índices compuestos `(tenant_id, profesional_id, inicio)` y `(tenant_id, sillon_id, inicio)`.
- **[Risk] Acoplamiento con `C-11` (Señas)** → **Mitigation**: el flag `sena_cobrada` en `Turno` y los metadatos calculados desde `Prestacion` (`requiere_sena`, `monto_sena`) permiten cumplir y testear RN-PA-01 hoy y ser actualizados directamente por `C-11` cuando se cree la tabla `sena`.

## Migration Plan

1. Ejecutar `alembic upgrade head` (aplica `005_agenda_turnos` creando `turno` y `bloqueo` con sus índices y `GRANT`s a `turnos_app`).
2. Para rollback, `alembic downgrade -1` revoca permisos en PostgreSQL y elimina `turno` y `bloqueo` en orden.
