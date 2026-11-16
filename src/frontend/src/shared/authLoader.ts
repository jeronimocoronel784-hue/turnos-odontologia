import { redirect } from "react-router-dom";
import { bootstrapSesion, estaAutenticado, getIdentidad } from "./sesion";

export async function requerirSesion({ request }: { request: Request }) {
  if (!estaAutenticado()) {
    const usuario = await bootstrapSesion();
    if (!usuario) {
      const url = new URL(request.url);
      const destino = encodeURIComponent(url.pathname + url.search);
      return redirect(`/login?destino=${destino}`);
    }
  }

  return { usuario: getIdentidad() };
}
