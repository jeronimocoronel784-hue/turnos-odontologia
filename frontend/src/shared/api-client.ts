// Cliente HTTP único del frontend (D7). NUNCA guarda datos clínicos en localStorage (R6).

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

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
