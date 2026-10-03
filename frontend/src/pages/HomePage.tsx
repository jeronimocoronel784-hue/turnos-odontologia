import { ApiStatus } from "../features/api-status/ApiStatus";

// Página raíz: shell mínima que refleja el estado de la API (spec foundation 1.4).
export function HomePage(): JSX.Element {
  return (
    <main className="mx-auto max-w-xl p-6">
      <h1 className="mb-2 text-2xl font-bold text-teal-900">Turnos Odontología</h1>
      <p className="mb-4 text-slate-600">
        Reservá y gestioná tus turnos. Estado de la conexión:
      </p>
      <ApiStatus />
    </main>
  );
}
