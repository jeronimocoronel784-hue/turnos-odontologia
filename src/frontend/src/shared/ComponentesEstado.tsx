import { ErrorApi } from "./api-client";

export function EstadoCargando({ mensaje = "Cargando..." }: { mensaje?: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center p-8 text-slate-500 space-y-3"
    >
      <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
      <span className="text-sm font-medium">{mensaje}</span>
    </div>
  );
}

export function EstadoVacio({
  titulo,
  descripcion,
  accion,
}: {
  titulo: string;
  descripcion: string;
  accion?: {
    texto: string;
    onClick: () => void;
  };
}) {
  return (
    <div className="text-center py-12 px-4 border-2 border-dashed border-slate-200 rounded-lg bg-slate-50/50">
      <h3 className="text-base font-semibold text-slate-800">{titulo}</h3>
      <p className="mt-1 text-sm text-slate-500 max-w-sm mx-auto">{descripcion}</p>
      {accion && (
        <div className="mt-4">
          <button
            type="button"
            onClick={accion.onClick}
            className="inline-flex items-center px-3.5 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500"
          >
            {accion.texto}
          </button>
        </div>
      )}
    </div>
  );
}

export function formatearMensajeError(error: unknown): {
  titulo: string;
  descripcion: string;
  esPermiso: boolean;
} {
  if (error instanceof ErrorApi) {
    if (error.status === 403) {
      return {
        titulo: "Acceso no autorizado",
        descripcion:
          error.detalle ||
          "No tenés los permisos necesarios para realizar esta acción o ver este contenido.",
        esPermiso: true,
      };
    }
    if (error.status === 404) {
      return {
        titulo: "No encontrado",
        descripcion:
          "El elemento solicitado no existe o no pertenece a tu consultorio.",
        esPermiso: false,
      };
    }
    if (error.status >= 500) {
      return {
        titulo: "Inconveniente en el servidor",
        descripcion:
          "Ocurrió un problema momentáneo en el servidor. Por favor reintentá en unos instantes.",
        esPermiso: false,
      };
    }
    return {
      titulo: "Atención",
      descripcion: error.detalle || "Ocurrió un error al procesar tu solicitud.",
      esPermiso: false,
    };
  }

  return {
    titulo: "Error de conexión",
    descripcion:
      "No pudimos comunicarnos con el consultorio. Comprobá tu conexión a internet o reintentá.",
    esPermiso: false,
  };
}

export function EstadoError({
  error,
  alReintentar,
}: {
  error: unknown;
  alReintentar?: () => void;
}) {
  const { titulo, descripcion } = formatearMensajeError(error);

  return (
    <div
      role="alert"
      className="p-6 bg-red-50 border border-red-200 rounded-lg text-slate-800 max-w-lg mx-auto my-6"
    >
      <h3 className="text-base font-semibold text-red-800">{titulo}</h3>
      <p className="mt-2 text-sm text-red-700 leading-relaxed">{descripcion}</p>
      {alReintentar && (
        <div className="mt-4">
          <button
            type="button"
            onClick={alReintentar}
            className="inline-flex items-center px-3 py-1.5 border border-red-300 text-xs font-medium rounded text-red-800 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 shadow-sm"
          >
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
}
