import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { rutasApp } from "../src/main";
import { crearTestQueryClient, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion, estaAutenticado } from "../src/shared/sesion";
import { EstadoError, EstadoVacio, EstadoCargando } from "../src/shared/ComponentesEstado";
import { ErrorApi } from "../src/shared/api-client";
import { render } from "@testing-library/react";

describe("Shell interno - Protección, Layout, Rutas y Estados", () => {
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

  it("sin sesión redirige de /app/agenda a /login con destino", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/refresh",
        metodo: "POST",
        status: 401,
        body: { detail: "No hay sesión" },
      },
    ]);
    restaurarFetch = restaurar;

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/app/agenda"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    // Debe mostrar la pantalla de login con el título
    expect(await screen.findByText(/Ingreso exclusivo para profesionales/i)).toBeInTheDocument();
  });

  it("con sesión activa renderiza el layout y la vista protegida", async () => {
    setSesion("tok-valido", {
      id: "u-1",
      tenant_id: "t-1",
      tenant_slug: "consultorio-demo",
      email: "doc@demo.com",
      nombre: "Dr. Ramos",
      roles: ["odontologo"],
    });

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/app/agenda"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Dr. Ramos")).toBeInTheDocument();
    expect(screen.getByTestId("agenda-page")).toBeInTheDocument();
  });

  it("layout oculta navegación si el rol no tiene permiso (odontólogo no ve comunicaciones)", async () => {
    setSesion("tok-valido", {
      id: "u-2",
      tenant_id: "t-1",
      tenant_slug: "consultorio-demo",
      email: "doc@demo.com",
      nombre: "Dr. Ramos",
      roles: ["odontologo"],
    });

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/app/agenda"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Agenda")).toBeInTheDocument();
    expect(screen.getByText("Pacientes")).toBeInTheDocument();
    expect(screen.queryByText("Comunicaciones")).not.toBeInTheDocument();
  });

  it("recepción sí ve comunicaciones en la barra de navegación", async () => {
    setSesion("tok-valido", {
      id: "u-3",
      tenant_id: "t-1",
      tenant_slug: "consultorio-demo",
      email: "recepcion@demo.com",
      nombre: "Laura Recepción",
      roles: ["recepcion"],
    });

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/app/agenda"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Comunicaciones")).toBeInTheDocument();
  });

  it("botón de cerrar sesión ejecuta logout, limpia estado y navega a /login", async () => {
    const user = userEvent.setup();
    setSesion("tok-valido", {
      id: "u-1",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "admin@demo.com",
      nombre: "Dueño",
      roles: ["dueno"],
    });

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/logout",
        metodo: "POST",
        status: 200,
        body: {},
      },
    ]);
    restaurarFetch = restaurar;

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/app/agenda"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    const btnLogout = await screen.findByRole("button", { name: /Cerrar sesión/i });
    await user.click(btnLogout);

    await waitFor(() => {
      expect(estaAutenticado()).toBe(false);
      expect(screen.getByText(/Ingreso exclusivo para profesionales/i)).toBeInTheDocument();
    });
  });

  it("componentes de estado manejan carga, vacío y errores con rioplatense (Task 2.7)", () => {
    const { rerender } = render(<EstadoCargando mensaje="Buscando turnos..." />);
    expect(screen.getByRole("status")).toHaveTextContent("Buscando turnos...");

    rerender(
      <EstadoVacio
        titulo="No hay turnos"
        descripcion="No se encontraron citas para la fecha seleccionada."
      />,
    );
    expect(screen.getByText("No hay turnos")).toBeInTheDocument();

    // 403
    rerender(<EstadoError error={new ErrorApi(403, "No tenés permiso para clínica")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Acceso no autorizado");
    expect(screen.getByText("No tenés permiso para clínica")).toBeInTheDocument();

    // 404
    rerender(<EstadoError error={new ErrorApi(404, "")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("No encontrado");

    // 500
    rerender(<EstadoError error={new ErrorApi(500, "")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Inconveniente en el servidor");
  });

  it("rutas públicas de C-15 siguen resolviendo sin sesión (Task 2.8)", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/health",
        metodo: "GET",
        status: 200,
        body: { estado: "ok", api: "ok", base_de_datos: "ok", redis: "ok", detalle: "" },
      },
    ]);
    restaurarFetch = restaurar;

    const router = createMemoryRouter(rutasApp, { initialEntries: ["/"] });
    const queryClient = crearTestQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Turnos Odontología")).toBeInTheDocument();
  });
});
