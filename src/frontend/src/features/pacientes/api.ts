import { apiFetch } from "../../shared/api-client";
import {
  PacienteRead,
  PacienteCreateInput,
  PacienteUpdateInput,
} from "../../shared/api-types";

export async function buscarPacientes(
  q?: string,
  incluirInactivos = false,
): Promise<PacienteRead[]> {
  const params = new URLSearchParams();
  if (q && q.trim()) params.set("q", q.trim());
  if (incluirInactivos) params.set("incluir_inactivos", "true");

  return apiFetch<PacienteRead[]>(`/api/pacientes?${params.toString()}`);
}

export async function obtenerPaciente(id: string): Promise<PacienteRead> {
  return apiFetch<PacienteRead>(`/api/pacientes/${id}`);
}

export async function crearPaciente(input: PacienteCreateInput): Promise<PacienteRead> {
  return apiFetch<PacienteRead>("/api/pacientes", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function actualizarPaciente(
  id: string,
  input: PacienteUpdateInput,
): Promise<PacienteRead> {
  return apiFetch<PacienteRead>(`/api/pacientes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function actualizarOptinWA(
  id: string,
  optin_wa: boolean,
): Promise<PacienteRead> {
  return apiFetch<PacienteRead>(`/api/pacientes/${id}/optin`, {
    method: "PATCH",
    body: JSON.stringify({ optin_wa }),
  });
}

export async function darDeBajaPaciente(id: string): Promise<void> {
  return apiFetch<void>(`/api/pacientes/${id}`, {
    method: "DELETE",
  });
}
