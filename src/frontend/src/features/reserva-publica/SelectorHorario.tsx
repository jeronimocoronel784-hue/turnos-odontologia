import React from "react";
import type { ProfesionalPublico, SlotDisponible } from "../../shared/api-types";
import { formatearHora } from "../../shared/formatters";

interface Props {
  fechaSeleccionada: string;
  onCambiarFecha: (fecha: string) => void;
  slots: SlotDisponible[];
  slotSeleccionado: SlotDisponible | null;
  onSeleccionarSlot: (slot: SlotDisponible) => void;
  profesionales: ProfesionalPublico[];
  cargando: boolean;
}

/** Próximos 14 días a partir de mañana, en formato YYYY-MM-DD local. */
function proximosDias(): { isoFecha: string; nombreDia: string; nroDia: number }[] {
  return Array.from({ length: 14 }).map((_, idx) => {
    const d = new Date();
    d.setDate(d.getDate() + idx + 1);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const isoFecha = `${yyyy}-${mm}-${dd}`;
    const nombreDia = new Intl.DateTimeFormat("es-AR", { weekday: "short" }).format(d);
    return { isoFecha, nombreDia, nroDia: d.getDate() };
  });
}

export const SelectorHorario: React.FC<Props> = ({
  fechaSeleccionada,
  onCambiarFecha,
  slots,
  slotSeleccionado,
  onSeleccionarSlot,
  profesionales,
  cargando,
}) => {
  const diasDisponibles = proximosDias();
  const nombrePorId = new Map(profesionales.map((p) => [p.id, p.nombre]));
  const hayVariosProfesionales = new Set(slots.map((s) => s.profesional_id)).size > 1;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">2. Elegí fecha y horario</h2>
        <p className="text-sm text-gray-500 mb-4">
          Seleccioná el día para ver los turnos disponibles en el consultorio.
        </p>

        <div className="flex gap-2 overflow-x-auto pb-3 pt-1 scrollbar-thin">
          {diasDisponibles.map((dia) => {
            const activo = dia.isoFecha === fechaSeleccionada;
            return (
              <button
                key={dia.isoFecha}
                type="button"
                aria-pressed={activo}
                onClick={() => onCambiarFecha(dia.isoFecha)}
                className={`flex-shrink-0 flex flex-col items-center justify-center w-16 py-3 rounded-xl border-2 transition-all ${
                  activo
                    ? "border-teal-700 bg-teal-800 text-white shadow-md"
                    : "border-gray-200 hover:border-gray-300 bg-white text-gray-700"
                }`}
              >
                <span className="text-xs uppercase font-medium">{dia.nombreDia}</span>
                <span className="text-lg font-bold mt-0.5">{dia.nroDia}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Horarios disponibles:</h3>

        {cargando ? (
          <div className="p-8 text-center text-gray-500 text-sm animate-pulse bg-gray-50 rounded-xl">
            Buscando horarios disponibles...
          </div>
        ) : slots.length === 0 ? (
          <div className="p-6 text-center text-gray-600 bg-amber-50 border border-amber-200 rounded-xl text-sm">
            <p className="font-semibold text-amber-900">No encontramos horarios para esta fecha.</p>
            <p className="text-xs text-amber-700 mt-1">
              Probá seleccionando otro día o consultá por lista de espera.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
            {slots.map((slot) => {
              const seleccionado =
                slotSeleccionado?.inicio === slot.inicio &&
                slotSeleccionado?.profesional_id === slot.profesional_id &&
                slotSeleccionado?.sillon_id === slot.sillon_id;

              return (
                <button
                  key={`${slot.inicio}-${slot.profesional_id}-${slot.sillon_id}`}
                  type="button"
                  aria-pressed={seleccionado}
                  onClick={() => onSeleccionarSlot(slot)}
                  className={`py-2.5 px-2 rounded-lg text-sm font-medium border text-center transition-all ${
                    seleccionado
                      ? "border-teal-700 bg-teal-700 text-white shadow-sm ring-2 ring-teal-700/20"
                      : "border-gray-200 hover:border-teal-600 bg-white text-gray-800"
                  }`}
                >
                  <span className="block">{formatearHora(slot.inicio)}</span>
                  {hayVariosProfesionales && (
                    <span
                      className={`block text-[10px] font-normal truncate ${
                        seleccionado ? "text-teal-100" : "text-gray-500"
                      }`}
                    >
                      {nombrePorId.get(slot.profesional_id) ?? ""}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
