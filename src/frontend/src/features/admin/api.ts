import { apiFetch } from "../../shared/api-client";
import type {
  CoberturaOSCreateInput,
  CoberturaOSRead,
  CoberturaOSUpdateInput,
  PoliticasRead,
  PoliticasUpdateInput,
  PrestacionCreateInput,
  PrestacionRead,
  PrestacionUpdateInput,
  SillonCreateInput,
  SillonRead,
  SillonUpdateInput,
  UsuarioCreateInput,
  UsuarioRead,
  UsuarioRolUpdateInput,
} from "../../shared/api-types";

// Prestaciones
export async function listarPrestacionesAdmin(): Promise<PrestacionRead[]> {
  return apiFetch<PrestacionRead[]>("/api/prestaciones");
}

export async function crearPrestacionAdmin(datos: PrestacionCreateInput): Promise<PrestacionRead> {
  return apiFetch<PrestacionRead>("/api/prestaciones", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function actualizarPrestacionAdmin(
  id: string,
  datos: PrestacionUpdateInput,
): Promise<PrestacionRead> {
  return apiFetch<PrestacionRead>(`/api/prestaciones/${id}`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}

export async function desactivarPrestacionAdmin(id: string): Promise<PrestacionRead> {
  return apiFetch<PrestacionRead>(`/api/prestaciones/${id}`, {
    method: "DELETE",
  });
}

// Sillones
export async function listarSillonesAdmin(): Promise<SillonRead[]> {
  return apiFetch<SillonRead[]>("/api/sillones");
}

export async function crearSillonAdmin(datos: SillonCreateInput): Promise<SillonRead> {
  return apiFetch<SillonRead>("/api/sillones", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function actualizarSillonAdmin(
  id: string,
  datos: SillonUpdateInput,
): Promise<SillonRead> {
  return apiFetch<SillonRead>(`/api/sillones/${id}`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}

export async function desactivarSillonAdmin(id: string): Promise<SillonRead> {
  return apiFetch<SillonRead>(`/api/sillones/${id}`, {
    method: "DELETE",
  });
}

// Coberturas OS
export async function listarCoberturasAdmin(): Promise<CoberturaOSRead[]> {
  return apiFetch<CoberturaOSRead[]>("/api/coberturas");
}

export async function crearCoberturaAdmin(datos: CoberturaOSCreateInput): Promise<CoberturaOSRead> {
  return apiFetch<CoberturaOSRead>("/api/coberturas", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function actualizarCoberturaAdmin(
  id: string,
  datos: CoberturaOSUpdateInput,
): Promise<CoberturaOSRead> {
  return apiFetch<CoberturaOSRead>(`/api/coberturas/${id}`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}

export async function desactivarCoberturaAdmin(id: string): Promise<CoberturaOSRead> {
  return apiFetch<CoberturaOSRead>(`/api/coberturas/${id}`, {
    method: "DELETE",
  });
}

// Políticas
export async function obtenerPoliticasAdmin(): Promise<PoliticasRead> {
  return apiFetch<PoliticasRead>("/api/tenant/politicas");
}

export async function actualizarPoliticasAdmin(datos: PoliticasUpdateInput): Promise<PoliticasRead> {
  return apiFetch<PoliticasRead>("/api/tenant/politicas", {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}

// Usuarios
export async function listarUsuariosAdmin(): Promise<UsuarioRead[]> {
  return apiFetch<UsuarioRead[]>("/api/usuarios");
}

export async function crearUsuarioAdmin(datos: UsuarioCreateInput): Promise<UsuarioRead> {
  return apiFetch<UsuarioRead>("/api/usuarios", {
    method: "POST",
    body: JSON.stringify(datos),
  });
}

export async function cambiarRolUsuarioAdmin(
  id: string,
  datos: UsuarioRolUpdateInput,
): Promise<UsuarioRead> {
  return apiFetch<UsuarioRead>(`/api/usuarios/${id}/rol`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
}
