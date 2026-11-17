import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { rutasApp } from "../src/main";
import { crearTestQueryClient } from "./render";
import { estaAutenticado, limpiarSesion } from "../src/shared/sesion";

function renderPaginaLegal() {
  const router = createMemoryRouter(rutasApp, { initialEntries: ["/privacidad"] });
  return render(
    <QueryClientProvider client={crearTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("features/legal/PaginaLegalPage (C-14)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  // -------------------------------------------------------------------------
  // 8.1 /privacidad es pública y no depende de la sesión
  // -------------------------------------------------------------------------
  it("8.1 /privacidad renderiza sin sesión y sin llamar a la API", async () => {
    const fetchOriginal = globalThis.fetch;
    const fetchMock = vi.fn(() => {
      throw new Error("La página legal no debe llamar a la API");
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    restaurarFetch = () => {
      globalThis.fetch = fetchOriginal;
    };

    expect(estaAutenticado()).toBe(false);

    renderPaginaLegal();

    expect(
      await screen.findByRole("heading", { name: "Política de Privacidad" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("pagina-legal")).toBeInTheDocument();
    expect(estaAutenticado()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/Ingreso exclusivo para profesionales/i)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8.1 Contenido legal mínimo exigido
  // -------------------------------------------------------------------------
  it("8.1 menciona Ley 25.326, Ley 26.529 (HCE), finalidad, derechos y retención mínima de 5 años", async () => {
    renderPaginaLegal();
    await screen.findByTestId("pagina-legal");

    const contenido = screen.getByTestId("pagina-legal").textContent ?? "";
    expect(contenido).toMatch(/Ley 25\.326/);
    expect(contenido).toMatch(/Ley 26\.529/);
    expect(contenido).toMatch(/Historia Clínica Electrónica/);
    expect(contenido).toMatch(/\(HCE\)/);

    expect(screen.getByRole("heading", { name: "Finalidad" })).toBeInTheDocument();
    expect(contenido).toMatch(/gestionar turnos/i);
    expect(screen.getByRole("heading", { name: "Derechos" })).toBeInTheDocument();
    expect(contenido).toMatch(/acceso, rectificación y supresión/i);
    expect(screen.getByRole("heading", { name: "Retención" })).toBeInTheDocument();
    expect(contenido).toMatch(/mínimo de 5 años/i);
    expect(contenido).toMatch(/RN-SE-02/);
  });

  it("8.1 sin VITE_CONTACTO_PRIVACIDAD muestra el contacto genérico del consultorio", async () => {
    vi.stubEnv("VITE_CONTACTO_PRIVACIDAD", "");

    renderPaginaLegal();
    await screen.findByTestId("pagina-legal");

    expect(screen.getByRole("heading", { name: "Contacto" })).toBeInTheDocument();
    expect(
      screen.getByText(/comunicate con el consultorio donde te atendiste/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Podés comunicarte a/i)).not.toBeInTheDocument();
  });

  it("8.1 con VITE_CONTACTO_PRIVACIDAD configurado publica el canal de contacto", async () => {
    vi.stubEnv("VITE_CONTACTO_PRIVACIDAD", "privacidad@consultorio-demo.test");

    renderPaginaLegal();
    await screen.findByTestId("pagina-legal");

    expect(
      screen.getByText(/Podés comunicarte a privacidad@consultorio-demo\.test/i),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8.1 Sin PHI ni escritura en el navegador
  // -------------------------------------------------------------------------
  it("8.1 no muestra datos de pacientes ni PHI y no escribe en localStorage", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    renderPaginaLegal();
    await screen.findByTestId("pagina-legal");

    const contenido = screen.getByTestId("pagina-legal").textContent ?? "";

    // Sin identificadores de pacientes: DNI, teléfonos ni emails de contacto de pacientes
    expect(contenido).not.toMatch(/\bDNI\b/i);
    expect(contenido).not.toMatch(/\b\d{7,8}\b/);
    expect(contenido).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
    expect(contenido).not.toMatch(/\b(paciente|Paciente)\s*:/);
    expect(contenido).toMatch(/no muestra datos de pacientes ni información sensible/i);

    expect(setItemSpy).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
