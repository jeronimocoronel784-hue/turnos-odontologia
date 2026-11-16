import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useLiquidacionTurno, useMutacionesCaja } from "../caja/queries";
import {
  compararMontosDecimales,
  formatearMontoARS,
} from "../../shared/formattersMonto";
import { EstadoCargando, EstadoError } from "../../shared/ComponentesEstado";
import { CampoFormulario } from "../../shared/ComponentesUI";
import { ErrorApi } from "../../shared/api-client";
import type { MedioPago, MovimientoCajaRead } from "../../shared/api-types";

export function CobroTurnoPage() {
  const { turnoId = "" } = useParams<{ turnoId: string }>();
  const [obraSocialInput, setObraSocialInput] = useState<string>("");
  const [obraSocialAplicada, setObraSocialAplicada] = useState<string | undefined>(undefined);
  const [medio, setMedio] = useState<MedioPago>("efectivo");
  const [movimientoGenerado, setMovimientoGenerado] = useState<MovimientoCajaRead | null>(null);
  const [errorCobro, setErrorCobro] = useState<string | null>(null);

  const { data: liquidacion, isLoading, error } = useLiquidacionTurno(turnoId, obraSocialAplicada);
  const mutaciones = useMutacionesCaja();

  if (isLoading) return <EstadoCargando mensaje="Calculando liquidación de la atención en servidor..." />;
  if (error || !liquidacion) return <EstadoError error={error} />;

  const saldoEsCero =
    compararMontosDecimales(liquidacion.saldo, "0.00") <= 0 || Boolean(movimientoGenerado);

  const handleCobrar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saldoEsCero) return;
    setErrorCobro(null);

    try {
      const mov = await mutaciones.cobrarSaldoTurno.mutateAsync({
        turnoId,
        datos: {
          medio,
          obra_social: obraSocialAplicada || liquidacion.obra_social || undefined,
        },
      });
      setMovimientoGenerado(mov);
    } catch (err) {
      setErrorCobro(
        err instanceof ErrorApi
          ? err.message
          : "No pudimos registrar el cobro del turno.",
      );
    }
  };

  return (
    <div data-testid="cobro-turno-page" className="space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cobro de Atención</h1>
          <p className="text-sm text-slate-600">
            Liquidación calculada íntegramente por el servidor (R8, Flujo 4).
          </p>
        </div>
        <Link
          to="/app/caja"
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          Ir a Caja Diaria
        </Link>
      </div>

      {/* Selector opcional de cobertura para recalcular en servidor */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setObraSocialAplicada(obraSocialInput.trim() || undefined);
        }}
        className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3"
      >
        <CampoFormulario id="os-turno-cobro" label="Obra social a consultar en servidor">
          <input
            id="os-turno-cobro"
            type="text"
            value={obraSocialInput}
            onChange={(e) => setObraSocialInput(e.target.value)}
            placeholder={liquidacion.obra_social ?? "Particular (sin OS)"}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
          />
        </CampoFormulario>
        <button
          type="submit"
          className="rounded bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
        >
          Recalcular en servidor
        </button>
      </form>

      {/* Los 4 importes del servidor (R8) */}
      <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-4">
        <div>
          <span className="block text-xs text-slate-500">Precio Particular</span>
          <strong className="text-lg font-mono text-slate-900">
            {formatearMontoARS(liquidacion.precio_particular)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Cobertura Obra Social</span>
          <strong className="text-lg font-mono text-sky-800">
            {formatearMontoARS(liquidacion.cobertura_os)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Seña Cobrada</span>
          <strong className="text-lg font-mono text-emerald-700">
            {formatearMontoARS(liquidacion.sena_cobrada)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Saldo a Cobrar</span>
          <strong className="text-lg font-mono font-bold text-slate-900">
            {movimientoGenerado ? formatearMontoARS("0.00") : formatearMontoARS(liquidacion.saldo)}
          </strong>
        </div>
      </div>

      {errorCobro && (
        <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorCobro}
        </div>
      )}

      {movimientoGenerado && (
        <div
          role="status"
          className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"
        >
          Atención saldada correctamente. Movimiento generado por{" "}
          <strong>{formatearMontoARS(movimientoGenerado.monto)}</strong> ({movimientoGenerado.medio}).
        </div>
      )}

      {saldoEsCero && !movimientoGenerado && (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          La atención ya está saldada (saldo cero). No quedan importes pendientes de cobro.
        </div>
      )}

      <form
        onSubmit={handleCobrar}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4"
      >
        <CampoFormulario id="medio-cobro-turno" label="Medio de pago" obligatorio>
          <select
            id="medio-cobro-turno"
            value={medio}
            onChange={(e) => setMedio(e.target.value as MedioPago)}
            disabled={saldoEsCero}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
          >
            <option value="efectivo">Efectivo</option>
            <option value="transferencia">Transferencia</option>
            <option value="mercadopago">Mercado Pago</option>
            <option value="tarjeta">Tarjeta</option>
          </select>
        </CampoFormulario>

        <button
          type="submit"
          disabled={saldoEsCero || mutaciones.cobrarSaldoTurno.isPending}
          className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Cobrar saldo de la atención
        </button>
      </form>
    </div>
  );
}
