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
    mensajes: (filtros: { turno_id?: string; paciente_id?: string }) =>
      ["comunicaciones", "mensajes", filtros] as const,
    plantillas: ["comunicaciones", "plantillas"] as const,
  },
  catalogos: {
    profesionales: ["catalogos", "profesionales"] as const,
    prestaciones: ["catalogos", "prestaciones"] as const,
    sillones: ["catalogos", "sillones"] as const,
    politicas: ["catalogos", "politicas"] as const,
  },
};
