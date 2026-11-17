import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuditoriaPage } from "../src/features/auditoria/AuditoriaPage";
import { rutasApp } from "../src/main";
import { crearTestQueryClient, mockFetchDoble, renderConProviders } from "./render";
import { limpiarSesion, setSesion } from "../src/shared/sesion";
import { AuditoriaEventoRead } from "../src/features/auditoria/api";
import { RolUsuario, UsuarioRead } from "../src/shared/api-types";

function usuario(
  id: string,
  nombre: string,
  rol: RolUsuario,
  activo = true,
): UsuarioRead {
  return {
    id,
    tenant_id: "t-1",
    email: `${id}@demo.com`,
    nombre,
    rol,
    activo,
  };
}

const USUARIOS: UsuarioRead[] = [
  usuario("u-dueno", "Dr. Dueño", "dueno"),
  usuario("u-inactivo", "Dra. Inactiva", "odontologo", false),
];

function evento(
  id: string,
  entidadId: string,
  actorId: string | null,
  created_at = "2026-11-16T23:30:00Z",
): AuditoriaEventoRead {
  return {
    id,
    actor_id: actorId,
    accion: "crear",
    entidad: "turno",
    entidad_id: entidadId,
    antes: null,
    despues: { estado: "confirmado" },
    created_at,
  };
}

const EVENTO_1 = evento("ev-1", "tur-1", "u-dueno");
const EVENTO_2 = evento("ev-2", "tur-2", "u-dueno");

const EVENTO_FILTRADO = {
  ...evento("ev-filtrado", "tur-9", "u-dueno"),
  accion: "actualizar",
};

const EVENTO_PAGINA_2 = evento("ev-pagina-2", "tur-2", "u-dueno");

function sesionConRol(rol: RolUsuario) {
  setSesion(`tok-${rol}`, {
    id: `u-${rol}`,
    tenant_id: "t-1",
    tenant_slug: "consultorio-demo",
    email: `${rol}@demo.com`,
    nombre: rol === "dueno" ? "Dr. Dueño" : "Usuario Demo",
    roles: [rol],
  });
}

function urlsDe(mock: { mock: { calls: unknown[][] } }): string[] {
  return mock.mock.calls.map((llamada) => {
    const [input] = llamada;
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.toString();
    return (input as Request).url;
  });
}

function renderRutas(ruta: string) {
  const router = createMemoryRouter(rutasApp, { initialEntries: [ruta] });
  return render(
    <QueryClientProvider client={crearTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function panelDeDataset(dataset: string): HTMLElement {
  const select = screen.getByLabelText(`Formato ${dataset}`);
  return select.parentElement as HTMLElement;
}

function respuestaJson(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockExportacionConJob(estados: string[]) {
  const fetchOriginal = globalThis.fetch;
  let indiceEstado = 0;

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

    if (url === "/api/auditoria") {
      return respuestaJson({ eventos: [EVENTO_1], siguiente_cursor: null });
    }
    if (url === "/api/usuarios") {
      return respuestaJson(USUARIOS);
    }
    if (url === "/api/exportacion/agenda?formato=csv") {
      return respuestaJson({ job_id: "job-1", estado: "pendiente" }, 202);
    }
    if (url === "/api/exportacion/jobs/job-1/descarga") {
      return new Response("turno_id,accion\ntur-1,crear", {
        status: 200,
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="agenda.csv"',
        },
      });
    }
    if (url === "/api/exportacion/jobs/job-1") {
      const estado = estados[Math.min(indiceEstado, estados.length - 1)];
      indiceEstado += 1;
      return respuestaJson({ job_id: "job-1", estado, nombre_archivo: "agenda.csv" });
    }

    throw new Error(`Fetch no mockeado para ${url}`);
  });

  globalThis.fetch = fetchMock as unknown as typeof fetch;

  return {
    mock: fetchMock,
    restaurar: () => {
      globalThis.fetch = fetchOriginal;
    },
  };
}

describe("features/auditoria/AuditoriaPage (C-14)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    sesionConRol("dueno");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  // -------------------------------------------------------------------------
  // 7.1 Dueño ve la sección y la tabla paginada
  // -------------------------------------------------------------------------
  it("7.1 el dueño ve la sección, la tabla paginada y la leyenda de zona ART", async () => {
    const { restaurar, mock } = mockFetchDoble([
      {
        ruta: "/api/auditoria",
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_1, EVENTO_2], siguiente_cursor: "cur-2" },
      },
      { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);

    expect(await screen.findByRole("heading", { name: "Auditoría" })).toBeInTheDocument();
    const tabla = await screen.findByRole("table");
    expect(within(tabla).getByText("tur-1")).toBeInTheDocument();
    expect(within(tabla).getByText("tur-2")).toBeInTheDocument();
    expect(within(tabla).getAllByText("Dr. Dueño")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Cargar más" })).toBeInTheDocument();

    // Tras la ventana del debounce de filtros los eventos siguen visibles.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });

    expect(screen.getByText("tur-1")).toBeInTheDocument();
    expect(screen.getByText("tur-2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cargar más" })).toBeInTheDocument();
    expect(
      screen.getByText(/Horarios en America\/Argentina\/Buenos_Aires \(ART\)/),
    ).toBeInTheDocument();
    expect(mock).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 7.2 RBAC: recepción y odontólogo sin acceso
  // -------------------------------------------------------------------------
  it("7.2 recepción no ve el ítem de menú y por URL directa recibe permiso denegado", async () => {
    sesionConRol("recepcion");
    const { restaurar } = mockFetchDoble([
      { ruta: /\/api\/auditoria/, metodo: "GET", status: 403, body: { detail: "No autorizado" } },
      { ruta: "/api/usuarios", metodo: "GET", status: 403, body: { detail: "No autorizado" } },
    ]);
    restaurarFetch = restaurar;

    renderRutas("/app/auditoria");

    expect(await screen.findByTestId("auditoria-page")).toBeInTheDocument();
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Acceso no autorizado");
    expect(screen.getByText("No tenés permiso para ver la auditoría.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Auditoría" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agenda" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("7.2 odontólogo no ve el ítem de menú y por URL directa recibe permiso denegado", async () => {
    sesionConRol("odontologo");
    const { restaurar } = mockFetchDoble([
      { ruta: /\/api\/auditoria/, metodo: "GET", status: 403, body: { detail: "No autorizado" } },
      { ruta: "/api/usuarios", metodo: "GET", status: 403, body: { detail: "No autorizado" } },
    ]);
    restaurarFetch = restaurar;

    renderRutas("/app/auditoria");

    expect(await screen.findByTestId("auditoria-page")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Acceso no autorizado");
    expect(screen.queryByRole("link", { name: "Auditoría" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7.3 Filtros disparan la consulta con los parámetros correctos
  // -------------------------------------------------------------------------
  it("7.3 los filtros de entidad, actor, acción y rango disparan la consulta con los parámetros correctos", async () => {
    const { restaurar, mock } = mockFetchDoble([
      {
        ruta: "/api/auditoria",
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_1], siguiente_cursor: null },
      },
      {
        ruta: /\/api\/auditoria\?/,
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_FILTRADO], siguiente_cursor: null },
      },
      { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);
    await screen.findByText("tur-1");

    fireEvent.change(screen.getByLabelText("Entidad"), { target: { value: "turno" } });
    fireEvent.change(screen.getByLabelText("Actor"), { target: { value: "u-dueno" } });
    fireEvent.change(screen.getByLabelText("Acción"), { target: { value: "crear" } });
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "2026-11-30" } });

    let urlFiltrada: string | undefined;
    await waitFor(
      () => {
        urlFiltrada = urlsDe(mock).find((url) => url.includes("entidad=turno"));
        expect(urlFiltrada).toBeDefined();
      },
      { timeout: 3000 },
    );

    const params = new URL(urlFiltrada as string, "http://localhost").searchParams;
    expect(params.get("entidad")).toBe("turno");
    expect(params.get("actor_id")).toBe("u-dueno");
    expect(params.get("accion")).toBe("crear");
    expect(params.get("desde")).toBe("2026-11-01");
    expect(params.get("hasta")).toBe("2026-11-30");
    expect(params.has("offset")).toBe(false);
    expect(params.has("limite")).toBe(false);
    expect(params.has("cursor")).toBe(false);

    // La tabla refleja el resultado de la consulta filtrada
    expect(await screen.findByText("tur-9")).toBeInTheDocument();
    expect(screen.getByText("actualizar")).toBeInTheDocument();
    expect(screen.queryByText("tur-1")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7.4 "Cargar más" usa el cursor de la página anterior
  // -------------------------------------------------------------------------
  it("7.4 'Cargar más' usa el cursor de la página anterior en lugar de un offset", async () => {
    const user = userEvent.setup();
    const { restaurar, mock } = mockFetchDoble([
      {
        ruta: "/api/auditoria",
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_1], siguiente_cursor: "cur-2" },
      },
      {
        ruta: /\/api\/auditoria\?cursor=cur-2/,
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_PAGINA_2], siguiente_cursor: null },
      },
      { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);
    await screen.findByText("tur-1");

    // Esperar a que pase la ventana del debounce y el botón siga disponible
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });

    await user.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByText("tur-2")).toBeInTheDocument();
    expect(screen.getByText("tur-1")).toBeInTheDocument();

    const urlsConCursor = urlsDe(mock).filter((url) => url.includes("cursor="));
    expect(urlsConCursor).toHaveLength(1);
    expect(urlsConCursor[0]).toContain("cursor=cur-2");
    expect(urlsConCursor[0]).not.toContain("offset");
    expect(urlsConCursor[0]).not.toContain("limite");

    // Segunda página sin siguiente cursor: desaparece el botón
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 7.5 Panel de exportación: cuatro datasets y formatos CSV/JSON
  // -------------------------------------------------------------------------
  it("7.5 el panel de exportación muestra los cuatro datasets con formatos CSV y JSON", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auditoria",
        metodo: "GET",
        status: 200,
        body: { eventos: [EVENTO_1], siguiente_cursor: null },
      },
      { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);
    await screen.findByText("tur-1");

    expect(screen.getByRole("heading", { name: "Exportación" })).toBeInTheDocument();

    (["agenda", "pacientes", "caja", "liquidaciones"] as const).forEach((dataset) => {
      const select = screen.getByRole("combobox", { name: `Formato ${dataset}` });
      expect(within(select).getByRole("option", { name: "CSV" })).toBeInTheDocument();
      expect(within(select).getByRole("option", { name: "JSON" })).toBeInTheDocument();
      expect(
        within(panelDeDataset(dataset)).getByRole("button", { name: "Exportar" }),
      ).toBeInTheDocument();
    });

    expect(screen.getAllByRole("button", { name: "Exportar" })).toHaveLength(4);
  });

  // -------------------------------------------------------------------------
  // 7.5 Exportación asíncrona 202 + sondeo del job
  // -------------------------------------------------------------------------
  it("7.5 en 202 sondea el job y descarga el archivo cuando queda listo", async () => {
    const user = userEvent.setup();
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    const { restaurar, mock } = mockExportacionConJob(["procesando", "listo"]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);
    await screen.findByText("tur-1");

    await user.click(within(panelDeDataset("agenda")).getByRole("button", { name: "Exportar" }));

    // Mientras sondea se muestra el estado "Exportando..."
    expect(await screen.findByRole("button", { name: "Exportando..." })).toBeDisabled();

    await waitFor(
      () => {
        expect(createObjectURLSpy).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );

    // Sondeó el estado más de una vez (procesando -> listo) y pidió la descarga
    const urls = urlsDe(mock);
    expect(urls.filter((url) => url === "/api/exportacion/jobs/job-1").length).toBeGreaterThanOrEqual(2);
    expect(urls).toContain("/api/exportacion/jobs/job-1/descarga");

    // El botón vuelve a estar habilitado al terminar
    await waitFor(() => {
      expect(
        within(panelDeDataset("agenda")).getByRole("button", { name: "Exportar" }),
      ).toBeEnabled();
    });
  });

  // -------------------------------------------------------------------------
  // 7.5 Errores de exportación uniformes (400/403/404/409/422/503)
  // -------------------------------------------------------------------------
  it.each([400, 403, 404, 409, 422, 503])(
    "7.5 un error %i de exportación se muestra de forma uniforme",
    async (status) => {
      const user = userEvent.setup();
      const { restaurar } = mockFetchDoble([
        {
          ruta: "/api/auditoria",
          metodo: "GET",
          status: 200,
          body: { eventos: [EVENTO_1], siguiente_cursor: null },
        },
        { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
        {
          ruta: "/api/exportacion/agenda?formato=csv",
          metodo: "GET",
          status,
          body: { detail: `Exportación rechazada (${status})` },
        },
      ]);
      restaurarFetch = restaurar;

      renderConProviders(<AuditoriaPage />);
      await screen.findByText("tur-1");

      await user.click(
        within(panelDeDataset("agenda")).getByRole("button", { name: "Exportar" }),
      );

      const alerta = await screen.findByRole("alert");
      expect(alerta).toHaveTextContent(`Exportación rechazada (${status})`);
      expect(
        within(panelDeDataset("agenda")).getByRole("button", { name: "Exportar" }),
      ).toBeEnabled();
    },
  );

  // -------------------------------------------------------------------------
  // 7.6 Fechas en ART y actores ausentes/eliminados
  // -------------------------------------------------------------------------
  it("7.6 muestra las fechas en ART y etiqueta actores ausentes o inactivos", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/auditoria",
        metodo: "GET",
        status: 200,
        body: {
          eventos: [
            // 02:30 UTC del 17/11 = 23:30 ART del 16/11 (cambio de día)
            evento("ev-sistema", "tur-sistema", null, "2026-11-17T02:30:00Z"),
            evento("ev-borrado", "tur-borrado", "u-eliminado", "2026-11-16T12:00:00Z"),
            evento("ev-inactivo", "tur-inactivo", "u-inactivo", "2026-11-16T12:00:00Z"),
          ],
          siguiente_cursor: null,
        },
      },
      { ruta: "/api/usuarios", metodo: "GET", status: 200, body: USUARIOS },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<AuditoriaPage />);

    await screen.findByText("tur-sistema");
    expect(screen.getByText("sistema")).toBeInTheDocument();
    expect(screen.getAllByText("usuario inactivo")).toHaveLength(2);

    // Fecha convertida a ART (UTC-3) incluyendo el cambio de día
    expect(screen.getByText(/16\/11\/2026.*23:30/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Fecha (ART)" })).toBeInTheDocument();
    expect(
      screen.getByText(/Horarios en America\/Argentina\/Buenos_Aires \(ART\)/),
    ).toBeInTheDocument();
  });
});
