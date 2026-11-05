import React from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { obtenerMiTurno, obtenerPreferenciaPago } from "../../shared/reserva-api";
import {
  formatearFechaLarga,
  formatearHora,
  formatearMoneda,
} from "../../shared/formatters";

export const PagarSenaPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();

  const {
    data: turno,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["mi-turno-pago", token],
    queryFn: ({ signal }) => obtenerMiTurno(token ?? "", signal),
    enabled: Boolean(token),
  });

  const mutationPago = useMutation({
    mutationFn: () => obtenerPreferenciaPago(token ?? ""),
    onSuccess: (preferencia) => {
      // Redirección al checkout oficial de Mercado Pago con la preferencia del servidor.
      window.location.assign(preferencia.init_point);
    },
  });

  if (!token) {
    return (
      <div className="max-w-md mx-auto p-6 text-center text-gray-700">
        <h1 className="text-xl font-bold">Enlace no válido</h1>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-gray-500">
        <div className="w-10 h-10 border-4 border-sky-600 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Cargando datos de pago...</p>
      </div>
    );
  }

  if (error || !turno) {
    return (
      <div className="max-w-md mx-auto my-12 p-8 bg-white rounded-2xl border border-gray-200 shadow-sm text-center">
        <h1 className="text-xl font-bold text-gray-900 mb-2">Enlace expirado o no encontrado</h1>
        <p className="text-sm text-gray-600 mb-6">
          No pudimos encontrar la información de este pago.
        </p>
        <Link
          to="/"
          className="inline-block py-2.5 px-5 bg-teal-800 text-white rounded-lg text-sm font-semibold hover:bg-teal-900"
        >
          Volver al inicio
        </Link>
      </div>
    );
  }

  const sinSena = !turno.requiere_sena;

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-md mx-auto space-y-6">
        <header className="text-center">
          <span className="inline-block px-3 py-1 bg-sky-100 text-sky-800 text-xs font-semibold rounded-full mb-2">
            Mercado Pago Seguro
          </span>
          <h1 className="text-2xl font-black text-gray-900">Pago de Seña</h1>
          <p className="text-xs text-gray-500 mt-1">
            Garantizá tu turno odontológico de forma rápida y segura
          </p>
        </header>

        <div className="bg-white rounded-2xl border border-gray-200 p-6 sm:p-8 shadow-sm space-y-6">
          {turno.sena_cobrada || sinSena ? (
            <div className="text-center py-6 space-y-4">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 text-green-700 text-2xl font-bold">
                ✓
              </div>
              <h2 className="text-xl font-bold text-gray-900">
                {sinSena ? "Este turno no requiere seña" : "¡Seña abonada con éxito!"}
              </h2>
              <p className="text-sm text-gray-600">
                {sinSena
                  ? "Tu cita ya está reservada. El saldo se abona en el consultorio el día de la atención."
                  : "Tu turno está asegurado. ¡Te esperamos!"}
              </p>
              <Link
                to={`/mis-turnos/${token}`}
                className="inline-block mt-2 py-3 px-6 bg-teal-800 hover:bg-teal-900 text-white font-bold text-sm rounded-xl transition-all"
              >
                Ver los datos de mi cita
              </Link>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-100 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Tratamiento:</span>
                  <span className="font-semibold text-gray-900">{turno.prestacion_nombre}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Día:</span>
                  <span className="font-medium text-gray-800 capitalize">
                    {formatearFechaLarga(turno.inicio)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Hora:</span>
                  <span className="font-medium text-teal-800">{formatearHora(turno.inicio)}</span>
                </div>
              </div>

              <div className="p-5 bg-sky-50 rounded-xl border border-sky-100 text-center">
                <span className="text-xs font-semibold text-sky-800 uppercase tracking-wide block">
                  Total a abonar de seña
                </span>
                <span className="text-3xl font-black text-sky-950 mt-1 block">
                  {formatearMoneda(turno.monto_sena)}
                </span>
                <span className="text-[11px] text-sky-700 mt-1 block">
                  El saldo restante se abona en el consultorio el día de la cita.
                </span>
              </div>

              {mutationPago.isError && (
                <p role="alert" className="text-xs text-red-600 text-center font-medium">
                  {mutationPago.error instanceof Error
                    ? mutationPago.error.message
                    : "No pudimos iniciar el pago. Probá de nuevo."}
                </p>
              )}

              <div className="space-y-3 pt-2">
                <button
                  type="button"
                  onClick={() => mutationPago.mutate()}
                  disabled={mutationPago.isPending}
                  className="w-full py-3.5 px-4 bg-[#009EE3] hover:bg-[#0086c2] disabled:bg-gray-400 text-white font-extrabold rounded-xl text-base shadow-sm flex items-center justify-center gap-2 transition-all"
                >
                  <span>{mutationPago.isPending ? "Abriendo Mercado Pago..." : "Pagar con Mercado Pago"}</span>
                  <span className="text-xl">➔</span>
                </button>

                <p className="text-[11px] text-gray-400 text-center">
                  Acepta tarjeta de débito, crédito, dinero en cuenta de Mercado Pago o transferencia.
                </p>
              </div>

              <div className="text-center pt-2">
                <Link
                  to={`/mis-turnos/${token}`}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium"
                >
                  Volver a los detalles de mi turno
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
