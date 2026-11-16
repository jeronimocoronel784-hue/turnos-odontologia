import { apiFetch } from "../../shared/api-client";
import {
  FichaClinicaRead,
  FichaClinicaUpdateInput,
  EvolucionRead,
  EvolucionCreateInput,
  OdontogramaRead,
  PiezaEventoRead,
  PiezaEventoCreateInput,
  AdjuntoRead,
  AdjuntoCreateInput,
  ConsentimientoRead,
  ConsentimientoCreateInput,
  ConsentimientoFirmaInput,
  PresupuestoRead,
  PresupuestoCreateInput,
  PresupuestoVincularTurnoInput,
  PresupuestoTurnoRead,
} from "../../shared/api-types";

// Ficha clínica
export async function obtenerFicha(pacienteId: string): Promise<FichaClinicaRead> {
  return apiFetch<FichaClinicaRead>(`/api/pacientes/${pacienteId}/ficha`);
}

export async function actualizarFicha(
  pacienteId: string,
  input: FichaClinicaUpdateInput,
): Promise<FichaClinicaRead> {
  return apiFetch<FichaClinicaRead>(`/api/pacientes/${pacienteId}/ficha`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

// Evoluciones
export async function obtenerEvoluciones(pacienteId: string): Promise<EvolucionRead[]> {
  return apiFetch<EvolucionRead[]>(`/api/pacientes/${pacienteId}/evoluciones`);
}

export async function crearEvolucion(
  pacienteId: string,
  input: EvolucionCreateInput,
): Promise<EvolucionRead> {
  return apiFetch<EvolucionRead>(`/api/pacientes/${pacienteId}/evoluciones`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Odontograma FDI
export async function obtenerOdontograma(pacienteId: string): Promise<OdontogramaRead> {
  return apiFetch<OdontogramaRead>(`/api/odontograma/${pacienteId}`);
}

export async function crearEventoPieza(
  pacienteId: string,
  input: PiezaEventoCreateInput,
): Promise<PiezaEventoRead> {
  return apiFetch<PiezaEventoRead>(`/api/odontograma/${pacienteId}/eventos`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function obtenerHistorialPieza(
  pacienteId: string,
  pieza: number,
): Promise<PiezaEventoRead[]> {
  return apiFetch<PiezaEventoRead[]>(
    `/api/odontograma/${pacienteId}/piezas/${pieza}/historial`,
  );
}

// Adjuntos
export async function obtenerAdjuntos(pacienteId: string): Promise<AdjuntoRead[]> {
  return apiFetch<AdjuntoRead[]>(`/api/pacientes/${pacienteId}/adjuntos`);
}

export async function crearAdjunto(
  pacienteId: string,
  input: AdjuntoCreateInput,
): Promise<AdjuntoRead> {
  return apiFetch<AdjuntoRead>(`/api/pacientes/${pacienteId}/adjuntos`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Consentimientos
export async function obtenerConsentimientos(
  pacienteId: string,
): Promise<ConsentimientoRead[]> {
  return apiFetch<ConsentimientoRead[]>(`/api/consentimientos?paciente_id=${pacienteId}`);
}

export async function crearConsentimiento(
  input: ConsentimientoCreateInput,
): Promise<ConsentimientoRead> {
  return apiFetch<ConsentimientoRead>("/api/consentimientos", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function firmarConsentimiento(
  id: string,
  input: ConsentimientoFirmaInput,
): Promise<ConsentimientoRead> {
  return apiFetch<ConsentimientoRead>(`/api/consentimientos/${id}/firmar`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function revocarConsentimiento(
  id: string,
  motivo: string,
): Promise<ConsentimientoRead> {
  return apiFetch<ConsentimientoRead>(`/api/consentimientos/${id}/revocar`, {
    method: "POST",
    body: JSON.stringify({ motivo }),
  });
}

// Presupuestos
export async function obtenerPresupuestos(pacienteId: string): Promise<PresupuestoRead[]> {
  return apiFetch<PresupuestoRead[]>(`/api/presupuestos?paciente_id=${pacienteId}`);
}

export async function crearPresupuesto(
  input: PresupuestoCreateInput,
): Promise<PresupuestoRead> {
  return apiFetch<PresupuestoRead>("/api/presupuestos", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function transicionarPresupuesto(
  id: string,
  accion: "presentar" | "aceptar" | "rechazar" | "finalizar",
): Promise<PresupuestoRead> {
  return apiFetch<PresupuestoRead>(`/api/presupuestos/${id}/${accion}`, {
    method: "POST",
  });
}

export async function vincularTurnoPresupuesto(
  presupuestoId: string,
  input: PresupuestoVincularTurnoInput,
): Promise<PresupuestoTurnoRead> {
  return apiFetch<PresupuestoTurnoRead>(`/api/presupuestos/${presupuestoId}/turnos`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
