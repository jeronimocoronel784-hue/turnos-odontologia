import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { EstadoListaEspera } from "../../shared/api-types";
import {
  aceptarHuecoListaEspera,
  darDeBajaListaEspera,
  obtenerListaEspera,
} from "../../shared/reserva-api";
import { formatearFechaHora, formatearRangoHorario } from "../../shared/formatters";

const ESTILOS_ESTADO: Record<EstadoListaEspera, { clase: string; texto: string }> = {
  activa: { clase: "bg-blue-100 text-blue-800", texto: "En espera" },
  avisada: { clase: "bg-amber-100 text-amber-800", texto: "¡Hay un hueco para vos!" },
  colocada: { clase: "bg-green-100 text-green-800", texto: "Turno asignado" },
  baja: { clase: "bg-gray-100 text-gray-700", texto: "Baja de la lista" },
};

/** Minutos restantes hasta el vencimiento del aviso (0 si ya venció). */
function minutosRestantes(venceAt: string, ahora: number): number {
  const vence = new Date(venceAt).getTime();
  if (Number.isNaN(vence)) return 0;
  return Math.max(0, Math.ceil((vence - ahora) / 60_000));
}

export const AceptarHuecoPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [ahora, setAhora] = useState<number>(() => Date.now());
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const {
    data: entrada,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["lista-espera", token],
    queryFn: ({ signal }) => obtenerListaEspera(token ?? "", signal),
    enabled: Boolean(token),
  });

  // Refresca el contador del aviso sin recargar la consulta.
  useEffect(() => {
    if (!entrada?.aviso_vence_at) return;
    const id = window.setInterval(() => setAhora(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, [entrada?.aviso_vence_at]);

  const mutationAceptar = useMutation({
    mutationFn: () => aceptarHuecoListaEspera(token ?? ""),
    onSuccess: () => {
      setErrorAccion(null);
      setMensajeExito("¡Listo! Te guardamos el hueco. Ya tenés tu turno asignado.");
      // El refetch trae estado `colocada` + `token_gestion` para linkear al turno.
      void refetch();
    },
    onError: (err: Error) => setErrorAccion(err.message),
  });

  const mutationBaja = useMutation({
    mutationFn: () => darDeBajaListaEspera(token ?? ""),
    onSuccess: () => {
      setErrorAccion(null);
      setMensajeExito("Te dimos de baja de la lista de espera. Podés volver a anotarte cuando quieras.");
      void refetch();
    },
    onError: (err: Error) => setErrorAccion(err.message),
  });

  if (!token) {
    return (
      <div className="max-w-md mx-auto p-6 text-center text-gray-700">
        <h1 className="text-xl font-bold">Enlace no válido</h1>
        <p className="text-sm text-gray-500 mt-2">
          El enlace de la lista de espera no es correcto o está incompleto.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-gray-500">
        <div className="w-10 h-10 border-4 border-teal-700 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Consultando tu lugar en la lista...</p>
      </div>
    );
  }

  if (error || !entrada) {
    return (
      <div className="max-w-md mx-auto my-12 p-8 bg-white rounded-2xl border border-gray-200 shadow-sm text-center">
        <span className="text-4xl mb-3 block">🔍</span>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Enlace no encontrado</h1>
        <p className="text-sm text-gray-600 mb-6 leading-relaxed">
          No encontramos ninguna entrada de lista de espera asociada a este enlace o ya expiró.
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

  const estilo = ESTILOS_ESTADO[entrada.estado];
  const puedeAceptar = entrada.estado === "avisada" && Boolean(entrada.hueco_inicio);
  const puedeBaja = entrada.estado === "activa" || entrada.estado === "avisada";
  const restantes = entrada.aviso_vence_at ? minutosRestantes(entrada.aviso_vence_at, ahora) : null;

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-lg mx-auto space-y-6">
        <header className="text-center">
          <h1 className="text-2xl font-black text-gray-900">Lista de Espera</h1>
          <p className="text-xs text-gray-500 mt-1">
            Te avisamos apenas se libere un horario para tu tratamiento
          </p>
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
            <span className="text-xs font-semibold text-gray-500 uppercase">Estado</span>
            <span className={`px-3 py-1 rounded-full text-xs font-bold ${estilo.clase}`}>
              {estilo.texto}
            </span>
          </div>

          <div className="space-y-4">
            <div>
              <span className="text-xs text-gray-500 block uppercase font-medium">Tratamiento</span>
              <p className="text-lg font-bold text-gray-900 mt-0.5">{entrada.prestacion_nombre}</p>
            </div>

            {entrada.profesional_nombre && (
              <div>
                <span className="text-xs text-gray-500 block uppercase font-medium">
                  Profesional
                </span>
                <p className="text-sm font-medium text-gray-800">{entrada.profesional_nombre}</p>
              </div>
            )}

            <div>
              <span className="text-xs text-gray-500 block uppercase font-medium">
                Aviso preferido
              </span>
              <p className="text-sm font-medium text-gray-800">
                {entrada.canal_aviso === "wa" ? "WhatsApp" : "Email"}
              </p>
            </div>
          </div>

          {entrada.estado === "avisada" && entrada.hueco_inicio && (
            <div className="p-5 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
              <p className="text-sm font-bold text-amber-900">¡Se liberó un horario!</p>
              <p className="text-base font-semibold text-gray-900 capitalize">
                {formatearFechaHora(entrada.hueco_inicio)}
              </p>
              {entrada.hueco_fin && (
                <p className="text-xs text-amber-800">
                  Duración: {formatearRangoHorario(entrada.hueco_inicio, entrada.hueco_fin)}
                </p>
              )}
              {entrada.aviso_vence_at && (
                <p className="text-xs font-semibold text-red-700">
                  {restantes !== null && restantes > 0
                    ? `Tenés ${restantes} minuto${restantes === 1 ? "" : "s"} para aceptarlo.`
                    : "Este aviso ya venció. Si seguís en la lista, te avisaremos del próximo hueco."}
                </p>
              )}
            </div>
          )}

          {entrada.estado === "colocada" && (
            <div className="p-5 bg-green-50 border border-green-200 rounded-xl text-center space-y-3">
              <p className="text-sm font-bold text-green-900">¡Tu turno quedó reservado!</p>
              {entrada.hueco_inicio && (
                <p className="text-sm text-green-800 capitalize">
                  {formatearFechaHora(entrada.hueco_inicio)}
                </p>
              )}
              {entrada.token_gestion && (
                <Link
                  to={`/mis-turnos/${entrada.token_gestion}`}
                  className="inline-block py-2.5 px-5 bg-teal-800 hover:bg-teal-900 text-white font-bold text-sm rounded-xl transition-all"
                >
                  Ver los datos de mi turno
                </Link>
              )}
            </div>
          )}

          {entrada.estado === "activa" && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
              <p className="text-xs text-slate-700 leading-relaxed">
                Estás anotado. Cuando alguien cancele un turno compatible con tu tratamiento, te
                vamos a avisar por el canal que elegiste.
              </p>
            </div>
          )}

          {entrada.estado === "baja" && (
            <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl">
              <p className="text-xs text-gray-600 leading-relaxed">
                Esta entrada ya no está activa. Si querés volver a la lista, pedí un nuevo alta en
                el portal del consultorio.
              </p>
            </div>
          )}

          {(puedeAceptar || puedeBaja) && (
            <div className="pt-4 border-t border-gray-100 space-y-3">
              {puedeAceptar && (
                <button
                  type="button"
                  onClick={() => mutationAceptar.mutate()}
                  disabled={mutationAceptar.isPending}
                  className="w-full py-3 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-400 text-white font-bold rounded-xl text-sm transition-all shadow-sm"
                >
                  {mutationAceptar.isPending ? "Reservando..." : "¡Sí, quiero ese horario!"}
                </button>
              )}

              {puedeBaja && (
                <button
                  type="button"
                  onClick={() => mutationBaja.mutate()}
                  disabled={mutationBaja.isPending}
                  className="w-full py-2.5 text-gray-500 hover:text-red-700 text-xs font-semibold text-center"
                >
                  {mutationBaja.isPending ? "Procesando..." : "Darme de baja de la lista"}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
