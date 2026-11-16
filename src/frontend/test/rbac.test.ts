import { describe, it, expect } from "vitest";
import { permite, MATRIZ_RBAC } from "../src/shared/rbac";
import { RolUsuario } from "../src/shared/api-types";

describe("shared/rbac - Matriz de permisos", () => {
  it("Dueño tiene CRUD sobre pacientes, agenda, clínica, presupuestos y consentimientos", () => {
    const roles: RolUsuario[] = ["dueno"];
    expect(permite(roles, "pacientes", "crear")).toBe(true);
    expect(permite(roles, "clinica", "actualizar")).toBe(true);
    expect(permite(roles, "agenda", "borrar")).toBe(true);
    expect(permite(roles, "caja", "reabrir_cierre")).toBe(true);
  });

  it("Recepción tiene CRUD sobre pacientes y agenda, pero solo lectura en clínica", () => {
    const roles: RolUsuario[] = ["recepcion"];
    expect(permite(roles, "pacientes", "crear")).toBe(true);
    expect(permite(roles, "agenda", "actualizar")).toBe(true);
    expect(permite(roles, "clinica", "leer")).toBe(true);
    expect(permite(roles, "clinica", "crear")).toBe(false);
    expect(permite(roles, "clinica", "actualizar")).toBe(false);
    expect(permite(roles, "caja", "reabrir_cierre")).toBe(false);
  });

  it("Odontólogo tiene CRUD en clínica, pero solo lectura en pacientes y agenda limitada", () => {
    const roles: RolUsuario[] = ["odontologo"];
    expect(permite(roles, "clinica", "crear")).toBe(true);
    expect(permite(roles, "clinica", "actualizar")).toBe(true);
    expect(permite(roles, "pacientes", "leer")).toBe(true);
    expect(permite(roles, "pacientes", "crear")).toBe(false);
    expect(permite(roles, "agenda", "borrar")).toBe(false);
    expect(permite(roles, "mensajes", "leer")).toBe(false);
  });

  it("deniega por defecto ante roles desconocidos, nulos o lista vacía", () => {
    expect(permite(null, "agenda", "leer")).toBe(false);
    expect(permite([], "agenda", "leer")).toBe(false);
    expect(permite(["desconocido" as RolUsuario], "agenda", "leer")).toBe(false);
  });

  it("valida consistencia con los recursos esperados de C-16", () => {
    const recursosEsperados = [
      "pacientes",
      "agenda",
      "bloqueos",
      "clinica",
      "presupuestos",
      "consentimientos",
      "mensajes",
    ] as const;

    recursosEsperados.forEach((recurso) => {
      expect(MATRIZ_RBAC[recurso]).toBeDefined();
    });
  });
});
