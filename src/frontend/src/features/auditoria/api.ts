import { apiFetch, ErrorApi } from "../../shared/api-client";
import { getAccessToken } from "../../shared/sesion";
import { UsuarioRead } from "../../shared/api-types";

export interface AuditoriaEventoRead {
  id: string;
  actor_id: string | null;
  accion: string;
  entidad: string;
  entidad_id: string;
  antes: Record<string, unknown> | null;
  despues: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditoriaPaginaRead {
  eventos: AuditoriaEventoRead[];
  siguiente_cursor: string | null;
}

export interface AuditoriaFiltros {
  entidad?: string;
  entidad_id?: string;
  actor_id?: string;
  accion?: string;
  desde?: string;
  hasta?: string;
  limite?: number;
  cursor?: string | null;
}

export async function listarAuditoria(
  filtros: AuditoriaFiltros = {},
): Promise<AuditoriaPaginaRead> {
  const params = new URLSearchParams();
  if (filtros.entidad) params.set("entidad", filtros.entidad);
  if (filtros.entidad_id) params.set("entidad_id", filtros.entidad_id);
  if (filtros.actor_id) params.set("actor_id", filtros.actor_id);
  if (filtros.accion) params.set("accion", filtros.accion);
  if (filtros.desde) params.set("desde", filtros.desde);
  if (filtros.hasta) params.set("hasta", filtros.hasta);
  if (filtros.limite) params.set("limite", String(filtros.limite));
  if (filtros.cursor) params.set("cursor", filtros.cursor);

  const qs = params.toString();
  return apiFetch<AuditoriaPaginaRead>(`/api/auditoria${qs ? `?${qs}` : ""}`);
}

export async function listarUsuariosAuditoria(): Promise<UsuarioRead[]> {
  return apiFetch<UsuarioRead[]>("/api/usuarios");
}

export interface ExportacionJobRead {
  job_id: string;
  estado: string;
  dataset?: string | null;
  formato?: string | null;
  filas?: number | null;
  creado_at?: string | null;
  expira_at?: string | null;
  nombre_archivo?: string | null;
  error?: string | null;
}

export async function obtenerEstadoJob(jobId: string): Promise<ExportacionJobRead> {
  return apiFetch<ExportacionJobRead>(`/api/exportacion/jobs/${jobId}`);
}

export async function descargarExportacionDirecta(
  dataset: string,
  formato: string,
  desde?: string,
  hasta?: string,
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams();
  params.set("formato", formato);
  if (desde) params.set("desde", desde);
  if (hasta) params.set("hasta", hasta);

  const token = getAccessToken();
  const headers: HeadersInit = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const respuesta = await fetch(`/api/exportacion/${dataset}?${params.toString()}`, {
    credentials: "include",
    headers,
  });
  if (!respuesta.ok) {
    let mensaje = `Error del servidor (${respuesta.status})`;
    try {
      const cuerpo = await respuesta.json();
      if (cuerpo && typeof cuerpo === "object") {
        if ("detail" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detail);
        else if ("detalle" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detalle);
      }
    } catch {
      // ignore
    }
    throw new ErrorApi(respuesta.status, mensaje);
  }
  const blob = await respuesta.blob();
  const filename = extraerFilename(respuesta.headers.get("Content-Disposition")) ?? `${dataset}.${formato}`;
  return { blob, filename };
}

export async function descargarJob(jobId: string): Promise<{ blob: Blob; filename: string }> {
  const tokenJob = getAccessToken();
  const headersJob: HeadersInit = {};
  if (tokenJob) headersJob["Authorization"] = `Bearer ${tokenJob}`;
  const respuesta = await fetch(`/api/exportacion/jobs/${jobId}/descarga`, {
    credentials: "include",
    headers: headersJob,
  });
  if (!respuesta.ok) {
    let mensaje = `Error del servidor (${respuesta.status})`;
    try {
      const cuerpo = await respuesta.json();
      if (cuerpo && typeof cuerpo === "object") {
        if ("detail" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detail);
        else if ("detalle" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detalle);
      }
    } catch {
      // ignore
    }
    throw new ErrorApi(respuesta.status, mensaje);
  }
  const blob = await respuesta.blob();
  const filename = extraerFilename(respuesta.headers.get("Content-Disposition")) ?? `${jobId}`;
  return { blob, filename };
}

function extraerFilename(cd: string | null): string | null {
  if (!cd) return null;
  const match = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
  if (match) {
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return match[1];
    }
  }
  return null;
}


