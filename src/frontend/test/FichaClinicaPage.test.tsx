import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FichaClinicaPage } from "../src/features/clinica/FichaClinicaPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "pac-test" }),
  };
});

describe("features/clinica - FichaClinicaPage (Odontograma, Evoluciones, Presupuestos)", () => {
  let restaurarFetch: (() => void) | null = null;

  const mockBasico = [
    {
      ruta: "/api/pacientes/pac-test",
      metodo: "GET",
      status: 200,
      body: {
        id: "pac-test",
        tenant_id: "t-1",
        nombre: "Federico Moreno",
        dni: "34111222",
        telefono: "1122334455",
        optin_wa: true,
        activo: true,
      },
    },
    {
      ruta: "/api/pacientes/pac-test/ficha",
      metodo: "GET",
      status: 200,
      body: {
        id: "f-1",
        paciente_id: "pac-test",
        antecedentes: "Hipertensión controlada",
        alergias: "Penicilina",
        medicacion: "Enalapril",
        habitos: "Ninguno",
      },
    },
    {
      ruta: "/api/pacientes/pac-test/evoluciones",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "evo-1",
          tenant_id: "t-1",
          ficha_clinica_id: "f-1",
          paciente_id: "pac-test",
          profesional_id: "u-doc-1",
          nota: "Primera consulta. Se observa caries en pieza 16.",
          created_at: "2026-11-20T10:00:00",
        },
      ],
    },
    {
      ruta: "/api/odontograma/pac-test",
      metodo: "GET",
      status: 200,
      body: {
        odontograma_id: "od-1",
        tenant_id: "t-1",
        paciente_id: "pac-test",
        piezas: [
          {
            pieza_fdi: 16,
            superficies: { oclusal: "caries" },
            ultimo_evento_id: "ev-1",
            updated_at: "2026-11-20T10:00:00",
          },
        ],
        eventos: [],
      },
    },
    {
      ruta: "/api/odontograma/pac-test/piezas/16/historial",
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "ev-1",
          tenant_id: "t-1",
          odontograma_id: "od-1",
          pieza_fdi: 16,
          superficie: "oclusal",
          evento: "caries",
          observacion: "Caries de esmalte",
          created_by: "u-doc-1",
          created_at: "2026-11-20T10:00:00",
        },
      ],
    },
    {
      ruta: "/api/pacientes/pac-test/adjuntos",
      metodo: "GET",
      status: 200,
      body: [],
    },
    {
      ruta: /\/api\/consentimientos\?/,
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "c-1",
          tenant_id: "t-1",
          paciente_id: "pac-test",
          prestacion_id: "prest-1",
          texto_version: "v1-2026",
          texto_contenido: "Consentimiento informado para cirugía...",
          canal: "presencial",
          revocado: false,
          created_at: "2026-11-20T10:00:00",
          updated_at: "2026-11-20T10:00:00",
        },
      ],
    },
    {
      ruta: /\/api\/presupuestos\?/,
      metodo: "GET",
      status: 200,
      body: [
        {
          id: "pres-1",
          tenant_id: "t-1",
          paciente_id: "pac-test",
          estado: "borrador",
          total: "30000.00",
          total_cobertura_os: "10000.00",
          total_a_cargo: "20000.00",
          created_by: "u-doc-1",
          items: [],
          turnos_vinculados: [],
          created_at: "2026-11-20T10:00:00",
          updated_at: "2026-11-20T10:00:00",
        },
      ],
    },
  ];

  beforeEach(() => {
    limpiarSesion();
    setSesion("tok-odontologo", {
      id: "u-doc-1",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "doc@demo.com",
      nombre: "Dr. Roberto",
      roles: ["odontologo"],
    });
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("renderiza odontograma FDI permanente y permite seleccionar pieza 16", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble(mockBasico);
    restaurarFetch = restaurar;

    renderConProviders(<FichaClinicaPage />);

    expect(await screen.findByText("Odontograma FDI Interactivo")).toBeInTheDocument();

    // Clic en la pieza 16
    const btnPieza16 = screen.getByRole("button", { name: /16/i });
    await user.click(btnPieza16);

    expect(await screen.findByText("Historial de Pieza 16")).toBeInTheDocument();
    expect(screen.getByText(/Caries de esmalte/i)).toBeInTheDocument();
  });

  it("permite registrar evento en pieza seleccionada", async () => {
    const user = userEvent.setup();
    let eventoEnviado: any = null;

    const { restaurar } = mockFetchDoble([
      ...mockBasico,
      {
        ruta: "/api/odontograma/pac-test/eventos",
        metodo: "POST",
        status: 201,
        body: {
          id: "ev-nuevo",
          tenant_id: "t-1",
          odontograma_id: "od-1",
          pieza_fdi: 16,
          superficie: "distal",
          evento: "obturacion",
          created_by: "u-doc-1",
          created_at: "2026-11-20T11:00:00",
        },
        validarBody: (body: any) => {
          eventoEnviado = body;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<FichaClinicaPage />);

    // Seleccionar pieza 16
    const btnPieza16 = await screen.findByRole("button", { name: /16/i });
    await user.click(btnPieza16);

    const btnGuardar = screen.getByRole("button", { name: /Guardar Evento/i });
    await user.click(btnGuardar);

    await waitFor(() => {
      expect(eventoEnviado).toEqual(
        expect.objectContaining({
          pieza_fdi: 16,
        }),
      );
    });
  });

  it("permite ver evoluciones y agregar una nota", async () => {
    const user = userEvent.setup();
    let evolucionEnviada: any = null;

    const { restaurar } = mockFetchDoble([
      ...mockBasico,
      {
        ruta: "/api/pacientes/pac-test/evoluciones",
        metodo: "POST",
        status: 201,
        body: {
          id: "evo-2",
          tenant_id: "t-1",
          ficha_clinica_id: "f-1",
          paciente_id: "pac-test",
          profesional_id: "u-doc-1",
          nota: "Se realizó obturación con composite.",
          created_at: "2026-11-20T11:00:00",
        },
        validarBody: (body: any) => {
          evolucionEnviada = body;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<FichaClinicaPage />);

    // Ir a pestaña Evoluciones
    const tabEvoluciones = await screen.findByRole("button", { name: /Evoluciones/i });
    await user.click(tabEvoluciones);

    expect(screen.getByText(/Se observa caries en pieza 16/i)).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText(/Describí los hallazgos/i),
      "Se realizó obturación con composite.",
    );
    await user.click(screen.getByRole("button", { name: /Registrar Evolución/i }));

    await waitFor(() => {
      expect(evolucionEnviada?.nota).toBe("Se realizó obturación con composite.");
    });
  });

  it("presupuestos muestra montos del servidor sin recalcular en cliente", async () => {
    const user = userEvent.setup();
    const { restaurar } = mockFetchDoble(mockBasico);
    restaurarFetch = restaurar;

    renderConProviders(<FichaClinicaPage />);

    // Ir a pestaña Presupuestos
    const tabPres = await screen.findByRole("button", { name: /Presupuestos/i });
    await user.click(tabPres);

    expect(await screen.findByText("Planes de Tratamiento y Presupuestos")).toBeInTheDocument();
    expect(screen.getByText("Total Particular:")).toBeInTheDocument();
    expect(screen.getByText(/30\.000/)).toBeInTheDocument();
    expect(screen.getByText(/20\.000/)).toBeInTheDocument(); // A cargo
  });

  it("consentimiento permite firmar en el acto presencialmente", async () => {
    const user = userEvent.setup();
    let firmaEnviada: any = null;

    const { restaurar } = mockFetchDoble([
      ...mockBasico,
      {
        ruta: "/api/consentimientos/c-1/firmar",
        metodo: "POST",
        status: 200,
        body: {
          id: "c-1",
          firmado_por: "Federico Moreno",
          firmado_at: "2026-11-20T11:30:00",
        },
        validarBody: (body: any) => {
          firmaEnviada = body;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<FichaClinicaPage />);

    // Ir a pestaña Consentimientos
    const tabCons = await screen.findByRole("button", { name: /Consentimientos/i });
    await user.click(tabCons);

    expect(await screen.findByText("Pendiente de firma")).toBeInTheDocument();

    const btnFirmar = screen.getByRole("button", { name: /Firmar en el acto/i });
    await user.click(btnFirmar);

    await user.type(
      screen.getByPlaceholderText(/Nombre del paciente o apoderado/i),
      "Federico Moreno",
    );
    await user.click(screen.getByRole("button", { name: /Registrar Firma/i }));

    await waitFor(() => {
      expect(firmaEnviada?.firmado_por).toBe("Federico Moreno");
      expect(firmaEnviada?.canal).toBe("presencial");
    });
  });
});
