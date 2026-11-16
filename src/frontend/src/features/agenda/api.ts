import { apiFetch } from "../../shared/api-client";
import {
  AgendaVistaRead,
  TurnoCreateInput,
  TurnoRead,
  TurnoEstadoUpdateInput,
  TurnoReprogramarInputInternal,
  BloqueoCreateInput,
  BloqueoRead,
  PoliticasRead,
  UsuarioRead,
  PrestacionRead,
  SillonRead,
  PacienteRead,
} from "../../shared/api-types";

export interface FiltrosAgenda {
  desde: string;
  hasta: string;
  profesional_id?: string;
  sillon_id?: string;
  estado?: string;
}

export async function obtenerAgenda(filtros: FiltrosAgenda): Promise<AgendaVistaRead> {
  const params = new URLSearchParams();
  params.set("desde", filtros.desde);
  params.set("hasta", filtros.hasta);
  if (filtros.profesional_id) params.set("profesional_id", filtros.profesional_id);
  if (filtros.sillon_id) params.set("sillon_id", filtros.sillon_id);
  if (filtros.estado) params.set("estado", filtros.estado);

  return apiFetch<AgendaVistaRead>(`/api/agenda?${params.toString()}`);
}

export async function crearTurno(input: TurnoCreateInput): Promise<TurnoRead> {
  return apiFetch<TurnoRead>("/api/turnos", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function actualizarEstadoTurno(
  turnoId: string,
  input: TurnoEstadoUpdateInput,
): Promise<TurnoRead> {
  return apiFetch<TurnoRead>(`/api/turnos/${turnoId}/estado`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function reprogramarTurno(
  turnoId: string,
  input: TurnoReprogramarInputInternal,
): Promise<TurnoRead> {
  return apiFetch<TurnoRead>(`/api/turnos/${turnoId}/reprogramar`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function crearBloqueo(input: BloqueoCreateInput): Promise<BloqueoRead> {
  return apiFetch<BloqueoRead>("/api/bloqueos", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function eliminarBloqueo(bloqueoId: string): Promise<void> {
  return apiFetch<void>(`/api/bloqueos/${bloqueoId}`, {
    method: "DELETE",
  });
}

export async function obtenerPoliticas(): Promise<PoliticasRead> {
  return apiFetch<PoliticasRead>("/api/tenant/politicas");
}

export async function obtenerProfesionales(): Promise<UsuarioRead[]> {
  const usuarios = await apiFetch<UsuarioRead[]>("/api/usuarios");
  return usuarios.filter((u) => u.rol === "odontologo" && u.activo);
}

export async function obtenerPrestaciones(): Promise<PrestacionRead[]> {
  const lista = await apiFetch<PrestacionRead[]>("/api/prestaciones");
  return lista.filter((p) => p.activa);
}

export async function obtenerSillones(): Promise<SillonRead[]> {
  const lista = await apiFetch<SillonRead[]>("/api/sillones");
  return lista.filter((s) => s.activo);
}

export async function obtenerPacientes(): Promise<PacienteRead[]> {
  return apiFetch<PacienteRead[]>("/api/pacientes");
}
