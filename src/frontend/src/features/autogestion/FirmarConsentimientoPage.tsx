import React, { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { firmarConsentimiento, obtenerConsentimiento } from "../../shared/reserva-api";
import { formatearFechaHora } from "../../shared/formatters";

function contextoDeDibujo(canvas: HTMLCanvasElement): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.strokeStyle = "#0f172a";
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  return ctx;
}

/** Convierte coordenadas del puntero al espacio interno del canvas (que puede estar escalado por CSS). */
function coordenadasCanvas(
  canvas: HTMLCanvasElement,
  evento: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>
): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect();
  const clienteX = "touches" in evento ? evento.touches[0].clientX : evento.clientX;
  const clienteY = "touches" in evento ? evento.touches[0].clientY : evento.clientY;
  return {
    x: ((clienteX - rect.left) * canvas.width) / rect.width,
    y: ((clienteY - rect.top) * canvas.height) / rect.height,
  };
}

export const FirmarConsentimientoPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [dibujando, setDibujando] = useState(false);
  const [tieneTrazo, setTieneTrazo] = useState(false);
  const [leido, setLeido] = useState(false);
  const [firmadoPor, setFirmadoPor] = useState("");
  const [firmaHash, setFirmaHash] = useState<string | null>(null);
  const [errorFirma, setErrorFirma] = useState<string | null>(null);

  const {
    data: consentimiento,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["consentimiento", token],
    queryFn: ({ signal }) => obtenerConsentimiento(token ?? "", signal),
    enabled: Boolean(token),
  });

  const mutationFirmar = useMutation({
    mutationFn: (firmaBase64: string) =>
      firmarConsentimiento(token ?? "", {
        firmado_por: firmadoPor.trim(),
        firma_datos: firmaBase64,
        canal: "token",
      }),
    onSuccess: (firmado) => {
      setFirmaHash(firmado.firma_hash);
      setErrorFirma(null);
      void refetch();
    },
    onError: (err: Error) => {
      setErrorFirma(err.message);
    },
  });

  const iniciarDibujo = (
    e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>
  ) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = contextoDeDibujo(canvas);
    if (!ctx) return;
    const { x, y } = coordenadasCanvas(canvas, e);
    ctx.beginPath();
    ctx.moveTo(x, y);
    setDibujando(true);
  };

  const dibujar = (
    e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>
  ) => {
    if (!dibujando) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = contextoDeDibujo(canvas);
    if (!ctx) return;
    const { x, y } = coordenadasCanvas(canvas, e);
    ctx.lineTo(x, y);
    ctx.stroke();
    setTieneTrazo(true);
  };

  const limpiarCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setTieneTrazo(false);
    setErrorFirma(null);
  };

  const handleEnviarFirma = () => {
    const canvas = canvasRef.current;
    if (!canvas || !tieneTrazo) {
      setErrorFirma("Por favor estampá tu firma en el recuadro antes de continuar.");
      return;
    }
    if (firmadoPor.trim().length < 3) {
      setErrorFirma("Escribí tu nombre y apellido tal como figuran en tu DNI.");
      return;
    }
    if (!leido) {
      setErrorFirma("Tenés que confirmar que leíste y comprendiste el consentimiento.");
      return;
    }
    mutationFirmar.mutate(canvas.toDataURL("image/png"));
  };

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
        <div className="w-10 h-10 border-4 border-teal-700 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Cargando consentimiento...</p>
      </div>
    );
  }

  if (error || !consentimiento) {
    return (
      <div className="max-w-md mx-auto my-12 p-8 bg-white rounded-2xl border border-gray-200 shadow-sm text-center">
        <h1 className="text-xl font-bold text-gray-900 mb-2">Consentimiento no encontrado</h1>
        <p className="text-sm text-gray-600 mb-6">El enlace ya no es válido o ya fue procesado.</p>
        <Link
          to="/"
          className="inline-block py-2.5 px-5 bg-teal-800 text-white rounded-lg text-sm font-semibold hover:bg-teal-900"
        >
          Ir al inicio
        </Link>
      </div>
    );
  }

  const yaFirmado = consentimiento.firmado;

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-lg mx-auto space-y-6">
        <header className="text-center">
          <span className="inline-block px-3 py-1 bg-amber-100 text-amber-900 text-xs font-semibold rounded-full mb-2">
            Documento Médico Legal
          </span>
          <h1 className="text-2xl font-black text-gray-900">Consentimiento Informado</h1>
          <p className="text-xs text-gray-500 mt-1">Firma digital obligatoria para tu atención clínica</p>
        </header>

        <div className="bg-white rounded-2xl border border-gray-200 p-6 sm:p-8 shadow-sm space-y-6">
          {consentimiento.revocado ? (
            <div className="text-center py-6 space-y-4">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-100 text-red-700 text-2xl font-bold">
                !
              </div>
              <h2 className="text-xl font-bold text-gray-900">Consentimiento revocado</h2>
              <p className="text-sm text-gray-600">
                Este consentimiento ya no está vigente. El consultorio tiene que emitir uno nuevo
                antes de la prestación.
              </p>
            </div>
          ) : yaFirmado ? (
            <div className="text-center py-6 space-y-4">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 text-green-700 text-2xl font-bold">
                ✓
              </div>
              <h2 className="text-xl font-bold text-gray-900">Consentimiento Firmado</h2>
              <p className="text-sm text-gray-600">
                Tu firma digital quedó registrada de forma inmutable y adjunta a tu historia clínica.
              </p>
              {consentimiento.firmado_at && (
                <p className="text-xs text-gray-400">
                  Fecha: {formatearFechaHora(consentimiento.firmado_at)}
                </p>
              )}
              {firmaHash && (
                <div className="p-3 bg-gray-50 rounded-lg text-[10px] text-gray-500 font-mono break-all border border-gray-100">
                  Hash de integridad SHA-256: {firmaHash}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <h2 className="text-base font-bold text-gray-900">Texto del consentimiento</h2>
                  <span className="text-[10px] text-gray-400 font-mono">
                    versión {consentimiento.texto_version}
                  </span>
                </div>
                <div className="max-h-56 overflow-y-auto p-4 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-700 leading-relaxed whitespace-pre-line">
                  {consentimiento.texto_contenido}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Nombre y apellido de quien firma <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={firmadoPor}
                  onChange={(e) => setFirmadoPor(e.target.value)}
                  placeholder="Ej: Juan Pérez"
                  className="w-full p-3 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-700 focus:border-teal-700"
                />
              </div>

              <label className="flex items-start gap-2.5 cursor-pointer text-xs text-gray-700">
                <input
                  type="checkbox"
                  checked={leido}
                  onChange={(e) => setLeido(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-700 focus:ring-teal-700"
                />
                <span>
                  Declaro que leí, comprendí y acepté los términos del procedimiento odontológico.
                </span>
              </label>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-xs font-semibold text-gray-700">
                    Estampá tu firma acá abajo:
                  </span>
                  <button
                    type="button"
                    onClick={limpiarCanvas}
                    className="text-xs text-teal-800 hover:text-teal-950 font-medium"
                  >
                    Borrar y reintentar
                  </button>
                </div>
                <div className="border-2 border-dashed border-gray-300 rounded-xl bg-gray-50 overflow-hidden touch-none">
                  <canvas
                    ref={canvasRef}
                    width={400}
                    height={160}
                    className="w-full h-40 cursor-crosshair"
                    onMouseDown={iniciarDibujo}
                    onMouseMove={dibujar}
                    onMouseUp={() => setDibujando(false)}
                    onMouseLeave={() => setDibujando(false)}
                    onTouchStart={iniciarDibujo}
                    onTouchMove={dibujar}
                    onTouchEnd={() => setDibujando(false)}
                  />
                </div>
                <p className="text-[11px] text-gray-400 mt-1 text-center">
                  Podés firmar con el dedo desde tu celular o con el puntero del mouse.
                </p>
              </div>

              {errorFirma && (
                <p role="alert" className="text-xs text-red-600 font-medium text-center">
                  {errorFirma}
                </p>
              )}

              <button
                type="button"
                onClick={handleEnviarFirma}
                disabled={mutationFirmar.isPending}
                className="w-full py-3.5 px-4 bg-teal-800 hover:bg-teal-900 disabled:bg-gray-400 text-white font-bold rounded-xl text-sm shadow-sm transition-all"
              >
                {mutationFirmar.isPending ? "Validando firma..." : "Confirmar y firmar digitalmente"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
