import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PacientesPage, PacienteDetallePage } from "../src/features/pacientes/PacientesPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

const mockedNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
    useParams: () => ({ id: "pac-123" }),
  };
});

describe("features/pacientes - PacientesPage y PacienteDetallePage", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    mockedNavigate.mockReset();
    setSesion("tok-recepcion", {
      id: "u-rec",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "rec@demo.com",
      nombre: "María Recepción",
      roles: ["recepcion"],
    });
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("busca pacientes por q y renderiza la lista", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/pacientes/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "pac-1",
            tenant_id: "t-1",
            nombre: "Elena Casares",
            dni: "28111222",
            telefono: "1155443322",
            optin_wa: true,
            activo: true,
          },
        ],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PacientesPage />);

    expect(await screen.findByText("Elena Casares")).toBeInTheDocument();
    expect(screen.getByText("28.111.222")).toBeInTheDocument();
    expect(screen.getByText("Opt-in Activo")).toBeInTheDocument();
  });

  it("alta de paciente valida campos requeridos y envía POST", async () => {
    const user = userEvent.setup();
    let postBody: any = null;

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/pacientes$/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: "/api/pacientes",
        metodo: "POST",
        status: 201,
        body: {
          id: "pac-nuevo",
          tenant_id: "t-1",
          nombre: "Nuevo Paciente",
          dni: "39888777",
          telefono: "1166778899",
          optin_wa: true,
          activo: true,
        },
        validarBody: (body: any) => {
          postBody = body;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PacientesPage />);

    const btnNuevo = await screen.findByRole("button", { name: /\+ Nuevo Paciente/i });
    await user.click(btnNuevo);

    await user.type(screen.getByLabelText(/Nombre completo \*/i), "Nuevo Paciente");
    await user.type(screen.getByLabelText(/DNI \*/i), "39888777");
    await user.type(screen.getByLabelText(/Teléfono \*/i), "1166778899");

    await user.click(screen.getByRole("button", { name: /Guardar Paciente/i }));

    await waitFor(() => {
      expect(postBody).toEqual(
        expect.objectContaining({
          nombre: "Nuevo Paciente",
          dni: "39888777",
          telefono: "1166778899",
          optin_wa: true,
        }),
      );
      expect(mockedNavigate).toHaveBeenCalledWith("/app/pacientes/pac-nuevo");
    });
  });

  it("409 por DNI duplicado muestra advertencia en la interfaz", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/pacientes$/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: "/api/pacientes",
        metodo: "POST",
        status: 409,
        body: { detail: "El DNI ya se encuentra registrado en este consultorio." },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PacientesPage />);

    const btnNuevo = await screen.findByRole("button", { name: /\+ Nuevo Paciente/i });
    await user.click(btnNuevo);

    await user.type(screen.getByLabelText(/Nombre completo \*/i), "Duplicado");
    await user.type(screen.getByLabelText(/DNI \*/i), "39888777");
    await user.type(screen.getByLabelText(/Teléfono \*/i), "1122334455");

    await user.click(screen.getByRole("button", { name: /Guardar Paciente/i }));

    expect(
      await screen.findByText(/Ya existe un paciente registrado con ese número de DNI/i),
    ).toBeInTheDocument();
  });

  it("detalle de paciente permite editar contacto y conmutar opt-in", async () => {
    const user = userEvent.setup();
    let patchLlamado = false;
    let optinLlamado = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/pacientes/pac-123",
        metodo: "GET",
        status: 200,
        body: {
          id: "pac-123",
          tenant_id: "t-1",
          nombre: "María Marta",
          dni: "20123456",
          telefono: "1144332211",
          email: "marta@mail.com",
          optin_wa: true,
          activo: true,
        },
      },
      {
        ruta: "/api/pacientes/pac-123",
        metodo: "PATCH",
        status: 200,
        body: {
          id: "pac-123",
          tenant_id: "t-1",
          nombre: "María Marta",
          dni: "20123456",
          telefono: "1199887766",
          email: "nuevo@mail.com",
          optin_wa: true,
          activo: true,
        },
        validarBody: () => {
          patchLlamado = true;
        },
      },
      {
        ruta: "/api/pacientes/pac-123/optin",
        metodo: "PATCH",
        status: 200,
        body: {
          id: "pac-123",
          tenant_id: "t-1",
          nombre: "María Marta",
          dni: "20123456",
          telefono: "1199887766",
          email: "nuevo@mail.com",
          optin_wa: false,
          activo: true,
        },
        validarBody: (b: any) => {
          optinLlamado = true;
          expect(b.optin_wa).toBe(false);
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PacienteDetallePage />);

    const encabezados = await screen.findAllByText("María Marta");
    expect(encabezados.length).toBeGreaterThan(0);

    // Toggle opt-in
    const btnOptin = screen.getByRole("button", { name: /Desactivar/i });
    await user.click(btnOptin);

    await waitFor(() => {
      expect(optinLlamado).toBe(true);
    });

    // Editar contacto
    const btnEditar = screen.getByRole("button", { name: /Editar Contacto/i });
    await user.click(btnEditar);

    const inputTel = screen.getByDisplayValue("1144332211");
    await user.clear(inputTel);
    await user.type(inputTel, "1199887766");

    await user.click(screen.getByRole("button", { name: /Guardar Cambios/i }));

    await waitFor(() => {
      expect(patchLlamado).toBe(true);
    });
  });
});
