import React, { useState } from "react";
import type { ReservaPublicaResponse } from "../../shared/api-types";
import { formatearFechaLarga, formatearHora, formatearMoneda } from "../../shared/formatters";

interface Props {
  reserva: ReservaPublicaResponse;
}

export const ConfirmacionReserva: React.FC<Props> = ({ reserva }) => {
  const [copiado, setCopiado] = useState(false);

  const linkGestion = reserva.token_gestion
    ? `${window.location.origin}/mis-turnos/${reserva.token_gestion}`
    : null;

  const copiarLink = () => {
    if (linkGestion) {
      navigator.clipboard.writeText(linkGestion);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-6 md:p-8 shadow-sm space-y-6">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-teal-100 text-teal-800 text-3xl mb-3">
          ✓
        </div>
        <h2 className="text-2xl font-bold text-gray-900">¡Tu reserva fue recibida!</h2>
        <p className="text-sm text-gray-600 mt-1">
          Te enviamos la confirmación por WhatsApp a tu teléfono.
        </p>
      </div>

      {/* Tarjeta de Resumen */}
      <div className="bg-gray-50 rounded-xl p-5 border border-gray-100 space-y-3">
        <div className="flex justify-between items-center pb-3 border-b border-gray-200">
          <span className="text-xs font-semibold uppercase text-gray-500">Tratamiento</span>
          <span className="font-bold text-gray-900 text-base">{reserva.prestacion_nombre}</span>
        </div>

        <div className="flex justify-between items-center pb-3 border-b border-gray-200">
          <span className="text-xs font-semibold uppercase text-gray-500">Fecha y Hora</span>
          <div className="text-right">
            <span className="font-semibold text-gray-900 block capitalize">
              {formatearFechaLarga(reserva.inicio)}
            </span>
            <span className="text-xs font-medium text-teal-700">
              {formatearHora(reserva.inicio)}
            </span>
          </div>
        </div>

        <div className="flex justify-between items-center pb-3 border-b border-gray-200">
          <span className="text-xs font-semibold uppercase text-gray-500">Profesional</span>
          <span className="font-medium text-gray-800">{reserva.profesional_nombre}</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-xs font-semibold uppercase text-gray-500">Sillón / Box</span>
          <span className="font-medium text-gray-800">{reserva.sillon_nombre}</span>
        </div>
      </div>

      {/* Alerta de Seña si corresponde */}
      {reserva.requiere_sena && !reserva.sena_cobrada && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-amber-900 font-bold text-sm">
            <span>💳</span>
            <span>Esta cita requiere seña para confirmarse</span>
          </div>
          <p className="text-xs text-amber-800 leading-relaxed">
            Para garantizar tu horario en el sillón odontológico, tenés que abonar la seña de{" "}
            <strong>{formatearMoneda(reserva.monto_sena)}</strong> por Mercado Pago.
          </p>

          {reserva.token_gestion && (
            <a
              href={`/pagar/${reserva.token_gestion}`}
              className="block w-full py-3 px-4 bg-sky-600 hover:bg-sky-700 text-white font-bold text-sm rounded-xl text-center shadow-sm transition-all"
            >
              Pagar seña con Mercado Pago
            </a>
          )}
        </div>
      )}

      {/* Link de Autogestión Personal */}
      {linkGestion && (
        <div className="pt-2">
          <p className="text-xs font-semibold text-gray-600 mb-2">
            Guardá este enlace para consultar, reprogramar o cancelar tu turno:
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              readOnly
              value={linkGestion}
              className="flex-1 p-2.5 bg-gray-100 rounded-lg text-xs text-gray-700 border border-gray-200 select-all"
            />
            <button
              type="button"
              onClick={copiarLink}
              className="px-4 py-2.5 bg-gray-800 hover:bg-gray-900 text-white text-xs font-semibold rounded-lg transition-all"
            >
              {copiado ? "¡Copiado!" : "Copiar"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
