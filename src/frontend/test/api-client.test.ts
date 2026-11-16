import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { apiFetch, ErrorApi } from "../src/shared/api-client";
import { setSesion, limpiarSesion, estaAutenticado, getAccessToken } from "../src/shared/sesion";

describe("shared/api-client - apiFetch", () => {
  const fetchOriginal = global.fetch;

  beforeEach(() => {
    limpiarSesion();
  });

  afterEach(() => {
    global.fetch = fetchOriginal;
  });

  it("reintenta con nuevo token si el primer request devuelve 401", async () => {
    setSesion("token-viejo", {
      id: "u-1",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "test@demo.com",
      nombre: "Test",
      roles: ["recepcion"],
    });

    let llamadasTurnos = 0;
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();

      if (url.includes("/api/turnos")) {
        llamadasTurnos++;
        const auth = init?.headers ? new Headers(init.headers).get("Authorization") : null;
        if (auth === "Bearer token-viejo") {
          return new Response(JSON.stringify({ detail: "Token expirado" }), { status: 401 });
        }
        if (auth === "Bearer token-renovado") {
          return new Response(JSON.stringify([{ id: "turno-1" }]), { status: 200 });
        }
      }

      if (url.includes("/api/auth/refresh")) {
        return new Response(
          JSON.stringify({
            access_token: "token-renovado",
            token_type: "bearer",
            expira_en_segundos: 900,
            usuario: {
              id: "u-1",
              tenant_id: "t-1",
              tenant_slug: "demo",
              email: "test@demo.com",
              nombre: "Test",
              roles: ["recepcion"],
            },
          }),
          { status: 200 },
        );
      }

      return new Response("", { status: 404 });
    }) as unknown as typeof fetch;

    const res = await apiFetch<Array<{ id: string }>>("/api/turnos");

    expect(llamadasTurnos).toBe(2);
    expect(res).toEqual([{ id: "turno-1" }]);
    expect(getAccessToken()).toBe("token-renovado");
  });

  it("segundo 401 o falla de refresh limpia la sesión y lanza ErrorApi(401)", async () => {
    setSesion("token-invalido", {
      id: "u-1",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "test@demo.com",
      nombre: "Test",
      roles: ["recepcion"],
    });

    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/turnos")) {
        return new Response(JSON.stringify({ detail: "Token vencido" }), { status: 401 });
      }
      if (url.includes("/api/auth/refresh")) {
        return new Response(JSON.stringify({ detail: "Refresh expirado" }), { status: 401 });
      }
      return new Response("", { status: 404 });
    }) as unknown as typeof fetch;

    await expect(apiFetch("/api/turnos")).rejects.toThrow(ErrorApi);
    expect(estaAutenticado()).toBe(false);
  });

  it("403 propaga mensaje amigable en detail", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(
        JSON.stringify({ detail: "No tenés permiso para editar la historia clínica." }),
        { status: 403, headers: { "Content-Type": "application/json" } },
      );
    }) as unknown as typeof fetch;

    await expect(apiFetch("/api/pacientes/p-1/ficha")).rejects.toMatchObject({
      status: 403,
      detalle: "No tenés permiso para editar la historia clínica.",
    });
  });

  it("204 responde null sin intentar parsear JSON", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;

    const res = await apiFetch<void>("/api/bloqueos/b-1", { method: "DELETE" });
    expect(res).toBeNull();
  });
});
