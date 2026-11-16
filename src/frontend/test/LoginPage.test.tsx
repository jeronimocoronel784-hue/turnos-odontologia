import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "../src/features/auth/LoginPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { limpiarSesion, estaAutenticado, getAccessToken } from "../src/shared/sesion";

const mockedNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  };
});

describe("features/auth/LoginPage", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    mockedNavigate.mockReset();
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("login 200 guarda sesión y navega al destino", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/login",
        metodo: "POST",
        status: 200,
        body: {
          access_token: "tok-valido",
          token_type: "bearer",
          expira_en_segundos: 900,
          usuario: {
            id: "u-1",
            tenant_id: "t-1",
            tenant_slug: "demo",
            email: "recepcion@demo.com",
            nombre: "Recepcionista",
            roles: ["recepcion"],
          },
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LoginPage />, { ruta: "/login?destino=/app/agenda" });

    await user.type(screen.getByLabelText(/Email/i), "recepcion@demo.com");
    await user.type(screen.getByLabelText(/^Contraseña/i), "password123");
    await user.click(screen.getByRole("button", { name: /Ingresar/i }));

    await waitFor(() => {
      expect(mockedNavigate).toHaveBeenCalledWith("/app/agenda", { replace: true });
    });
    expect(estaAutenticado()).toBe(true);
    expect(getAccessToken()).toBe("tok-valido");
  });

  it("401 muestra mensaje genérico sin revelar el email", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/login",
        metodo: "POST",
        status: 401,
        body: { detail: "Credenciales inválidas" },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email/i), "noexiste@demo.com");
    await user.type(screen.getByLabelText(/^Contraseña/i), "claveerronea");
    await user.click(screen.getByRole("button", { name: /Ingresar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email o contraseña incorrectos.");
    expect(screen.queryByText(/noexiste@demo.com/)).not.toBeInTheDocument();
  });

  it("429 pide esperar", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auth/login",
        metodo: "POST",
        status: 429,
        body: { detail: "Rate limit excedido" },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/Email/i), "bloqueado@demo.com");
    await user.type(screen.getByLabelText(/^Contraseña/i), "clave");
    await user.click(screen.getByRole("button", { name: /Ingresar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demasiados intentos. Por favor esperá unos minutos antes de reintentar.",
    );
  });

  it("formulario vacío no llama a la API y muestra validación local", async () => {
    const user = userEvent.setup();
    const mock = vi.fn();
    global.fetch = mock;

    renderConProviders(<LoginPage />);

    await user.click(screen.getByRole("button", { name: /Ingresar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Por favor completá tu email y contraseña.",
    );
    expect(mock).not.toHaveBeenCalled();
  });
});
