import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useCierresCaja, useSenas } from "../caja/queries";
import { useLiquidacionesOS } from "../os/queries";
import { useAgenda } from "../agenda/queries";
import {
  clasificarDiferenciaCaja,
  formatearMontoARS,
} from "../../shared/formattersMonto";
import { EstadoCargando } from "../../shared/ComponentesEstado";

export function PanelPage() {
  const hoy = new Date().toISOString().slice(0, 10);
  const desdeISO = `${hoy}T00:00:00Z`;
  const hastaISO = `${hoy}T23:59:59Z`;

  const cierresQuery = useCierresCaja({ fecha: hoy });
  const liquidacionesQuery = useLiquidacionesOS();
  const senasQuery = useSenas();
  const agendaQuery = useAgenda({ desde: desdeISO, hasta: hastaISO });

  // 6.3 Refresco acotado del panel (30s visible, pausado en segundo plano)
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void cierresQuery.refetch();
        void liquidacionesQuery.refetch();
        void senasQuery.refetch();
        void agendaQuery.refetch();
      }
    }, 30_000);
    return () => window.clearInterval(id);
  }, [cierresQuery, liquidacionesQuery, senasQuery, agendaQuery]);

  const cierreHoy = (cierresQuery.data ?? [])[0] ?? null;
  const liquidacionesAbiertas = (liquidacionesQuery.data ?? []).filter(
    (l) => l.estado === "borrador" || l.estado === "presentada",
  );
  const senasActivas = (senasQuery.data ?? []).filter(
    (s) => s.estado === "pendiente" || s.estado === "vencida",
  );
  const turnosHoy = agendaQuery.data?.turnos ?? [];

  const conteosTurnos = {
    pendiente: turnosHoy.filter((t) => t.estado === "pendiente").length,
    confirmado: turnosHoy.filter((t) => t.estado === "confirmado").length,
    presente: turnosHoy.filter((t) => t.estado === "presente").length,
    finalizado: turnosHoy.filter((t) => t.estado === "finalizado").length,
  };

  return (
    <div data-testid="panel-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Panel del Consultorio</h1>
          <p className="text-sm text-slate-600">
            Resumen operativo del día ({hoy}) con importes calculados por el servidor (R8).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Tarjeta 1: Cierre de Caja del Día */}
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">1. Cierre de Caja del Día</h2>
            <Link to="/app/caja" className="text-xs font-semibold text-emerald-700 hover:underline">
              Ir a Caja
            </Link>
          </div>

          {cierresQuery.isLoading && <EstadoCargando mensaje="Consultando cierre de hoy..." />}

          {cierresQuery.error && (
            <div role="alert" className="space-y-2 rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <p>No pudimos cargar el cierre del día.</p>
              <button
                type="button"
                onClick={() => void cierresQuery.refetch()}
                className="font-semibold underline"
              >
                Reintentar
              </button>
            </div>
          )}

          {!cierresQuery.isLoading && !cierresQuery.error && !cierreHoy && (
            <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-900">
              <p className="font-semibold">Caja sin abrir hoy</p>
              <p className="text-xs">
                Todavía no se registró la apertura de caja para la fecha {hoy}.
              </p>
              <Link
                to="/app/caja"
                className="inline-block rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
              >
                Abrir caja del día
              </Link>
            </div>
          )}

          {!cierresQuery.isLoading && !cierresQuery.error && cierreHoy && (
            <div className="grid grid-cols-3 gap-2 rounded bg-slate-50 p-3 text-xs">
              <div>
                <span className="block text-slate-500">Sistema</span>
                <strong className="text-sm font-mono">
                  {formatearMontoARS(cierreHoy.total_sistema)}
                </strong>
              </div>
              <div>
                <span className="block text-slate-500">Contado</span>
                <strong className="text-sm font-mono">
                  {cierreHoy.total_contado !== null && cierreHoy.total_contado !== undefined
                    ? formatearMontoARS(cierreHoy.total_contado)
                    : "Pendiente"}
                </strong>
              </div>
              <div>
                <span className="block text-slate-500">Estado / Diferencia</span>
                <strong className="text-xs uppercase">
                  {cierreHoy.estado} · {clasificarDiferenciaCaja(cierreHoy.diferencia)}
                </strong>
              </div>
            </div>
          )}
        </section>

        {/* Tarjeta 2: Liquidaciones Abiertas */}
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">
              2. Liquidaciones de Obras Sociales
            </h2>
            <Link
              to="/app/os/liquidaciones"
              className="text-xs font-semibold text-emerald-700 hover:underline"
            >
              Ver liquidaciones
            </Link>
          </div>

          {liquidacionesQuery.isLoading && (
            <EstadoCargando mensaje="Consultando liquidaciones..." />
          )}

          {liquidacionesQuery.error && (
            <div role="alert" className="space-y-2 rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <p>No pudimos cargar las liquidaciones abiertas.</p>
              <button
                type="button"
                onClick={() => void liquidacionesQuery.refetch()}
                className="font-semibold underline"
              >
                Reintentar
              </button>
            </div>
          )}

          {!liquidacionesQuery.isLoading &&
            !liquidacionesQuery.error &&
            liquidacionesAbiertas.length === 0 && (
              <div className="rounded border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                No hay liquidaciones en borrador ni presentadas actualmente.{" "}
                <Link to="/app/os/liquidaciones" className="font-semibold text-emerald-700 underline">
                  Ir a Liquidaciones
                </Link>
              </div>
            )}

          {!liquidacionesQuery.isLoading &&
            !liquidacionesQuery.error &&
            liquidacionesAbiertas.length > 0 && (
              <ul className="space-y-2 text-xs">
                {liquidacionesAbiertas.map((l) => (
                  <li
                    key={l.id}
                    className="flex items-center justify-between rounded bg-slate-50 px-3 py-2"
                  >
                    <span>
                      <strong>{l.obra_social}</strong> ({l.periodo}) ·{" "}
                      <span className="uppercase">{l.estado}</span>
                    </span>
                    <strong className="font-mono">{formatearMontoARS(l.total)}</strong>
                  </li>
                ))}
              </ul>
            )}
        </section>

        {/* Tarjeta 3: Señas Pendientes o Vencidas */}
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">
              3. Señas Pendientes o Vencidas ({senasActivas.length})
            </h2>
            <Link to="/app/caja" className="text-xs font-semibold text-emerald-700 hover:underline">
              Gestionar señas
            </Link>
          </div>

          {senasActivas.length === 0 ? (
            <p className="text-xs text-slate-500">No hay señas pendientes ni vencidas.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {senasActivas.map((s) => (
                <li
                  key={s.id}
                  className="flex items-center justify-between rounded bg-slate-50 px-3 py-2"
                >
                  <span>
                    Turno {s.turno_id} · <strong className="uppercase">{s.estado}</strong>
                  </span>
                  <strong className="font-mono">{formatearMontoARS(s.monto)}</strong>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Tarjeta 4: Turnos del Día por Estado */}
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">
              4. Turnos del Día ({turnosHoy.length})
            </h2>
            <Link
              to="/app/agenda"
              className="text-xs font-semibold text-emerald-700 hover:underline"
            >
              Ver Agenda
            </Link>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-xs">
            <div className="rounded bg-amber-50 p-2.5">
              <span className="block text-amber-800">Pendientes</span>
              <strong className="text-base text-amber-900">{conteosTurnos.pendiente}</strong>
            </div>
            <div className="rounded bg-sky-50 p-2.5">
              <span className="block text-sky-800">Confirmados</span>
              <strong className="text-base text-sky-900">{conteosTurnos.confirmado}</strong>
            </div>
            <div className="rounded bg-emerald-50 p-2.5">
              <span className="block text-emerald-800">En atención</span>
              <strong className="text-base text-emerald-900">{conteosTurnos.presente}</strong>
            </div>
            <div className="rounded bg-slate-100 p-2.5">
              <span className="block text-slate-600">Finalizados</span>
              <strong className="text-base text-slate-900">{conteosTurnos.finalizado}</strong>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
