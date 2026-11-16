import React, { useState, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useClinica, useHistorialPieza, useMutacionesClinica } from "./queries";
import { usePaciente } from "../pacientes/queries";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import {
  CUADRANTES_PERMANENTES,
  CUADRANTES_DECIDUOS,
  SUPERFICIES,
  EVENTOS_PIEZA,
  COLOR_EVENTO,
} from "./odontograma.constantes";
import { SuperficieDental, TipoEventoPieza, TipoAdjunto } from "../../shared/api-types";
import { formatearFechaHora, formatearMoneda } from "../../shared/formatters";
import { EstadoCargando, EstadoError } from "../../shared/ComponentesEstado";
import { ErrorApi } from "../../shared/api-client";

export function FichaClinicaPage() {
  const { id: pacienteId } = useParams<{ id: string }>();
  const usuario = getIdentidad();
  const roles = usuario?.roles || [];
  const puedeEditarClinica = permite(roles, "clinica", "actualizar");
  const puedeFirmarConsentimiento = permite(roles, "consentimientos", "actualizar");

  const [pestana, setPestana] = useState<"ficha" | "odontograma" | "evoluciones" | "presupuestos" | "consentimientos" | "adjuntos">("odontograma");

  const { data: paciente } = usePaciente(pacienteId || "");
  const {
    ficha,
    evoluciones,
    odontograma,
    adjuntos,
    consentimientos,
    presupuestos,
    cargando,
    error,
  } = useClinica(pacienteId || "");

  const mutaciones = useMutacionesClinica(pacienteId || "");

  // Anamnesis form
  const [antecedentes, setAntecedentes] = useState("");
  const [alergias, setAlergias] = useState("");
  const [medicacion, setMedicacion] = useState("");
  const [habitos, setHabitos] = useState("");
  const [notaEvolucionFicha, setNotaEvolucionFicha] = useState("");

  // Odontograma state
  const [denticion, setDenticion] = useState<"permanente" | "decidua">("permanente");
  const [piezaSeleccionada, setPiezaSeleccionada] = useState<number | null>(null);
  const [superficieSeleccionada, setSuperficieSeleccionada] = useState<SuperficieDental>("oclusal");
  const [eventoSeleccionado, setEventoSeleccionado] = useState<TipoEventoPieza>("caries");
  const [obsEvento, setObsEvento] = useState("");

  // Nueva evolución
  const [notaEvolucion, setNotaEvolucion] = useState("");
  const [correccionDeId, setCorreccionDeId] = useState<string | null>(null);

  // Nuevo consentimiento
  const [prestacionConsentimiento, setPrestacionConsentimiento] = useState("");
  const [textoConsentimiento, setTextoConsentimiento] = useState("Por la presente presto mi conformidad para la realización de la prestación informada...");
  const [firmanteNombre, setFirmanteNombre] = useState("");
  const [consentimientoAFirmarId, setConsentimientoAFirmarId] = useState<string | null>(null);
  const [motivoRevocacion, setMotivoRevocacion] = useState("");
  const [consentimientoARevocarId, setConsentimientoARevocarId] = useState<string | null>(null);

  // Nuevo presupuesto
  const [obraSocialPresupuesto] = useState("");
  const [prestacionPresupuestoId, setPrestacionPresupuestoId] = useState("");
  const [piezaPresupuesto, setPiezaPresupuesto] = useState<number | undefined>(undefined);
  const [cantidadPresupuesto, setCantidadPresupuesto] = useState(1);

  // Nuevo adjunto
  const [nombreAdjunto, setNombreAdjunto] = useState("");
  const [tipoAdjunto, setTipoAdjunto] = useState<TipoAdjunto>("radiografia");
  const [storageKey, setStorageKey] = useState("");

  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  React.useEffect(() => {
    if (ficha) {
      setAntecedentes(ficha.antecedentes || "");
      setAlergias(ficha.alergias || "");
      setMedicacion(ficha.medicacion || "");
      setHabitos(ficha.habitos || "");
    }
  }, [ficha]);

  const { data: historialPieza } = useHistorialPieza(pacienteId || "", piezaSeleccionada);

  const eventosPorPieza = useMemo(() => {
    const mapa = new Map<number, Record<string, string>>();
    if (odontograma?.piezas) {
      odontograma.piezas.forEach((p) => {
        mapa.set(p.pieza_fdi, p.superficies);
      });
    }
    return mapa;
  }, [odontograma]);

  function mostrarAlertaExito(msg: string) {
    setMensajeExito(msg);
    setTimeout(() => setMensajeExito(null), 3500);
  }

  // Handlers
  async function handleGuardarFicha(e: React.FormEvent) {
    e.preventDefault();
    setErrorAccion(null);
    try {
      await mutaciones.guardarFicha.mutateAsync({
        antecedentes,
        alergias,
        medicacion,
        habitos,
        nota_evolucion: notaEvolucionFicha.trim() || undefined,
      });
      setNotaEvolucionFicha("");
      mostrarAlertaExito("Ficha médica actualizada correctamente.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "No se pudo guardar la ficha.");
    }
  }

  async function handleAgregarEvolucion(e: React.FormEvent) {
    e.preventDefault();
    if (!notaEvolucion.trim()) return;
    setErrorAccion(null);
    try {
      await mutaciones.registrarEvolucion.mutateAsync({
        nota: notaEvolucion.trim(),
        es_correccion_de_id: correccionDeId || undefined,
      });
      setNotaEvolucion("");
      setCorreccionDeId(null);
      mostrarAlertaExito("Evolución clínica registrada.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al registrar evolución.");
    }
  }

  async function handleRegistrarEventoOdontograma(e: React.FormEvent) {
    e.preventDefault();
    if (!piezaSeleccionada) return;
    setErrorAccion(null);
    try {
      await mutaciones.registrarEventoPieza.mutateAsync({
        pieza_fdi: piezaSeleccionada,
        superficie: superficieSeleccionada,
        evento: eventoSeleccionado,
        observacion: obsEvento.trim() || undefined,
      });
      setObsEvento("");
      mostrarAlertaExito(`Evento registrado en pieza ${piezaSeleccionada}.`);
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al registrar evento.");
    }
  }

  async function handleCrearConsentimiento(e: React.FormEvent) {
    e.preventDefault();
    if (!pacienteId || !prestacionConsentimiento) return;
    setErrorAccion(null);
    try {
      await mutaciones.altaConsentimiento.mutateAsync({
        paciente_id: pacienteId,
        prestacion_id: prestacionConsentimiento,
        texto_version: "v1-2026",
        texto_contenido: textoConsentimiento.trim(),
      });
      setPrestacionConsentimiento("");
      mostrarAlertaExito("Consentimiento creado en estado borrador.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al crear consentimiento.");
    }
  }

  async function handleFirmarConsentimiento(e: React.FormEvent) {
    e.preventDefault();
    if (!consentimientoAFirmarId || !firmanteNombre.trim()) return;
    setErrorAccion(null);
    try {
      await mutaciones.registrarFirma.mutateAsync({
        id: consentimientoAFirmarId,
        input: {
          firmado_por: firmanteNombre.trim(),
          firma_datos: "data:image/png;base64,firma_simulada_ok",
          canal: "presencial",
        },
      });
      setConsentimientoAFirmarId(null);
      setFirmanteNombre("");
      mostrarAlertaExito("Consentimiento firmado y registrado.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al registrar firma.");
    }
  }

  async function handleRevocarConsentimiento(e: React.FormEvent) {
    e.preventDefault();
    if (!consentimientoARevocarId || !motivoRevocacion.trim()) return;
    setErrorAccion(null);
    try {
      await mutaciones.anularConsentimiento.mutateAsync({
        id: consentimientoARevocarId,
        motivo: motivoRevocacion.trim(),
      });
      setConsentimientoARevocarId(null);
      setMotivoRevocacion("");
      mostrarAlertaExito("Consentimiento revocado.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al revocar consentimiento.");
    }
  }

  async function handleCrearPresupuesto(e: React.FormEvent) {
    e.preventDefault();
    if (!pacienteId || !prestacionPresupuestoId) return;
    setErrorAccion(null);
    try {
      await mutaciones.altaPresupuesto.mutateAsync({
        paciente_id: pacienteId,
        obra_social: obraSocialPresupuesto.trim() || undefined,
        items: [
          {
            prestacion_id: prestacionPresupuestoId,
            pieza_fdi: piezaPresupuesto || undefined,
            cantidad: cantidadPresupuesto,
          },
        ],
      });
      setPrestacionPresupuestoId("");
      setPiezaPresupuesto(undefined);
      mostrarAlertaExito("Presupuesto generado con montos calculados por el servidor.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al generar presupuesto.");
    }
  }

  async function handleCrearAdjunto(e: React.FormEvent) {
    e.preventDefault();
    if (!pacienteId || !nombreAdjunto.trim() || !storageKey.trim()) return;
    setErrorAccion(null);
    try {
      await mutaciones.subirAdjunto.mutateAsync({
        tipo: tipoAdjunto,
        nombre_archivo: nombreAdjunto.trim(),
        mime_type: "application/pdf",
        tamano_bytes: 102400,
        storage_key: storageKey.trim(),
      });
      setNombreAdjunto("");
      setStorageKey("");
      mostrarAlertaExito("Metadatos del adjunto clínico registrados.");
    } catch (err) {
      setErrorAccion(err instanceof ErrorApi ? err.detalle : "Error al registrar adjunto.");
    }
  }

  if (cargando) return <EstadoCargando mensaje="Cargando historia clínica y odontograma..." />;
  if (error) return <EstadoError error={error} />;

  const cuadrantes = denticion === "permanente" ? CUADRANTES_PERMANENTES : CUADRANTES_DECIDUOS;

  return (
    <div className="space-y-6" data-testid="ficha-clinica-page">
      {/* Cabecera */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Link to="/app/pacientes" className="hover:underline">Pacientes</Link>
            <span>/</span>
            <Link to={`/app/pacientes/${pacienteId}`} className="hover:underline">{paciente?.nombre}</Link>
            <span>/</span>
            <span className="font-semibold text-slate-900">Historia Clínica</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mt-1">
            Historia Clínica · {paciente?.nombre}
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to={`/app/pacientes/${pacienteId}`}
            className="px-3 py-1.5 border border-slate-300 rounded text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Ver Contacto
          </Link>
        </div>
      </div>

      {mensajeExito && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-md">
          {mensajeExito}
        </div>
      )}

      {errorAccion && (
        <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
          {errorAccion}
        </div>
      )}

      {/* Navegación por pestañas */}
      <div className="border-b border-slate-200 bg-white px-4 rounded-t-lg shadow-xs">
        <nav className="flex space-x-6 overflow-x-auto">
          {[
            { id: "odontograma", label: "🦷 Odontograma FDI" },
            { id: "evoluciones", label: `📝 Evoluciones (${evoluciones.length})` },
            { id: "ficha", label: "📋 Anamnesis / Ficha" },
            { id: "presupuestos", label: `💰 Presupuestos (${presupuestos.length})` },
            { id: "consentimientos", label: `✍️ Consentimientos (${consentimientos.length})` },
            { id: "adjuntos", label: `📎 Adjuntos (${adjuntos.length})` },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setPestana(tab.id as any)}
              className={`py-4 px-1 border-b-2 font-medium text-sm whitespace-nowrap transition ${
                pestana === tab.id
                  ? "border-emerald-600 text-emerald-700 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* PESTAÑA: ODONTOGRAMA FDI */}
      {pestana === "odontograma" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-slate-200 pb-4">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Odontograma FDI Interactivo</h3>
              <p className="text-xs text-slate-500">
                Seleccioná una pieza para ver su historial clínico y registrar eventos por superficie.
              </p>
            </div>
            <div className="flex items-center rounded-md border border-slate-300 p-0.5 bg-slate-50">
              <button
                type="button"
                onClick={() => setDenticion("permanente")}
                className={`px-3 py-1 text-xs font-semibold rounded ${
                  denticion === "permanente" ? "bg-white text-emerald-800 shadow-xs" : "text-slate-600"
                }`}
              >
                Permanente (11–48)
              </button>
              <button
                type="button"
                onClick={() => setDenticion("decidua")}
                className={`px-3 py-1 text-xs font-semibold rounded ${
                  denticion === "decidua" ? "bg-white text-emerald-800 shadow-xs" : "text-slate-600"
                }`}
              >
                Decidua (51–85)
              </button>
            </div>
          </div>

          {/* Grilla FDI por cuadrantes */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-50 p-4 rounded-xl border border-slate-200">
            {/* Superior Derecho */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-500 block text-right">
                Superior Derecho (Q{denticion === "permanente" ? "1" : "5"})
              </span>
              <div className="flex justify-end gap-1.5 flex-wrap">
                {cuadrantes.superiorDerecho.map((pieza) => {
                  const superficies = eventosPorPieza.get(pieza) || {};
                  const tieneEvento = Object.keys(superficies).length > 0;
                  const seleccionada = piezaSeleccionada === pieza;

                  return (
                    <button
                      key={pieza}
                      type="button"
                      onClick={() => setPiezaSeleccionada(pieza)}
                      className={`w-11 h-12 rounded-lg font-bold text-sm border flex flex-col items-center justify-between p-1 transition ${
                        seleccionada
                          ? "border-emerald-600 ring-2 ring-emerald-500 bg-emerald-50 text-emerald-900"
                          : tieneEvento
                          ? "border-blue-400 bg-blue-50/80 text-blue-900"
                          : "border-slate-300 bg-white text-slate-700 hover:border-slate-400"
                      }`}
                    >
                      <span className="text-[10px] text-slate-400">{pieza}</span>
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300" style={{
                        backgroundColor: tieneEvento ? COLOR_EVENTO[superficies[Object.keys(superficies)[0]] as TipoEventoPieza] || "#3b82f6" : "#cbd5e1"
                      }} />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Superior Izquierdo */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-500 block">
                Superior Izquierdo (Q{denticion === "permanente" ? "2" : "6"})
              </span>
              <div className="flex justify-start gap-1.5 flex-wrap">
                {cuadrantes.superiorIzquierdo.map((pieza) => {
                  const superficies = eventosPorPieza.get(pieza) || {};
                  const tieneEvento = Object.keys(superficies).length > 0;
                  const seleccionada = piezaSeleccionada === pieza;

                  return (
                    <button
                      key={pieza}
                      type="button"
                      onClick={() => setPiezaSeleccionada(pieza)}
                      className={`w-11 h-12 rounded-lg font-bold text-sm border flex flex-col items-center justify-between p-1 transition ${
                        seleccionada
                          ? "border-emerald-600 ring-2 ring-emerald-500 bg-emerald-50 text-emerald-900"
                          : tieneEvento
                          ? "border-blue-400 bg-blue-50/80 text-blue-900"
                          : "border-slate-300 bg-white text-slate-700 hover:border-slate-400"
                      }`}
                    >
                      <span className="text-[10px] text-slate-400">{pieza}</span>
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300" style={{
                        backgroundColor: tieneEvento ? COLOR_EVENTO[superficies[Object.keys(superficies)[0]] as TipoEventoPieza] || "#3b82f6" : "#cbd5e1"
                      }} />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Inferior Derecho */}
            <div className="space-y-2 pt-4 border-t border-slate-200">
              <span className="text-xs font-bold text-slate-500 block text-right">
                Inferior Derecho (Q{denticion === "permanente" ? "4" : "8"})
              </span>
              <div className="flex justify-end gap-1.5 flex-wrap">
                {cuadrantes.inferiorDerecho.map((pieza) => {
                  const superficies = eventosPorPieza.get(pieza) || {};
                  const tieneEvento = Object.keys(superficies).length > 0;
                  const seleccionada = piezaSeleccionada === pieza;

                  return (
                    <button
                      key={pieza}
                      type="button"
                      onClick={() => setPiezaSeleccionada(pieza)}
                      className={`w-11 h-12 rounded-lg font-bold text-sm border flex flex-col items-center justify-between p-1 transition ${
                        seleccionada
                          ? "border-emerald-600 ring-2 ring-emerald-500 bg-emerald-50 text-emerald-900"
                          : tieneEvento
                          ? "border-blue-400 bg-blue-50/80 text-blue-900"
                          : "border-slate-300 bg-white text-slate-700 hover:border-slate-400"
                      }`}
                    >
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300" style={{
                        backgroundColor: tieneEvento ? COLOR_EVENTO[superficies[Object.keys(superficies)[0]] as TipoEventoPieza] || "#3b82f6" : "#cbd5e1"
                      }} />
                      <span className="text-[10px] text-slate-400">{pieza}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Inferior Izquierdo */}
            <div className="space-y-2 pt-4 border-t border-slate-200">
              <span className="text-xs font-bold text-slate-500 block">
                Inferior Izquierdo (Q{denticion === "permanente" ? "3" : "7"})
              </span>
              <div className="flex justify-start gap-1.5 flex-wrap">
                {cuadrantes.inferiorIzquierdo.map((pieza) => {
                  const superficies = eventosPorPieza.get(pieza) || {};
                  const tieneEvento = Object.keys(superficies).length > 0;
                  const seleccionada = piezaSeleccionada === pieza;

                  return (
                    <button
                      key={pieza}
                      type="button"
                      onClick={() => setPiezaSeleccionada(pieza)}
                      className={`w-11 h-12 rounded-lg font-bold text-sm border flex flex-col items-center justify-between p-1 transition ${
                        seleccionada
                          ? "border-emerald-600 ring-2 ring-emerald-500 bg-emerald-50 text-emerald-900"
                          : tieneEvento
                          ? "border-blue-400 bg-blue-50/80 text-blue-900"
                          : "border-slate-300 bg-white text-slate-700 hover:border-slate-400"
                      }`}
                    >
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300" style={{
                        backgroundColor: tieneEvento ? COLOR_EVENTO[superficies[Object.keys(superficies)[0]] as TipoEventoPieza] || "#3b82f6" : "#cbd5e1"
                      }} />
                      <span className="text-[10px] text-slate-400">{pieza}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Panel de Pieza Seleccionada */}
          {piezaSeleccionada ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4 border-t border-slate-200">
              {/* Formulario de registro de evento */}
              {puedeEditarClinica && (
                <div className="p-4 bg-white border border-slate-200 rounded-lg shadow-xs space-y-4">
                  <h4 className="text-sm font-bold text-slate-900">
                    Registrar Evento en Pieza {piezaSeleccionada}
                  </h4>
                  <form onSubmit={handleRegistrarEventoOdontograma} className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-slate-700 mb-1">Superficie</label>
                        <select
                          value={superficieSeleccionada}
                          onChange={(e) => setSuperficieSeleccionada(e.target.value as SuperficieDental)}
                          className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                        >
                          {SUPERFICIES.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-slate-700 mb-1">Evento Clínico</label>
                        <select
                          value={eventoSeleccionado}
                          onChange={(e) => setEventoSeleccionado(e.target.value as TipoEventoPieza)}
                          className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white capitalize"
                        >
                          {EVENTOS_PIEZA.map((ev) => (
                            <option key={ev} value={ev}>{ev}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Observación</label>
                      <input
                        type="text"
                        value={obsEvento}
                        onChange={(e) => setObsEvento(e.target.value)}
                        placeholder="Detalle o diagnóstico..."
                        className="w-full border border-slate-300 rounded p-1.5 text-sm"
                      />
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="submit"
                        disabled={mutaciones.registrarEventoPieza.isPending}
                        className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
                      >
                        {mutaciones.registrarEventoPieza.isPending ? "Guardando..." : "Guardar Evento"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Historial cronológico de la pieza */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-3">
                <h4 className="text-sm font-bold text-slate-800">
                  Historial de Pieza {piezaSeleccionada}
                </h4>
                {!historialPieza || historialPieza.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">No hay intervenciones previas en esta pieza.</p>
                ) : (
                  <div className="space-y-2 max-h-56 overflow-y-auto">
                    {historialPieza.map((ev) => (
                      <div key={ev.id} className="p-2 bg-white rounded border border-slate-200 text-xs">
                        <div className="flex justify-between font-semibold">
                          <span className="capitalize">{ev.evento} ({ev.superficie})</span>
                          <span className="text-slate-400">{formatearFechaHora(ev.created_at)}</span>
                        </div>
                        {ev.observacion && <p className="text-slate-600 mt-1">{ev.observacion}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="text-center text-sm text-slate-500 italic py-2">
              Hacé clic en cualquier diente para ver su ficha y registrar procedimientos.
            </p>
          )}
        </div>
      )}

      {/* PESTAÑA: EVOLUCIONES */}
      {pestana === "evoluciones" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-200 pb-3">
            <h3 className="text-base font-bold text-slate-900">Evoluciones Clínicas (Inmutables)</h3>
            <p className="text-xs text-slate-500">
              Las evoluciones son registros append-only. Si cometiste un error podés ingresar una enmienda aditiva.
            </p>
          </div>

          {puedeEditarClinica && (
            <form onSubmit={handleAgregarEvolucion} className="space-y-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
              <label className="block text-sm font-semibold text-slate-800">
                {correccionDeId ? "Enmienda / Corrección aditiva" : "Nueva Nota de Evolución"}
              </label>
              {correccionDeId && (
                <div className="text-xs text-amber-700 bg-amber-50 p-2 rounded flex justify-between">
                  <span>Referencia a evolución previa #{correccionDeId.slice(0, 8)}</span>
                  <button type="button" onClick={() => setCorreccionDeId(null)} className="underline">Cancelar enmienda</button>
                </div>
              )}
              <textarea
                value={notaEvolucion}
                onChange={(e) => setNotaEvolucion(e.target.value)}
                required
                rows={3}
                placeholder="Describí los hallazgos, tratamiento efectuado o indicaciones..."
                className="w-full border border-slate-300 rounded p-2 text-sm bg-white"
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={mutaciones.registrarEvolucion.isPending}
                  className="px-4 py-2 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
                >
                  {mutaciones.registrarEvolucion.isPending ? "Guardando..." : "Registrar Evolución"}
                </button>
              </div>
            </form>
          )}

          <div className="space-y-3">
            {evoluciones.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No hay notas de evolución registradas aún.</p>
            ) : (
              evoluciones.map((evo) => (
                <div key={evo.id} className="p-4 bg-white border border-slate-200 rounded-lg space-y-2">
                  <div className="flex justify-between items-start text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">
                      Profesional ID: {evo.profesional_id}
                    </span>
                    <span>{formatearFechaHora(evo.created_at)}</span>
                  </div>
                  {evo.es_correccion_de_id && (
                    <span className="inline-block text-[10px] bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium">
                      Enmienda a evolución #{evo.es_correccion_de_id.slice(0, 8)}
                    </span>
                  )}
                  <p className="text-sm text-slate-800 whitespace-pre-wrap">{evo.nota}</p>
                  {puedeEditarClinica && !evo.es_correccion_de_id && (
                    <div className="pt-2 border-t border-slate-100 flex justify-end">
                      <button
                        type="button"
                        onClick={() => {
                          setCorreccionDeId(evo.id);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                        className="text-xs text-emerald-700 hover:underline font-medium"
                      >
                        Agregar enmienda a esta nota
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* PESTAÑA: ANAMNESIS / FICHA */}
      {pestana === "ficha" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-200 pb-3">
            <h3 className="text-base font-bold text-slate-900">Anamnesis y Antecedentes Médicos</h3>
          </div>

          <form onSubmit={handleGuardarFicha} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Antecedentes Médicos</label>
                <textarea
                  value={antecedentes}
                  onChange={(e) => setAntecedentes(e.target.value)}
                  disabled={!puedeEditarClinica}
                  rows={3}
                  className="w-full border border-slate-300 rounded p-2 text-sm disabled:bg-slate-50"
                  placeholder="Enfermedades crónicas, intervenciones previas..."
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Alergias</label>
                <textarea
                  value={alergias}
                  onChange={(e) => setAlergias(e.target.value)}
                  disabled={!puedeEditarClinica}
                  rows={3}
                  className="w-full border border-slate-300 rounded p-2 text-sm disabled:bg-slate-50"
                  placeholder="Medicamentos, látex, anestésicos..."
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Medicación Actual</label>
                <textarea
                  value={medicacion}
                  onChange={(e) => setMedicacion(e.target.value)}
                  disabled={!puedeEditarClinica}
                  rows={3}
                  className="w-full border border-slate-300 rounded p-2 text-sm disabled:bg-slate-50"
                  placeholder="Anticoagulantes, antibióticos..."
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Hábitos</label>
                <textarea
                  value={habitos}
                  onChange={(e) => setHabitos(e.target.value)}
                  disabled={!puedeEditarClinica}
                  rows={3}
                  className="w-full border border-slate-300 rounded p-2 text-sm disabled:bg-slate-50"
                  placeholder="Tabaquismo, bruxismo..."
                />
              </div>
            </div>

            {puedeEditarClinica && (
              <div className="flex justify-end pt-3">
                <button
                  type="submit"
                  disabled={mutaciones.guardarFicha.isPending}
                  className="px-4 py-2 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
                >
                  {mutaciones.guardarFicha.isPending ? "Guardando..." : "Guardar Ficha"}
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* PESTAÑA: PRESUPUESTOS */}
      {pestana === "presupuestos" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-200 pb-3 flex justify-between items-center">
            <div>
              <h3 className="text-base font-bold text-slate-900">Planes de Tratamiento y Presupuestos</h3>
              <p className="text-xs text-slate-500">
                Los montos y coberturas son calculados en servidor (R8: nunca calculados en cliente).
              </p>
            </div>
          </div>

          {puedeEditarClinica && (
            <form onSubmit={handleCrearPresupuesto} className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
              <h4 className="text-sm font-semibold text-slate-800">Generar Presupuesto</h4>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-700 mb-1">ID Prestación</label>
                  <input
                    type="text"
                    required
                    value={prestacionPresupuestoId}
                    onChange={(e) => setPrestacionPresupuestoId(e.target.value)}
                    placeholder="UUID prestación..."
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Pieza FDI (opcional)</label>
                  <input
                    type="number"
                    value={piezaPresupuesto || ""}
                    onChange={(e) => setPiezaPresupuesto(e.target.value ? Number(e.target.value) : undefined)}
                    placeholder="Ej: 16"
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Cantidad</label>
                  <input
                    type="number"
                    min="1"
                    max="32"
                    value={cantidadPresupuesto}
                    onChange={(e) => setCantidadPresupuesto(Number(e.target.value))}
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={mutaciones.altaPresupuesto.isPending}
                  className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
                >
                  {mutaciones.altaPresupuesto.isPending ? "Generando..." : "Crear Presupuesto"}
                </button>
              </div>
            </form>
          )}

          <div className="space-y-4">
            {presupuestos.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No hay presupuestos para este paciente.</p>
            ) : (
              presupuestos.map((pres) => (
                <div key={pres.id} className="p-4 bg-white border border-slate-200 rounded-lg space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-slate-900 text-sm">
                      Presupuesto #{pres.id.slice(0, 8)} · Estado: <span className="capitalize text-emerald-700">{pres.estado}</span>
                    </span>
                    <span className="text-xs text-slate-400">{formatearFechaHora(pres.created_at)}</span>
                  </div>

                  {/* Totales calculados por servidor */}
                  <div className="grid grid-cols-3 gap-2 bg-slate-50 p-2.5 rounded text-xs">
                    <div>Total Particular: <strong className="block text-sm">{formatearMoneda(pres.total)}</strong></div>
                    <div>Cobertura OS: <strong className="block text-sm">{formatearMoneda(pres.total_cobertura_os)}</strong></div>
                    <div>A Cargo Paciente: <strong className="block text-sm text-emerald-800">{formatearMoneda(pres.total_a_cargo)}</strong></div>
                  </div>

                  {/* Transiciones de estado */}
                  <div className="flex gap-2 justify-end pt-2 border-t border-slate-100">
                    {pres.estado === "borrador" && (
                      <button
                        type="button"
                        onClick={() => mutaciones.cambiarEstadoPresupuesto.mutate({ id: pres.id, accion: "presentar" })}
                        className="px-2.5 py-1 text-xs font-medium rounded bg-blue-50 text-blue-700 border border-blue-200"
                      >
                        Presentar
                      </button>
                    )}
                    {pres.estado === "presentado" && (
                      <>
                        <button
                          type="button"
                          onClick={() => mutaciones.cambiarEstadoPresupuesto.mutate({ id: pres.id, accion: "aceptar" })}
                          className="px-2.5 py-1 text-xs font-medium rounded bg-emerald-50 text-emerald-700 border border-emerald-200"
                        >
                          Aceptar
                        </button>
                        <button
                          type="button"
                          onClick={() => mutaciones.cambiarEstadoPresupuesto.mutate({ id: pres.id, accion: "rechazar" })}
                          className="px-2.5 py-1 text-xs font-medium rounded bg-red-50 text-red-700 border border-red-200"
                        >
                          Rechazar
                        </button>
                      </>
                    )}
                    {pres.estado === "aceptado" && (
                      <button
                        type="button"
                        onClick={() => mutaciones.cambiarEstadoPresupuesto.mutate({ id: pres.id, accion: "finalizar" })}
                        className="px-2.5 py-1 text-xs font-medium rounded bg-purple-50 text-purple-700 border border-purple-200"
                      >
                        Finalizar Tratamiento
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* PESTAÑA: CONSENTIMIENTOS */}
      {pestana === "consentimientos" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-200 pb-3 flex justify-between items-center">
            <div>
              <h3 className="text-base font-bold text-slate-900">Consentimientos Informados</h3>
              <p className="text-xs text-slate-500">
                Gestión de firma y revocación auditable (dueño, odontólogo y recepción).
              </p>
            </div>
          </div>

          {/* Form alta consentimiento */}
          <form onSubmit={handleCrearConsentimiento} className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
            <h4 className="text-sm font-semibold text-slate-800">Nuevo Consentimiento</h4>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">ID Prestación</label>
              <input
                type="text"
                required
                value={prestacionConsentimiento}
                onChange={(e) => setPrestacionConsentimiento(e.target.value)}
                placeholder="UUID de la prestación..."
                className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Texto del Consentimiento (v1-2026)</label>
              <textarea
                value={textoConsentimiento}
                onChange={(e) => setTextoConsentimiento(e.target.value)}
                required
                rows={2}
                className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={mutaciones.altaConsentimiento.isPending}
                className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
              >
                {mutaciones.altaConsentimiento.isPending ? "Creando..." : "Crear Borrador"}
              </button>
            </div>
          </form>

          {/* Listado */}
          <div className="space-y-3">
            {consentimientos.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No hay consentimientos para este paciente.</p>
            ) : (
              consentimientos.map((c) => (
                <div key={c.id} className="p-4 bg-white border border-slate-200 rounded-lg space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="font-bold text-sm text-slate-900">Versión: {c.texto_version}</span>
                      <div className="mt-1 flex items-center gap-2">
                        {c.revocado ? (
                          <span className="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded font-semibold">
                            Revocado ({c.revocado_motivo})
                          </span>
                        ) : c.firmado_at ? (
                          <span className="text-xs px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-semibold">
                            Firmado por {c.firmado_por} ({formatearFechaHora(c.firmado_at)})
                          </span>
                        ) : (
                          <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-800 rounded font-semibold">
                            Pendiente de firma
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {!c.firmado_at && !c.revocado && puedeFirmarConsentimiento && (
                        <button
                          type="button"
                          onClick={() => setConsentimientoAFirmarId(c.id)}
                          className="px-2.5 py-1 bg-emerald-600 text-white text-xs font-medium rounded hover:bg-emerald-700"
                        >
                          Firmar en el acto
                        </button>
                      )}

                      {!c.revocado && (
                        <button
                          type="button"
                          onClick={() => setConsentimientoARevocarId(c.id)}
                          className="px-2.5 py-1 border border-red-200 text-red-600 text-xs font-medium rounded hover:bg-red-50"
                        >
                          Revocar
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-slate-600">{c.texto_contenido}</p>
                </div>
              ))
            )}
          </div>

          {/* Modal Firmar */}
          {consentimientoAFirmarId && (
            <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
              <div className="bg-white rounded-lg shadow-xl max-w-sm w-full p-5 border border-slate-200">
                <h4 className="font-bold text-base mb-2">Firma Presencial</h4>
                <form onSubmit={handleFirmarConsentimiento} className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Nombre y Apellido del firmante</label>
                    <input
                      type="text"
                      required
                      value={firmanteNombre}
                      onChange={(e) => setFirmanteNombre(e.target.value)}
                      placeholder="Nombre del paciente o apoderado..."
                      className="w-full border border-slate-300 rounded p-1.5 text-sm"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setConsentimientoAFirmarId(null)} className="px-3 py-1.5 border rounded text-xs">Cancelar</button>
                    <button type="submit" className="px-3 py-1.5 bg-emerald-600 text-white rounded text-xs font-medium">Registrar Firma</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Modal Revocar */}
          {consentimientoARevocarId && (
            <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
              <div className="bg-white rounded-lg shadow-xl max-w-sm w-full p-5 border border-slate-200">
                <h4 className="font-bold text-base mb-2">Revocar Consentimiento</h4>
                <form onSubmit={handleRevocarConsentimiento} className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Motivo de revocación (obligatorio)</label>
                    <textarea
                      required
                      value={motivoRevocacion}
                      onChange={(e) => setMotivoRevocacion(e.target.value)}
                      rows={2}
                      className="w-full border border-slate-300 rounded p-1.5 text-sm"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setConsentimientoARevocarId(null)} className="px-3 py-1.5 border rounded text-xs">Volver</button>
                    <button type="submit" className="px-3 py-1.5 bg-red-600 text-white rounded text-xs font-medium">Confirmar Revocación</button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* PESTAÑA: ADJUNTOS */}
      {pestana === "adjuntos" && (
        <div className="bg-white rounded-b-lg shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-200 pb-3">
            <h3 className="text-base font-bold text-slate-900">Estudios y Adjuntos Clínicos</h3>
            <p className="text-xs text-slate-500">
              Registro de metadatos de radiografías, tomografías y estudios clínicos.
            </p>
          </div>

          {puedeEditarClinica && (
            <form onSubmit={handleCrearAdjunto} className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
              <h4 className="text-sm font-semibold text-slate-800">Registrar Metadatos de Adjunto</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Nombre de archivo</label>
                  <input
                    type="text"
                    required
                    value={nombreAdjunto}
                    onChange={(e) => setNombreAdjunto(e.target.value)}
                    placeholder="Ej: Panorámica_2026.png"
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Tipo de Estudio</label>
                  <select
                    value={tipoAdjunto}
                    onChange={(e) => setTipoAdjunto(e.target.value as TipoAdjunto)}
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white capitalize"
                  >
                    <option value="radiografia">Radiografía</option>
                    <option value="foto">Foto Clínica</option>
                    <option value="estudio_pdf">Estudio PDF</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Clave de almacenamiento (storage_key)</label>
                  <input
                    type="text"
                    required
                    value={storageKey}
                    onChange={(e) => setStorageKey(e.target.value)}
                    placeholder="storage/rx/123.png"
                    className="w-full border border-slate-300 rounded p-1.5 text-sm bg-white"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={mutaciones.subirAdjunto.isPending}
                  className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700"
                >
                  {mutaciones.subirAdjunto.isPending ? "Guardando..." : "Guardar Adjunto"}
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {adjuntos.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No hay adjuntos registrados para este paciente.</p>
            ) : (
              adjuntos.map((adj) => (
                <div key={adj.id} className="p-3 bg-white border border-slate-200 rounded flex justify-between items-center text-xs">
                  <div>
                    <span className="font-bold text-slate-900">{adj.nombre_archivo}</span>
                    <span className="text-slate-500 ml-2 capitalize">({adj.tipo})</span>
                    <div className="text-slate-400 mt-0.5">Clave: {adj.storage_key}</div>
                  </div>
                  <span className="text-slate-400">{formatearFechaHora(adj.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
