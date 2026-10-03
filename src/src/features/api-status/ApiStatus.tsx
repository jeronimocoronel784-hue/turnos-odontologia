import { useQuery } from "@tanstack/react-query";
import { obtenerSalud } from "../../shared/api-client";

// Muestra el estado de la API (conectado / error en rioplatense). Sin `any` (R5).
export function ApiStatus(): JSX.Element {
  const consulta = useQuery({
    queryKey: ["salud"],
    queryFn: ({ signal }: { signal: AbortSignal | undefined }) => obtenerSalud(signal),
  });

  if (consulta.isPending) {
    return <p className="text-slate-600">Chequeando la conexión con la API…</p>;
  }
  if (consulta.isError) {
    const mensaje = consulta.error instanceof Error ? consulta.error.message : "Error desconocido.";
    return (
      <p role="alert" className="rounded bg-red-50 p-3 text-red-700">
        Che, no pudimos conectar con la API: {mensaje}
      </p>
    );
  }
  return (
    <p role="status" className="rounded bg-emerald-50 p-3 text-emerald-700">
      Conectado: la API y sus servicios están ok.
    </p>
  );
}
