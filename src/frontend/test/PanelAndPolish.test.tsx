import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { PanelPage } from "../src/features/panel/PanelPage";
import { rutasApp } from "../src/main";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

describe("features/panel y verificaciones de cierre C-17 (Bloques 1.6, 6 y 7)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    setSesion("tok-dueno", {
      id: "u-dueno",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "dueno@demo.com",
      nombre: "Dr. Dueño",
      roles: ["dueno"],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("1.6 rutasApp en main.tsx incluye todas las rutas de C-17 sin romper C-15 ni C-16", () => {
    const rutasPublicas = rutasApp.map((r) => r.path);
    expect(rutasPublicas).toContain("/reservar/:slug");
    expect(rutasPublicas).toContain("/mis-turnos/:token");

    const shellApp = rutasApp.find((r) => r.path === "/app");
    expect(shellApp).toBeDefined();
    const hijas = (shellApp?.children ?? []).map((c) => c.path);

    // Rutas de C-16 preservadas
    expect(hijas).toContain("agenda");
    expect(hijas).toContain("pacientes");
    expect(hijas).toContain("comunicaciones");

    // Nuevas rutas de C-17
    expect(hijas).toContain("caja");
    expect(hijas).toContain("caja/cierres/:id");
    expect(hijas).toContain("cobros/turno/:turnoId");
    expect(hijas).toContain("os/liquidaciones");
    expect(hijas).toContain("os/liquidaciones/:id");
    expect(hijas).toContain("admin/prestaciones");
    expect(hijas).toContain("admin/sillones");
    expect(hijas).toContain("admin/coberturas");
    expect(hijas).toContain("admin/politicas");
    expect(hijas).toContain("admin/usuarios");
    expect(hijas).toContain("panel");
  });

  it("6.1 y 6.2 PanelPage carga las 4 consultas en paralelo mostrando montos del servidor y conteos", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "cie-hoy",
            tenant_id: "t-1",
            fecha: "2026-11-16",
            total_sistema: "45000.00",
            total_contado: "45000.00",
            diferencia: "0.00",
            estado: "cerrado",
            abierto_por: "u-dueno",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T18:00:00Z",
          },
        ],
      },
      {
        ruta: /\/api\/liquidaciones/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "liq-1",
            tenant_id: "t-1",
            obra_social: "OSDE",
            periodo: "202611",
            estado: "borrador",
            total: "80000.00",
            total_reconocido: null,
            created_by: "u-dueno",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
            turnos_sin_cobertura: 0,
            advertencias: [],
            detalles: [],
          },
        ],
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "sen-1",
            tenant_id: "t-1",
            turno_id: "tur-1",
            monto: "15000.00",
            estado: "pendiente",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
          },
        ],
      },
      {
        ruta: /\/api\/agenda/,
        metodo: "GET",
        status: 200,
        body: {
          turnos: [
            {
              id: "tur-1",
              tenant_id: "t-1",
              paciente_id: "pac-1",
              profesional_id: "u-odonto",
              sillon_id: "sil-1",
              prestacion_id: "pres-1",
              inicio: "2026-11-16T10:00:00Z",
              fin: "2026-11-16T10:30:00Z",
              estado: "confirmado",
              origen: "online",
              sobreturno: false,
            },
          ],
          bloqueos: [],
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PanelPage />);

    const montosCaja = await screen.findAllByText(/45\.000,00/);
    expect(montosCaja.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/80\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/15\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/OSDE/)).toBeInTheDocument();
  });

  it("6.2 y 6.3 caso 'caja sin abrir' no muestra totales en cero como cuadrados y tolera fallo parcial de red", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/liquidaciones/,
        metodo: "GET",
        status: 500,
        body: { detail: "Error temporal en liquidaciones" },
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/agenda/,
        metodo: "GET",
        status: 200,
        body: { turnos: [], bloqueos: [] },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PanelPage />);

    expect(await screen.findByText(/caja sin abrir hoy/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /abrir caja del día/i })).toBeInTheDocument();
    // Fallo parcial en liquidaciones conserva la tarjeta de caja y muestra botón reintentar en liquidaciones
    expect(
      await screen.findByText(/no pudimos cargar las liquidaciones/i),
    ).toBeInTheDocument();
  });

  it("7.5 verifica que no se escribe nada en localStorage ni sessionStorage (R6, R9)", async () => {
    const spyLocal = vi.spyOn(Storage.prototype, "setItem");

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/liquidaciones/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/agenda/,
        metodo: "GET",
        status: 200,
        body: { turnos: [], bloqueos: [] },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PanelPage />);
    await screen.findByText(/caja sin abrir hoy/i);

    limpiarSesion();
    expect(spyLocal).not.toHaveBeenCalled();
    spyLocal.mockRestore();
  });
});
