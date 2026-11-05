import React, { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { EstadoTurno, SlotDisponible } from "../../shared/api-types";
import {
  cancelarMiTurno,
  confirmarMiTurno,
  obtenerDisponibilidadMiTurno,
  obtenerMiTurno,
  reprogramarMiTurno,
} from "../../shared/reserva-api";
import {
  formatearFechaLarga,
  formatearHora,
  formatearMoneda,
  formatearRangoHorario,
} from "../../shared/formatters";

/** Fecha local en YYYY-MM-DD (evita el corrimiento de `toISOString` en UTC). */
function fechaLocalIso(diasAdelante: number): string {
  const d = new Date();
  d.setDate(d.getDate() + diasAdelante);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

const ESTADOS_TERMINALES: ReadonlySet<EstadoTurno> = new Set<EstadoTurno>([
  "cancelado",
  "ausente",
  "finalizado",
  "reprogramado",
]);

function BadgeEstado({ estado }: { estado: EstadoTurno }): JSX.Element {
  const estilos: Record<EstadoTurno, { clase: string; texto: string }> = {
    pendiente: { clase: "bg-blue-100 text-blue-800", texto: "Pendiente de confirmación" },
    confirmado: { clase: "bg-green-100 text-green-800", texto: "Confirmado" },
    presente: { clase: "bg-amber-100 text-amber-800", texto: "Estás en el consultorio" },
    finalizado: { clase: "bg-gray-100 text-gray-800", texto: "Finalizado" },
    cancelado: { clase: "bg-red-100 text-red-800", texto: "Cancelado" },
    ausente: { clase: "bg-red-100 text-red-800", texto: "Ausente" },
    reprogramado: { clase: "bg-purple-100 text-purple-800", texto: "Reprogramado" },
  };
  const estilo = estilos[estado];
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-bold ${estilo.clase}`}>
      {estilo.texto}
    </span>
  );
}

export const MiTurnoPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const mensajeNavegacion = (location.state as { mensaje?: string } | null)?.mensaje ?? null;

  const [mostrarCancelar, setMostrarCancelar] = useState(false);
  const [motivoCancelacion, setMotivoCancelacion] = useState("");
  const [mostrarReprogramar, setMostrarReprogramar] = useState(false);
  const [fechaReprogramar, setFechaReprogramar] = useState(() => fechaLocalIso(1));
  const [slotNuevo, setSlotNuevo] = useState<SlotDisponible | null>(null);
  const [mensajeExito, setMensajeExito] = useState<string | null>(mensajeNavegacion);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const {
    data: turno,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["mi-turno", token],
    queryFn: ({ signal }) => obtenerMiTurno(token ?? "", signal),
    enabled: Boolean(token),
  });

  const mutationConfirmar = useMutation({
    mutationFn: () => confirmarMiTurno(token ?? ""),
    onSuccess: () => {
      setErrorAccion(null);
      setMensajeExito("¡Tu turno fue confirmado con éxito! Te esperamos.");
      void refetch();
    },
    onError: (err: Error) => setErrorAccion(err.message),
  });

  const mutationCancelar = useMutation({
    mutationFn: (motivo?: string) => cancelarMiTurno(token ?? "", { motivo }),
    onSuccess: () => {
      setErrorAccion(null);
      setMensajeExito("Tu turno fue cancelado correctamente.");
      setMostrarCancelar(false);
      void refetch();
    },
    onError: (err: Error) => setErrorAccion(err.message),
  });

  const {
    data: slotsReprogramar,
    isFetching: buscandoSlots,
    error: errorSlots,
  } = useQuery({
    queryKey: ["mi-turno-disponibilidad", token, fechaReprogramar],
    queryFn: ({ signal }) =>
      obtenerDisponibilidadMiTurno(token ?? "", fechaReprogramar, signal),
    enabled: Boolean(token) && mostrarReprogramar,
  });

  const mutationReprogramar = useMutation({
    mutationFn: (slot: SlotDisponible) =>
      reprogramarMiTurno(token ?? "", {
        nuevo_inicio: slot.inicio,
        motivo: "Reprogramación desde el portal del paciente",
      }),
    onSuccess: (nuevo) => {
      setErrorAccion(null);
      if (nuevo.token_gestion) {
        navigate(`/mis-turnos/${nuevo.token_gestion}`, {
          replace: true,
          state: { mensaje: "¡Listo! Tu turno quedó reprogramado para el nuevo horario." },
        });
      } else {
        setMensajeExito("¡Listo! Tu turno quedó reprogramado.");
        void refetch();
      }
    },
    onError: (err: Error) => setErrorAccion(err.message),
  });

  if (!token) {
    return (
      <div className="max-w-md mx-auto p-6 text-center text-gray-700">
        <h1 className="text-xl font-bold">Enlace no válido</h1>
        <p className="text-sm text-gray-500 mt-2">
          El enlace de consulta de turno no es correcto o está incompleto.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-gray-500">
        <div className="w-10 h-10 border-4 border-teal-700 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Buscando tu turno...</p>
      </div>
    );
  }

  if (error || !turno) {
    return (
      <div className="max-w-md mx-auto my-12 p-8 bg-white rounded-2xl border border-gray-200 shadow-sm text-center">
        <span className="text-4xl mb-3 block">🔍</span>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Turno no encontrado</h1>
        <p className="text-sm text-gray-600 mb-6 leading-relaxed">
          No encontramos ninguna cita asociada a este enlace o ya expiró.
        </p>
        <Link
          to="/"
          className="inline-block py-2.5 px-5 bg-teal-800 text-white rounded-lg text-sm font-semibold hover:bg-teal-900"
        >
          Ir al inicio
        </Link>
      </div>
    );
  }

  const esTerminal = ESTADOS_TERMINALES.has(turno.estado);

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-lg mx-auto space-y-6">
        <header className="text-center">
          <h1 className="text-2xl font-black text-gray-900">Gestión de tu Cita</h1>
          <p className="text-xs text-gray-500 mt-1">Consultá o administrá tu turno odontológico</p>
        </header>

        {mensajeExito && (
          <div
            role="status"
            className="p-4 bg-teal-50 border border-teal-200 text-teal-900 text-sm rounded-xl text-center font-medium"
          >
            {mensajeExito}
          </div>
        )}

        {errorAccion && (
          <div
            role="alert"
            className="p-4 bg-red-50 border border-red-200 text-red-800 text-sm rounded-xl text-center font-medium"
          >
            {errorAccion}
          </div>
        )}

        <div className="bg-white rounded-2xl border border-gray-200 p-6 sm:p-8 shadow-sm space-y-6">
          <div className="flex justify-between items-center pb-4 border-b border-gray-100">
            <span className="text-xs font-semibold text-gray-500 uppercase">Estado actual</span>
            <BadgeEstado estado={turno.estado} />
          </div>

          <div className="space-y-4">
            <div>
              <span className="text-xs text-gray-500 block uppercase font-medium">Tratamiento</span>
              <p className="text-lg font-bold text-gray-900 mt-0.5">{turno.prestacion_nombre}</p>
            </div>

            <div>
              <span className="text-xs text-gray-500 block uppercase font-medium">Fecha y Horario</span>
              <p className="text-base font-semibold text-gray-800 mt-0.5 capitalize">
                {formatearFechaLarga(turno.inicio)}
              </p>
              <p className="text-sm font-bold text-teal-800">
                {formatearRangoHorario(turno.inicio, turno.fin)}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <span className="text-xs text-gray-500 block uppercase font-medium">Profesional</span>
                <p className="text-sm font-medium text-gray-800">{turno.profesional_nombre}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500 block uppercase font-medium">Sillón / Box</span>
                <p className="text-sm font-medium text-gray-800">{turno.sillon_nombre}</p>
              </div>
            </div>

            {turno.requiere_sena && (
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-100 flex justify-between items-center text-sm">
                <div>
                  <span className="font-semibold text-gray-800 block">Seña de la cita</span>
                  <span className="text-xs text-gray-500">
                    Monto: {formatearMoneda(turno.monto_sena)}
                  </span>
                </div>
                <span
                  className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                    turno.sena_cobrada
                      ? "bg-green-100 text-green-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {turno.sena_cobrada ? "Seña abonada" : "Seña pendiente"}
                </span>
              </div>
            )}
          </div>

          {!esTerminal && (
            <div className="pt-4 border-t border-gray-100 space-y-3">
              {turno.estado === "pendiente" && (
                <button
                  type="button"
                  onClick={() => mutationConfirmar.mutate()}
                  disabled={mutationConfirmar.isPending}
                  className="w-full py-3 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-400 text-white font-bold rounded-xl text-sm transition-all shadow-sm"
                >
                  {mutationConfirmar.isPending ? "Confirmando..." : "Confirmar mi asistencia"}
                </button>
              )}

              {turno.requiere_sena && !turno.sena_cobrada && (
                <Link
                  to={`/pagar/${token}`}
                  className="block w-full py-3 bg-sky-600 hover:bg-sky-700 text-white font-bold rounded-xl text-sm text-center transition-all shadow-sm"
                >
                  Pagar seña pendiente con Mercado Pago
                </Link>
              )}

              {!mostrarReprogramar ? (
                <button
                  type="button"
                  onClick={() => {
                    setMostrarReprogramar(true);
                    setErrorAccion(null);
                  }}
                  className="w-full py-2.5 text-teal-800 hover:text-teal-950 text-xs font-semibold text-center"
                >
                  Quiero cambiar el día u horario
                </button>
              ) : (
                <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-slate-900">Elegí el nuevo horario</p>
                    <button
                      type="button"
                      onClick={() => {
                        setMostrarReprogramar(false);
                        setSlotNuevo(null);
                      }}
                      className="text-xs text-gray-500 hover:text-gray-800 font-medium"
                    >
                      Cancelar
                    </button>
                  </div>

                  <label className="block text-xs font-medium text-gray-600">
                    Día
                    <input
                      type="date"
                      min={fechaLocalIso(1)}
                      value={fechaReprogramar}
                      onChange={(e) => {
                        setFechaReprogramar(e.target.value);
                        setSlotNuevo(null);
                      }}
                      className="mt-1 w-full p-2.5 text-xs rounded-lg border border-gray-300 bg-white"
                    />
                  </label>

                  {buscandoSlots ? (
                    <p className="text-xs text-gray-500 animate-pulse">Buscando horarios...</p>
                  ) : errorSlots ? (
                    <p className="text-xs text-red-600">
                      No pudimos traer horarios. Probá con otro día.
                    </p>
                  ) : (slotsReprogramar ?? []).length === 0 ? (
                    <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2.5">
                      No hay horarios libres ese día. Probá con otra fecha.
                    </p>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {(slotsReprogramar ?? []).map((slot) => {
                        const activo = slotNuevo?.inicio === slot.inicio;
                        return (
                          <button
                            key={`${slot.inicio}-${slot.sillon_id}`}
                            type="button"
                            aria-pressed={activo}
                            onClick={() => setSlotNuevo(slot)}
                            className={`py-2 rounded-lg text-xs font-semibold border transition-all ${
                              activo
                                ? "border-teal-700 bg-teal-700 text-white"
                                : "border-gray-200 bg-white text-gray-800 hover:border-teal-600"
                            }`}
                          >
                            {formatearHora(slot.inicio)}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  <button
                    type="button"
                    disabled={!slotNuevo || mutationReprogramar.isPending}
                    onClick={() => {
                      if (slotNuevo) mutationReprogramar.mutate(slotNuevo);
                    }}
                    className="w-full py-2.5 text-xs font-bold text-white bg-teal-800 rounded-lg hover:bg-teal-900 disabled:bg-gray-400"
                  >
                    {mutationReprogramar.isPending
                      ? "Reprogramando..."
                      : "Confirmar nuevo horario"}
                  </button>
                </div>
              )}

              {!mostrarCancelar ? (
                <button
                  type="button"
                  onClick={() => setMostrarCancelar(true)}
                  className="w-full py-2.5 text-red-600 hover:text-red-800 text-xs font-semibold text-center"
                >
                  Necesito cancelar mi turno
                </button>
              ) : (
                <div className="p-4 bg-red-50 rounded-xl border border-red-200 space-y-3">
                  <p className="text-xs font-semibold text-red-900">
                    ¿Estás seguro de que deseás cancelar tu cita?
                  </p>
                  <input
                    type="text"
                    placeholder="Motivo de la cancelación (opcional)"
                    value={motivoCancelacion}
                    onChange={(e) => setMotivoCancelacion(e.target.value)}
                    className="w-full p-2.5 text-xs rounded-lg border border-red-300 bg-white"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setMostrarCancelar(false)}
                      className="flex-1 py-2 text-xs font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100"
                    >
                      Volver
                    </button>
                    <button
                      type="button"
                      onClick={() => mutationCancelar.mutate(motivoCancelacion || undefined)}
                      disabled={mutationCancelar.isPending}
                      className="flex-1 py-2 text-xs font-bold text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:bg-gray-400"
                    >
                      {mutationCancelar.isPending ? "Cancelando..." : "Sí, cancelar turno"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
