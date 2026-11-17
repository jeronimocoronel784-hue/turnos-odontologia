import { describe, it, expect } from "vitest";
import { permite, MATRIZ_RBAC } from "../src/shared/rbac";
import { RolUsuario } from "../src/shared/api-types";

describe("shared/rbac - Matriz de permisos (C-16 + C-17)", () => {
  it("Dueño tiene CRUD sobre pacientes, agenda, clínica, presupuestos, consentimientos, caja, liquidaciones, configuracion y usuarios", () => {
    const roles: RolUsuario[] = ["dueno"];
    expect(permite(roles, "pacientes", "crear")).toBe(true);
    expect(permite(roles, "clinica", "actualizar")).toBe(true);
    expect(permite(roles, "agenda", "borrar")).toBe(true);
    expect(permite(roles, "caja", "reabrir_cierre")).toBe(true);
    expect(permite(roles, "liquidaciones", "exportar")).toBe(true);
    expect(permite(roles, "configuracion", "crear")).toBe(true);
    expect(permite(roles, "usuarios", "crear")).toBe(true);
  });

  it("Recepción tiene CRUD en caja (sin reabrir_cierre), liquidaciones con exportar y solo lectura en configuracion y usuarios", () => {
    const roles: RolUsuario[] = ["recepcion"];
    expect(permite(roles, "pacientes", "crear")).toBe(true);
    expect(permite(roles, "agenda", "actualizar")).toBe(true);
    expect(permite(roles, "clinica", "leer")).toBe(true);
    expect(permite(roles, "clinica", "crear")).toBe(false);
    expect(permite(roles, "caja", "crear")).toBe(true);
    expect(permite(roles, "caja", "reabrir_cierre")).toBe(false);
    expect(permite(roles, "liquidaciones", "crear")).toBe(true);
    expect(permite(roles, "liquidaciones", "exportar")).toBe(true);
    expect(permite(roles, "configuracion", "leer")).toBe(true);
    expect(permite(roles, "configuracion", "crear")).toBe(false);
    expect(permite(roles, "usuarios", "leer")).toBe(true);
    expect(permite(roles, "usuarios", "crear")).toBe(false);
  });

  it("Odontólogo tiene solo lectura en caja, liquidaciones (sin exportar), configuracion y usuarios", () => {
    const roles: RolUsuario[] = ["odontologo"];
    expect(permite(roles, "clinica", "crear")).toBe(true);
    expect(permite(roles, "caja", "leer")).toBe(true);
    expect(permite(roles, "caja", "crear")).toBe(false);
    expect(permite(roles, "caja", "reabrir_cierre")).toBe(false);
    expect(permite(roles, "liquidaciones", "leer")).toBe(true);
    expect(permite(roles, "liquidaciones", "exportar")).toBe(false);
    expect(permite(roles, "configuracion", "leer")).toBe(true);
    expect(permite(roles, "configuracion", "crear")).toBe(false);
    expect(permite(roles, "usuarios", "leer")).toBe(true);
    expect(permite(roles, "usuarios", "crear")).toBe(false);
  });

  it("deniega por defecto ante roles desconocidos, nulos o lista vacía", () => {
    expect(permite(null, "agenda", "leer")).toBe(false);
    expect(permite([], "agenda", "leer")).toBe(false);
    expect(permite(["desconocido" as RolUsuario], "caja", "leer")).toBe(false);
  });

  it("valida consistencia con todos los recursos de C-16 y C-17", () => {
    const recursosEsperados = [
      "pacientes",
      "agenda",
      "bloqueos",
      "clinica",
      "presupuestos",
      "consentimientos",
      "mensajes",
      "caja",
      "liquidaciones",
      "configuracion",
      "usuarios",
      "auditoria",
      "exportacion",
      "exportacion_tenant",
    ] as const;

    recursosEsperados.forEach((recurso) => {
      expect(MATRIZ_RBAC[recurso]).toBeDefined();
    });
  });

  it("C-14: auditoria solo lectura para Dueño; exportacion_tenant y pacientes.exportar solo Dueño", () => {
    const dueno: RolUsuario[] = ["dueno"];
    const recepcion: RolUsuario[] = ["recepcion"];
    const odontologo: RolUsuario[] = ["odontologo"];

    expect(permite(dueno, "auditoria", "leer")).toBe(true);
    expect(permite(dueno, "auditoria", "crear")).toBe(false);
    expect(permite(recepcion, "auditoria", "leer")).toBe(false);
    expect(permite(odontologo, "auditoria", "leer")).toBe(false);

    expect(permite(dueno, "exportacion_tenant", "exportar")).toBe(true);
    expect(permite(recepcion, "exportacion_tenant", "exportar")).toBe(false);
    expect(permite(odontologo, "exportacion_tenant", "exportar")).toBe(false);

    expect(permite(dueno, "pacientes", "exportar")).toBe(true);
    expect(permite(recepcion, "pacientes", "exportar")).toBe(false);
    expect(permite(odontologo, "pacientes", "exportar")).toBe(false);
  });
});
