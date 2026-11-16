import { describe, it, expect, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderConProviders, mockFetchDoble } from "./render";
import { useQuery } from "@tanstack/react-query";

function ComponenteConQuery({ url }: { url: string }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["test", url],
    queryFn: async () => {
      const res = await fetch(url);
      if (!res.ok) {
        const json = await res.json();
        throw new Error(json.detail || "Error");
      }
      return res.json();
    },
  });

  if (isLoading) return <div>Cargando...</div>;
  if (error) return <div>Error: {error.message}</div>;
  return <div>Resultado: {data.mensaje}</div>;
}

describe("Helper renderConProviders y mockFetchDoble", () => {
  let restaurarFetch: (() => void) | null = null;

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  it("responde 200 con body esperado", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/test-ok",
        metodo: "GET",
        status: 200,
        body: { mensaje: "Éxito" },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComponenteConQuery url="/api/test-ok" />);

    expect(await screen.findByText("Resultado: Éxito")).toBeInTheDocument();
  });

  it("responde 409 con error de conflicto", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/test-conflict",
        metodo: "GET",
        status: 409,
        body: { detail: "El turno ya se encuentra ocupado." },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComponenteConQuery url="/api/test-conflict" />);

    expect(await screen.findByText("Error: El turno ya se encuentra ocupado.")).toBeInTheDocument();
  });
});
