# Modelo de Datos

## Dominios

- **Tenancy/config**: Tenant/Consultorio, Usuario, Sillón/Box, Prestación, Cobertura OS.
- **Agenda**: Turno/Cita (con máquina de estados), Bloqueo, Sobreturno, ListaEspera.
- **Clínica**: Paciente, FichaClínica/Anamnesis, Odontograma (piezas/eventos FDI), Evolución, Presupuesto/PlanTratamiento, Consentimiento.
- **Finanzas**: Caja/Movimiento, Cierre, Seña, Cobro MP, Liquidación OS.
- **Comunicación**: Mensaje/Recordatorio (outbox), Plantilla.
- **Transversal**: Auditoría (append-only).

Toda tabla de negocio lleva `tenant_id` (aislación multi-tenant lógica). Todo cambio crítico en Turno/HC/Caja escribe en Auditoría.

## ERD (Entity Relationship Diagram)

```
Tenant 1──N Usuario (rol por tenant)
Tenant 1──N Sillon | Prestacion | CoberturaOS | Paciente | Plantilla
Paciente 1──1 FichaClinica ──N Evolucion
Paciente 1──N Turno N──1 Profesional(Usuario) + N──1 Sillon + N──1 Prestacion
Turno 1──N Sobreturno(marca) | 1──N Mensaje(outbox) | 0..1 Seña | 0..N CobroMP
Turno 1──N ListaEspera(derivados) | N──1 Bloqueo(conflicto, si aplica)
Paciente 1──1 Odontograma ──N PiezaEvento(FDI pieza/superficie/evento)
Paciente 1──N Presupuesto ──N PresupuestoItem ──N Turno(vinculados)
Paciente 1──N Consentimiento (firma previa a invasiva)
Turno/Cobro 1──N MovimientoCaja N──1 Cierre | LiquidacionOS N──N Turno
Todo cambio crítico ──► Auditoria (append-only: quien/que/cuando/antes/despues)
```

## Entidades

### Tenant (Consultorio)
- Atributos: `id (uuid)`, `slug (str, único)`, `nombre`, `cuit`, `direccion`, `telefono`, `email`, `politicas (jsonb: anticipacion_min_hs, sena_default, cancelacion_hs)`, `activo (bool)`, `created_at`.
- Relaciones: 1──N con Usuarios, Pacientes, Turnos, Prestaciones, Sillones, Movimientos.
- Constraints: `slug` único global; `cuit` válido AR si se informa.
- Índices: `slug`, `activo`.

### Usuario
- Atributos: `id`, `tenant_id (fk)`, `nombre`, `email (único por tenant)`, `password_hash`, `rol (enum: dueno, recepcion, odontologo)`, `matricula (nullable)`, `activo`, `created_at`.
- Relaciones: N──1 Tenant; 1──N Turno (como profesional).
- Constraints: email único por (`tenant_id`, `email`); `matricula` obligatoria si rol odontólogo. **Suposición:** un usuario pertenece a un solo tenant en v1 (multi-consultorio del mismo dueño = tenants separados).
- Índices: (`tenant_id`, `email`), (`tenant_id`, `rol`).

### Paciente
- Atributos: `id`, `tenant_id`, `nombre`, `dni (str)`, `telefono`, `email (nullable)`, `fecha_nac`, `obra_social_id (nullable)`, `nro_afiliado (nullable)`, `optin_wa (bool, default false)`, `observaciones`, `activo`, `created_at`.
- Relaciones: N──1 Tenant; 1──N Turnos, Presupuestos, Consentimientos; 1──1 Ficha.
- Constraints: (`tenant_id`, `dni`) único; mensajes WA automáticos solo si `optin_wa = true`.
- Índices: (`tenant_id`, `dni`), (`tenant_id`, `telefono`).

### Profesional (rol, no tabla propia)
- Se modela como `Usuario` con `rol = odontologo` + `matricula`. La agenda referencia `profesional_id → usuarios.id`.
- Constraint: el turno solo acepta usuarios con rol odontólogo (o dueño con flag clínico).

### Sillon (Box)
- Atributos: `id`, `tenant_id`, `nombre`, `sucursal (str, default "central")`, `activo`.
- Relaciones: 1──N Turnos.
- Constraints: nombre único por tenant+sucursal.
- Índices: (`tenant_id`, `sucursal`).

### Prestacion
- Atributos: `id`, `tenant_id`, `nombre`, `duracion_min (int)`, `precio_particular (numeric)`, `requiere_sena (bool)`, `monto_sena (numeric, nullable)`, `invasiva (bool, default false)`, `activa`.
- Relaciones: 1──N Turnos, PresupuestoItems, CoberturaOS.
- Constraints: `duracion_min > 0`; si `requiere_sena` entonces `monto_sena > 0`.
- Índices: (`tenant_id`, `activa`).

### Turno (Cita)
- Atributos: `id`, `tenant_id`, `paciente_id`, `profesional_id`, `sillon_id`, `prestacion_id`, `inicio (timestamptz)`, `fin (timestamptz)`, `estado (enum: pendiente, confirmado, presente, ausente, cancelado, reprogramado, finalizado)`, `origen (presencial, online, whatsapp)`, `token_gestion (uuid, único)`, `sobreturno (bool, default false)`, `motivo_cancelacion (nullable)`, `turno_origen_id (nullable, si reprogramado)`, `created_at/updated_at`.
- Relaciones: N──1 Paciente/Profesional/Sillón/Prestación; 1──N Mensajes; 0..1 Seña; 0..N Cobros.
- Constraints: sin solapamiento por (`profesional_id`, rango) ni por (`sillon_id`, rango) salvo `sobreturno = true` explícito; `fin = inicio + duracion_prestacion` (salvo override auditado); transición de estados solo por grafo permitido (ver RN).
- Índices: (`tenant_id`, `profesional_id`, `inicio`), (`tenant_id`, `sillon_id`, `inicio`), `token_gestion`, (`tenant_id`, `estado`, `inicio`).

### Bloqueo
- Atributos: `id`, `tenant_id`, `profesional_id (nullable)`, `sillon_id (nullable)`, `desde`, `hasta`, `motivo (feriado, vacaciones, manual, administrativo)`, `created_by`.
- Constraints: al menos uno de profesional/sillón informado; los slots cubiertos no son reservables.
- Índices: (`tenant_id`, `desde`, `hasta`).

### Sobreturno
- Se modela como `Turno` con `sobreturno = true` + `motivo` en observaciones; siempre auditado y visible como marcado. No tabla separada.

### ListaEspera
- Atributos: `id`, `tenant_id`, `paciente_id`, `prestacion_id`, `profesional_id (nullable)`, `prioridad (int)`, `estado (activa, avisada, colocada, baja)`, `canal_aviso (wa, email)`, `created_at`.
- Relaciones: N──1 Paciente/Prestación; al colocarse genera Turno.
- Constraints: orden por (`prioridad`, `created_at`); un aviso por hueco por entrada (idempotencia).
- Índices: (`tenant_id`, `estado`, `prioridad`, `created_at`).

### FichaClinica / Anamnesis
- Atributos: `id`, `tenant_id`, `paciente_id (único)`, `antecedentes (text)`, `alergias`, `medicacion`, `habitos`, `datos_json (jsonb)`, `updated_at`.
- Constraints: una por paciente; edición solo rol clínico; cada edición genera Evolución + Auditoría.

### Odontograma (FDI)
- Atributos cabecera: `id`, `tenant_id`, `paciente_id`, `updated_at`.
- PiezaEvento: `id`, `odontograma_id`, `pieza_fdi (11–48)`, `superficie (enum: oclusal, mesial, distal, vestibular, lingual, radicular, total)`, `evento (sano, caries, obturacion, corona, endodoncia, implante, extraccion, ausente, sellador, provisoria)`, `turno_id (nullable, origen)`, `observacion`, `created_by/at`.
- Constraints: `pieza_fdi` válida FDI; historial inmutable (los cambios son nuevos eventos, nunca UPDATE destructivo).
- Índices: (`odontograma_id`, `pieza_fdi`, `created_at`).

### Presupuesto / PlanTratamiento
- Atributos: `id`, `tenant_id`, `paciente_id`, `estado (borrador, presentado, aceptado, rechazado, en_curso, finalizado)`, `total`, `validez_hasta`, `created_by/at`.
- Item: `id`, `presupuesto_id`, `prestacion_id`, `pieza_fdi (nullable)`, `cantidad`, `precio_unit`, `cobertura_os (numeric)`, `a_cargo (numeric)`.
- Relaciones: 1──N Items; N──N Turnos (citas del plan).
- Constraints: `a_cargo = precio_unit*cantidad - cobertura_os`; aceptar requiere firma si incluye invasiva.

### Caja / Movimiento
- Atributos: Movimiento: `id`, `tenant_id`, `tipo (ingreso, egreso)`, `concepto`, `medio (efectivo, debito, credito, transferencia, mp)`, `monto`, `turno_id (nullable)`, `cobro_mp_id (nullable)`, `cierre_id (nullable)`, `created_by/at`.
- Cierre: `id`, `tenant_id`, `fecha`, `total_sistema`, `total_contado`, `diferencia`, `estado (abierto, cerrado)`, `cerrado_por/at`.
- Constraints: movimiento con `cierre_id` cerrado es inmutable; reapertura solo Dueño + Auditoría.
- Índices: (`tenant_id`, `created_at`), (`tenant_id`, `cierre_id`).

### Sena
- Atributos: `id`, `tenant_id`, `turno_id (único)`, `monto`, `estado (pendiente, cobrada, aplicada, devuelta, vencida)`, `mp_payment_id (nullable)`, `vence_at (nullable)`.
- Constraints: una seña activa por turno; transición por grafo; idempotencia por `mp_payment_id`.
- Índices: (`tenant_id`, `estado`), `turno_id` único.

### CobroMP
- Atributos: `id`, `tenant_id`, `turno_id (nullable)`, `sena_id (nullable)`, `mp_payment_id (único)`, `mp_preference_id`, `monto`, `estado_mp`, `estado_conciliacion (pendiente, conciliado, discrepancia)`, `payload (jsonb)`, `created_at`.
- Constraints: `mp_payment_id` único (idempotencia de webhook); todo webhook se persiste antes de procesar.
- Índices: `mp_payment_id`, (`tenant_id`, `estado_conciliacion`).

### CoberturaOS / Liquidacion
- CoberturaOS: `id`, `tenant_id`, `obra_social (str)`, `prestacion_id`, `arancel (numeric)`, `copago (numeric)`, `vigencia_desde/hasta`, `activa`.
- Liquidacion: `id`, `tenant_id`, `obra_social`, `periodo (yyyymm)`, `estado (borrador, presentada, pagada, con_debitos)`, `total`, `created_at`.
- LiquidacionDetalle: `liquidacion_id`, `turno_id`, `monto_reclamado`, `monto_reconocido (nullable)`, `debito_motivo (nullable)`.
- Constraints: turno liquidable solo si `finalizado` y con OS; un turno en una sola liquidación abierta por OS/período.

### Mensaje / Recordatorio (outbox)
- Atributos: `id`, `tenant_id`, `turno_id (nullable)`, `lista_espera_id (nullable)`, `canal (wa, email)`, `plantilla (str)`, `destino`, `payload (jsonb)`, `estado (pendiente, enviado, entregado, leido, fallido)`, `idempotency_key (único)`, `intentos`, `programado_para`, `enviado_at`, `error (nullable)`.
- Constraints: `idempotency_key` único (no doble recordatorio/cobro); WA solo con `optin_wa`.
- Índices: (`estado`, `programado_para`), `idempotency_key`.

### Auditoria (append-only)
- Atributos: `id`, `tenant_id`, `actor_id`, `accion`, `entidad`, `entidad_id`, `antes (jsonb)`, `despues (jsonb)`, `ip (nullable)`, `created_at`.
- Constraints: sin UPDATE/DELETE (permiso solo INSERT+SELECT); retención mínima 5 años. **Suposición:** plazo legal a confirmar con asesor (se adopta 5 años por prudencia).
- Índices: (`tenant_id`, `entidad`, `entidad_id`, `created_at`).

### Consentimiento
- Atributos: `id`, `tenant_id`, `paciente_id`, `prestacion_id`, `turno_id (nullable)`, `texto_version`, `firma_hash`, `firmado_por`, `firmado_at`, `canal (presencial, token)`, ` revocado (bool, default false)`.
- Constraints: prestación invasiva exige consentimiento firmado previo (RN); revocación auditada.
- Índices: (`paciente_id`, `prestacion_id`), (`turno_id`).

## Seed data inicial

- Tenant piloto (slug del consultorio) + usuario Dueño inicial.
- Roles y permisos base (matriz §03).
- Sillón "Box 1" + Profesional de prueba.
- Catálogo mínimo de prestaciones (limpieza 30', consulta 20', arreglo 45', endodoncia 60', extracción 45') con precios y flags de seña/invasiva.
- Plantillas WA/email: confirmación, recordatorio 24h, cancelación, hueco de lista de espera, seña pendiente.
- Motivos de bloqueo (feriado, vacaciones, administrativo) y estados de turno con su grafo.
