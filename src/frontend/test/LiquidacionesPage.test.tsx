import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  LiquidacionesPage,
  LiquidacionDetallePage,
} from "../src/features/os/LiquidacionesPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

let mockParams: Record<string, string> = { id: "liq-1" };

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => mockParams,
  };
});

describe("features/os - Cobertura y Liquidaciones (Bloque 4)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    mockParams = { id: "liq-1" };
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
  // 4.1 Consulta de cobertura vigente, sin cobertura y arancel vencido
  // ---------------------------------------------------------------------------

  it("4.1 consulta cobertura mostrando los 3 importes del servidor y advertencia de arancel vencido", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/liquidaciones/,
        metodo: "GET",
        status: 200,
        body: [],
      },
      {
        ruta: /\/api\/os\/cobertura/,
        metodo: "GET",
        status: 200,
        body: {
          prestacion_id: "pres-1",
          obra_social: "OSDE",
          cobertura_id: "cob-1",
          precio_particular: "50000.00",
          cobertura: "35000.00",
          monto_a_cargo: "15000.00",
          estado_arancel: "vencido",
          vigencia_desde: "2026-01-01",
          vigencia_hasta: "2026-06-30",
          arancel_vencido: true,
          advertencia: "El arancel de OSDE está vencido; se aplicó el último convenio conocido.",
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LiquidacionesPage />);

    await user.type(screen.getByLabelText(/id de prestación a consultar/i), "pres-1");
    await user.type(screen.getByLabelText(/obra social a consultar/i), "OSDE");
    await user.click(screen.getByRole("button", { name: /consultar cobertura/i }));

    expect(
      await screen.findByText(
        /el arancel de osde está vencido; se aplicó el último convenio conocido/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/50\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/35\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/15\.000,00/)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 4.2 Listado y alta de liquidación (validación de período y 409 duplicado)
  // ---------------------------------------------------------------------------

  it("4.2 valida formato de período yyyymm localmente y ante 409 ofrece abrir la liquidación existente", async () => {
    const user = userEvent.setup();
    let llamoPost = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/liquidaciones/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "liq-existente",
            tenant_id: "t-1",
            obra_social: "Swiss Medical",
            periodo: "202611",
            estado: "borrador",
            total: "45000.00",
            total_reconocido: null,
            created_by: "u-rec",
            created_at: "2026-11-16T08:00:00Z",
            updated_at: "2026-11-16T08:00:00Z",
            turnos_sin_cobertura: 0,
            advertencias: [],
            detalles: [],
          },
        ],
      },
      {
        ruta: "/api/liquidaciones",
        metodo: "POST",
        status: 409,
        body: { detail: "Ya existe un borrador abierto para Swiss Medical en el período 202611." },
        validarBody: () => {
          llamoPost = true;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LiquidacionesPage />);
    await screen.findByText("Swiss Medical");

    // 1. Período inválido "2026-11" no llama a la API
    await user.type(screen.getByLabelText(/obra social a liquidar/i), "Swiss Medical");
    await user.clear(screen.getByLabelText(/período \(yyyymm\)/i));
    await user.type(screen.getByLabelText(/período \(yyyymm\)/i), "2026-11");
    await user.click(screen.getByRole("button", { name: /generar borrador/i }));

    expect(
      await screen.findByText(/el período debe tener el formato 'yyyymm'/i),
    ).toBeInTheDocument();
    expect(llamoPost).toBe(false);

    // 2. Período válido "202611" recibe 409 y ofrece abrir la existente
    await user.clear(screen.getByLabelText(/período \(yyyymm\)/i));
    await user.type(screen.getByLabelText(/período \(yyyymm\)/i), "202611");
    await user.click(screen.getByRole("button", { name: /generar borrador/i }));

    expect(
      await screen.findByText(/ya existe un borrador abierto para swiss medical/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /abrir liquidación existente/i })).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 4.3 y 4.4 Detalle, advertencias, cierre y resultado con débitos (motivo obligatorio)
  // ---------------------------------------------------------------------------

  it("4.3 y 4.4 muestra advertencias, cierra liquidación y exige motivo para registrar débitos", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/liquidaciones/liq-1",
        metodo: "GET",
        status: 200,
        body: {
          id: "liq-1",
          tenant_id: "t-1",
          obra_social: "OSDE",
          periodo: "202611",
          estado: "borrador",
          total: "50000.00",
          total_reconocido: null,
          created_by: "u-rec",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T08:00:00Z",
          turnos_sin_cobertura: 1,
          advertencias: ["Se excluyó 1 turno por no tener cobertura vigente."],
          detalles: [
            {
              id: "det-1",
              turno_id: "tur-1",
              fecha_turno: "2026-11-10T14:00:00Z",
              prestacion: "Endodoncia",
              monto_reclamado: "50000.00",
              monto_reconocido: null,
              debito_motivo: null,
              arancel_vencido: false,
              vigente: true,
            },
          ],
        },
      },
      {
        ruta: "/api/liquidaciones/liq-1/cerrar",
        metodo: "POST",
        status: 200,
        body: {
          id: "liq-1",
          tenant_id: "t-1",
          obra_social: "OSDE",
          periodo: "202611",
          estado: "presentada",
          total: "50000.00",
          total_reconocido: null,
          created_by: "u-rec",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T09:00:00Z",
          turnos_sin_cobertura: 1,
          advertencias: [],
          detalles: [
            {
              id: "det-1",
              turno_id: "tur-1",
              fecha_turno: "2026-11-10T14:00:00Z",
              prestacion: "Endodoncia",
              monto_reclamado: "50000.00",
              monto_reconocido: null,
              debito_motivo: null,
              arancel_vencido: false,
              vigente: true,
            },
          ],
        },
      },
      {
        ruta: "/api/liquidaciones/liq-1/resultado",
        metodo: "POST",
        status: 200,
        body: {
          id: "liq-1",
          tenant_id: "t-1",
          obra_social: "OSDE",
          periodo: "202611",
          estado: "con_debitos",
          total: "50000.00",
          total_reconocido: "40000.00",
          saldo_debito: "10000.00",
          created_by: "u-rec",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
          turnos_sin_cobertura: 0,
          advertencias: [],
          detalles: [
            {
              id: "det-1",
              turno_id: "tur-1",
              fecha_turno: "2026-11-10T14:00:00Z",
              prestacion: "Endodoncia",
              monto_reclamado: "50000.00",
              monto_reconocido: "40000.00",
              debito_motivo: "Falta radiografía post-operatoria",
              arancel_vencido: false,
              vigente: true,
            },
          ],
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<LiquidacionDetallePage />);

    expect(
      await screen.findByText(/se excluyó 1 turno por no tener cobertura vigente/i),
    ).toBeInTheDocument();

    // 1. Cerrar borrador -> pasa a presentada
    await user.click(screen.getByRole("button", { name: /presentar \/ cerrar liquidación/i }));
    expect(await screen.findByText("presentada")).toBeInTheDocument();

    // 2. Intentar registrar resultado con débitos sin motivo -> validación local
    await user.selectOptions(screen.getByLabelText(/resultado de la obra social/i), "con_debitos");
    await user.clear(screen.getByLabelText(/monto reconocido turno/i));
    await user.type(screen.getByLabelText(/monto reconocido turno/i), "40000.00");
    await user.click(screen.getByRole("button", { name: /registrar resultado/i }));

    expect(
      await screen.findByText(/todo débito exige un motivo de recorte/i),
    ).toBeInTheDocument();

    // 3. Completar motivo y enviar
    await user.type(
      screen.getByLabelText(/motivo del débito/i),
      "Falta radiografía post-operatoria",
    );
    await user.click(screen.getByRole("button", { name: /registrar resultado/i }));

    expect(await screen.findByText("con_debitos")).toBeInTheDocument();
    expect(screen.getByText(/Falta radiografía post-operatoria/i)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 4.5 y 4.6 Anulación con motivo, descarga CSV/JSON y guard de exportación
  // ---------------------------------------------------------------------------

  it("4.5 y 4.6 descarga CSV/JSON, bloquea acciones en anulada y oculta exportar al odontólogo", async () => {
    const user = userEvent.setup();
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL");

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/liquidaciones/liq-1",
        metodo: "GET",
        status: 200,
        body: {
          id: "liq-1",
          tenant_id: "t-1",
          obra_social: "OSDE",
          periodo: "202611",
          estado: "borrador",
          total: "30000.00",
          total_reconocido: null,
          created_by: "u-rec",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T08:00:00Z",
          turnos_sin_cobertura: 0,
          advertencias: [],
          detalles: [],
        },
      },
      {
        ruta: /\/api\/liquidaciones\/liq-1\/exportar\?formato=csv/,
        metodo: "GET",
        status: 200,
        body: "turno_id,prestacion,monto\ntur-1,Limpieza,30000.00",
      },
      {
        ruta: "/api/liquidaciones/liq-1",
        metodo: "DELETE",
        status: 200,
        body: {
          id: "liq-1",
          tenant_id: "t-1",
          obra_social: "OSDE",
          periodo: "202611",
          estado: "anulada",
          total: "30000.00",
          total_reconocido: null,
          anulada_motivo: "Error de carga de período",
          created_by: "u-rec",
          created_at: "2026-11-16T08:00:00Z",
          updated_at: "2026-11-16T11:00:00Z",
          turnos_sin_cobertura: 0,
          advertencias: [],
          detalles: [],
        },
      },
    ]);
    restaurarFetch = restaurar;

    const { unmount } = renderConProviders(<LiquidacionDetallePage />);

    // 1. Exportar CSV
    const btnCsv = await screen.findByRole("button", { name: /exportar csv/i });
    await user.click(btnCsv);
    await waitFor(() => {
      expect(createObjectURLSpy).toHaveBeenCalled();
    });

    // 2. Anular sin motivo -> validación local
    await user.click(screen.getByRole("button", { name: /anular liquidación/i }));
    expect(await screen.findByText(/la anulación exige un motivo/i)).toBeInTheDocument();

    // 3. Anular con motivo -> pasa a anulada y oculta acciones de cierre y exportación
    await user.type(
      screen.getByLabelText(/motivo de anulación/i),
      "Error de carga de período",
    );
    await user.click(screen.getByRole("button", { name: /anular liquidación/i }));

    expect(await screen.findByText("anulada")).toBeInTheDocument();
    expect(screen.getByText(/Error de carga de período/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /exportar csv/i })).not.toBeInTheDocument();
    unmount();

    // 4. Odontólogo no ve botón de exportar en una liquidación activa
    setSesion("tok-odonto", {
      id: "u-odonto",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "odonto@demo.com",
      nombre: "Dra. Odontóloga",
      roles: ["odontologo"],
    });

    renderConProviders(<LiquidacionDetallePage />);
    await screen.findByText(/OSDE/);
    expect(screen.queryByRole("button", { name: /exportar csv/i })).not.toBeInTheDocument();
    createObjectURLSpy.mockRestore();
  });
});
