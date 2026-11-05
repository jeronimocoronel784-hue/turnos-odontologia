// Cliente HTTP de reserva y autogestión pública (R5: estricto, sin any).
import type {
  CatalogoDisponibilidad,
  ConsentimientoFirmado,
  ConsentimientoPublico,
  FirmaConsentimientoInput,
  ListaEsperaPublica,
  PreferenciaPago,
  ReservaPublicaInput,
  ReservaPublicaResponse,
  SlotDisponible,
  CancelarTurnoInput,
  ReprogramarTurnoInput,
} from "./api-types";

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/**
 * Error de la API pública con el status HTTP y los datos que el backend adjunta.
 * Permite distinguir un 409 de solapamiento (con slots alternativos) de otros fallos.
 */
export class ErrorApi extends Error {
  readonly status: number;
  readonly slotsAlternativos: SlotDisponible[];

  constructor(mensaje: string, status: number, slotsAlternativos: SlotDisponible[] = []) {
    super(mensaje);
    this.name = "ErrorApi";
    this.status = status;
    this.slotsAlternativos = slotsAlternativos;
  }
}

function extraerMensaje(cuerpo: unknown, status: number): string {
  if (typeof cuerpo === "object" && cuerpo !== null) {
    if ("detail" in cuerpo) {
      const detail = (cuerpo as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const primero: unknown = detail[0];
        if (typeof primero === "object" && primero !== null && "msg" in primero) {
          return String((primero as { msg: unknown }).msg);
        }
      }
    }
    if ("detalle" in cuerpo) {
      return String((cuerpo as { detalle: unknown }).detalle);
    }
  }
  if (status === 401) {
    return "Ese link no es válido o ya venció. Pedí uno nuevo en el consultorio.";
  }
  if (status === 404) {
    return "No encontramos esa información o el enlace ya no está disponible.";
  }
  if (status === 409) {
    return "¡Uh! Ese horario se acaba de ocupar recién. Elegí otro disponible.";
  }
  return "Ocurrió un error inesperado al procesar tu solicitud.";
}

function extraerSlots(cuerpo: unknown): SlotDisponible[] {
  if (typeof cuerpo !== "object" || cuerpo === null || !("slots_alternativos" in cuerpo)) {
    return [];
  }
  const slots = (cuerpo as { slots_alternativos: unknown }).slots_alternativos;
  return Array.isArray(slots) ? (slots as SlotDisponible[]) : [];
}

async function procesarRespuesta<T>(respuesta: Response): Promise<T> {
  const esJson = respuesta.headers.get("content-type")?.includes("application/json") ?? false;
  const cuerpo: unknown = esJson ? await respuesta.json() : null;

  if (!respuesta.ok) {
    throw new ErrorApi(
      extraerMensaje(cuerpo, respuesta.status),
      respuesta.status,
      extraerSlots(cuerpo)
    );
  }

  return cuerpo as T;
}

function urlApi(ruta: string): string {
  return `${BASE_URL}${ruta}`;
}

export async function obtenerDisponibilidadPublica(
  slug: string,
  params?: {
    prestacion_id?: string;
    profesional_id?: string;
    sillon_id?: string;
    fecha?: string;
  },
  signal?: AbortSignal
): Promise<CatalogoDisponibilidad> {
  const query = new URLSearchParams();
  if (params?.prestacion_id) query.set("prestacion_id", params.prestacion_id);
  if (params?.profesional_id) query.set("profesional_id", params.profesional_id);
  if (params?.sillon_id) query.set("sillon_id", params.sillon_id);
  if (params?.fecha) query.set("fecha", params.fecha);

  const qs = query.toString();
  const url = urlApi(`/api/reservar/${encodeURIComponent(slug)}${qs ? `?${qs}` : ""}`);
  const respuesta = await fetch(url, { signal });
  return procesarRespuesta<CatalogoDisponibilidad>(respuesta);
}

export async function crearReservaPublica(
  slug: string,
  payload: ReservaPublicaInput
): Promise<ReservaPublicaResponse> {
  const respuesta = await fetch(urlApi(`/api/reservar/${encodeURIComponent(slug)}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return procesarRespuesta<ReservaPublicaResponse>(respuesta);
}

export async function obtenerMiTurno(
  token: string,
  signal?: AbortSignal
): Promise<ReservaPublicaResponse> {
  const respuesta = await fetch(urlApi(`/api/mis-turnos/${encodeURIComponent(token)}`), {
    signal,
  });
  return procesarRespuesta<ReservaPublicaResponse>(respuesta);
}

export async function confirmarMiTurno(token: string): Promise<ReservaPublicaResponse> {
  const respuesta = await fetch(urlApi(`/api/mis-turnos/${encodeURIComponent(token)}/confirmar`), {
    method: "POST",
  });
  return procesarRespuesta<ReservaPublicaResponse>(respuesta);
}

export async function cancelarMiTurno(
  token: string,
  payload?: CancelarTurnoInput
): Promise<ReservaPublicaResponse> {
  const respuesta = await fetch(urlApi(`/api/mis-turnos/${encodeURIComponent(token)}/cancelar`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
  return procesarRespuesta<ReservaPublicaResponse>(respuesta);
}

export async function reprogramarMiTurno(
  token: string,
  payload: ReprogramarTurnoInput
): Promise<ReservaPublicaResponse> {
  const respuesta = await fetch(
    urlApi(`/api/mis-turnos/${encodeURIComponent(token)}/reprogramar`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return procesarRespuesta<ReservaPublicaResponse>(respuesta);
}

export async function obtenerDisponibilidadMiTurno(
  token: string,
  fecha?: string,
  signal?: AbortSignal
): Promise<SlotDisponible[]> {
  const query = new URLSearchParams();
  if (fecha) query.set("fecha", fecha);
  const qs = query.toString();
  const respuesta = await fetch(
    urlApi(`/api/mis-turnos/${encodeURIComponent(token)}/disponibilidad${qs ? `?${qs}` : ""}`),
    { signal }
  );
  return procesarRespuesta<SlotDisponible[]>(respuesta);
}

export async function obtenerPreferenciaPago(token: string): Promise<PreferenciaPago> {
  const respuesta = await fetch(urlApi(`/api/mis-turnos/${encodeURIComponent(token)}/pago`), {
    method: "POST",
  });
  return procesarRespuesta<PreferenciaPago>(respuesta);
}

export async function obtenerConsentimiento(
  token: string,
  signal?: AbortSignal
): Promise<ConsentimientoPublico> {
  const respuesta = await fetch(urlApi(`/api/firmar/${encodeURIComponent(token)}`), { signal });
  return procesarRespuesta<ConsentimientoPublico>(respuesta);
}

export async function firmarConsentimiento(
  token: string,
  payload: FirmaConsentimientoInput
): Promise<ConsentimientoFirmado> {
  const respuesta = await fetch(urlApi(`/api/firmar/${encodeURIComponent(token)}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return procesarRespuesta<ConsentimientoFirmado>(respuesta);
}

export async function obtenerListaEspera(
  token: string,
  signal?: AbortSignal
): Promise<ListaEsperaPublica> {
  const respuesta = await fetch(urlApi(`/api/lista-espera/${encodeURIComponent(token)}`), {
    signal,
  });
  return procesarRespuesta<ListaEsperaPublica>(respuesta);
}

export async function aceptarHuecoListaEspera(token: string): Promise<ListaEsperaPublica> {
  const respuesta = await fetch(
    urlApi(`/api/lista-espera/${encodeURIComponent(token)}/aceptar`),
    { method: "POST" }
  );
  return procesarRespuesta<ListaEsperaPublica>(respuesta);
}

export async function darDeBajaListaEspera(token: string): Promise<ListaEsperaPublica> {
  const respuesta = await fetch(urlApi(`/api/lista-espera/${encodeURIComponent(token)}/baja`), {
    method: "POST",
  });
  return procesarRespuesta<ListaEsperaPublica>(respuesta);
}
