import { apiFetch } from "../../shared/api-client";
import { LoginRequest, TokenResponse } from "../../shared/api-types";
import { setSesion, limpiarSesion } from "../../shared/sesion";

export async function loginStaff(credenciales: LoginRequest): Promise<TokenResponse> {
  const respuesta = await apiFetch<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(credenciales),
  });

  setSesion(respuesta.access_token, respuesta.usuario);
  return respuesta;
}

export async function logoutStaff(): Promise<void> {
  try {
    await apiFetch<void>("/api/auth/logout", {
      method: "POST",
    });
  } finally {
    limpiarSesion();
  }
}
