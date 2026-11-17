import React, { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import { ErrorApi } from "../../shared/api-client";
import { EstadoCargando, EstadoError, EstadoVacio } from "../../shared/ComponentesEstado";
import {
  obtenerEstadoJob,
  descargarJob,
  AuditoriaEventoRead,
  AuditoriaFiltros,
  ExportacionJobRead,
} from "./api";
import { useAuditoriaTrail, useUsuariosAuditoria } from "./queries";
import { UsuarioRead } from "../../shared/api-types";

const DATASETS = ["agenda", "pacientes", "caja", "liquidaciones"] as const;

function formatearFechaHoraART(iso: string): string {
  try {
    const fecha = new Date(iso);
    return new Intl.DateTimeFormat("es-AR", {
      timeZone: "America/Argentina/Buenos_Aires",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(fecha);
  } catch {
    return iso;
  }
}

function descargarBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function AuditoriaPage() {
  const queryClient = useQueryClient();
  const usuario = getIdentidad();
  const roles = usuario?.roles || [];

  const [filtros, setFiltros] = useState<AuditoriaFiltros>({});
  const [entidad, setEntidad] = useState("");
  const [actorId, setActorId] = useState("");
  const [accion, setAccion] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");

  const [cursor, setCursor] = useState<string | null>(null);
  const [eventos, setEventos] = useState<AuditoriaEventoRead[]>([]);
  const [siguienteCursor, setSiguienteCursor] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);

  const [usuarios, setUsuarios] = useState<UsuarioRead[]>([]);

  const [errorExport, setErrorExport] = useState<string | null>(null);
  const [exportando, setExportando] = useState<string | null>(null);
  const [formatos, setFormatos] = useState<Record<string, string>>({
    agenda: "csv",
    pacientes: "csv",
    caja: "csv",
    liquidaciones: "csv",
  });

  const usuariosQuery = useUsuariosAuditoria();
  const trailQuery = useAuditoriaTrail(filtros, cursor);

  // Cargar usuarios para el selector de actor
  useEffect(() => {
    if (usuariosQuery.data) setUsuarios(usuariosQuery.data);
  }, [usuariosQuery.data]);

  // Acumular eventos al cambiar de página
  useEffect(() => {
    if (trailQuery.data) {
      if (cursor === null) {
        setEventos(trailQuery.data.eventos);
      } else {
        setEventos((prev) => [...prev, ...trailQuery.data!.eventos]);
      }
      setSiguienteCursor(trailQuery.data.siguiente_cursor);
      setCargandoMas(false);
    }
  }, [trailQuery.data, cursor]);

  // Aplicar filtros: resetear paginación
  function aplicarFiltros(nuevos: AuditoriaFiltros) {
    setEventos([]);
    setCursor(null);
    setSiguienteCursor(null);
    setFiltros(nuevos);
  }

  function handleFiltrar(e?: React.FormEvent) {
    if (e) e.preventDefault();
    aplicarFiltros({
      entidad: entidad.trim() || undefined,
      actor_id: actorId || undefined,
      accion: accion.trim() || undefined,
      desde: desde || undefined,
      hasta: hasta || undefined,
    });
  }

  // Auto-aplicar al cambiar campos (para que los filtros disparen la consulta)
  useEffect(() => {
    const t = setTimeout(() => {
      handleFiltrar();
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entidad, actorId, accion, desde, hasta]);

  function cargarMas() {
    if (!siguienteCursor) return;
    setCargandoMas(true);
    setCursor(siguienteCursor);
  }

  async function handleExportar(dataset: string) {
    setErrorExport(null);
    setExportando(dataset);
    const formato = formatos[dataset] || "csv";
    try {
      const params = new URLSearchParams();
      params.set("formato", formato);
      const token = (await import("../../shared/sesion")).getAccessToken();
      const headers: HeadersInit = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const r = await fetch(`/api/exportacion/${dataset}?${params.toString()}`, {
        credentials: "include",
        headers,
      });
      if (r.status === 202) {
        const job = (await r.json()) as ExportacionJobRead;
        await sondearJob(job.job_id);
        return;
      }
      if (!r.ok) {
        let mensaje = `Error del servidor (${r.status})`;
        try {
          const cuerpo = await r.json();
          if (cuerpo && typeof cuerpo === "object") {
            if ("detail" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detail);
            else if ("detalle" in cuerpo) mensaje = String((cuerpo as Record<string, unknown>).detalle);
          }
        } catch {
          // ignore
        }
        throw new ErrorApi(r.status, mensaje);
      }
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition");
      const filename =
        (cd?.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/)?.[1] ?? `${dataset}.${formato}`);
      descargarBlob(blob, decodeURIComponent(filename));
    } catch (err) {
      const msg = err instanceof ErrorApi ? err.detalle : "No se pudo exportar.";
      setErrorExport(msg);
    } finally {
      setExportando(null);
    }
  }

  async function sondearJob(jobId: string) {
    let intentos = 0;
    while (intentos < 100) {
      intentos += 1;
      const job = await obtenerEstadoJob(jobId);
      if (job.estado === "listo") {
        const { blob, filename } = await descargarJob(jobId);
        descargarBlob(blob, filename);
        return;
      }
      if (job.estado === "error") {
        throw new ErrorApi(409, job.error || "No pudimos generar el archivo. Probá de nuevo.");
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    throw new ErrorApi(503, "Tiempo de espera agotado.");
  }

  if (!permite(roles, "auditoria", "leer")) {
    return (
      <div data-testid="auditoria-page" className="space-y-6">
        <EstadoError error={new ErrorApi(403, "No tenés permiso para ver la auditoría.")} />
      </div>
    );
  }

  const isLoading = trailQuery.isLoading;
  const error = trailQuery.error;

  function nombreActor(actorIdVal: string | null): string {
    if (!actorIdVal) return "sistema";
    const u = usuarios.find((x) => x.id === actorIdVal);
    if (!u) return "usuario inactivo";
    if (!u.activo) return "usuario inactivo";
    return u.nombre;
  }

  return (
    <div data-testid="auditoria-page" className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Auditoría</h1>
        <p className="text-sm text-slate-500">
          Trail de acciones del consultorio (solo lectura). Horarios en America/Argentina/Buenos_Aires (ART).
        </p>
      </div>

      {/* Filtros */}
      <form onSubmit={handleFiltrar} className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div>
          <label htmlFor="filtro-entidad" className="block text-xs font-medium text-slate-700 mb-1">
            Entidad
          </label>
          <input
            id="filtro-entidad"
            type="text"
            value={entidad}
            onChange={(e) => setEntidad(e.target.value)}
            className="w-full border border-slate-300 rounded-md p-2 text-sm"
            list="entidades-conocidas"
          />
          <datalist id="entidades-conocidas">
            <option value="turno" />
            <option value="paciente" />
            <option value="caja" />
            <option value="liquidacion" />
            <option value="exportacion" />
          </datalist>
        </div>
        <div>
          <label htmlFor="filtro-actor" className="block text-xs font-medium text-slate-700 mb-1">
            Actor
          </label>
          <select
            id="filtro-actor"
            value={actorId}
            onChange={(e) => setActorId(e.target.value)}
            className="w-full border border-slate-300 rounded-md p-2 text-sm"
          >
            <option value="">Todos</option>
            {usuarios.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nombre}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filtro-accion" className="block text-xs font-medium text-slate-700 mb-1">
            Acción
          </label>
          <input
            id="filtro-accion"
            type="text"
            value={accion}
            onChange={(e) => setAccion(e.target.value)}
            className="w-full border border-slate-300 rounded-md p-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="filtro-desde" className="block text-xs font-medium text-slate-700 mb-1">
            Desde
          </label>
          <input
            id="filtro-desde"
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="w-full border border-slate-300 rounded-md p-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="filtro-hasta" className="block text-xs font-medium text-slate-700 mb-1">
            Hasta
          </label>
          <input
            id="filtro-hasta"
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="w-full border border-slate-300 rounded-md p-2 text-sm"
          />
        </div>
        <div className="sm:col-span-2 lg:col-span-5 flex justify-end">
          <button
            type="submit"
            className="px-4 py-2 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700"
          >
            Filtrar
          </button>
        </div>
      </form>

      {/* Tabla */}
      {isLoading ? (
        <EstadoCargando mensaje="Cargando auditoría..." />
      ) : error ? (
        <EstadoError error={error} alReintentar={() => queryClient.invalidateQueries()} />
      ) : eventos.length === 0 ? (
        <EstadoVacio titulo="Sin eventos" descripcion="No hay eventos para los filtros seleccionados." />
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-700 font-semibold">
              <tr>
                <th className="py-3 px-4">Fecha (ART)</th>
                <th className="py-3 px-4">Actor</th>
                <th className="py-3 px-4">Entidad</th>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Acción</th>
                <th className="py-3 px-4">Detalles</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {eventos.map((ev) => (
                <tr key={ev.id} className="hover:bg-slate-50 transition">
                  <td className="py-3 px-4 text-slate-700">{formatearFechaHoraART(ev.created_at)}</td>
                  <td className="py-3 px-4 text-slate-700">{nombreActor(ev.actor_id)}</td>
                  <td className="py-3 px-4 text-slate-700">{ev.entidad}</td>
                  <td className="py-3 px-4 text-slate-700">{ev.entidad_id}</td>
                  <td className="py-3 px-4 text-slate-700">{ev.accion}</td>
                  <td className="py-3 px-4 text-slate-700">
                    <details>
                      <summary className="cursor-pointer text-emerald-700">ver</summary>
                      {ev.antes && (
                        <pre className="text-xs bg-slate-50 p-2 rounded mt-1 overflow-auto">
                          {JSON.stringify(ev.antes, null, 2)}
                        </pre>
                      )}
                      {ev.despues && (
                        <pre className="text-xs bg-slate-50 p-2 rounded mt-1 overflow-auto">
                          {JSON.stringify(ev.despues, null, 2)}
                        </pre>
                      )}
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {siguienteCursor && (
            <div className="p-4 flex justify-center">
              <button
                type="button"
                onClick={cargarMas}
                disabled={cargandoMas || trailQuery.isFetching}
                className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                {cargandoMas ? "Cargando..." : "Cargar más"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Panel de exportación */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200">
        <h2 className="text-lg font-bold text-slate-900 mb-3">Exportación</h2>
        {errorExport && (
          <div role="alert" className="mb-3 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
            {errorExport}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {DATASETS.map((ds) => (
            <div key={ds} className="border border-slate-200 rounded-md p-3">
              <div className="font-medium text-slate-800 mb-2 capitalize">{ds}</div>
              <select
                aria-label={`Formato ${ds}`}
                value={formatos[ds]}
                onChange={(e) => setFormatos((prev) => ({ ...prev, [ds]: e.target.value }))}
                className="w-full border border-slate-300 rounded-md p-2 text-sm mb-2"
              >
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
              </select>
              <button
                type="button"
                onClick={() => handleExportar(ds)}
                disabled={exportando === ds}
                className="w-full px-3 py-2 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
              >
                {exportando === ds ? "Exportando..." : "Exportar"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
