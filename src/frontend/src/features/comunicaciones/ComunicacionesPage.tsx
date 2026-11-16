import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCrearPlantilla, useMensajes, usePlantillas, useReenviarMensaje } from "./queries";
import { sanitizarErrorProveedor } from "./sanitizar";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import { formatearFechaHora } from "../../shared/formatters";
import { ErrorApi } from "../../shared/api-client";
import type { CanalMensaje, MensajeRead, PlantillaRead } from "../../shared/api-types";

function etiquetaCanal(canal: CanalMensaje): string {
  if (canal === "wa") return "WhatsApp";
  if (canal === "email") return "Email";
  return "Manual";
}

function estiloEstadoMensaje(estado: string): string {
  switch (estado) {
    case "enviado":
      return "bg-emerald-100 text-emerald-800 border-emerald-200";
    case "pendiente":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "fallido":
      return "bg-rose-100 text-rose-800 border-rose-200";
    case "omitido":
      return "bg-slate-200 text-slate-800 border-slate-300";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

export function ComunicacionesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtroTurno, setFiltroTurno] = useState<string>(searchParams.get("turno_id") ?? "");
  const [filtroPaciente, setFiltroPaciente] = useState<string>(
    searchParams.get("paciente_id") ?? "",
  );
  const [filtroEstado, setFiltroEstado] = useState<string>(searchParams.get("estado") ?? "");

  const [avisoExito, setAvisoExito] = useState<string | null>(null);
  const [avisoAdvertencia, setAvisoAdvertencia] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [mensajesLocalOverride, setMensajesLocalOverride] = useState<Record<string, MensajeRead>>(
    {},
  );

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeReenviar =
    permite(roles, "mensajes", "reenviar") ||
    permite(roles, "mensajes", "actualizar") ||
    permite(roles, "mensajes", "crear");

  const filtrosActivos = {
    turno_id: filtroTurno.trim() || undefined,
    paciente_id: filtroPaciente.trim() || undefined,
    estado: filtroEstado.trim() || undefined,
  };

  const { data: mensajesRaw, isLoading, error } = useMensajes(filtrosActivos);
  const reenviarMut = useReenviarMensaje();

  const mensajes: MensajeRead[] = (mensajesRaw ?? []).map(
    (m) => mensajesLocalOverride[m.id] ?? m,
  );

  const aplicarFiltros = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (filtroTurno.trim()) next.set("turno_id", filtroTurno.trim());
    if (filtroPaciente.trim()) next.set("paciente_id", filtroPaciente.trim());
    if (filtroEstado.trim()) next.set("estado", filtroEstado.trim());
    setSearchParams(next);
  };

  const manejarReenvio = async (msg: MensajeRead) => {
    setAvisoExito(null);
    setAvisoAdvertencia(null);
    setErrorAccion(null);

    try {
      const actualizado = await reenviarMut.mutateAsync(msg.id);
      setMensajesLocalOverride((prev) => ({
        ...prev,
        [actualizado.id]: actualizado,
      }));

      if (
        actualizado.estado === "omitido" ||
        (actualizado.error && actualizado.error.toLowerCase().includes("opt-in"))
      ) {
        setAvisoAdvertencia(
          "Atención: el mensaje no se enviará porque el paciente no tiene opt-in de WhatsApp activo. Se registró la omisión (RN-CO-01).",
        );
      } else {
        setAvisoExito("Reenvío encolado en estado pendiente correctamente.");
      }
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorAccion(err.message);
      } else if (err instanceof Error) {
        setErrorAccion(err.message);
      } else {
        setErrorAccion("No pudimos reenviar el mensaje en este momento. Intentá de nuevo.");
      }
    }
  };

  return (
    <div data-testid="comunicaciones-page" className="space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Log de Comunicaciones</h1>
          <p className="text-sm text-slate-600">
            Historial de mensajes transaccionales y recordatorios por turno o paciente (RN-CO-01 / RN-CO-04).
          </p>
        </div>
        <Link
          to="/app/comunicaciones/plantillas"
          className="inline-flex items-center rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          Ver Plantillas Versionadas
        </Link>
      </div>

      {/* Filtros */}
      <form
        onSubmit={aplicarFiltros}
        className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 sm:grid-cols-4"
      >
        <div>
          <label htmlFor="filtro-turno" className="block text-xs font-medium text-slate-700">
            Turno
          </label>
          <input
            id="filtro-turno"
            type="text"
            value={filtroTurno}
            onChange={(e) => setFiltroTurno(e.target.value)}
            placeholder="Filtrar por turno..."
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="filtro-paciente" className="block text-xs font-medium text-slate-700">
            Paciente
          </label>
          <input
            id="filtro-paciente"
            type="text"
            value={filtroPaciente}
            onChange={(e) => setFiltroPaciente(e.target.value)}
            placeholder="Filtrar por paciente..."
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="filtro-estado" className="block text-xs font-medium text-slate-700">
            Estado
          </label>
          <select
            id="filtro-estado"
            value={filtroEstado}
            onChange={(e) => setFiltroEstado(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
          >
            <option value="">Todos los estados</option>
            <option value="pendiente">Pendiente</option>
            <option value="enviado">Enviado</option>
            <option value="fallido">Fallido</option>
            <option value="omitido">Omitido (sin opt-in)</option>
          </select>
        </div>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
          >
            Filtrar
          </button>
        </div>
      </form>

      {/* Alertas de operación */}
      {avisoExito && (
        <div
          role="status"
          className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          {avisoExito}
        </div>
      )}

      {avisoAdvertencia && (
        <div
          role="alert"
          className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        >
          {avisoAdvertencia}
        </div>
      )}

      {errorAccion && (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          {errorAccion}
        </div>
      )}

      {isLoading && <p className="text-sm text-slate-500">Cargando mensajes...</p>}

      {error && (
        <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          No pudimos cargar el historial de mensajes. Revisá tu conexión e intentá de nuevo.
        </div>
      )}

      {!isLoading && !error && mensajes.length === 0 && (
        <div
          data-testid="comunicaciones-vacio"
          className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-center"
        >
          <p className="text-base font-medium text-slate-800">
            No hay mensajes registrados para esta consulta.
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Recordá que según la regla RN-CO-01 solo se envían mensajes automáticos a pacientes con opt-in de WhatsApp activo.
          </p>
        </div>
      )}

      {!isLoading && mensajes.length > 0 && (
        <div className="space-y-3">
          {mensajes.map((msg) => {
            const errorCrudo = msg.error ?? msg.error_mensaje ?? null;
            const errorLimpio = sanitizarErrorProveedor(errorCrudo);

            return (
              <div
                key={msg.id}
                data-testid={`mensaje-item-${msg.id}`}
                className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800">
                      {etiquetaCanal(msg.canal)}
                    </span>
                    <span className="text-sm font-semibold text-slate-900">{msg.plantilla}</span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700">
                      v{msg.plantilla_version}
                    </span>
                    <span
                      className={`rounded border px-2 py-0.5 text-xs font-medium ${estiloEstadoMensaje(
                        msg.estado,
                      )}`}
                    >
                      {msg.estado}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-xs text-slate-600">
                    <span>
                      Intentos: <strong>{msg.intentos} / {msg.max_intentos}</strong>
                    </span>
                    {msg.programado_para && (
                      <span>Programado: {formatearFechaHora(msg.programado_para)}</span>
                    )}
                    {puedeReenviar && (
                      <button
                        type="button"
                        disabled={reenviarMut.isPending}
                        onClick={() => manejarReenvio(msg)}
                        className="rounded-md border border-sky-600 bg-white px-2.5 py-1 text-xs font-medium text-sky-700 hover:bg-sky-50 disabled:opacity-50"
                      >
                        Reenviar
                      </button>
                    )}
                  </div>
                </div>

                <p className="mt-2 rounded bg-slate-50 p-2.5 text-sm text-slate-800">
                  {msg.cuerpo_renderizado}
                </p>

                {errorLimpio && (
                  <p
                    data-testid={`mensaje-error-${msg.id}`}
                    className="mt-2 rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs text-rose-800"
                  >
                    Motivo del proveedor: {errorLimpio}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function PlantillasPage() {
  const { data: plantillas, isLoading, error } = usePlantillas();
  const crearPlantillaMut = useCrearPlantilla();

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEditarPlantillas = permite(roles, "mensajes", "crear");

  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [codigo, setCodigo] = useState("recordatorio_24h");
  const [canal, setCanal] = useState<CanalMensaje>("wa");
  const [asunto, setAsunto] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [exitoForm, setExitoForm] = useState<string | null>(null);

  const iniciarNuevaVersionDesde = (pl: PlantillaRead) => {
    setCodigo(pl.codigo);
    setCanal(pl.canal);
    setAsunto(pl.asunto ?? "");
    setCuerpo(pl.cuerpo);
    setErrorForm(null);
    setExitoForm(null);
    setMostrarFormulario(true);
  };

  const guardarNuevaVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);
    setExitoForm(null);

    if (!codigo.trim() || !cuerpo.trim()) {
      setErrorForm("Che, el código y el cuerpo de la plantilla son obligatorios.");
      return;
    }

    try {
      const creada = await crearPlantillaMut.mutateAsync({
        codigo: codigo.trim(),
        canal,
        asunto: asunto.trim() || undefined,
        cuerpo: cuerpo.trim(),
        activa: true,
      });
      setExitoForm(`Versión v${creada.version} creada para ${creada.codigo}.`);
      setMostrarFormulario(false);
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorForm(err.message);
      } else {
        setErrorForm("No pudimos guardar la nueva versión de la plantilla.");
      }
    }
  };

  return (
    <div data-testid="plantillas-page" className="space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Plantillas de Mensajes</h1>
          <p className="text-sm text-slate-600">
            Catálogo versionado de plantillas de comunicación. Los mensajes enviados conservan siempre la versión con la que se generaron (RN-CO-04).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/app/comunicaciones"
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Volver al Log
          </Link>
          {puedeEditarPlantillas && (
            <button
              type="button"
              onClick={() => {
                setErrorForm(null);
                setExitoForm(null);
                setMostrarFormulario((v) => !v);
              }}
              className="rounded-md bg-sky-600 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
            >
              Nueva versión
            </button>
          )}
        </div>
      </div>

      {exitoForm && (
        <div
          role="status"
          className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          {exitoForm}
        </div>
      )}

      {errorForm && (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          {errorForm}
        </div>
      )}

      {puedeEditarPlantillas && mostrarFormulario && (
        <form
          onSubmit={guardarNuevaVersion}
          className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
        >
          <h2 className="text-base font-semibold text-slate-900">
            Crear nueva versión de plantilla
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="pl-codigo" className="block text-xs font-medium text-slate-700">
                Código de plantilla
              </label>
              <input
                id="pl-codigo"
                type="text"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label htmlFor="pl-canal" className="block text-xs font-medium text-slate-700">
                Canal
              </label>
              <select
                id="pl-canal"
                value={canal}
                onChange={(e) => setCanal(e.target.value as CanalMensaje)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="wa">WhatsApp</option>
                <option value="email">Email</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="pl-cuerpo" className="block text-xs font-medium text-slate-700">
              Cuerpo de la plantilla
            </label>
            <textarea
              id="pl-cuerpo"
              rows={3}
              value={cuerpo}
              onChange={(e) => setCuerpo(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setMostrarFormulario(false)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={crearPlantillaMut.isPending}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
            >
              Guardar versión
            </button>
          </div>
        </form>
      )}

      {isLoading && <p className="text-sm text-slate-500">Cargando plantillas...</p>}

      {error && (
        <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          No pudimos consultar las plantillas del consultorio.
        </div>
      )}

      {!isLoading && plantillas && plantillas.length > 0 && (
        <div className="space-y-3">
          {plantillas.map((pl) => (
            <div
              key={pl.id}
              data-testid={`plantilla-item-${pl.codigo}-v${pl.version}`}
              className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900">{pl.codigo}</span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-800">
                    v{pl.version}
                  </span>
                  <span className="rounded bg-sky-50 px-2 py-0.5 text-xs text-sky-800">
                    {etiquetaCanal(pl.canal)}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      pl.activa
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {pl.activa ? "Activa" : "Inactiva"}
                  </span>
                </div>

                {puedeEditarPlantillas && (
                  <button
                    type="button"
                    onClick={() => iniciarNuevaVersionDesde(pl)}
                    className="text-xs font-medium text-sky-700 hover:underline"
                  >
                    Editar en nueva versión
                  </button>
                )}
              </div>

              <p className="mt-2 rounded bg-slate-50 p-2.5 font-mono text-xs text-slate-800">
                {pl.cuerpo}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
