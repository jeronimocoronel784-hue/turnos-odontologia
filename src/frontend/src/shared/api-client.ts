import { getAccessToken, bootstrapSesion, limpiarSesion } from "./sesion";

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

export class ErrorApi extends Error {
  readonly status: number;
  readonly detalle: string;

  constructor(status: number, detalle: string) {
    super(detalle);
    this.name = "ErrorApi";
    this.status = status;
    this.detalle = detalle;
  }
}

export interface EstadoApi {
  estado: string;
  api: string;
  base_de_datos: string;
  redis: string;
  detalle: string;
}

export async function obtenerSalud(senal: AbortSignal | undefined): Promise<EstadoApi> {
  const respuesta = await fetch(`${BASE_URL}/api/health`, { signal: senal });
  const cuerpo: unknown = await respuesta.json();
  if (!respuesta.ok) {
    const detalle =
      typeof cuerpo === "object" && cuerpo !== null && "detalle" in cuerpo
        ? String((cuerpo as Record<string, unknown>).detalle)
        : "La API no responde como se esperaba.";
    throw new Error(detalle);
  }
  return cuerpo as EstadoApi;
}

export async function apiFetch<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  const url = ruta.startsWith("http") ? ruta : `${BASE_URL}${ruta}`;
  const headers = new Headers(init.headers);

  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const opciones: RequestInit = {
    ...init,
    headers,
    credentials: init.credentials ?? "include",
  };

  let respuesta = await fetch(url, opciones);

  // Manejo de refresh único si da 401 y no es una ruta de auth
  const esRutaAuth = ruta.includes("/api/auth/login") || ruta.includes("/api/auth/refresh");
  if (respuesta.status === 401 && !esRutaAuth) {
    const usuarioRefrescado = await bootstrapSesion(true);
    const nuevoToken = getAccessToken();

    if (usuarioRefrescado && nuevoToken) {
      headers.set("Authorization", `Bearer ${nuevoToken}`);
      respuesta = await fetch(url, { ...opciones, headers });
    } else {
      limpiarSesion();
      throw new ErrorApi(401, "Sesión vencida. Por favor ingresá nuevamente.");
    }
  }

  if (respuesta.status === 204) {
    return null as unknown as T;
  }

  if (!respuesta.ok) {
    let mensaje = `Error del servidor (${respuesta.status})`;
    try {
      const cuerpoError: unknown = await respuesta.json();
      if (typeof cuerpoError === "object" && cuerpoError !== null) {
        if ("detail" in cuerpoError) {
          mensaje = String((cuerpoError as Record<string, unknown>).detail);
        } else if ("detalle" in cuerpoError) {
          mensaje = String((cuerpoError as Record<string, unknown>).detalle);
        }
      }
    } catch {
      // Si no es JSON, conservar el mensaje estándar
    }

    if (respuesta.status === 401) {
      limpiarSesion();
    }

    throw new ErrorApi(respuesta.status, mensaje);
  }

  // Parsear respuesta exitosa
  const texto = await respuesta.text();
  if (!texto) {
    return null as unknown as T;
  }

  return JSON.parse(texto) as T;
}
