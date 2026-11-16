import { apiFetch, ErrorApi } from "../../shared/api-client";
import { getAccessToken } from "../../shared/sesion";
import type {
  CoberturaLookupRead,
  LiquidacionOSAnularInput,
  LiquidacionOSCerrarInput,
  LiquidacionOSCreateInput,
  LiquidacionOSDebitosInput,
  LiquidacionOSRead,
  ResultadoOSInput,
} from "../../shared/api-types";

export interface FiltrosCoberturaLookup {
  prestacion_id?: string;
  turno_id?: string;
  obra_social?: string;
  fecha?: string;
}

export async function consultarCoberturaOS(
  filtros: FiltrosCoberturaLookup,
): Promise<CoberturaLookupRead> {
  const params = new URLSearchParams();
  if (filtros.prestacion_id) params.set("prestacion_id", filtros.prestacion_id);
  if (filtros.turno_id) params.set("turno_id", filtros.turno_id);
  if (filtros.obra_social) params.set("obra_social", filtros.obra_social);
  if (filtros.fecha) params.set("fecha", filtros.fecha);
  return apiFetch<CoberturaLookupRead>(`/api/os/cobertura?${params.toString()}`);
}

export async function listarLiquidacionesOS(filtros?: {
  obra_social?: string;
  periodo?: string;
  estado?: string;
}): Promise<LiquidacionOSRead[]> {
  const params = new URLSearchParams();
  if (filtros?.obra_social) params.set("obra_social", filtros.obra_social);
  if (filtros?.periodo) params.set("periodo", filtros.periodo);
  if (filtros?.estado) params.set("estado", filtros.estado);
  const qs = params.toString();
  const ruta = qs ? `/api/liquidaciones?${qs}` : "/api/liquidaciones";
  return apiFetch<LiquidacionOSRead[]>(ruta);
}

export async function obtenerLiquidacionOS(id: string): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>(`/api/liquidaciones/${id}`);
}

export async function crearLiquidacionOS(
  datos: LiquidacionOSCreateInput,
): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>("/api/liquidaciones", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function actualizarDebitosLiquidacionOS(
  id: string,
  datos: LiquidacionOSDebitosInput,
): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>(`/api/liquidaciones/${id}`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}

export async function cerrarLiquidacionOS(
  id: string,
  datos?: LiquidacionOSCerrarInput,
): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>(`/api/liquidaciones/${id}/cerrar`, {
    method: "POST",
    body: datos ? JSON.stringify(datos) : undefined,
  });
}

export async function registrarResultadoLiquidacionOS(
  id: string,
  datos: ResultadoOSInput,
): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>(`/api/liquidaciones/${id}/resultado`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function anularLiquidacionOS(
  id: string,
  datos: LiquidacionOSAnularInput,
): Promise<LiquidacionOSRead> {
  return apiFetch<LiquidacionOSRead>(`/api/liquidaciones/${id}`, {
    method: "DELETE",
    body: JSON.stringify(datos),
  });
}

/**
 * Descarga la exportación CSV/JSON desde el servidor usando fetch con Bearer,
 * extrae el nombre de archivo de Content-Disposition y limpia la URL temporal (D5, 4.6).
 */
export async function descargarExportacionLiquidacion(
  id: string,
  formato: "csv" | "json",
  fallbackNombre: string,
): Promise<string> {
  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`/api/liquidaciones/${id}/exportar?formato=${formato}`, {
    method: "GET",
    credentials: "include",
    headers,
  });

  if (!res.ok) {
    let detalle = "No pudimos exportar la liquidación.";
    try {
      const errJson = (await res.json()) as { detail?: string };
      if (errJson?.detail) detalle = errJson.detail;
    } catch {
      // Ignorar si no es JSON
    }
    throw new ErrorApi(res.status, detalle);
  }

  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const filename = match?.[1] ?? `${fallbackNombre}.${formato}`;

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  return filename;
}
