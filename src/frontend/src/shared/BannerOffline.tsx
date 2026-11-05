import React, { useEffect, useState } from "react";

/**
 * Aviso global de conexión (C-15, US-063).
 *
 * La app es una PWA instalable: si el paciente pierde internet, mostramos un
 * mensaje claro en vez de dejar botones que fallen sin explicación. No se
 * persisten datos clínicos ni de pacientes en el dispositivo (R6/R9): sólo se
 * avisa que las acciones que requieren red van a fallar hasta reconectar.
 */
export const BannerOffline: React.FC = () => {
  const [enLinea, setEnLinea] = useState<boolean>(() =>
    typeof navigator === "undefined" ? true : navigator.onLine
  );

  useEffect(() => {
    const alConectar = () => setEnLinea(true);
    const alDesconectar = () => setEnLinea(false);
    window.addEventListener("online", alConectar);
    window.addEventListener("offline", alDesconectar);
    return () => {
      window.removeEventListener("online", alConectar);
      window.removeEventListener("offline", alDesconectar);
    };
  }, []);

  if (enLinea) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 bottom-0 z-50 bg-amber-500 text-amber-950 px-4 py-3 text-center text-sm font-semibold shadow-lg"
    >
      Estás sin internet. Podés seguir mirando la app, pero para reservar, pagar o cancelar
      necesitás reconectarte.
    </div>
  );
};
