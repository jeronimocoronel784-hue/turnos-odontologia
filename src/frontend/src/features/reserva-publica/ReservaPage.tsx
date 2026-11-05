import React, { useState, useEffect, useTransition } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import type {
  PrestacionPublica,
  ReservaPublicaInput,
  ReservaPublicaResponse,
  SlotDisponible,
} from "../../shared/api-types";
import {
  ErrorApi,
  crearReservaPublica,
  obtenerDisponibilidadPublica,
} from "../../shared/reserva-api";
import { SelectorPrestacion } from "./SelectorPrestacion";
import { SelectorHorario } from "./SelectorHorario";
import { FormularioPaciente, type DatosPacienteForm } from "./FormularioPaciente";
import { ConfirmacionReserva } from "./ConfirmacionReserva";

/** Fecha local en YYYY-MM-DD (evita el corrimiento de `toISOString` en UTC). */
function fechaLocalIso(diasAdelante: number): string {
  const d = new Date();
  d.setDate(d.getDate() + diasAdelante);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export const ReservaPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [, startTransition] = useTransition();

  const [paso, setPaso] = useState<1 | 2 | 3 | 4>(1);
  const [prestacionSel, setPrestacionSel] = useState<PrestacionPublica | null>(null);
  const [profesionalIdSel, setProfesionalIdSel] = useState<string | null>(null);
  const [fechaSel, setFechaSel] = useState<string>(() => fechaLocalIso(1));
  const [slotSel, setSlotSel] = useState<SlotDisponible | null>(null);
  const [datosPaciente, setDatosPaciente] = useState<DatosPacienteForm>({
    nombre: "",
    dni: "",
    telefono: "",
    email: "",
    fecha_nac: "",
    nro_afiliado: "",
    optin_wa: true,
  });
  const [reservaConfirmada, setReservaConfirmada] = useState<ReservaPublicaResponse | null>(null);
  const [errorEnvio, setErrorEnvio] = useState<string | null>(null);

  const {
    data: catalogo,
    isLoading: cargandoCatalogo,
    isFetching: actualizandoCatalogo,
    error: errorCatalogo,
    refetch: recargarCatalogo,
  } = useQuery({
    queryKey: ["disponibilidad", slug, prestacionSel?.id, profesionalIdSel, fechaSel],
    queryFn: ({ signal }) =>
      obtenerDisponibilidadPublica(
        slug ?? "",
        {
          prestacion_id: prestacionSel?.id,
          profesional_id: profesionalIdSel ?? undefined,
          fecha: fechaSel,
        },
        signal
      ),
    enabled: Boolean(slug),
  });

  const mutationReserva = useMutation({
    mutationFn: (payload: ReservaPublicaInput) => crearReservaPublica(slug ?? "", payload),
    onSuccess: (data) => {
      setReservaConfirmada(data);
      setPaso(4);
    },
    onError: (err: Error) => {
      setErrorEnvio(err.message);
      // 409: el horario se ocupó mientras completaba el formulario. Recargamos slots.
      if (err instanceof ErrorApi && err.status === 409) {
        setSlotSel(null);
        setPaso(2);
        void recargarCatalogo();
      }
    },
  });

  useEffect(() => {
    setSlotSel(null);
  }, [fechaSel, prestacionSel?.id, profesionalIdSel]);

  if (!slug) {
    return (
      <div className="max-w-md mx-auto p-6 text-center text-gray-700">
        <h1 className="text-xl font-bold">Falta el identificador del consultorio</h1>
        <p className="text-sm text-gray-500 mt-2">
          Por favor, utilizá el enlace provisto por el consultorio para reservar.
        </p>
      </div>
    );
  }

  if (cargandoCatalogo) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-gray-500">
        <div className="w-10 h-10 border-4 border-teal-700 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Cargando consultorio...</p>
      </div>
    );
  }

  if (errorCatalogo || !catalogo) {
    return (
      <div className="max-w-lg mx-auto my-12 p-8 bg-white rounded-2xl border border-gray-200 shadow-sm text-center">
        <span className="text-4xl mb-3 block">🏥</span>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Consultorio no encontrado</h1>
        <p className="text-sm text-gray-600 mb-6 leading-relaxed">
          Che, no encontramos ese consultorio o no está disponible en este momento. Verificá que el
          enlace esté bien escrito.
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

  const handleConfirmarReserva = () => {
    if (!prestacionSel || !slotSel) return;
    setErrorEnvio(null);

    mutationReserva.mutate({
      nombre: datosPaciente.nombre.trim(),
      dni: datosPaciente.dni.replace(/\D/g, ""),
      telefono: datosPaciente.telefono.trim(),
      email: datosPaciente.email.trim() || undefined,
      fecha_nac: datosPaciente.fecha_nac || undefined,
      nro_afiliado: datosPaciente.nro_afiliado.trim() || undefined,
      optin_wa: datosPaciente.optin_wa,
      prestacion_id: prestacionSel.id,
      profesional_id: slotSel.profesional_id,
      sillon_id: slotSel.sillon_id,
      inicio: slotSel.inicio,
    });
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6">
      <div className="max-w-xl mx-auto">
        <header className="mb-6 text-center">
          <span className="inline-block px-3 py-1 bg-teal-100 text-teal-800 text-xs font-semibold rounded-full mb-2">
            Reserva Online 24/7
          </span>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900">
            {catalogo.tenant_nombre}
          </h1>
        </header>

        {paso < 4 && (
          <div className="flex items-center justify-between mb-8 px-2" aria-label="Pasos de la reserva">
            {[1, 2, 3].map((nroPaso) => (
              <div key={nroPaso} className="flex items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-colors ${
                    paso === nroPaso
                      ? "bg-teal-700 text-white ring-4 ring-teal-700/20"
                      : paso > nroPaso
                        ? "bg-teal-900 text-white"
                        : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {paso > nroPaso ? "✓" : nroPaso}
                </div>
                {nroPaso < 3 && (
                  <div
                    className={`w-16 sm:w-28 h-1 mx-2 rounded transition-colors ${
                      paso > nroPaso ? "bg-teal-800" : "bg-gray-200"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        <main className="bg-white rounded-2xl border border-gray-200 p-6 sm:p-8 shadow-sm">
          {errorEnvio && paso !== 3 && (
            <div
              role="alert"
              className="mb-5 p-4 bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded-xl"
            >
              <p className="font-semibold">Ese horario se ocupó recién</p>
              <p className="text-xs mt-0.5">{errorEnvio}</p>
            </div>
          )}

          {paso === 1 && (
            <div className="space-y-6">
              <SelectorPrestacion
                prestaciones={catalogo.prestaciones}
                prestacionSeleccionadaId={prestacionSel?.id ?? null}
                onSeleccionarPrestacion={(prest) => setPrestacionSel(prest)}
                profesionales={catalogo.profesionales}
                profesionalSeleccionadoId={profesionalIdSel}
                onSeleccionarProfesional={(id) => setProfesionalIdSel(id)}
              />

              <button
                type="button"
                disabled={!prestacionSel}
                onClick={() => startTransition(() => setPaso(2))}
                className="w-full py-3.5 px-4 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold rounded-xl text-base shadow-sm transition-all"
              >
                Continuar a horarios
              </button>
            </div>
          )}

          {paso === 2 && (
            <div className="space-y-6">
              <SelectorHorario
                fechaSeleccionada={fechaSel}
                onCambiarFecha={(f) => setFechaSel(f)}
                slots={catalogo.slots_disponibles}
                slotSeleccionado={slotSel}
                onSeleccionarSlot={(slot) => setSlotSel(slot)}
                profesionales={catalogo.profesionales}
                cargando={actualizandoCatalogo}
              />

              <div className="flex gap-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setPaso(1)}
                  className="py-3 px-5 border border-gray-300 rounded-xl text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Volver
                </button>
                <button
                  type="button"
                  disabled={!slotSel}
                  onClick={() => startTransition(() => setPaso(3))}
                  className="flex-1 py-3 px-4 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold rounded-xl text-sm shadow-sm transition-all"
                >
                  Continuar a mis datos
                </button>
              </div>
            </div>
          )}

          {paso === 3 && (
            <div className="space-y-6">
              <FormularioPaciente
                datos={datosPaciente}
                onChange={(d) => setDatosPaciente(d)}
                onSubmit={handleConfirmarReserva}
                enviando={mutationReserva.isPending}
                error={errorEnvio}
              />

              <button
                type="button"
                onClick={() => setPaso(2)}
                disabled={mutationReserva.isPending}
                className="w-full py-2.5 text-center text-sm font-semibold text-gray-600 hover:text-gray-900"
              >
                Volver a elegir horario
              </button>
            </div>
          )}

          {paso === 4 && reservaConfirmada && <ConfirmacionReserva reserva={reservaConfirmada} />}
        </main>
      </div>
    </div>
  );
};
