import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  bootstrapSesion,
  getAccessToken,
  getIdentidad,
  limpiarSesion,
  estaAutenticado,
} from "../src/shared/sesion";
import { mockFetchDoble } from "./render";

describe("shared/sesion - Gestión de sesión en memoria", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("refresh 200 restaura identidad y access token en memoria", async () => {
    const usuarioMock = {
      id: "u-1",
      tenant_id: "t-1",
      tenant_slug: "consultorio-centro",
      email: "recepcion@consultorio.com",
      nombre: "María Recepcionista",
      roles: ["recepcion" as const],
    };

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/refresh",
        metodo: "POST",
        status: 200,
        body: {
          access_token: "token-secreto-123",
          token_type: "bearer",
          expira_en_segundos: 900,
          usuario: usuarioMock,
        },
      },
    ]);
    restaurarFetch = restaurar;

    const res = await bootstrapSesion();

    expect(res).toEqual(usuarioMock);
    expect(getAccessToken()).toBe("token-secreto-123");
    expect(getIdentidad()).toEqual(usuarioMock);
    expect(estaAutenticado()).toBe(true);
  });

  it("refresh 401 deja sin sesión", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/refresh",
        metodo: "POST",
        status: 401,
        body: { detail: "Refresh token vencido o inválido." },
      },
    ]);
    restaurarFetch = restaurar;

    const res = await bootstrapSesion();

    expect(res).toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(getIdentidad()).toBeNull();
    expect(estaAutenticado()).toBe(false);
  });

  it("dos bootstraps simultáneos hacen una sola llamada a refresh", async () => {
    let llamadas = 0;
    const fetchOriginal = global.fetch;
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/auth/refresh")) {
        llamadas++;
        // delay simulado
        await new Promise((r) => setTimeout(r, 20));
        return new Response(
          JSON.stringify({
            access_token: "tok-memo",
            token_type: "bearer",
            expira_en_segundos: 900,
            usuario: {
              id: "u-2",
              tenant_id: "t-1",
              tenant_slug: "demo",
              email: "doc@demo.com",
              nombre: "Dr. Gómez",
              roles: ["odontologo"],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("", { status: 404 });
    }) as unknown as typeof fetch;

    restaurarFetch = () => {
      global.fetch = fetchOriginal;
    };

    const [res1, res2] = await Promise.all([bootstrapSesion(), bootstrapSesion()]);

    expect(llamadas).toBe(1);
    expect(res1?.email).toBe("doc@demo.com");
    expect(res2?.email).toBe("doc@demo.com");
  });

  it("nunca escribe credenciales en localStorage ni sessionStorage (R6, R9)", async () => {
    const localSetItem = vi.spyOn(Storage.prototype, "setItem");
    const sessionSetItem = vi.spyOn(sessionStorage, "setItem");

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/refresh",
        metodo: "POST",
        status: 200,
        body: {
          access_token: "token-sensible",
          token_type: "bearer",
          expira_en_segundos: 900,
          usuario: {
            id: "u-1",
            tenant_id: "t-1",
            tenant_slug: "demo",
            email: "admin@demo.com",
            nombre: "Admin",
            roles: ["dueno"],
          },
        },
      },
    ]);
    restaurarFetch = restaurar;

    await bootstrapSesion();

    expect(localSetItem).not.toHaveBeenCalled();
    expect(sessionSetItem).not.toHaveBeenCalled();

    localSetItem.mockRestore();
    sessionSetItem.mockRestore();
  });
});
