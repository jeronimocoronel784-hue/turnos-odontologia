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
