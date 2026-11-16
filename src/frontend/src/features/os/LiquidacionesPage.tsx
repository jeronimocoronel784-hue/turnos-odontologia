import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useCoberturaOS,
  useLiquidacionesOS,
  useLiquidacionOSDetalle,
  useMutacionesOS,
} from "./queries";
import { descargarExportacionLiquidacion } from "./api";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import {
  compararMontosDecimales,
  formatearMontoARS,
  normalizarDecimalDosPosiciones,
} from "../../shared/formattersMonto";
import { formatearFechaHora } from "../../shared/formatters";
import { EstadoCargando, EstadoError, EstadoVacio } from "../../shared/ComponentesEstado";
import { CampoFormulario, TablaAccesible } from "../../shared/ComponentesUI";
import { ErrorApi } from "../../shared/api-client";
import type { LiquidacionOSRead } from "../../shared/api-types";

function validarPeriodoYYYYMM(valor: string): boolean {
  const limpio = valor.trim();
  if (!/^\d{6}$/.test(limpio)) return false;
  const mes = Number(limpio.slice(4, 6));
  return mes >= 1 && mes <= 12;
}

export function LiquidacionesPage() {
  // Consulta de Cobertura (4.1)
  const [prestacionConsulta, setPrestacionConsulta] = useState<string>("");
  const [osConsulta, setOsConsulta] = useState<string>("");
  const [consultaDisparada, setConsultaDisparada] = useState<{
    prestacion_id: string;
    obra_social?: string;
  } | null>(null);

  // Alta de Liquidación (4.2)
  const [osNueva, setOsNueva] = useState<string>("");
  const [periodoNuevo, setPeriodoNuevo] = useState<string>("202611");
  const [errorPeriodo, setErrorPeriodo] = useState<string | null>(null);
  const [errorOs, setErrorOs] = useState<string | null>(null);
  const [errorAlta, setErrorAlta] = useState<string | null>(null);
  const [conflictoExistenteId, setConflictoExistenteId] = useState<string | null>(null);
  const [exitoAlta, setExitoAlta] = useState<string | null>(null);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeCrear = permite(roles, "liquidaciones", "crear");

  const coberturaQuery = useCoberturaOS(
    consultaDisparada ?? {},
    Boolean(consultaDisparada?.prestacion_id),
  );
  const liquidacionesQuery = useLiquidacionesOS();
  const mutaciones = useMutacionesOS();

  const liquidaciones = liquidacionesQuery.data ?? [];

  const handleConsultarCobertura = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prestacionConsulta.trim()) return;
    setConsultaDisparada({
      prestacion_id: prestacionConsulta.trim(),
      obra_social: osConsulta.trim() || undefined,
    });
  };

  const handleCrearLiquidacion = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorOs(null);
    setErrorPeriodo(null);
    setErrorAlta(null);
    setConflictoExistenteId(null);
    setExitoAlta(null);

    let invalido = false;
    if (!osNueva.trim()) {
      setErrorOs("La obra social es obligatoria.");
      invalido = true;
    }
    if (!validarPeriodoYYYYMM(periodoNuevo)) {
      setErrorPeriodo("El período debe tener el formato 'yyyymm' (ej: 202611).");
      invalido = true;
    }
    if (invalido) return;

    try {
      const creada = await mutaciones.crearLiquidacion.mutateAsync({
        obra_social: osNueva.trim(),
        periodo: periodoNuevo.trim(),
      });
      setExitoAlta(`Borrador creado para ${creada.obra_social} (${creada.periodo}).`);
    } catch (err) {
      if (err instanceof ErrorApi && err.status === 409) {
        setErrorAlta(err.message);
        const existente = liquidaciones.find(
          (l) =>
            l.obra_social.toLowerCase() === osNueva.trim().toLowerCase() &&
            l.periodo === periodoNuevo.trim(),
        );
        setConflictoExistenteId(existente?.id ?? liquidaciones[0]?.id ?? "liq-existente");
      } else {
        setErrorAlta(err instanceof ErrorApi ? err.message : "Error al generar la liquidación.");
      }
    }
  };

  return (
    <div data-testid="liquidaciones-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Obras Sociales · Cobertura y Liquidaciones
        </h1>
        <p className="text-sm text-slate-600">
          Consulta de aranceles vigentes al agendar y facturación mensual con control de débitos (RN-OS-01 / RN-OS-02).
        </p>
      </div>

      {/* Consulta de Cobertura (4.1) */}
      <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
        <h2 className="text-base font-bold text-slate-900">
          Simulador de Cobertura al Agendar (US-040)
        </h2>
        <form
          onSubmit={handleConsultarCobertura}
          className="grid grid-cols-1 gap-3 sm:grid-cols-3"
        >
          <CampoFormulario id="cob-prestacion" label="ID de prestación a consultar" obligatorio>
            <input
              id="cob-prestacion"
              type="text"
              value={prestacionConsulta}
              onChange={(e) => setPrestacionConsulta(e.target.value)}
              placeholder="UUID o código de prestación..."
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-os" label="Obra social a consultar">
            <input
              id="cob-os"
              type="text"
              value={osConsulta}
              onChange={(e) => setOsConsulta(e.target.value)}
              placeholder="Ej: OSDE / Swiss Medical..."
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <div className="flex items-end">
            <button
              type="submit"
              className="w-full rounded-md bg-sky-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-sky-700"
            >
              Consultar cobertura
            </button>
          </div>
        </form>

        {coberturaQuery.error && (
          <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
            No pudimos verificar la cobertura en este momento. La atención puede continuar sin cobertura confirmada.
          </div>
        )}

        {coberturaQuery.data && (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            {coberturaQuery.data.arancel_vencido && coberturaQuery.data.advertencia && (
              <div
                role="alert"
                className="rounded border border-amber-300 bg-amber-50 p-2.5 text-xs font-medium text-amber-900"
              >
                {coberturaQuery.data.advertencia}
              </div>
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-xs">
              <div>
                <span className="block text-slate-500">Precio Particular</span>
                <strong className="text-sm font-mono">
                  {formatearMontoARS(coberturaQuery.data.precio_particular)}
                </strong>
              </div>
              <div>
                <span className="block text-slate-500">Cobertura OS</span>
                <strong className="text-sm font-mono text-sky-800">
                  {formatearMontoARS(coberturaQuery.data.cobertura)}
                </strong>
              </div>
              <div>
                <span className="block text-slate-500">Monto a Cargo del Paciente</span>
                <strong className="text-sm font-mono text-emerald-800">
                  {formatearMontoARS(coberturaQuery.data.monto_a_cargo)}
                </strong>
                {coberturaQuery.data.estado_arancel === "sin_cobertura" && (
                  <span className="block text-[11px] text-slate-600">
                    Sin cobertura vigente: se factura como particular (RN-OS-01).
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Alta de Liquidación (4.2) */}
      {puedeCrear && (
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <h2 className="text-base font-bold text-slate-900">
            Generar Nueva Liquidación Mensual
          </h2>
          {exitoAlta && (
            <div role="status" className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              {exitoAlta}
            </div>
          )}
          {errorAlta && (
            <div role="alert" className="space-y-2 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              <p>{errorAlta}</p>
              {conflictoExistenteId && (
                <Link
                  to={`/app/os/liquidaciones/${conflictoExistenteId}`}
                  className="inline-block font-semibold text-rose-900 underline"
                >
                  Abrir liquidación existente
                </Link>
              )}
            </div>
          )}

          <form
            onSubmit={handleCrearLiquidacion}
            noValidate
            className="grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            <CampoFormulario
              id="liq-os"
              label="Obra social a liquidar"
              obligatorio
              error={errorOs}
            >
              <input
                id="liq-os"
                type="text"
                value={osNueva}
                onChange={(e) => setOsNueva(e.target.value)}
                placeholder="Ej: OSDE..."
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>

            <CampoFormulario
              id="liq-periodo"
              label="Período (yyyymm)"
              obligatorio
              error={errorPeriodo}
            >
              <input
                id="liq-periodo"
                type="text"
                value={periodoNuevo}
                onChange={(e) => setPeriodoNuevo(e.target.value)}
                placeholder="202611"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>

            <div className="flex items-end">
              <button
                type="submit"
                disabled={mutaciones.crearLiquidacion.isPending}
                className="w-full rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
              >
                Generar borrador
              </button>
            </div>
          </form>
        </section>
      )}

      {/* Listado de Liquidaciones */}
      <section className="space-y-3">
        <h2 className="text-base font-bold text-slate-900">Liquidaciones del Consultorio</h2>
        {liquidacionesQuery.isLoading && <EstadoCargando mensaje="Cargando liquidaciones..." />}
        {liquidacionesQuery.error && <EstadoError error={liquidacionesQuery.error} />}

        {!liquidacionesQuery.isLoading && liquidaciones.length === 0 && (
          <EstadoVacio
            titulo="Sin liquidaciones registradas"
            descripcion="Recordá que solo los turnos en estado finalizado entran en la liquidación mensual (RN-OS-02)."
          />
        )}

        {liquidaciones.length > 0 && (
          <TablaAccesible
            caption="Liquidaciones por obra social y período"
            columnas={["Obra Social", "Período", "Estado", "Total Reclamado", "Total Reconocido", "Acción"]}
          >
            {liquidaciones.map((l) => (
              <tr key={l.id}>
                <td className="px-3 py-2 font-semibold">{l.obra_social}</td>
                <td className="px-3 py-2 font-mono">{l.periodo}</td>
                <td className="px-3 py-2">
                  <span className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-semibold">
                    {l.estado}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono font-semibold">
                  {formatearMontoARS(l.total)}
                </td>
                <td className="px-3 py-2 font-mono">
                  {l.total_reconocido !== null && l.total_reconocido !== undefined
                    ? formatearMontoARS(l.total_reconocido)
                    : "—"}
                </td>
                <td className="px-3 py-2">
                  <Link
                    to={`/app/os/liquidaciones/${l.id}`}
                    className="text-xs font-semibold text-emerald-700 hover:underline"
                  >
                    Ver detalle
                  </Link>
                </td>
              </tr>
            ))}
          </TablaAccesible>
        )}
      </section>
    </div>
  );
}

export function LiquidacionDetallePage() {
  const { id = "" } = useParams<{ id: string }>();
  const { data: liqRaw, isLoading, error } = useLiquidacionOSDetalle(id);
  const mutaciones = useMutacionesOS();

  const [liqOverride, setLiqOverride] = useState<LiquidacionOSRead | null>(null);
  const [resultadoTipo, setResultadoTipo] = useState<"pagada" | "con_debitos">("pagada");
  const [montoReconocidoInput, setMontoReconocidoInput] = useState<string>("");
  const [motivoDebitoInput, setMotivoDebitoInput] = useState<string>("");
  const [errorDebito, setErrorDebito] = useState<string | null>(null);

  const [motivoAnulacion, setMotivoAnulacion] = useState<string>("");
  const [errorAnulacion, setErrorAnulacion] = useState<string | null>(null);
  const [errorOperacion, setErrorOperacion] = useState<string | null>(null);
  const [exitoOperacion, setExitoOperacion] = useState<string | null>(null);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeActualizar = permite(roles, "liquidaciones", "actualizar");
  const puedeBorrar = permite(roles, "liquidaciones", "borrar");
  const puedeExportar = permite(roles, "liquidaciones", "exportar");

  const liq = liqOverride ?? liqRaw;

  if (isLoading) return <EstadoCargando mensaje="Cargando detalle de liquidación..." />;
  if (error || !liq) return <EstadoError error={error} />;

  const esAnulada = liq.estado === "anulada";

  const handleCerrar = async () => {
    setErrorOperacion(null);
    try {
      const cerrada = await mutaciones.cerrarLiquidacion.mutateAsync({ id: liq.id });
      setLiqOverride(cerrada);
      setExitoOperacion("Liquidación presentada correctamente.");
    } catch (err) {
      setErrorOperacion(err instanceof ErrorApi ? err.message : "No pudimos cerrar la liquidación.");
    }
  };

  const handleRegistrarResultado = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDebito(null);
    setErrorOperacion(null);

    const primerTurno = liq.detalles[0];
    const recNorm = normalizarDecimalDosPosiciones(
      montoReconocidoInput || primerTurno?.monto_reclamado || liq.total,
    );

    const hayRecorte =
      resultadoTipo === "con_debitos" ||
      (primerTurno && compararMontosDecimales(recNorm, primerTurno.monto_reclamado) < 0);

    if (hayRecorte && !motivoDebitoInput.trim()) {
      setErrorDebito("Todo débito exige un motivo de recorte obligatorio (US-041).");
      return;
    }

    try {
      const resuelta = await mutaciones.registrarResultado.mutateAsync({
        id: liq.id,
        datos: {
          resultado: resultadoTipo,
          detalles: primerTurno
            ? [
                {
                  turno_id: primerTurno.turno_id,
                  monto_reconocido: recNorm,
                  debito_motivo: motivoDebitoInput.trim() || undefined,
                },
              ]
            : [],
        },
      });
      setLiqOverride(resuelta);
      setExitoOperacion(`Resultado registrado: ${resuelta.estado}.`);
    } catch (err) {
      setErrorOperacion(err instanceof ErrorApi ? err.message : "Error al registrar resultado.");
    }
  };

  const handleAnular = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorAnulacion(null);
    setErrorOperacion(null);

    if (!motivoAnulacion.trim()) {
      setErrorAnulacion("La anulación exige un motivo obligatorio.");
      return;
    }

    try {
      const anulada = await mutaciones.anularLiquidacion.mutateAsync({
        id: liq.id,
        datos: { motivo: motivoAnulacion.trim() },
      });
      setLiqOverride(anulada);
    } catch (err) {
      setErrorOperacion(err instanceof ErrorApi ? err.message : "Error al anular la liquidación.");
    }
  };

  const handleExportar = async (formato: "csv" | "json") => {
    setErrorOperacion(null);
    try {
      const nombre = await descargarExportacionLiquidacion(
        liq.id,
        formato,
        `liquidacion-${liq.obra_social}-${liq.periodo}`,
      );
      setExitoOperacion(`Archivo ${nombre} descargado.`);
    } catch (err) {
      setErrorOperacion(err instanceof ErrorApi ? err.message : "No pudimos exportar el archivo.");
    }
  };

  return (
    <div data-testid="liquidacion-detalle-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Liquidación · {liq.obra_social} ({liq.periodo})
          </h1>
          <p className="text-sm text-slate-600">
            Estado actual:{" "}
            <strong className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs uppercase">
              {liq.estado}
            </strong>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!esAnulada && puedeExportar && (
            <>
              <button
                type="button"
                onClick={() => void handleExportar("csv")}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-50"
              >
                Exportar CSV
              </button>
              <button
                type="button"
                onClick={() => void handleExportar("json")}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-50"
              >
                Exportar JSON
              </button>
            </>
          )}
          <Link
            to="/app/os/liquidaciones"
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Volver al listado
          </Link>
        </div>
      </div>

      {exitoOperacion && (
        <div role="status" className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {exitoOperacion}
        </div>
      )}

      {errorOperacion && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorOperacion}
        </div>
      )}

      {/* Advertencias y turnos sin cobertura (4.3) */}
      {(liq.turnos_sin_cobertura > 0 || liq.advertencias.length > 0) && (
        <div
          role="alert"
          className="space-y-1 rounded-lg border border-amber-300 bg-amber-50 p-3.5 text-xs text-amber-900"
        >
          <strong className="block text-sm">
            Advertencias del servidor (Turnos sin cobertura: {liq.turnos_sin_cobertura})
          </strong>
          {liq.advertencias.map((adv, i) => (
            <p key={i}>{adv}</p>
          ))}
        </div>
      )}

      {esAnulada && liq.anulada_motivo && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          Liquidación anulada (solo lectura). Motivo: <strong>{liq.anulada_motivo}</strong>
        </div>
      )}

      {/* Totales del servidor */}
      <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-3">
        <div>
          <span className="block text-xs text-slate-500">Total Reclamado</span>
          <strong className="text-lg font-mono text-slate-900">
            {formatearMontoARS(liq.total)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Total Reconocido</span>
          <strong className="text-lg font-mono text-emerald-800">
            {liq.total_reconocido !== null && liq.total_reconocido !== undefined
              ? formatearMontoARS(liq.total_reconocido)
              : "Pendiente de resultado"}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Saldo Débito</span>
          <strong className="text-lg font-mono text-rose-700">
            {liq.saldo_debito !== null && liq.saldo_debito !== undefined
              ? formatearMontoARS(liq.saldo_debito)
              : "—"}
          </strong>
        </div>
      </div>

      {/* Detalles por turno */}
      <section className="space-y-3">
        <h2 className="text-base font-bold text-slate-900">Turnos Incluidos</h2>
        {liq.detalles.length === 0 ? (
          <EstadoVacio
            titulo="Sin turnos liquidados en este período"
            descripcion="Solo los turnos en estado finalizado entran en la liquidación (RN-OS-02)."
          />
        ) : (
          <TablaAccesible
            caption="Detalle de turnos de la liquidación"
            columnas={["Fecha", "Prestación", "Reclamado", "Reconocido", "Motivo de Débito"]}
          >
            {liq.detalles.map((d) => (
              <tr key={d.id}>
                <td className="px-3 py-2 text-xs">{formatearFechaHora(d.fecha_turno)}</td>
                <td className="px-3 py-2 font-medium">{d.prestacion}</td>
                <td className="px-3 py-2 font-mono">{formatearMontoARS(d.monto_reclamado)}</td>
                <td className="px-3 py-2 font-mono">
                  {d.monto_reconocido !== null && d.monto_reconocido !== undefined
                    ? formatearMontoARS(d.monto_reconocido)
                    : "—"}
                </td>
                <td className="px-3 py-2 text-xs text-rose-700">{d.debito_motivo ?? "—"}</td>
              </tr>
            ))}
          </TablaAccesible>
        )}
      </section>

      {/* Acciones sobre borrador: presentar o anular */}
      {!esAnulada && liq.estado === "borrador" && puedeActualizar && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void handleCerrar()}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            Presentar / Cerrar liquidación
          </button>
        </div>
      )}

      {/* Registrar Resultado / Débitos cuando está presentada (4.4) */}
      {!esAnulada && liq.estado === "presentada" && puedeActualizar && (
        <form
          onSubmit={handleRegistrarResultado}
          noValidate
          className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
        >
          <h2 className="text-sm font-bold text-slate-900">
            Registrar Resultado de la Obra Social (US-041)
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <CampoFormulario id="res-tipo" label="Resultado de la obra social" obligatorio>
              <select
                id="res-tipo"
                value={resultadoTipo}
                onChange={(e) => setResultadoTipo(e.target.value as "pagada" | "con_debitos")}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="pagada">Pagada (total)</option>
                <option value="con_debitos">Con débitos (recorte)</option>
              </select>
            </CampoFormulario>

            <CampoFormulario id="res-monto" label="Monto reconocido turno" obligatorio>
              <input
                id="res-monto"
                type="number"
                step="0.01"
                value={montoReconocidoInput}
                onChange={(e) => setMontoReconocidoInput(e.target.value)}
                placeholder={liq.total}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>

            <CampoFormulario
              id="res-motivo"
              label="Motivo del débito"
              error={errorDebito}
            >
              <input
                id="res-motivo"
                type="text"
                value={motivoDebitoInput}
                onChange={(e) => setMotivoDebitoInput(e.target.value)}
                placeholder="Obligatorio si hay débito..."
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-sky-700"
            >
              Registrar resultado
            </button>
          </div>
        </form>
      )}

      {/* Anulación con motivo obligatorio (4.5) */}
      {!esAnulada && liq.estado === "borrador" && puedeBorrar && (
        <form
          onSubmit={handleAnular}
          noValidate
          className="space-y-3 rounded-lg border border-rose-200 bg-rose-50/40 p-4"
        >
          <h2 className="text-sm font-bold text-rose-900">Anular Liquidación (Baja Lógica · R7)</h2>
          <CampoFormulario
            id="motivo-anulacion-liq"
            label="Motivo de anulación"
            obligatorio
            error={errorAnulacion}
          >
            <input
              id="motivo-anulacion-liq"
              type="text"
              value={motivoAnulacion}
              onChange={(e) => setMotivoAnulacion(e.target.value)}
              placeholder="Indicá el motivo de la anulación..."
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <button
            type="submit"
            className="rounded-md bg-rose-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
          >
            Anular liquidación
          </button>
        </form>
      )}
    </div>
  );
}
