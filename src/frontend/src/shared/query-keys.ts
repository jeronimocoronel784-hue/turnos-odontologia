export const queryKeys = {
  agenda: {
    todas: ["agenda"] as const,
    rango: (filtros: {
      desde: string;
      hasta: string;
      profesional_id?: string;
      sillon_id?: string;
      estado?: string;
    }) => ["agenda", "rango", filtros] as const,
  },
  pacientes: {
    todos: ["pacientes"] as const,
    lista: (q?: string) => ["pacientes", "lista", q ?? ""] as const,
    detalle: (id: string) => ["pacientes", "detalle", id] as const,
    ficha: (id: string) => ["pacientes", "ficha", id] as const,
  },
  clinica: {
    evoluciones: (pacienteId: string) => ["clinica", "evoluciones", pacienteId] as const,
    adjuntos: (pacienteId: string) => ["clinica", "adjuntos", pacienteId] as const,
    odontograma: (pacienteId: string) => ["clinica", "odontograma", pacienteId] as const,
    historialPieza: (pacienteId: string, pieza: number) =>
      ["clinica", "odontograma", pacienteId, "pieza", pieza] as const,
    consentimientos: (pacienteId: string) => ["clinica", "consentimientos", pacienteId] as const,
    presupuestos: (pacienteId: string) => ["clinica", "presupuestos", pacienteId] as const,
  },
  comunicaciones: {
    mensajes: (filtros: { turno_id?: string; paciente_id?: string; estado?: string }) =>
      ["comunicaciones", "mensajes", filtros] as const,
    plantillas: ["comunicaciones", "plantillas"] as const,
  },
  catalogos: {
    profesionales: ["catalogos", "profesionales"] as const,
    prestaciones: ["catalogos", "prestaciones"] as const,
    sillones: ["catalogos", "sillones"] as const,
    politicas: ["catalogos", "politicas"] as const,
  },
  caja: {
    movimientos: (filtros: {
      desde?: string;
      hasta?: string;
      cierre_id?: string;
      medio?: string;
      tipo?: string;
    }) => ["caja", "movimientos", filtros] as const,
    cierres: (filtros?: { fecha?: string; estado?: string }) =>
      ["caja", "cierres", filtros ?? {}] as const,
    cierreDetalle: (id: string) => ["caja", "cierre", id] as const,
    liquidacionTurno: (turnoId: string, obraSocial?: string) =>
      ["caja", "liquidacionTurno", turnoId, obraSocial ?? ""] as const,
    senas: (filtros?: { turno_id?: string; estado?: string }) =>
      ["caja", "senas", filtros ?? {}] as const,
  },
  os: {
    cobertura: (filtros: {
      prestacion_id?: string;
      turno_id?: string;
      obra_social?: string;
      fecha?: string;
    }) => ["os", "cobertura", filtros] as const,
    liquidaciones: (filtros?: { obra_social?: string; periodo?: string; estado?: string }) =>
      ["os", "liquidaciones", filtros ?? {}] as const,
    liquidacionDetalle: (id: string) => ["os", "liquidacion", id] as const,
  },
  admin: {
    prestaciones: ["admin", "prestaciones"] as const,
    sillones: ["admin", "sillones"] as const,
    coberturas: ["admin", "coberturas"] as const,
    politicas: ["admin", "politicas"] as const,
    usuarios: ["admin", "usuarios"] as const,
  },
  panel: {
    dia: (fecha: string) => ["panel", "dia", fecha] as const,
  },
};
