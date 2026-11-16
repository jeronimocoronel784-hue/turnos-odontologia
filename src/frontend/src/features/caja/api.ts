import { apiFetch } from "../../shared/api-client";
import type {
  CierreCajaAbrirInput,
  CierreCajaCerrarInput,
  CierreCajaReabrirInput,
  CierreCajaRead,
  CobrarTurnoInput,
  LiquidacionTurnoRead,
  MovimientoCajaCreateInput,
  MovimientoCajaRead,
  SenaCobrarInput,
  SenaCreateInput,
  SenaRead,
  SenaResolverCancelacionInput,
} from "../../shared/api-types";

export interface FiltrosMovimientosCaja {
  desde?: string;
  hasta?: string;
  cierre_id?: string;
  medio?: string;
  tipo?: string;
}

export async function listarMovimientosCaja(
  filtros?: FiltrosMovimientosCaja,
): Promise<MovimientoCajaRead[]> {
  const params = new URLSearchParams();
  if (filtros?.desde) params.set("desde", filtros.desde);
  if (filtros?.hasta) params.set("hasta", filtros.hasta);
  if (filtros?.cierre_id) params.set("cierre_id", filtros.cierre_id);
  const qs = params.toString();
  const ruta = qs ? `/api/caja/movimientos?${qs}` : "/api/caja/movimientos";
  const lista = await apiFetch<MovimientoCajaRead[]>(ruta);
  return lista.filter((m) => {
    if (filtros?.medio && m.medio !== filtros.medio) return false;
    if (filtros?.tipo && m.tipo !== filtros.tipo) return false;
    return true;
  });
}

export async function crearMovimientoCaja(
  datos: MovimientoCajaCreateInput,
): Promise<MovimientoCajaRead> {
  return apiFetch<MovimientoCajaRead>("/api/caja/movimientos", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function listarCierresCaja(filtros?: {
  fecha?: string;
  estado?: string;
}): Promise<CierreCajaRead[]> {
  const params = new URLSearchParams();
  if (filtros?.fecha) params.set("fecha", filtros.fecha);
  if (filtros?.estado) params.set("estado", filtros.estado);
  const qs = params.toString();
  const ruta = qs ? `/api/caja/cierre?${qs}` : "/api/caja/cierre";
  return apiFetch<CierreCajaRead[]>(ruta);
}

export async function obtenerCierreCaja(cierreId: string): Promise<CierreCajaRead> {
  return apiFetch<CierreCajaRead>(`/api/caja/cierre/${cierreId}`);
}

export async function abrirCierreCaja(datos: CierreCajaAbrirInput): Promise<CierreCajaRead> {
  return apiFetch<CierreCajaRead>("/api/caja/cierre", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function cerrarCierreCaja(
  cierreId: string,
  datos: CierreCajaCerrarInput,
): Promise<CierreCajaRead> {
  return apiFetch<CierreCajaRead>(`/api/caja/cierre/${cierreId}/cerrar`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function reabrirCierreCaja(
  cierreId: string,
  datos: CierreCajaReabrirInput,
): Promise<CierreCajaRead> {
  return apiFetch<CierreCajaRead>(`/api/caja/cierre/${cierreId}/reabrir`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

// Cobro de Turno
export async function obtenerLiquidacionTurno(
  turnoId: string,
  obraSocial?: string,
): Promise<LiquidacionTurnoRead> {
  const params = new URLSearchParams();
  if (obraSocial) params.set("obra_social", obraSocial);
  const qs = params.toString();
  const ruta = qs
    ? `/api/caja/turnos/${turnoId}/liquidacion?${qs}`
    : `/api/caja/turnos/${turnoId}/liquidacion`;
  return apiFetch<LiquidacionTurnoRead>(ruta);
}

export async function cobrarTurno(
  turnoId: string,
  datos: CobrarTurnoInput,
): Promise<MovimientoCajaRead> {
  return apiFetch<MovimientoCajaRead>(`/api/caja/turnos/${turnoId}/cobrar`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

// Señas
export async function listarSenas(filtros?: {
  turno_id?: string;
  estado?: string;
}): Promise<SenaRead[]> {
  const params = new URLSearchParams();
  if (filtros?.turno_id) params.set("turno_id", filtros.turno_id);
  if (filtros?.estado) params.set("estado", filtros.estado);
  const qs = params.toString();
  const ruta = qs ? `/api/senas?${qs}` : "/api/senas";
  return apiFetch<SenaRead[]>(ruta);
}

export async function crearSena(datos: SenaCreateInput): Promise<SenaRead> {
  return apiFetch<SenaRead>("/api/senas", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function cobrarSena(senaId: string, datos: SenaCobrarInput): Promise<SenaRead> {
  return apiFetch<SenaRead>(`/api/senas/${senaId}/cobrar`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function resolverCancelacionSena(
  senaId: string,
  datos: SenaResolverCancelacionInput,
): Promise<SenaRead> {
  return apiFetch<SenaRead>(`/api/senas/${senaId}/cancelacion`, {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function vencerSena(senaId: string): Promise<SenaRead> {
  return apiFetch<SenaRead>(`/api/senas/${senaId}/vencer`, {
    method: "POST",
  });
}
