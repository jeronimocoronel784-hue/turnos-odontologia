import React, { useState, useMemo } from "react";
import {
  useAgenda,
  useCatalogosAgenda,
  useMutacionesAgenda,
} from "./queries";
import { getIdentidad } from "../../shared/sesion";
import { EstadoTurno, TurnoRead, BloqueoRead } from "../../shared/api-types";
import {
  formatearHora,
  formatearFechaCorta,
  formatearFechaLarga,
} from "../../shared/formatters";
import { EstadoCargando, EstadoVacio, EstadoError } from "../../shared/ComponentesEstado";
import { ErrorApi } from "../../shared/api-client";

export function AgendaPage() {
  const usuario = getIdentidad();
  const esOdontologo = usuario?.roles.includes("odontologo");

  const [fechaSeleccionada, setFechaSeleccionada] = useState<string>(() => {
    return new Date().toISOString().slice(0, 10);
  });
  const [profesionalFiltro, setProfesionalFiltro] = useState<string>(() => {
    return esOdontologo && usuario ? usuario.id : "";
  });
  const [sillonFiltro, setSillonFiltro] = useState<string>("");
  const [estadoFiltro, setEstadoFiltro] = useState<string>("");

  // Modales
  const [turnoSeleccionado, setTurnoSeleccionado] = useState<TurnoRead | null>(null);
  const [mostrarModalAlta, setMostrarModalAlta] = useState(false);
  const [mostrarModalBloqueo, setMostrarModalBloqueo] = useState(false);
  const [mostrarModalReprogramar, setMostrarModalReprogramar] = useState(false);
  const [mostrarModalCancelar, setMostrarModalCancelar] = useState(false);

  // Form states
  const [pacienteId, setPacienteId] = useState("");
  const [profesionalId, setProfesionalId] = useState(() => (esOdontologo && usuario ? usuario.id : ""));
  const [sillonId, setSillonId] = useState("");
  const [prestacionId, setPrestacionId] = useState("");
  const [horaInicio, setHoraInicio] = useState("09:00");
  const [duracionMin, setDuracionMin] = useState(30);
  const [overrideDuracion, setOverrideDuracion] = useState(false);
  const [esSobreturno, setEsSobreturno] = useState(false);
  const [observaciones, setObservaciones] = useState("");

  // Cancelar / Reprogramar form states
  const [motivoCancelacion, setMotivoCancelacion] = useState("");
  const [nuevaFechaReprogramar, setNuevaFechaReprogramar] = useState(fechaSeleccionada);
  const [nuevaHoraReprogramar, setNuevaHoraReprogramar] = useState("10:00");
  const [motivoReprogramar, setMotivoReprogramar] = useState("");

  // Bloqueo form states
  const [bloqueoProfId, setBloqueoProfId] = useState("");
  const [bloqueoSillonId, setBloqueoSillonId] = useState("");
  const [bloqueoHoraDesde, setBloqueoHoraDesde] = useState("12:00");
  const [bloqueoHoraHasta, setBloqueoHoraHasta] = useState("13:00");
  const [bloqueoMotivo, setBloqueoMotivo] = useState<"feriado" | "vacaciones" | "mantenimiento" | "manual">("manual");
  const [bloqueoDesc, setBloqueoDesc] = useState("");

  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const inicioDia = `${fechaSeleccionada}T00:00:00`;
  const finDia = `${fechaSeleccionada}T23:59:59`;

  const { data: agendaData, isLoading, error, refetch } = useAgenda({
    desde: inicioDia,
    hasta: finDia,
    profesional_id: profesionalFiltro || undefined,
    sillon_id: sillonFiltro || undefined,
    estado: estadoFiltro || undefined,
  });

  const {
    profesionales,
    prestaciones,
    sillones,
    politicas,
    pacientes,
    cargando: cargandoCatalogos,
  } = useCatalogosAgenda();

  const { altaTurno, cambiarEstado, reprogramar, altaBloqueo, bajaBloqueo } = useMutacionesAgenda();

  const pacientesMap = useMemo(() => {
    const mapa = new Map<string, { nombre: string; dni: string; telefono: string }>();
    pacientes.forEach((p) => {
      mapa.set(p.id, { nombre: p.nombre, dni: p.dni, telefono: p.telefono });
    });
    return mapa;
  }, [pacientes]);

  const prestacionesMap = useMemo(() => {
    const mapa = new Map<string, string>();
    prestaciones.forEach((p) => mapa.set(p.id, p.nombre));
    return mapa;
  }, [prestaciones]);

  const profesionalesMap = useMemo(() => {
    const mapa = new Map<string, string>();
    profesionales.forEach((u) => mapa.set(u.id, u.nombre));
    return mapa;
  }, [profesionales]);

  const sillonesMap = useMemo(() => {
    const mapa = new Map<string, string>();
    sillones.forEach((s) => mapa.set(s.id, s.nombre));
    return mapa;
  }, [sillones]);

  function cambiarDia(delta: number) {
    const d = new Date(`${fechaSeleccionada}T12:00:00`);
    d.setDate(d.getDate() + delta);
    setFechaSeleccionada(d.toISOString().slice(0, 10));
  }

  // Handlers
  async function handleCrearTurno(e: React.FormEvent) {
    e.preventDefault();
    setErrorAccion(null);

    if (!pacienteId || !profesionalId || !sillonId || !prestacionId) {
      setErrorAccion("Por favor completá paciente, profesional, sillón y prestación.");
      return;
    }

    if ((overrideDuracion || esSobreturno) && !observaciones.trim()) {
      setErrorAccion(
        "Para sobreturnos o duración personalizada es obligatorio ingresar el motivo en observaciones.",
      );
      return;
    }

    const inicioIso = `${fechaSeleccionada}T${horaInicio}:00`;
    const fechaInicioObj = new Date(inicioIso);
    const fechaFinObj = new Date(fechaInicioObj.getTime() + duracionMin * 60000);
    const finIso = fechaFinObj.toISOString().slice(0, 19);

    try {
      await altaTurno.mutateAsync({
        paciente_id: pacienteId,
        profesional_id: profesionalId,
        sillon_id: sillonId,
        prestacion_id: prestacionId,
        inicio: inicioIso,
        fin: finIso,
        sobreturno: esSobreturno,
        observaciones: observaciones.trim() || undefined,
      });
      setMostrarModalAlta(false);
      setObservaciones("");
      setEsSobreturno(false);
      setOverrideDuracion(false);
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorAccion(err.detalle);
      } else {
        setErrorAccion("No se pudo agendar el turno. Revisá posibles solapamientos.");
      }
    }
  }

  async function handleCambiarEstado(turnoId: string, nuevoEstado: EstadoTurno, motivo?: string) {
    setErrorAccion(null);
    try {
      await cambiarEstado.mutateAsync({
        id: turnoId,
        input: { estado: nuevoEstado, motivo_cancelacion: motivo },
      });
      if (turnoSeleccionado?.id === turnoId) {
        setTurnoSeleccionado(null);
      }
      setMostrarModalCancelar(false);
      setMotivoCancelacion("");
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorAccion(err.detalle);
      } else {
        setErrorAccion("No se pudo actualizar el estado del turno.");
      }
    }
  }

  async function handleReprogramar(e: React.FormEvent) {
    e.preventDefault();
    if (!turnoSeleccionado) return;
    setErrorAccion(null);

    const nuevoInicioIso = `${nuevaFechaReprogramar}T${nuevaHoraReprogramar}:00`;
    try {
      await reprogramar.mutateAsync({
        id: turnoSeleccionado.id,
        input: {
          nuevo_inicio: nuevoInicioIso,
          motivo: motivoReprogramar.trim() || undefined,
        },
      });
      setMostrarModalReprogramar(false);
      setTurnoSeleccionado(null);
      setMotivoReprogramar("");
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorAccion(err.detalle);
      } else {
        setErrorAccion("No se pudo reprogramar el turno. Verificá solapamientos.");
      }
    }
  }

  async function handleCrearBloqueo(e: React.FormEvent) {
    e.preventDefault();
    setErrorAccion(null);

    if (!bloqueoProfId && !bloqueoSillonId) {
      setErrorAccion("Tenés que indicar al menos un profesional o un sillón para el bloqueo.");
      return;
    }

    const desdeIso = `${fechaSeleccionada}T${bloqueoHoraDesde}:00`;
    const hastaIso = `${fechaSeleccionada}T${bloqueoHoraHasta}:00`;

    if (hastaIso <= desdeIso) {
      setErrorAccion("La hora hasta debe ser posterior a la hora desde.");
      return;
    }

    try {
      await altaBloqueo.mutateAsync({
        profesional_id: bloqueoProfId || undefined,
        sillon_id: bloqueoSillonId || undefined,
        desde: desdeIso,
        hasta: hastaIso,
        motivo: bloqueoMotivo,
        descripcion: bloqueoDesc.trim() || undefined,
      });
      setMostrarModalBloqueo(false);
      setBloqueoDesc("");
    } catch (err) {
      if (err instanceof ErrorApi) {
        setErrorAccion(err.detalle);
      } else {
        setErrorAccion("No se pudo registrar el bloqueo.");
      }
    }
  }

  const turnosOrdenados = useMemo(() => {
    if (!agendaData?.turnos) return [];
    return [...agendaData.turnos].sort(
      (a, b) => new Date(a.inicio).getTime() - new Date(b.inicio).getTime(),
    );
  }, [agendaData]);

  const bloqueosOrdenados = useMemo(() => {
    if (!agendaData?.bloqueos) return [];
    return [...agendaData.bloqueos].sort(
      (a, b) => new Date(a.desde).getTime() - new Date(b.desde).getTime(),
    );
  }, [agendaData]);

  return (
    <div className="space-y-6" data-testid="agenda-page">
      {/* Barra de cabecera: Fecha, Navegación y Acciones principales */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center rounded-md border border-slate-300 shadow-sm">
            <button
              type="button"
              onClick={() => cambiarDia(-1)}
              className="px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 border-r border-slate-300 rounded-l-md"
              aria-label="Día anterior"
            >
              ◀
            </button>
            <button
              type="button"
              onClick={() => setFechaSeleccionada(new Date().toISOString().slice(0, 10))}
              className="px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Hoy
            </button>
            <button
              type="button"
              onClick={() => cambiarDia(1)}
              className="px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 border-l border-slate-300 rounded-r-md"
              aria-label="Día siguiente"
            >
              ▶
            </button>
          </div>

          <input
            type="date"
            value={fechaSeleccionada}
            onChange={(e) => setFechaSeleccionada(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm focus:outline-none focus:ring-emerald-500 focus:border-emerald-500"
          />

          <span className="text-sm font-medium text-slate-600 hidden lg:inline capitalize">
            {formatearFechaLarga(`${fechaSeleccionada}T12:00:00`)}
          </span>
        </div>

        {/* Botones de acción */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMostrarModalAlta(true)}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-emerald-600 hover:bg-emerald-700"
          >
            + Nuevo Turno
          </button>
          <button
            type="button"
            onClick={() => setMostrarModalBloqueo(true)}
            className="inline-flex items-center px-3 py-2 border border-slate-300 text-sm font-medium rounded-md text-slate-700 bg-white hover:bg-slate-50"
          >
            Bloquear Franja
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white p-3 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Profesional</label>
          <select
            value={profesionalFiltro}
            onChange={(e) => setProfesionalFiltro(e.target.value)}
            disabled={esOdontologo}
            className="w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white"
          >
            <option value="">Todos los profesionales</option>
            {profesionales.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Sillón</label>
          <select
            value={sillonFiltro}
            onChange={(e) => setSillonFiltro(e.target.value)}
            className="w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white"
          >
            <option value="">Todos los sillones</option>
            {sillones.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nombre} ({s.sucursal})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Estado</label>
          <select
            value={estadoFiltro}
            onChange={(e) => setEstadoFiltro(e.target.value)}
            className="w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white"
          >
            <option value="">Todos los estados</option>
            <option value="pendiente">Pendiente</option>
            <option value="confirmado">Confirmado</option>
            <option value="presente">Presente</option>
            <option value="finalizado">Finalizado</option>
            <option value="cancelado">Cancelado</option>
            <option value="ausente">Ausente</option>
            <option value="reprogramado">Reprogramado</option>
          </select>
        </div>
      </div>

      {/* Alerta de política de cancelación si aplica */}
      {politicas && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-3 py-2 rounded-md flex justify-between items-center">
          <span>
            ℹ️ Política de cancelación del consultorio: anticipación mínima de{" "}
            <strong>{politicas.cancelacion_horas} horas</strong>. Fuera de ese plazo, la seña
            podría retenerse según las reglas del consultorio.
          </span>
        </div>
      )}

      {errorAccion && !mostrarModalCancelar && !mostrarModalAlta && !mostrarModalReprogramar && !mostrarModalBloqueo && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md"
        >
          {errorAccion}
        </div>
      )}

      {/* Contenido de la agenda */}
      {isLoading || cargandoCatalogos ? (
        <EstadoCargando mensaje="Cargando agenda del día..." />
      ) : error ? (
        <EstadoError error={error} alReintentar={() => refetch()} />
      ) : turnosOrdenados.length === 0 && bloqueosOrdenados.length === 0 ? (
        <EstadoVacio
          titulo="No hay turnos ni bloqueos"
          descripcion={`No hay actividades programadas para el ${formatearFechaCorta(
            `${fechaSeleccionada}T12:00:00`,
          )} con los filtros seleccionados.`}
          accion={{
            texto: "+ Agendar turno",
            onClick: () => setMostrarModalAlta(true),
          }}
        />
      ) : (
        <div className="space-y-3">
          {/* Bloqueos */}
          {bloqueosOrdenados.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Bloqueos Horarios
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {bloqueosOrdenados.map((bloqueo) => (
                  <div
                    key={bloqueo.id}
                    className="p-3 bg-slate-100 border border-slate-300 rounded-lg flex justify-between items-center text-slate-700"
                  >
                    <div>
                      <div className="text-sm font-semibold flex items-center gap-2">
                        <span>⛔ Bloqueo: {bloqueo.motivo}</span>
                        <span className="text-xs font-normal text-slate-500">
                          ({formatearHora(bloqueo.desde)} - {formatearHora(bloqueo.hasta)})
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {bloqueo.profesional_id && (
                          <span>Prof: {profesionalesMap.get(bloqueo.profesional_id) || "Asignado"} · </span>
                        )}
                        {bloqueo.sillon_id && (
                          <span>Sillón: {sillonesMap.get(bloqueo.sillon_id) || "Asignado"}</span>
                        )}
                        {bloqueo.descripcion && ` · ${bloqueo.descripcion}`}
                      </div>
                    </div>
                    {!esOdontologo && (
                      <button
                        type="button"
                        onClick={() => bajaBloqueo.mutate(bloqueo.id)}
                        className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1"
                      >
                        Desbloquear
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Turnos */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Turnos ({turnosOrdenados.length})
            </h3>
            <div className="grid grid-cols-1 gap-2.5">
              {turnosOrdenados.map((turno) => {
                const pacienteInfo = pacientesMap.get(turno.paciente_id);
                const esPropioOdontologo = !esOdontologo || turno.profesional_id === usuario?.id;

                return (
                  <div
                    key={turno.id}
                    className={`p-4 bg-white border rounded-lg shadow-sm transition flex flex-col md:flex-row md:items-center md:justify-between gap-4 ${
                      turno.estado === "cancelado"
                        ? "border-slate-200 bg-slate-50 opacity-60"
                        : "border-slate-200 hover:border-emerald-500"
                    }`}
                  >
                    {/* Info del turno */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-base font-bold text-slate-900">
                          {formatearHora(turno.inicio)} - {formatearHora(turno.fin)}
                        </span>

                        {/* Badges de estado con texto explicito (Task 3.3) */}
                        <span
                          className={`text-xs px-2 py-0.5 font-semibold rounded-full capitalize ${
                            turno.estado === "confirmado"
                              ? "bg-blue-100 text-blue-800"
                              : turno.estado === "presente"
                              ? "bg-purple-100 text-purple-800"
                              : turno.estado === "finalizado"
                              ? "bg-emerald-100 text-emerald-800"
                              : turno.estado === "cancelado"
                              ? "bg-red-100 text-red-800"
                              : turno.estado === "ausente"
                              ? "bg-slate-200 text-slate-700"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {turno.estado}
                        </span>

                        {turno.sobreturno && (
                          <span className="text-xs px-2 py-0.5 bg-orange-100 text-orange-800 font-bold rounded-full">
                            Sobreturno
                          </span>
                        )}

                        {!turno.sena_cobrada && (
                          <span className="text-xs px-2 py-0.5 bg-rose-50 text-rose-700 border border-rose-200 font-medium rounded-full">
                            Seña pendiente
                          </span>
                        )}

                        {turno.turno_origen_id && (
                          <span className="text-xs px-2 py-0.5 bg-sky-50 text-sky-700 border border-sky-200 rounded-full">
                            Reprogramado
                          </span>
                        )}
                      </div>

                      <div className="mt-1 flex items-center gap-2 text-sm text-slate-800 font-semibold">
                        <span>{pacienteInfo?.nombre || "Paciente"}</span>
                        {pacienteInfo?.dni && (
                          <span className="text-xs text-slate-500 font-normal">
                            (DNI {pacienteInfo.dni})
                          </span>
                        )}
                      </div>

                      <div className="mt-1 text-xs text-slate-600 flex flex-wrap gap-x-3 gap-y-1">
                        <span>Prestación: {prestacionesMap.get(turno.prestacion_id) || "Consulta"}</span>
                        <span>Prof: {profesionalesMap.get(turno.profesional_id) || "Odontólogo"}</span>
                        <span>Sillón: {sillonesMap.get(turno.sillon_id) || "Box"}</span>
                        {turno.observaciones && (
                          <span className="italic text-slate-500">"{turno.observaciones}"</span>
                        )}
                        {turno.motivo_cancelacion && (
                          <span className="text-red-600">Motivo: {turno.motivo_cancelacion}</span>
                        )}
                      </div>
                    </div>

                    {/* Acciones sobre el turno segun grafo y permisos */}
                    {esPropioOdontologo && turno.estado !== "cancelado" && turno.estado !== "finalizado" && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {turno.estado === "pendiente" && (
                          <button
                            type="button"
                            onClick={() => handleCambiarEstado(turno.id, "confirmado")}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                          >
                            Confirmar
                          </button>
                        )}

                        {(turno.estado === "pendiente" || turno.estado === "confirmado") && (
                          <button
                            type="button"
                            onClick={() => handleCambiarEstado(turno.id, "presente")}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200"
                          >
                            Presente
                          </button>
                        )}

                        {turno.estado === "presente" && (
                          <button
                            type="button"
                            onClick={() => handleCambiarEstado(turno.id, "finalizado")}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
                          >
                            Finalizar
                          </button>
                        )}

                        {(turno.estado === "confirmado" || turno.estado === "pendiente") && (
                          <button
                            type="button"
                            onClick={() => handleCambiarEstado(turno.id, "ausente")}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-300"
                          >
                            Ausente
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => {
                            setTurnoSeleccionado(turno);
                            setMostrarModalReprogramar(true);
                          }}
                          className="px-2.5 py-1 text-xs font-medium rounded bg-white text-slate-700 hover:bg-slate-50 border border-slate-300"
                        >
                          Reprogramar
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setTurnoSeleccionado(turno);
                            setMostrarModalCancelar(true);
                          }}
                          className="px-2.5 py-1 text-xs font-medium rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                        >
                          Cancelar
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Modal Alta Turno */}
      {mostrarModalAlta && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6 border border-slate-200 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Agendar Nuevo Turno</h3>
            <form onSubmit={handleCrearTurno} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Paciente</label>
                <select
                  value={pacienteId}
                  onChange={(e) => setPacienteId(e.target.value)}
                  required
                  className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                >
                  <option value="">Seleccionar paciente...</option>
                  {pacientes.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre} (DNI {p.dni})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Prestación</label>
                <select
                  value={prestacionId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setPrestacionId(id);
                    const prestacion = prestaciones.find((p) => p.id === id);
                    if (prestacion && !overrideDuracion) {
                      setDuracionMin(prestacion.duracion_min);
                    }
                  }}
                  required
                  className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                >
                  <option value="">Seleccionar prestación...</option>
                  {prestaciones.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre} ({p.duracion_min} min - ${p.precio_particular})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Profesional</label>
                  <select
                    value={profesionalId}
                    onChange={(e) => setProfesionalId(e.target.value)}
                    required
                    disabled={esOdontologo}
                    className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    {profesionales.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nombre}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Sillón / Box</label>
                  <select
                    value={sillonId}
                    onChange={(e) => setSillonId(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    {sillones.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.nombre} ({s.sucursal})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Hora Inicio</label>
                  <input
                    type="time"
                    value={horaInicio}
                    onChange={(e) => setHoraInicio(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Duración (min)</label>
                  <input
                    type="number"
                    min="5"
                    step="5"
                    value={duracionMin}
                    onChange={(e) => setDuracionMin(Number(e.target.value))}
                    disabled={!overrideDuracion}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm bg-slate-50 disabled:text-slate-500"
                  />
                </div>
              </div>

              <div className="space-y-2 pt-2 border-t border-slate-200">
                <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={overrideDuracion}
                    onChange={(e) => setOverrideDuracion(e.target.checked)}
                    className="rounded text-emerald-600 focus:ring-emerald-500"
                  />
                  <span>Modificar duración estimada (requiere motivo)</span>
                </label>

                <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={esSobreturno}
                    onChange={(e) => setEsSobreturno(e.target.checked)}
                    className="rounded text-emerald-600 focus:ring-emerald-500"
                  />
                  <span>Agendar como sobreturno (requiere motivo)</span>
                </label>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Observaciones / Motivo {(overrideDuracion || esSobreturno) && "(Obligatorio)"}
                </label>
                <textarea
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  rows={2}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  placeholder="Detalles clínicos o justificación de sobreturno..."
                />
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setMostrarModalAlta(false)}
                  className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={altaTurno.isPending}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
                >
                  {altaTurno.isPending ? "Agendando..." : "Confirmar Turno"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Cancelar con Motivo */}
      {mostrarModalCancelar && turnoSeleccionado && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 border border-slate-200">
            <h3 className="text-lg font-bold text-slate-900 mb-2">Cancelar Turno</h3>
            <p className="text-sm text-slate-600 mb-4">
              Por auditoría clínica y de cancelaciones, ingresá el motivo de la cancelación.
            </p>
            {errorAccion && (
              <div
                role="alert"
                className="mb-3 p-2.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-md"
              >
                {errorAccion}
              </div>
            )}
            <form
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                if (!motivoCancelacion.trim()) {
                  setErrorAccion("Tenés que ingresar un motivo para cancelar el turno.");
                  return;
                }
                handleCambiarEstado(turnoSeleccionado.id, "cancelado", motivoCancelacion.trim());
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Motivo de cancelación (obligatorio)
                </label>
                <textarea
                  value={motivoCancelacion}
                  onChange={(e) => setMotivoCancelacion(e.target.value)}
                  required
                  rows={3}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  placeholder="Ej: Paciente solicitó reprogramación por viaje..."
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setMostrarModalCancelar(false)}
                  className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Volver
                </button>
                <button
                  type="submit"
                  disabled={cambiarEstado.isPending}
                  className="px-4 py-2 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-50"
                >
                  {cambiarEstado.isPending ? "Cancelando..." : "Confirmar Cancelación"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Reprogramar en 1-clic */}
      {mostrarModalReprogramar && turnoSeleccionado && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 border border-slate-200">
            <h3 className="text-lg font-bold text-slate-900 mb-2">Reprogramar Turno</h3>
            <p className="text-xs text-slate-500 mb-4">
              Turno actual: {formatearFechaCorta(turnoSeleccionado.inicio)} a las{" "}
              {formatearHora(turnoSeleccionado.inicio)}
            </p>
            <form onSubmit={handleReprogramar} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nueva Fecha</label>
                  <input
                    type="date"
                    value={nuevaFechaReprogramar}
                    onChange={(e) => setNuevaFechaReprogramar(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nueva Hora</label>
                  <input
                    type="time"
                    value={nuevaHoraReprogramar}
                    onChange={(e) => setNuevaHoraReprogramar(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Motivo (opcional)</label>
                <textarea
                  value={motivoReprogramar}
                  onChange={(e) => setMotivoReprogramar(e.target.value)}
                  rows={2}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  placeholder="Motivo de la reprogramación..."
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setMostrarModalReprogramar(false)}
                  className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Volver
                </button>
                <button
                  type="submit"
                  disabled={reprogramar.isPending}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
                >
                  {reprogramar.isPending ? "Reprogramando..." : "Confirmar Reprogramación"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Bloqueo Horario */}
      {mostrarModalBloqueo && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 border border-slate-200">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Bloquear Franja Horaria</h3>
            <form onSubmit={handleCrearBloqueo} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Desde</label>
                  <input
                    type="time"
                    value={bloqueoHoraDesde}
                    onChange={(e) => setBloqueoHoraDesde(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Hasta</label>
                  <input
                    type="time"
                    value={bloqueoHoraHasta}
                    onChange={(e) => setBloqueoHoraHasta(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Profesional (opcional)</label>
                <select
                  value={bloqueoProfId}
                  onChange={(e) => setBloqueoProfId(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                >
                  <option value="">Aplica a todos o seleccionar...</option>
                  {profesionales.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Sillón (opcional)</label>
                <select
                  value={bloqueoSillonId}
                  onChange={(e) => setBloqueoSillonId(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                >
                  <option value="">Aplica a todos o seleccionar...</option>
                  {sillones.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre} ({s.sucursal})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Motivo</label>
                <select
                  value={bloqueoMotivo}
                  onChange={(e) =>
                    setBloqueoMotivo(e.target.value as "feriado" | "vacaciones" | "mantenimiento" | "manual")
                  }
                  className="w-full border border-slate-300 rounded-md p-2 text-sm bg-white"
                >
                  <option value="manual">Manual / Administrativo</option>
                  <option value="feriado">Feriado</option>
                  <option value="vacaciones">Vacaciones</option>
                  <option value="mantenimiento">Mantenimiento</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Descripción</label>
                <input
                  type="text"
                  value={bloqueoDesc}
                  onChange={(e) => setBloqueoDesc(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  placeholder="Detalle del bloqueo..."
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setMostrarModalBloqueo(false)}
                  className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={altaBloqueo.isPending}
                  className="px-4 py-2 bg-slate-900 text-white rounded-md text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
                >
                  {altaBloqueo.isPending ? "Guardando..." : "Crear Bloqueo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
