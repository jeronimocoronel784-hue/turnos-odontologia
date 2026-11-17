import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgendaPage } from "../src/features/agenda/AgendaPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

describe("features/agenda/AgendaPage", () => {
  let restaurarFetch: (() => void) | null = null;

  const mockCatalogos = [
    {
      ruta: "/api/usuarios",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "u-doc-1",
          tenant_id: "t-1",
          email: "doc1@demo.com",
          nombre: "Dr. Juan Pérez",
          rol: "odontologo",
          activo: true,
        },
        {
          id: "u-doc-2",
          tenant_id: "t-1",
          email: "doc2@demo.com",
          nombre: "Dra. Ana López",
          rol: "odontologo",
          activo: true,
        },
      ],
    },
    {
      ruta: "/api/admin/prestaciones",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "prest-1",
          tenant_id: "t-1",
          nombre: "Consulta General",
          duracion_min: 30,
          precio_particular: "15000.00",
          requiere_sena: false,
          monto_sena: null,
          invasiva: false,
          activa: true,
        },
      ],
    },
    {
      ruta: "/api/admin/sillones",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "sill-1",
          tenant_id: "t-1",
          nombre: "Sillón Principal",
          sucursal: "central",
          activo: true,
        },
      ],
    },
    {
      ruta: "/api/admin/tenant/politicas",
      metodo: "GET",
      status: 200,
      body: {
        anticipacion_min_dias: 1,
        sena_default_pct: 30,
        cancelacion_horas: 24,
      },
    },
    {
      ruta: "/api/pacientes",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "pac-1",
          tenant_id: "t-1",
          nombre: "Carlos Gómez",
          dni: "30123456",
          telefono: "1122334455",
          optin_wa: true,
          activo: true,
        },
      ],
    },
  ];

  beforeEach(() => {
    limpiarSesion();
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

  it("renderiza turnos y bloqueos con sus estados textuales y etiquetas", async () => {
    const { restaurar } = mockFetchDoble([
      ...mockCatalogos,
      {
        ruta: /\/api\/agenda\?/,
        metodo: "GET",
        status: 200,
        body: {
          turnos: [
            {
              id: "t-1",
              tenant_id: "t-1",
              paciente_id: "pac-1",
              profesional_id: "u-doc-1",
              sillon_id: "sill-1",
              prestacion_id: "prest-1",
              inicio: "2026-11-20T09:00:00",
              fin: "2026-11-20T09:30:00",
              estado: "pendiente",
              origen: "presencial",
              sobreturno: true,
              sena_cobrada: false,
              created_at: "2026-11-20T08:00:00",
              updated_at: "2026-11-20T08:00:00",
            },
          ],
          bloqueos: [
            {
              id: "b-1",
              tenant_id: "t-1",
              profesional_id: "u-doc-1",
              desde: "2026-11-20T12:00:00",
              hasta: "2026-11-20T13:00:00",
              motivo: "almuerzo",
              descripcion: "Almuerzo médico",
              created_at: "2026-11-20T08:00:00",
              updated_at: "2026-11-20T08:00:00",
            },
          ],
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AgendaPage />);

    expect(await screen.findByText("Carlos Gómez")).toBeInTheDocument();
    expect(screen.getByText("pendiente")).toBeInTheDocument();
    expect(screen.getByText("Sobreturno")).toBeInTheDocument();
    expect(screen.getByText("Seña pendiente")).toBeInTheDocument();
    expect(screen.getByText(/Bloqueo: almuerzo/i)).toBeInTheDocument();
  });

  it("permite cambiar estado a confirmado y luego presente", async () => {
    const user = userEvent.setup();
    let patchLlamado = false;

    const { restaurar } = mockFetchDoble([
      ...mockCatalogos,
      {
        ruta: /\/api\/agenda\?/,
        metodo: "GET",
        status: 200,
        body: {
          turnos: [
            {
              id: "t-1",
              tenant_id: "t-1",
              paciente_id: "pac-1",
              profesional_id: "u-doc-1",
              sillon_id: "sill-1",
              prestacion_id: "prest-1",
              inicio: "2026-11-20T10:00:00",
              fin: "2026-11-20T10:30:00",
              estado: "pendiente",
              origen: "presencial",
              sobreturno: false,
              sena_cobrada: true,
              created_at: "2026-11-20T08:00:00",
              updated_at: "2026-11-20T08:00:00",
            },
          ],
          bloqueos: [],
        },
      },
      {
        ruta: "/api/turnos/t-1/estado",
        metodo: "PATCH",
        status: 200,
        body: {
          id: "t-1",
          estado: "confirmado",
        },
        validarBody: (body: any) => {
          patchLlamado = true;
          expect(body.estado).toBe("confirmado");
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AgendaPage />);

    const btnConfirmar = await screen.findByRole("button", { name: /Confirmar/i });
    await user.click(btnConfirmar);

    await waitFor(() => {
      expect(patchLlamado).toBe(true);
    });
  });

  it("cancelar exige ingresar motivo y no se envía si está vacío", async () => {
    const user = userEvent.setup();
    const mock = vi.fn();

    const { restaurar } = mockFetchDoble([
      ...mockCatalogos,
      {
        ruta: /\/api\/agenda\?/,
        metodo: "GET",
        status: 200,
        body: {
          turnos: [
            {
              id: "t-2",
              tenant_id: "t-1",
              paciente_id: "pac-1",
              profesional_id: "u-doc-1",
              sillon_id: "sill-1",
              prestacion_id: "prest-1",
              inicio: "2026-11-20T11:00:00",
              fin: "2026-11-20T11:30:00",
              estado: "confirmado",
              origen: "presencial",
              sobreturno: false,
              sena_cobrada: true,
              created_at: "2026-11-20T08:00:00",
              updated_at: "2026-11-20T08:00:00",
            },
          ],
          bloqueos: [],
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AgendaPage />);

    const btnCancelar = await screen.findByRole("button", { name: /Cancelar/i });
    await user.click(btnCancelar);

    expect(await screen.findByText(/Cancelar Turno/i)).toBeInTheDocument();

    const btnConfirmarCancelacion = screen.getByRole("button", { name: /Confirmar Cancelación/i });
    await user.click(btnConfirmarCancelacion);

    expect(await screen.findByText(/Tenés que ingresar un motivo para cancelar el turno/i)).toBeInTheDocument();
  });

  it("odontólogo ve en solo lectura los turnos de otros profesionales", async () => {
    setSesion("tok-odontologo", {
      id: "u-doc-1",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "doc1@demo.com",
      nombre: "Dr. Juan Pérez",
      roles: ["odontologo"],
    });

    const { restaurar } = mockFetchDoble([
      ...mockCatalogos,
      {
        ruta: /\/api\/agenda\?/,
        metodo: "GET",
        status: 200,
        body: {
          turnos: [
            {
              id: "t-otro",
              tenant_id: "t-1",
              paciente_id: "pac-1",
              profesional_id: "u-doc-2", // Otro profesional
              sillon_id: "sill-1",
              prestacion_id: "prest-1",
              inicio: "2026-11-20T14:00:00",
              fin: "2026-11-20T14:30:00",
              estado: "pendiente",
              origen: "presencial",
              sobreturno: false,
              sena_cobrada: true,
              created_at: "2026-11-20T08:00:00",
              updated_at: "2026-11-20T08:00:00",
            },
          ],
          bloqueos: [],
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AgendaPage />);

    expect(await screen.findByText("Carlos Gómez")).toBeInTheDocument();
    // No debe ver botones de acción como Confirmar o Cancelar
    expect(screen.queryByRole("button", { name: /Confirmar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancelar/i })).not.toBeInTheDocument();
  });

  it("muestra la advertencia de política de cancelación (Task 3.8)", async () => {
    const { restaurar } = mockFetchDoble([
      ...mockCatalogos,
      {
        ruta: /\/api\/agenda\?/,
        metodo: "GET",
        status: 200,
        body: { turnos: [], bloqueos: [] },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AgendaPage />);

    expect(await screen.findByText(/anticipación mínima de/i)).toBeInTheDocument();
    expect(screen.getByText(/24 horas/i)).toBeInTheDocument();
  });
});
