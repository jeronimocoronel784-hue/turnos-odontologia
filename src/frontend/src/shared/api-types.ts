// Tipos TypeScript estrictos (R5: prohibido any). Espejan 1:1 los schemas Pydantic
// públicos del backend (app/api/schemas_agenda.py, schemas_clinica.py,
// schemas_mercadopago.py y schemas_lista_espera.py).

// ---------------------------------------------------------------------------
// Catálogo y disponibilidad pública (GET /api/reservar/:slug)
// ---------------------------------------------------------------------------

export interface PrestacionPublica {
  id: string;
  nombre: string;
  duracion_min: number;
  /** Monto formateado por el backend (R8: el cliente nunca calcula precios). */
  precio_particular: string;
  requiere_sena: boolean;
  monto_sena: string | null;
}

export interface ProfesionalPublico {
  id: string;
  nombre: string;
  matricula: string | null;
}

export interface SillonPublico {
  id: string;
  nombre: string;
  sucursal: string;
}

export interface SlotDisponible {
  /** ISO 8601 con zona horaria. */
  inicio: string;
  fin: string;
  profesional_id: string;
  sillon_id: string;
}

export interface CatalogoDisponibilidad {
  tenant_slug: string;
  tenant_nombre: string;
  prestaciones: PrestacionPublica[];
  profesionales: ProfesionalPublico[];
  sillones: SillonPublico[];
  slots_disponibles: SlotDisponible[];
}

// ---------------------------------------------------------------------------
// Reserva pública (POST /api/reservar/:slug)
// ---------------------------------------------------------------------------

export interface ReservaPublicaInput {
  nombre: string;
  dni: string;
  telefono: string;
  email?: string;
  /** YYYY-MM-DD */
  fecha_nac?: string;
  obra_social_id?: string;
  nro_afiliado?: string;
  optin_wa: boolean;
  prestacion_id: string;
  profesional_id: string;
  sillon_id: string;
  /** ISO 8601 con zona horaria. */
  inicio: string;
}

/** Estados reales de la máquina de estados del turno (RN-AG-07). */
export type EstadoTurno =
  | "pendiente"
  | "confirmado"
  | "presente"
  | "finalizado"
  | "cancelado"
  | "ausente"
  | "reprogramado";

export interface ReservaPublicaResponse {
  turno_id: string;
  estado: EstadoTurno;
  inicio: string;
  fin: string;
  prestacion_id: string;
  prestacion_nombre: string;
  profesional_id: string;
  profesional_nombre: string;
  sillon_id: string;
  sillon_nombre: string;
  requiere_sena: boolean;
  monto_sena: string | null;
  sena_cobrada: boolean;
  token_gestion: string | null;
}

export interface CancelarTurnoInput {
  motivo?: string;
}

export interface ReprogramarTurnoInput {
  nuevo_inicio: string;
  motivo?: string;
}

// ---------------------------------------------------------------------------
// Pago de seña (POST /api/mis-turnos/:token/pago)
// ---------------------------------------------------------------------------

export interface PreferenciaPago {
  id: string;
  init_point: string;
  sandbox_init_point: string;
  external_reference: string;
  monto: string;
  expiration_date_to: string;
}

// ---------------------------------------------------------------------------
// Consentimiento informado público (GET/POST /api/firmar/:token)
// ---------------------------------------------------------------------------

export type CanalFirmaConsentimiento = "presencial" | "token";

export interface ConsentimientoPublico {
  consentimiento_id: string;
  prestacion_id: string;
  texto_version: string;
  texto_contenido: string;
  firmado: boolean;
  firmado_at: string | null;
  revocado: boolean;
}

export interface FirmaConsentimientoInput {
  firmado_por: string;
  /** Trazo de la firma (data URL PNG) o confirmación digital. */
  firma_datos: string;
  canal: CanalFirmaConsentimiento;
}

/** Respuesta del backend al registrar la firma (ConsentimientoRead). */
export interface ConsentimientoFirmado {
  id: string;
  tenant_id: string;
  paciente_id: string;
  prestacion_id: string;
  turno_id: string | null;
  texto_version: string;
  texto_contenido: string;
  firma_hash: string | null;
  firmado_por: string | null;
  firmado_at: string | null;
  canal: string;
  revocado: boolean;
  revocado_motivo: string | null;
  revocado_at: string | null;
  token_firma: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Lista de espera pública (GET/POST /api/lista-espera/:token)
// ---------------------------------------------------------------------------

export type EstadoListaEspera = "activa" | "avisada" | "colocada" | "baja";
export type CanalAvisoListaEspera = "wa" | "email";

export interface ListaEsperaPublica {
  entrada_id: string;
  estado: EstadoListaEspera;
  prestacion_id: string;
  prestacion_nombre: string;
  profesional_id: string | null;
  profesional_nombre: string | null;
  canal_aviso: CanalAvisoListaEspera;
  hueco_inicio: string | null;
  hueco_fin: string | null;
  aviso_vence_at: string | null;
  turno_colocado_id: string | null;
  token_gestion: string | null;
}

// ---------------------------------------------------------------------------
// Shell interno y Autenticación (POST /api/auth/*)
// ---------------------------------------------------------------------------

export type RolUsuario = "dueno" | "recepcion" | "odontologo" | "paciente";

export interface IdentidadRead {
  id: string;
  tenant_id: string;
  tenant_slug: string;
  email: string;
  nombre: string;
  roles: RolUsuario[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expira_en_segundos: number;
  usuario: IdentidadRead;
}

export interface LoginRequest {
  email: string;
  password: string;
  tenant_slug?: string;
}

// ---------------------------------------------------------------------------
// Agenda interna (GET/POST /api/turnos, /api/agenda, /api/bloqueos)
// ---------------------------------------------------------------------------

export type OrigenTurno = "online" | "presencial" | "telefonico";
export type MotivoBloqueo = "feriado" | "vacaciones" | "mantenimiento" | "manual";

export interface TurnoCreateInput {
  paciente_id: string;
  profesional_id: string;
  sillon_id: string;
  prestacion_id: string;
  inicio: string;
  fin?: string;
  origen?: OrigenTurno;
  sobreturno?: boolean;
  observaciones?: string;
  sena_cobrada?: boolean;
}

export interface TurnoEstadoUpdateInput {
  estado: EstadoTurno;
  motivo_cancelacion?: string;
  sena_cobrada?: boolean;
}

export interface TurnoReprogramarInputInternal {
  nuevo_inicio: string;
  profesional_id?: string;
  sillon_id?: string;
  motivo?: string;
}

export interface TurnoRead {
  id: string;
  tenant_id: string;
  paciente_id: string;
  profesional_id: string;
  sillon_id: string;
  prestacion_id: string;
  inicio: string;
  fin: string;
  estado: EstadoTurno;
  origen: OrigenTurno;
  sobreturno: boolean;
  observaciones?: string | null;
  motivo_cancelacion?: string | null;
  turno_origen_id?: string | null;
  sena_cobrada: boolean;
  created_at: string;
  updated_at: string;
  token_gestion?: string | null;
}

export interface BloqueoCreateInput {
  profesional_id?: string;
  sillon_id?: string;
  desde: string;
  hasta: string;
  motivo?: MotivoBloqueo;
  descripcion?: string;
}

export interface BloqueoRead {
  id: string;
  tenant_id: string;
  profesional_id?: string | null;
  sillon_id?: string | null;
  desde: string;
  hasta: string;
  motivo: MotivoBloqueo;
  descripcion?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgendaVistaRead {
  turnos: TurnoRead[];
  bloqueos: BloqueoRead[];
}

// ---------------------------------------------------------------------------
// Pacientes (GET/POST/PATCH /api/pacientes)
// ---------------------------------------------------------------------------

export interface FichaClinicaRead {
  id: string;
  paciente_id: string;
  antecedentes?: string | null;
  alergias?: string | null;
  medicacion?: string | null;
  habitos?: string | null;
  datos_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface PacienteRead {
  id: string;
  tenant_id: string;
  nombre: string;
  dni: string;
  telefono: string;
  email?: string | null;
  fecha_nac?: string | null;
  obra_social_id?: string | null;
  nro_afiliado?: string | null;
  optin_wa: boolean;
  observaciones?: string | null;
  activo: boolean;
  created_at: string;
  updated_at: string;
  ficha_clinica?: FichaClinicaRead | null;
}

export interface PacienteCreateInput {
  nombre: string;
  dni: string;
  telefono: string;
  email?: string;
  fecha_nac?: string;
  obra_social_id?: string;
  nro_afiliado?: string;
  optin_wa?: boolean;
  observaciones?: string;
}

export interface PacienteUpdateInput {
  nombre?: string;
  telefono?: string;
  email?: string;
  fecha_nac?: string;
  obra_social_id?: string;
  nro_afiliado?: string;
  observaciones?: string;
  activo?: boolean;
}

// ---------------------------------------------------------------------------
// Clínica, Odontograma FDI y Consentimiento (GET/POST /api/clinica/*)
// ---------------------------------------------------------------------------

export interface FichaClinicaUpdateInput {
  antecedentes?: string;
  alergias?: string;
  medicacion?: string;
  habitos?: string;
  datos_json?: Record<string, unknown>;
  nota_evolucion?: string;
}

export interface EvolucionCreateInput {
  nota: string;
  turno_id?: string;
  es_correccion_de_id?: string;
}

export interface EvolucionRead {
  id: string;
  tenant_id: string;
  ficha_clinica_id: string;
  paciente_id: string;
  turno_id?: string | null;
  profesional_id: string;
  nota: string;
  es_correccion_de_id?: string | null;
  created_at: string;
}

export type TipoAdjunto = "radiografia" | "foto" | "estudio_pdf" | "otro";

export interface AdjuntoCreateInput {
  tipo: TipoAdjunto;
  nombre_archivo: string;
  mime_type: string;
  tamano_bytes: number;
  storage_key: string;
  evolucion_id?: string;
  pieza_evento_id?: string;
}

export interface AdjuntoRead {
  id: string;
  tenant_id: string;
  paciente_id: string;
  ficha_clinica_id: string;
  evolucion_id?: string | null;
  pieza_evento_id?: string | null;
  tipo: string;
  nombre_archivo: string;
  mime_type: string;
  tamano_bytes: number;
  storage_key: string;
  created_by: string;
  created_at: string;
}

export type SuperficieDental =
  | "oclusal"
  | "mesial"
  | "distal"
  | "vestibular"
  | "palatina"
  | "lingual"
  | "cervical"
  | "pieza_completa";

export type TipoEventoPieza =
  | "sano"
  | "caries"
  | "obturacion"
  | "corona"
  | "endodoncia"
  | "extraccion_indicada"
  | "ausente"
  | "implante"
  | "protesis"
  | "sellador";

export interface PiezaEventoCreateInput {
  pieza_fdi: number;
  superficie: SuperficieDental;
  evento: TipoEventoPieza;
  turno_id?: string;
  observacion?: string;
}

export interface PiezaEventoRead {
  id: string;
  tenant_id: string;
  odontograma_id: string;
  pieza_fdi: number;
  superficie: string;
  evento: string;
  turno_id?: string | null;
  observacion?: string | null;
  created_by: string;
  created_at: string;
}

export interface EstadoPiezaFDIRead {
  pieza_fdi: number;
  superficies: Record<string, string>;
  ultimo_evento_id: string;
  updated_at: string;
}

export interface OdontogramaRead {
  odontograma_id: string;
  tenant_id: string;
  paciente_id: string;
  piezas: EstadoPiezaFDIRead[];
  eventos: PiezaEventoRead[];
}

export interface ConsentimientoCreateInput {
  paciente_id: string;
  prestacion_id: string;
  turno_id?: string;
  texto_version: string;
  texto_contenido: string;
}

export interface ConsentimientoRevocarInput {
  motivo: string;
}

// ---------------------------------------------------------------------------
// Presupuestos y Planes de Tratamiento (GET/POST /api/presupuestos)
// ---------------------------------------------------------------------------

export interface PresupuestoItemInput {
  prestacion_id: string;
  pieza_fdi?: number;
  cantidad?: number;
}

export interface PresupuestoItemRead {
  id: string;
  tenant_id: string;
  presupuesto_id: string;
  prestacion_id: string;
  pieza_fdi?: number | null;
  cantidad: number;
  precio_unit: string;
  cobertura_os: string;
  a_cargo: string;
  created_at: string;
}

export interface PresupuestoCreateInput {
  paciente_id: string;
  obra_social?: string;
  validez_hasta?: string;
  observaciones?: string;
  items: PresupuestoItemInput[];
}

export interface PresupuestoTurnoRead {
  id: string;
  tenant_id: string;
  presupuesto_id: string;
  turno_id: string;
  presupuesto_item_id?: string | null;
  created_at: string;
}

export interface PresupuestoRead {
  id: string;
  tenant_id: string;
  paciente_id: string;
  obra_social?: string | null;
  estado: string;
  total: string;
  total_cobertura_os: string;
  total_a_cargo: string;
  validez_hasta?: string | null;
  observaciones?: string | null;
  created_by: string;
  items: PresupuestoItemRead[];
  turnos_vinculados: PresupuestoTurnoRead[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Comunicaciones (GET/POST /api/mensajes, /api/plantillas)
// ---------------------------------------------------------------------------

export type CanalMensaje = "wa" | "email" | "manual";
export type EstadoMensaje = "pendiente" | "enviado" | "fallido" | "cancelado";

export interface PlantillaCreateInput {
  codigo: string;
  canal?: CanalMensaje;
  asunto?: string;
  cuerpo: string;
  activa?: boolean;
}

export interface PlantillaRead {
  id: string;
  tenant_id: string;
  codigo: string;
  canal: CanalMensaje;
  version: number;
  asunto?: string | null;
  cuerpo: string;
  activa: boolean;
  created_at: string;
  updated_at: string;
}

export interface MensajeCreateInput {
  paciente_id?: string;
  turno_id?: string;
  lista_espera_id?: string;
  canal?: CanalMensaje;
  plantilla: string;
  destino: string;
  variables?: Record<string, string>;
  ventana?: string;
  programado_para?: string;
}

export interface MensajeRead {
  id: string;
  tenant_id: string;
  paciente_id?: string | null;
  turno_id?: string | null;
  lista_espera_id?: string | null;
  canal: CanalMensaje;
  plantilla: string;
  plantilla_version: number;
  destino: string;
  cuerpo_renderizado: string;
  payload: Record<string, unknown>;
  estado: EstadoMensaje;
  idempotency_key: string;
  intentos: number;
  max_intentos: number;
  ultimo_intento_at?: string | null;
  proximo_intento_at?: string | null;
  error?: string | null;
  error_mensaje?: string | null;
  enviado_at?: string | null;
  proveedor_message_id?: string | null;
  programado_para?: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Catálogo interno, Políticas y Usuarios
// ---------------------------------------------------------------------------

export interface SillonRead {
  id: string;
  tenant_id: string;
  nombre: string;
  sucursal: string;
  activo: boolean;
  created_at: string;
  updated_at: string;
}

export interface PrestacionRead {
  id: string;
  tenant_id: string;
  nombre: string;
  duracion_min: number;
  precio_particular: string;
  requiere_sena: boolean;
  monto_sena?: string | null;
  invasiva: boolean;
  activa: boolean;
  created_at: string;
  updated_at: string;
}

export interface CoberturaOSRead {
  id: string;
  tenant_id: string;
  obra_social: string;
  prestacion_id: string;
  arancel: string;
  copago: string;
  vigencia_desde: string;
  vigencia_hasta?: string | null;
  activa: boolean;
  created_at: string;
  updated_at: string;
}

export interface PoliticasRead {
  anticipacion_min_dias: number;
  sena_default_pct: number;
  cancelacion_horas: number;
  anticipacion_min_hs?: number | null;
}

export interface UsuarioRead {
  id: string;
  tenant_id: string;
  email: string;
  nombre: string;
  rol: RolUsuario;
  matricula?: string | null;
  activo: boolean;
}

