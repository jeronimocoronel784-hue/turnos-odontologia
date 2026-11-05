import React, { useState } from "react";
import { formatearDni } from "../../shared/formatters";

export interface DatosPacienteForm {
  nombre: string;
  dni: string;
  telefono: string;
  email: string;
  fecha_nac: string;
  nro_afiliado: string;
  optin_wa: boolean;
}

interface Props {
  datos: DatosPacienteForm;
  onChange: (nuevosDatos: DatosPacienteForm) => void;
  onSubmit: () => void;
  enviando: boolean;
  error: string | null;
}

export const FormularioPaciente: React.FC<Props> = ({
  datos,
  onChange,
  onSubmit,
  enviando,
  error,
}) => {
  const [erroresLocales, setErroresLocales] = useState<Record<string, string>>({});

  const validarYContinuar = (e: React.FormEvent) => {
    e.preventDefault();
    const nuevosErrores: Record<string, string> = {};

    if (!datos.nombre.trim()) {
      nuevosErrores.nombre = "Ingresá tu nombre completo.";
    }
    const dniLimpio = datos.dni.replace(/\D/g, "");
    if (!dniLimpio || dniLimpio.length < 7 || dniLimpio.length > 8) {
      nuevosErrores.dni = "Ingresá un DNI argentino válido (7 u 8 dígitos).";
    }
    const telLimpio = datos.telefono.replace(/\D/g, "");
    if (!telLimpio || telLimpio.length < 8) {
      nuevosErrores.telefono = "Ingresá un teléfono móvil válido para confirmar tu turno.";
    }
    if (!datos.optin_wa) {
      nuevosErrores.optin_wa = "Necesitamos tu confirmación para enviarte el recordatorio por WhatsApp.";
    }

    setErroresLocales(nuevosErrores);
    if (Object.keys(nuevosErrores).length === 0) {
      onSubmit();
    }
  };

  return (
    <form onSubmit={validarYContinuar} className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-gray-800 mb-1">3. Completá tus datos</h2>
        <p className="text-sm text-gray-500">
          Tus datos personales son necesarios para agendar tu cita en el consultorio.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-800 text-sm rounded-xl flex items-start gap-2">
          <span>⚠️</span>
          <div>
            <p className="font-semibold">No pudimos completar tu reserva</p>
            <p className="text-xs text-red-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Nombre y Apellido */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1">
          Nombre y Apellido <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          placeholder="Ej: Juan Pérez"
          value={datos.nombre}
          onChange={(e) => onChange({ ...datos, nombre: e.target.value })}
          className={`w-full p-3 rounded-lg border text-sm ${
            erroresLocales.nombre ? "border-red-400 bg-red-50" : "border-gray-300"
          } focus:ring-2 focus:ring-teal-700 focus:border-teal-700`}
        />
        {erroresLocales.nombre && (
          <p className="text-xs text-red-600 mt-1">{erroresLocales.nombre}</p>
        )}
      </div>

      {/* DNI y Teléfono */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            DNI <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            placeholder="Ej: 38.123.456"
            value={datos.dni}
            onChange={(e) => onChange({ ...datos, dni: formatearDni(e.target.value) })}
            className={`w-full p-3 rounded-lg border text-sm ${
              erroresLocales.dni ? "border-red-400 bg-red-50" : "border-gray-300"
            } focus:ring-2 focus:ring-teal-700 focus:border-teal-700`}
          />
          {erroresLocales.dni && (
            <p className="text-xs text-red-600 mt-1">{erroresLocales.dni}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Teléfono Móvil (WhatsApp) <span className="text-red-500">*</span>
          </label>
          <input
            type="tel"
            placeholder="Ej: 11 4567-8910"
            value={datos.telefono}
            onChange={(e) => onChange({ ...datos, telefono: e.target.value })}
            className={`w-full p-3 rounded-lg border text-sm ${
              erroresLocales.telefono ? "border-red-400 bg-red-50" : "border-gray-300"
            } focus:ring-2 focus:ring-teal-700 focus:border-teal-700`}
          />
          {erroresLocales.telefono && (
            <p className="text-xs text-red-600 mt-1">{erroresLocales.telefono}</p>
          )}
        </div>
      </div>

      {/* Email y Fecha de Nacimiento */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Correo electrónico (Opcional)
          </label>
          <input
            type="email"
            placeholder="tunombre@email.com"
            value={datos.email}
            onChange={(e) => onChange({ ...datos, email: e.target.value })}
            className="w-full p-3 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-700 focus:border-teal-700"
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">
            Fecha de Nacimiento (Opcional)
          </label>
          <input
            type="date"
            value={datos.fecha_nac}
            onChange={(e) => onChange({ ...datos, fecha_nac: e.target.value })}
            className="w-full p-3 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-700 focus:border-teal-700"
          />
        </div>
      </div>

      {/* Obra Social y Nro Afiliado */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1">
          Nro. de Afiliado a Obra Social (Opcional)
        </label>
        <input
          type="text"
          placeholder="Ej: OSDE 12345678"
          value={datos.nro_afiliado}
          onChange={(e) => onChange({ ...datos, nro_afiliado: e.target.value })}
          className="w-full p-3 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-700 focus:border-teal-700"
        />
        <p className="text-xs text-gray-400 mt-1">
          Si tenés cobertura médica, la liquidación se coordinará en tu cita presencial.
        </p>
      </div>

      {/* Checkbox de WhatsApp obligatorio */}
      <div className="pt-2">
        <label className="flex items-start gap-3 p-3 bg-teal-50/60 rounded-xl border border-teal-100 cursor-pointer">
          <input
            type="checkbox"
            checked={datos.optin_wa}
            onChange={(e) => onChange({ ...datos, optin_wa: e.target.checked })}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-700 focus:ring-teal-700"
          />
          <span className="text-xs text-gray-700 leading-relaxed">
            Acepto recibir recordatorios, avisos de confirmación y el enlace de gestión de mi cita por{" "}
            <strong>WhatsApp</strong> (RN-CO-01).
          </span>
        </label>
        {erroresLocales.optin_wa && (
          <p className="text-xs text-red-600 mt-1">{erroresLocales.optin_wa}</p>
        )}
      </div>

      <button
        type="submit"
        disabled={enviando}
        className="w-full py-3.5 px-4 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-400 text-white font-bold rounded-xl text-base shadow-sm transition-all"
      >
        {enviando ? "Confirmando tu reserva..." : "Reservar mi turno"}
      </button>
    </form>
  );
};
