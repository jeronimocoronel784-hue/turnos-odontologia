import { apiFetch } from "../../shared/api-client";
import type {
  MensajeCreateInput,
  MensajeRead,
  PlantillaCreateInput,
  PlantillaRead,
} from "../../shared/api-types";

export interface FiltrosMensajes {
  estado?: string;
  turno_id?: string;
  paciente_id?: string;
}

export async function listarMensajes(filtros?: FiltrosMensajes): Promise<MensajeRead[]> {
  const params = new URLSearchParams();
  if (filtros?.estado) params.set("estado", filtros.estado);
  if (filtros?.turno_id) params.set("turno_id", filtros.turno_id);
  if (filtros?.paciente_id) params.set("paciente_id", filtros.paciente_id);

  const qs = params.toString();
  const ruta = qs ? `/api/mensajes?${qs}` : "/api/mensajes";
  return apiFetch<MensajeRead[]>(ruta);
}

export async function crearMensaje(datos: MensajeCreateInput): Promise<MensajeRead> {
  return apiFetch<MensajeRead>("/api/mensajes", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function reenviarMensaje(mensajeId: string): Promise<MensajeRead> {
  return apiFetch<MensajeRead>(`/api/mensajes/${mensajeId}/reenviar`, {
    method: "POST",
  });
}

export async function listarPlantillas(): Promise<PlantillaRead[]> {
  return apiFetch<PlantillaRead[]>("/api/plantillas");
}

export async function crearPlantilla(datos: PlantillaCreateInput): Promise<PlantillaRead> {
  return apiFetch<PlantillaRead>("/api/plantillas", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}
