import React from "react";
import type { PrestacionPublica, ProfesionalPublico } from "../../shared/api-types";
import { formatearMoneda } from "../../shared/formatters";

interface Props {
  prestaciones: PrestacionPublica[];
  prestacionSeleccionadaId: string | null;
  onSeleccionarPrestacion: (prestacion: PrestacionPublica) => void;
  profesionales: ProfesionalPublico[];
  profesionalSeleccionadoId: string | null;
  onSeleccionarProfesional: (profesionalId: string | null) => void;
}

export const SelectorPrestacion: React.FC<Props> = ({
  prestaciones,
  prestacionSeleccionadaId,
  onSeleccionarPrestacion,
  profesionales,
  profesionalSeleccionadoId,
  onSeleccionarProfesional,
}) => {
  return (
    <div className="space-y-6">
      {/* Selección de Tratamiento */}
      <div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">1. Elegí el tratamiento</h2>
        <p className="text-sm text-gray-500 mb-4">
          Seleccioná la prestación odontológica que necesitás realizarte.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {prestaciones.map((prestacion) => {
            const seleccionada = prestacion.id === prestacionSeleccionadaId;
            return (
              <button
                key={prestacion.id}
                type="button"
                onClick={() => onSeleccionarPrestacion(prestacion)}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  seleccionada
                    ? "border-teal-700 bg-teal-50 shadow-sm ring-2 ring-teal-700/20"
                    : "border-gray-200 hover:border-gray-300 bg-white"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-gray-900 text-base">{prestacion.nombre}</h3>
                    <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                      <span>⏱</span> Duración aprox: {prestacion.duracion_min} minutos
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="font-bold text-teal-800 text-base">
                      {formatearMoneda(prestacion.precio_particular)}
                    </span>
                    {prestacion.requiere_sena && prestacion.monto_sena && (
                      <span className="block text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full mt-1 border border-amber-200">
                        Seña: {formatearMoneda(prestacion.monto_sena)}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selección de Profesional opcional */}
      {profesionales.length > 1 && (
        <div className="pt-4 border-t border-gray-100">
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            ¿Preferís atenderte con algún profesional en particular? (Opcional)
          </label>
          <select
            value={profesionalSeleccionadoId ?? ""}
            onChange={(e) => onSeleccionarProfesional(e.target.value ? e.target.value : null)}
            className="w-full p-3 rounded-lg border border-gray-300 bg-white text-gray-800 text-sm focus:ring-2 focus:ring-teal-700 focus:border-teal-700"
          >
            <option value="">Cualquier profesional disponible</option>
            {profesionales.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre} {p.matricula ? `(Mat. ${p.matricula})` : ""}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};
