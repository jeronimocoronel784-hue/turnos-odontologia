import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CajaPage, CierreDetallePage } from "../src/features/caja/CajaPage";
import { CobroTurnoPage } from "../src/features/cobros/CobroTurnoPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

let mockParams: Record<string, string> = { id: "cie-1", turnoId: "tur-1" };

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => mockParams,
  };
});

describe("features/caja y features/cobros (Bloques 2 y 3)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    mockParams = { id: "cie-1", turnoId: "tur-1" };
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

  // ---------------------------------------------------------------------------
  // 2.1, 2.2, 2.3, 2.4 Movimientos y aviso sin cierre abierto
  // ---------------------------------------------------------------------------

  it("2.2 y 2.4 lista movimientos formateando montos del servidor y avisa cuando no hay cierre abierto", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/caja\/movimientos/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "mov-1",
            tenant_id: "t-1",
            tipo: "ingreso",
            concepto: "Cobro limpieza dental",
            medio: "efectivo",
            monto: "15000.00",
            cierre_id: null,
            created_by: "u-rec",
            created_at: "2026-11-16T10:00:00Z",
          },
        ],
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<CajaPage />);

    expect(await screen.findByText("Cobro limpieza dental")).toBeInTheDocument();
    expect(screen.getByText(/15\.000,00/)).toBeInTheDocument();
    expect(
      screen.getByText(/no hay un cierre de caja abierto/i),
    ).toBeInTheDocument();
  });

  it("2.3 alta de ingreso y egreso valida concepto y monto > 0 y envía POST", async () => {
    const user = userEvent.setup();
    const payloadsEnviados: unknown[] = [];

    const movimientosLista = [
      {
        id: "mov-1",
        tenant_id: "t-1",
        tipo: "ingreso",
        concepto: "Inicial",
        medio: "efectivo",
        monto: "10000.00",
        cierre_id: "cie-1",
        created_by: "u-rec",
        created_at: "2026-11-16T09:00:00Z",
      },
    ];

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "cie-1",
            tenant_id: "t-1",
            fecha: "2026-11-16",
            total_sistema: "10000.00",
            total_contado: null,
            diferencia: null,
            estado: "abierto",
            abierto_por: "u-rec",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
          },
        ],
      },
      {
        ruta: /\/api\/caja\/movimientos/,
        metodo: "GET",
        status: 200,
        body: movimientosLista,
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: "/api/caja/movimientos",
        metodo: "POST",
        status: 201,
        body: {
          id: "mov-2",
          tenant_id: "t-1",
          tipo: "egreso",
          concepto: "Insumos descartables",
          medio: "efectivo",
          monto: "3500.00",
          cierre_id: "cie-1",
          created_by: "u-rec",
          created_at: "2026-11-16T11:00:00Z",
        },
        validarBody: (b) => {
          payloadsEnviados.push(b);
          movimientosLista.push({
            id: "mov-2",
            tenant_id: "t-1",
            tipo: "egreso",
            concepto: "Insumos descartables",
            medio: "efectivo",
            monto: "3500.00",
            cierre_id: "cie-1",
            created_by: "u-rec",
            created_at: "2026-11-16T11:00:00Z",
          });
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<CajaPage />);
    await screen.findByText("Inicial");

    // Intentar enviar vacío -> validación local, no llama a POST
    await user.click(screen.getByRole("button", { name: /registrar movimiento/i }));
    expect(await screen.findByText(/el concepto es obligatorio/i)).toBeInTheDocument();
    expect(payloadsEnviados).toHaveLength(0);

    // Completar egreso válido
    await user.selectOptions(screen.getByLabelText(/tipo de movimiento/i), "egreso");
    await user.type(screen.getByLabelText(/concepto del movimiento/i), "Insumos descartables");
    await user.clear(screen.getByLabelText(/monto del movimiento/i));
    await user.type(screen.getByLabelText(/monto del movimiento/i), "3500.00");

    await user.click(screen.getByRole("button", { name: /registrar movimiento/i }));

    expect(await screen.findByText("Insumos descartables")).toBeInTheDocument();
    expect(payloadsEnviados).toHaveLength(1);
    expect(payloadsEnviados[0]).toMatchObject({
      tipo: "egreso",
      concepto: "Insumos descartables",
      monto: "3500.00",
    });
  });

  // ---------------------------------------------------------------------------
  // 2.5 y 2.6 Apertura de cierre (409 abre existente) y cierre con confirmación de diferencia
  // ---------------------------------------------------------------------------

  it("2.5 apertura de cierre ante 409 muestra aviso y selecciona el cierre existente", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "cie-existente",
            tenant_id: "t-1",
            fecha: "2026-11-16",
            total_sistema: "20000.00",
            total_contado: null,
            diferencia: null,
            estado: "abierto",
            abierto_por: "u-rec",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/caja/cierre",
        metodo: "POST",
        status: 409,
        body: { detail: "Ya existe un cierre de caja para la fecha 2026-11-16." },
      },
      {
        ruta: /\/api\/caja\/movimientos/,
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
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<CajaPage />);
    const btnAbrir = await screen.findByRole("button", { name: /abrir cierre del día/i });
    await user.click(btnAbrir);

    expect(
      await screen.findByText(/ya existe un cierre de caja para la fecha/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/cierre existente cargado/i)).toBeInTheDocument();
  });

  it("2.6 cerrar caja con diferencia distinta de cero pide confirmación explícita con etiqueta faltante/sobrante", async () => {
    const user = userEvent.setup();
    let cierreEnviado = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre(\?.*)?$/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "cie-1",
            tenant_id: "t-1",
            fecha: "2026-11-16",
            total_sistema: "20000.00",
            total_contado: null,
            diferencia: null,
            estado: "abierto",
            abierto_por: "u-rec",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/caja/cierre/cie-1/cerrar",
        metodo: "POST",
        status: 200,
        body: {
          id: "cie-1",
          tenant_id: "t-1",
          fecha: "2026-11-16",
          total_sistema: "20000.00",
          total_contado: "19500.00",
          diferencia: "-500.00",
          estado: "cerrado",
          abierto_por: "u-rec",
          cerrado_por: "u-rec",
          cerrado_at: "2026-11-16T18:00:00Z",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T18:00:00Z",
        },
        validarBody: () => {
          cierreEnviado = true;
        },
      },
      {
        ruta: /\/api\/caja\/movimientos/,
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
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<CajaPage />);

    const inputContado = await screen.findByLabelText(/total contado en caja/i);
    await user.clear(inputContado);
    await user.type(inputContado, "19500.00");

    await user.click(screen.getByRole("button", { name: /cerrar caja/i }));

    // Debe abrir el diálogo de confirmación sin haber enviado todavía
    expect(cierreEnviado).toBe(false);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/faltante/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirmar cierre con diferencia/i }));
    await waitFor(() => {
      expect(cierreEnviado).toBe(true);
    });
  });

  // ---------------------------------------------------------------------------
  // 2.7 Cierre cerrado inmutable y reapertura solo Dueño con motivo
  // ---------------------------------------------------------------------------

  it("2.7 cierre cerrado es inmutable para recepción y permite reabrir con motivo al Dueño", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/caja/cierre/cie-1",
        metodo: "GET",
        status: 200,
        body: {
          id: "cie-1",
          tenant_id: "t-1",
          fecha: "2026-11-16",
          total_sistema: "20000.00",
          total_contado: "20000.00",
          diferencia: "0.00",
          estado: "cerrado",
          abierto_por: "u-rec",
          cerrado_por: "u-rec",
          cerrado_at: "2026-11-16T18:00:00Z",
          reabierto_motivo: null,
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T18:00:00Z",
        },
      },
      {
        ruta: "/api/caja/cierre/cie-1/reabrir",
        metodo: "POST",
        status: 200,
        body: {
          id: "cie-1",
          tenant_id: "t-1",
          fecha: "2026-11-16",
          total_sistema: "20000.00",
          total_contado: null,
          diferencia: null,
          estado: "abierto",
          abierto_por: "u-rec",
          cerrado_por: null,
          cerrado_at: null,
          reabierto_motivo: "Faltó cargar cobro de urgencia",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T19:00:00Z",
        },
      },
    ]);
    restaurarFetch = restaurar;

    // 1. Recepción NO ve botón de reabrir
    const { unmount } = renderConProviders(<CierreDetallePage />);
    expect(await screen.findByText(/cierre cerrado \(inmutable\)/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reabrir cierre/i })).not.toBeInTheDocument();
    unmount();

    // 2. Dueño SÍ ve reabrir, valida motivo obligatorio y reabre
    setSesion("tok-dueno", {
      id: "u-dueno",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "dueno@demo.com",
      nombre: "Dr. Dueño",
      roles: ["dueno"],
    });

    renderConProviders(<CierreDetallePage />);
    const btnReabrir = await screen.findByRole("button", { name: /reabrir cierre/i });

    // Sin motivo -> validación local
    await user.click(btnReabrir);
    expect(await screen.findByText(/el motivo de reapertura es obligatorio/i)).toBeInTheDocument();

    await user.type(
      screen.getByLabelText(/motivo de reapertura/i),
      "Faltó cargar cobro de urgencia",
    );
    await user.click(btnReabrir);

    expect(
      await screen.findByText(/Faltó cargar cobro de urgencia/i),
    ).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 3.1 y 3.2 Cobro del saldo de la atención y saldo cero deshabilitado
  // ---------------------------------------------------------------------------

  it("3.1 y 3.2 CobroTurnoPage muestra los 4 importes del servidor, cobra saldo y deshabilita si saldo es 0.00", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/turnos\/tur-1\/liquidacion/,
        metodo: "GET",
        status: 200,
        body: {
          turno_id: "tur-1",
          precio_particular: "50000.00",
          cobertura_os: "15000.00",
          sena_cobrada: "10000.00",
          saldo: "25000.00",
          obra_social: "OSDE",
        },
      },
      {
        ruta: "/api/caja/turnos/tur-1/cobrar",
        metodo: "POST",
        status: 201,
        body: {
          id: "mov-cobro-1",
          tenant_id: "t-1",
          tipo: "ingreso",
          concepto: "Cobro turno tur-1",
          medio: "tarjeta",
          monto: "25000.00",
          turno_id: "tur-1",
          created_by: "u-rec",
          created_at: "2026-11-16T12:00:00Z",
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<CobroTurnoPage />);

    expect(await screen.findByText(/50\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/15\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/10\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/25\.000,00/)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/medio de pago/i), "tarjeta");
    await user.click(screen.getByRole("button", { name: /cobrar saldo de la atención/i }));

    expect(await screen.findByText(/atención saldada correctamente/i)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 3.3 y 3.4 Gestión de señas y guard de solo lectura para odontólogo
  // ---------------------------------------------------------------------------

  it("3.3 y 3.4 gestiona cobro y ausencia de señas y oculta escritura al odontólogo", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/caja\/cierre/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/caja\/movimientos/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/senas/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "sen-1",
            tenant_id: "t-1",
            turno_id: "tur-10",
            monto: "10000.00",
            estado: "pendiente",
            vence_at: "2026-11-17T10:00:00Z",
            created_at: "2026-11-16T09:00:00Z",
            updated_at: "2026-11-16T09:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/senas/sen-1/cobrar",
        metodo: "POST",
        status: 200,
        body: {
          id: "sen-1",
          tenant_id: "t-1",
          turno_id: "tur-10",
          monto: "10000.00",
          estado: "cobrada",
          vence_at: "2026-11-17T10:00:00Z",
          created_at: "2026-11-16T09:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
      },
    ]);
    restaurarFetch = restaurar;

    const { unmount } = renderConProviders(<CajaPage />);

    const btnCobrarSena = await screen.findByRole("button", { name: /cobrar seña/i });
    await user.click(btnCobrarSena);
    expect(await screen.findByText("cobrada")).toBeInTheDocument();
    unmount();

    // Odontólogo en modo solo lectura: no ve alta de movimiento ni acciones de cobro
    setSesion("tok-odonto", {
      id: "u-odonto",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "odonto@demo.com",
      nombre: "Dra. Odontóloga",
      roles: ["odontologo"],
    });

    renderConProviders(<CajaPage />);
    expect(await screen.findByText(/modo solo lectura/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /registrar movimiento/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cobrar seña/i })).not.toBeInTheDocument();
  });
});
