import { IdentidadRead, TokenResponse } from "./api-types";

export interface SesionEstado {
  autenticado: boolean;
  usuario: IdentidadRead | null;
  accessToken: string | null;
}

let accessTokenMemoria: string | null = null;
let identidadMemoria: IdentidadRead | null = null;
let bootstrapPromesa: Promise<IdentidadRead | null> | null = null;

type Listener = (estado: SesionEstado) => void;
const listeners = new Set<Listener>();

function notificar() {
  const estado: SesionEstado = {
    autenticado: accessTokenMemoria !== null && identidadMemoria !== null,
    usuario: identidadMemoria,
    accessToken: accessTokenMemoria,
  };
  listeners.forEach((listener) => {
    try {
      listener(estado);
    } catch {
      // Ignorar errores en listeners individuales
    }
  });
}

export function getAccessToken(): string | null {
  return accessTokenMemoria;
}

export function getIdentidad(): IdentidadRead | null {
  return identidadMemoria;
}

export function estaAutenticado(): boolean {
  return accessTokenMemoria !== null && identidadMemoria !== null;
}

export function setSesion(token: string, usuario: IdentidadRead): void {
  accessTokenMemoria = token;
  identidadMemoria = usuario;
  notificar();
}

export function limpiarSesion(): void {
  accessTokenMemoria = null;
  identidadMemoria = null;
  bootstrapPromesa = null;
  notificar();
}

export function suscribirASesion(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function bootstrapSesion(forzar = false): Promise<IdentidadRead | null> {
  if (!forzar && accessTokenMemoria && identidadMemoria) {
    return identidadMemoria;
  }

  if (bootstrapPromesa) {
    return bootstrapPromesa;
  }

  bootstrapPromesa = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });

      if (!res.ok) {
        limpiarSesion();
        return null;
      }

      const datos = (await res.json()) as TokenResponse;
      accessTokenMemoria = datos.access_token;
      identidadMemoria = datos.usuario;
      notificar();
      return datos.usuario;
    } catch {
      limpiarSesion();
      return null;
    } finally {
      bootstrapPromesa = null;
    }
  })();

  return bootstrapPromesa;
}
