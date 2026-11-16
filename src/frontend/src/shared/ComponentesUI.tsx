import type { ReactNode } from "react";

export interface TablaAccesibleProps {
  caption: string;
  columnas: readonly string[];
  children: ReactNode;
}

export function TablaAccesible({ caption, columnas, children }: TablaAccesibleProps) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-xs">
      <table aria-label={caption} className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase text-slate-600">
          <tr>
            {columnas.map((col) => (
              <th key={col} scope="col" className="px-3 py-2.5">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 text-slate-800">{children}</tbody>
      </table>
    </div>
  );
}

export interface CampoFormularioProps {
  id: string;
  label: string;
  obligatorio?: boolean;
  error?: string | null;
  ayuda?: string;
  children: ReactNode;
}

export function CampoFormulario({
  id,
  label,
  obligatorio = false,
  error,
  ayuda,
  children,
}: CampoFormularioProps) {
  const errorId = `${id}-error`;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-slate-700">
        {label}
        {obligatorio && (
          <span aria-hidden="true" className="ml-0.5 text-rose-600">
            *
          </span>
        )}
      </label>
      {children}
      {ayuda && !error && <p className="text-xs text-slate-500">{ayuda}</p>}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-medium text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
}

export interface DialogoConfirmacionProps {
  abierto: boolean;
  titulo: string;
  descripcion: string;
  textoConfirmar?: string;
  textoCancelar?: string;
  destructivo?: boolean;
  cargando?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
  children?: ReactNode;
}

export function DialogoConfirmacion({
  abierto,
  titulo,
  descripcion,
  textoConfirmar = "Confirmar",
  textoCancelar = "Cancelar",
  destructivo = false,
  cargando = false,
  onConfirmar,
  onCancelar,
  children,
}: DialogoConfirmacionProps) {
  if (!abierto) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialogo-titulo"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
    >
      <div className="w-full max-w-md space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-xl">
        <div className="space-y-1">
          <h3 id="dialogo-titulo" className="text-base font-bold text-slate-900">
            {titulo}
          </h3>
          <p className="text-sm text-slate-600">{descripcion}</p>
        </div>

        {children}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancelar}
            className="rounded-md border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
          >
            {textoCancelar}
          </button>
          <button
            type="button"
            disabled={cargando}
            onClick={onConfirmar}
            className={`rounded-md px-3.5 py-1.5 text-xs font-semibold text-white focus:ring-2 focus:outline-none disabled:opacity-50 ${
              destructivo
                ? "bg-rose-600 hover:bg-rose-700 focus:ring-rose-500"
                : "bg-emerald-600 hover:bg-emerald-700 focus:ring-emerald-500"
            }`}
          >
            {cargando ? "Procesando..." : textoConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
