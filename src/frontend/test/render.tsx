import React from "react";
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

export function crearTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface RenderConProvidersOpciones extends Omit<RenderOptions, "wrapper"> {
  ruta?: string;
  queryClient?: QueryClient;
}

export function renderConProviders(
  ui: React.ReactElement,
  opciones: RenderConProvidersOpciones = {},
) {
  const { ruta = "/", queryClient = crearTestQueryClient(), ...resto } = opciones;

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[ruta]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...resto }),
    queryClient,
  };
}

export interface ReglaMockFetch {
  ruta: string | RegExp;
  metodo?: string;
  status?: number;
  body?: unknown;
  validarBody?: (body: unknown) => void;
}

export function mockFetchDoble(reglas: ReglaMockFetch[]) {
  const fetchOriginal = global.fetch;

  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const metodo = (init?.method || "GET").toUpperCase();

    const regla = reglas.find((r) => {
      const metodoCoincide = !r.metodo || r.metodo.toUpperCase() === metodo;
      const rutaCoincide = typeof r.ruta === "string" ? url === r.ruta : r.ruta.test(url);
      return metodoCoincide && rutaCoincide;
    });

    if (!regla) {
      throw new Error(`Fetch no mockeado para [${metodo}] ${url}`);
    }

    if (regla.validarBody && init?.body) {
      const parsedBody = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
      regla.validarBody(parsedBody);
    }

    const status = regla.status ?? 200;
    const responseBody = regla.body !== undefined ? JSON.stringify(regla.body) : "";

    return new Response(responseBody, {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });

  global.fetch = mock as unknown as typeof fetch;

  return {
    mock,
    restaurar: () => {
      global.fetch = fetchOriginal;
    },
  };
}
