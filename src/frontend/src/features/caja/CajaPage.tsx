import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useCierreDetalle,
  useCierresCaja,
  useMovimientosCaja,
  useMutacionesCaja,
  useSenas,
} from "./queries";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import {
  clasificarDiferenciaCaja,
  compararMontosDecimales,
  formatearMontoARS,
  normalizarDecimalDosPosiciones,
} from "../../shared/formattersMonto";
import { formatearFechaHora } from "../../shared/formatters";
import { EstadoCargando, EstadoError, EstadoVacio } from "../../shared/ComponentesEstado";
import {
  CampoFormulario,
  DialogoConfirmacion,
  TablaAccesible,
} from "../../shared/ComponentesUI";
import { ErrorApi } from "../../shared/api-client";
import type {
  CierreCajaRead,
  MedioPago,
  SenaRead,
  TipoMovimientoCaja,
} from "../../shared/api-types";

function etiquetaDiferencia(dif: string | null | undefined): string {
  const tipo = clasificarDiferenciaCaja(dif);
  if (tipo === "cuadrada") return "Caja cuadrada (sin diferencia)";
  if (tipo === "sobrante") return `Sobrante (${formatearMontoARS(dif)})`;
  return `Faltante (${formatearMontoARS(dif)})`;
}

export function CajaPage() {
  const hoyISO = new Date().toISOString().slice(0, 10);
  const [fechaFiltro, setFechaFiltro] = useState<string>(hoyISO);
  const [medioFiltro, setMedioFiltro] = useState<string>("");
  const [tipoFiltro, setTipoFiltro] = useState<string>("");
  const [estadoSenaFiltro, setEstadoSenaFiltro] = useState<string>("");

  // Formulario de nuevo movimiento
  const [tipoMov, setTipoMov] = useState<TipoMovimientoCaja>("ingreso");
  const [conceptoMov, setConceptoMov] = useState<string>("");
  const [medioMov, setMedioMov] = useState<MedioPago>("efectivo");
  const [montoMov, setMontoMov] = useState<string>("");
  const [errorConcepto, setErrorConcepto] = useState<string | null>(null);
  const [errorMonto, setErrorMonto] = useState<string | null>(null);

  // Apertura y cierre
  const [fechaApertura, setFechaApertura] = useState<string>(hoyISO);
  const [totalContado, setTotalContado] = useState<string>("");
  const [errorContado, setErrorContado] = useState<string | null>(null);
  const [dialogoDiferencia, setDialogoDiferencia] = useState<{
    abierto: boolean;
    cierreId: string;
    contadoNorm: string;
    clasificacion: "sobrante" | "faltante";
  } | null>(null);

  // Overrides locales para reflejar mutaciones de forma inmediata
  const [cierreOverride, setCierreOverride] = useState<CierreCajaRead | null>(null);
  const [senasOverride, setSenasOverride] = useState<Record<string, SenaRead>>({});

  // Mensajes de operación
  const [avisoExito, setAvisoExito] = useState<string | null>(null);
  const [avisoInfo, setAvisoInfo] = useState<string | null>(null);
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEscribirCaja = permite(roles, "caja", "crear");
  const puedeActualizarCaja = permite(roles, "caja", "actualizar");

  const desdeISO = `${fechaFiltro}T00:00:00Z`;
  const hastaISO = `${fechaFiltro}T23:59:59Z`;

  const cierresQuery = useCierresCaja({ fecha: fechaFiltro });
  const movimientosQuery = useMovimientosCaja({
    desde: desdeISO,
    hasta: hastaISO,
    medio: medioFiltro || undefined,
    tipo: tipoFiltro || undefined,
  });
  const senasQuery = useSenas({ estado: estadoSenaFiltro || undefined });
  const mutaciones = useMutacionesCaja();

  const cierresLista = cierresQuery.data ?? [];
  const cierreDelDia = cierreOverride ?? cierresLista[0] ?? null;
  const hayCierreAbierto = cierreDelDia?.estado === "abierto";

  const movimientos = movimientosQuery.data ?? [];
  const senas = (senasQuery.data ?? []).map((s) => senasOverride[s.id] ?? s);

  const handleCrearMovimiento = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorConcepto(null);
    setErrorMonto(null);
    setErrorGeneral(null);
    setAvisoExito(null);

    let invalido = false;
    if (!conceptoMov.trim()) {
      setErrorConcepto("El concepto es obligatorio.");
      invalido = true;
    }
    const montoNum = Number(montoMov);
    if (!montoMov.trim() || Number.isNaN(montoNum) || montoNum <= 0) {
      setErrorMonto("El monto debe ser mayor a cero.");
      invalido = true;
    }
    if (invalido) return;

    try {
      await mutaciones.crearMovimiento.mutateAsync({
        tipo: tipoMov,
        concepto: conceptoMov.trim(),
        medio: medioMov,
        monto: normalizarDecimalDosPosiciones(montoMov),
      });
      setConceptoMov("");
      setMontoMov("");
      setAvisoExito("Movimiento registrado con el monto confirmado por el servidor.");
    } catch (err) {
      setErrorGeneral(
        err instanceof ErrorApi ? err.message : "No pudimos registrar el movimiento.",
      );
    }
  };

  const handleAbrirCierre = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorGeneral(null);
    setAvisoExito(null);
    setAvisoInfo(null);

    if (!fechaApertura.trim()) {
      setErrorGeneral("Seleccioná una fecha válida para abrir la caja.");
      return;
    }

    try {
      const nuevo = await mutaciones.abrirCierre.mutateAsync({ fecha: fechaApertura.trim() });
      setCierreOverride(nuevo);
      setAvisoExito(`Cierre abierto para la fecha ${nuevo.fecha}.`);
    } catch (err) {
      if (err instanceof ErrorApi && err.status === 409) {
        setErrorGeneral(err.message);
        setAvisoInfo("Cierre existente cargado para operar sobre él sin duplicar la apertura.");
        void cierresQuery.refetch();
      } else {
        setErrorGeneral(
          err instanceof ErrorApi ? err.message : "No pudimos abrir el cierre del día.",
        );
      }
    }
  };

  const ejecutarCierre = async (cierreId: string, contadoNorm: string) => {
    try {
      const cerrado = await mutaciones.cerrarCierre.mutateAsync({
        id: cierreId,
        datos: { total_contado: contadoNorm },
      });
      setCierreOverride(cerrado);
      setDialogoDiferencia(null);
      setAvisoExito("Caja cerrada correctamente con los totales del servidor.");
    } catch (err) {
      setDialogoDiferencia(null);
      setErrorGeneral(err instanceof ErrorApi ? err.message : "Error al cerrar la caja.");
    }
  };

  const handleIntentarCerrarCaja = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cierreDelDia) return;
    setErrorContado(null);
    setErrorGeneral(null);

    const num = Number(totalContado);
    if (!totalContado.trim() || Number.isNaN(num) || num < 0) {
      setErrorContado("Ingresá un total contado válido (mayor o igual a cero).");
      return;
    }

    const contadoNorm = normalizarDecimalDosPosiciones(totalContado);
    const cmp = compararMontosDecimales(contadoNorm, cierreDelDia.total_sistema);

    if (cmp !== 0) {
      setDialogoDiferencia({
        abierto: true,
        cierreId: cierreDelDia.id,
        contadoNorm,
        clasificacion: cmp > 0 ? "sobrante" : "faltante",
      });
      return;
    }

    await ejecutarCierre(cierreDelDia.id, contadoNorm);
  };

  const handleCobrarSena = async (sena: SenaRead) => {
    setErrorGeneral(null);
    try {
      const cobrada = await mutaciones.cobrarSenaMut.mutateAsync({
        id: sena.id,
        datos: { medio: "efectivo" },
      });
      setSenasOverride((prev) => ({ ...prev, [cobrada.id]: cobrada }));
      setAvisoExito("Seña marcada como cobrada.");
    } catch (err) {
      setErrorGeneral(err instanceof ErrorApi ? err.message : "No pudimos cobrar la seña.");
    }
  };

  const handleAusenciaSena = async (sena: SenaRead) => {
    setErrorGeneral(null);
    try {
      const resuelta = await mutaciones.cancelarSenaMut.mutateAsync({
        id: sena.id,
        datos: { ausente: true, motivo: "Paciente ausente al turno" },
      });
      setSenasOverride((prev) => ({ ...prev, [resuelta.id]: resuelta }));
      setAvisoExito(`Seña resuelta por ausencia: estado ${resuelta.estado}.`);
    } catch (err) {
      setErrorGeneral(err instanceof ErrorApi ? err.message : "No pudimos resolver la seña.");
    }
  };

  const handleVencerSena = async (sena: SenaRead) => {
    setErrorGeneral(null);
    try {
      const vencida = await mutaciones.vencerSenaMut.mutateAsync(sena.id);
      setSenasOverride((prev) => ({ ...prev, [vencida.id]: vencida }));
      setAvisoExito("Seña marcada como vencida.");
    } catch (err) {
      setErrorGeneral(err instanceof ErrorApi ? err.message : "No pudimos vencer la seña.");
    }
  };

  return (
    <div data-testid="caja-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Caja Diaria y Señas</h1>
          <p className="text-sm text-slate-600">
            Movimientos de ingreso y egreso, arqueo de cierre diario y gestión de señas (RN-PA-01 / RN-PA-05).
          </p>
        </div>

        {!puedeEscribirCaja && (
          <span className="inline-flex items-center rounded-md border border-slate-300 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            Modo solo lectura
          </span>
        )}
      </div>

      {avisoExito && (
        <div
          role="status"
          className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          {avisoExito}
        </div>
      )}

      {avisoInfo && (
        <div
          role="status"
          className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"
        >
          {avisoInfo}
        </div>
      )}

      {errorGeneral && (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          {errorGeneral}
        </div>
      )}

      {/* Aviso de falta de cierre abierto (2.4) */}
      {! cierresQuery.isLoading && !hayCierreAbierto && (
        <div
          role="alert"
          data-testid="aviso-sin-cierre-abierto"
          className="rounded-md border border-amber-300 bg-amber-50 p-3.5 text-sm text-amber-900"
        >
          Atención: no hay un cierre de caja abierto para la fecha seleccionada. Podés registrar movimientos, pero sin cierre abierto no van a entrar en el cierre del día (RN-PA-05).
        </div>
      )}

      {/* Panel de Cierre del Día */}
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-slate-900">Estado del Cierre Diario</h2>
          {cierreDelDia && (
            <Link
              to={`/app/caja/cierres/${cierreDelDia.id}`}
              className="text-xs font-semibold text-emerald-700 hover:underline"
            >
              Ver detalle del cierre ({cierreDelDia.estado})
            </Link>
          )}
        </div>

        {puedeEscribirCaja && (
          <form onSubmit={handleAbrirCierre} className="flex flex-wrap items-end gap-3">
            <CampoFormulario id="fecha-apertura" label="Fecha de apertura" obligatorio>
              <input
                id="fecha-apertura"
                type="date"
                value={fechaApertura}
                onChange={(e) => setFechaApertura(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>
            <button
              type="submit"
              disabled={mutaciones.abrirCierre.isPending}
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            >
              Abrir cierre del día
            </button>
          </form>
        )}

        {cierreDelDia && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-4 bg-slate-50 p-3 rounded-lg text-xs">
              <div>
                <span className="text-slate-500 block">Estado</span>
                <strong className="text-sm uppercase text-slate-900">{cierreDelDia.estado}</strong>
              </div>
              <div>
                <span className="text-slate-500 block">Total Sistema</span>
                <strong className="text-sm text-slate-900">
                  {formatearMontoARS(cierreDelDia.total_sistema)}
                </strong>
              </div>
              <div>
                <span className="text-slate-500 block">Total Contado</span>
                <strong className="text-sm text-slate-900">
                  {cierreDelDia.total_contado !== null && cierreDelDia.total_contado !== undefined
                    ? formatearMontoARS(cierreDelDia.total_contado)
                    : "Pendiente de arqueo"}
                </strong>
              </div>
              <div>
                <span className="text-slate-500 block">Diferencia</span>
                <strong className="text-sm text-slate-900">
                  {cierreDelDia.diferencia !== null && cierreDelDia.diferencia !== undefined
                    ? etiquetaDiferencia(cierreDelDia.diferencia)
                    : "—"}
                </strong>
              </div>
            </div>

            {cierreDelDia.estado === "abierto" && puedeActualizarCaja && (
              <form
                onSubmit={handleIntentarCerrarCaja}
                className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-3"
              >
                <CampoFormulario
                  id="input-total-contado"
                  label="Total contado en caja"
                  obligatorio
                  error={errorContado}
                >
                  <input
                    id="input-total-contado"
                    type="number"
                    step="0.01"
                    value={totalContado}
                    onChange={(e) => setTotalContado(e.target.value)}
                    placeholder="0.00"
                    className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                  />
                </CampoFormulario>
                <button
                  type="submit"
                  disabled={mutaciones.cerrarCierre.isPending}
                  className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-semibold text-white hover:bg-slate-800 focus:ring-2 focus:ring-slate-600 focus:outline-none"
                >
                  Cerrar caja
                </button>
              </form>
            )}
          </div>
        )}
      </section>

      {/* Alta de Movimiento (2.3) */}
      {puedeEscribirCaja && (
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <h2 className="mb-3 text-base font-bold text-slate-900">
            Registrar Movimiento (Ingreso / Egreso)
          </h2>
          <form
            onSubmit={handleCrearMovimiento}
            noValidate
            className="grid grid-cols-1 gap-3 sm:grid-cols-5"
          >
            <CampoFormulario id="mov-tipo" label="Tipo de movimiento" obligatorio>
              <select
                id="mov-tipo"
                value={tipoMov}
                onChange={(e) => setTipoMov(e.target.value as TipoMovimientoCaja)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="ingreso">Ingreso</option>
                <option value="egreso">Egreso</option>
              </select>
            </CampoFormulario>

            <div className="sm:col-span-2">
              <CampoFormulario
                id="mov-concepto"
                label="Concepto del movimiento"
                obligatorio
                error={errorConcepto}
              >
                <input
                  id="mov-concepto"
                  type="text"
                  value={conceptoMov}
                  onChange={(e) => setConceptoMov(e.target.value)}
                  placeholder="Ej: Cobro consulta / Compra insumos..."
                  className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                />
              </CampoFormulario>
            </div>

            <CampoFormulario id="mov-medio" label="Medio del movimiento" obligatorio>
              <select
                id="mov-medio"
                value={medioMov}
                onChange={(e) => setMedioMov(e.target.value as MedioPago)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="efectivo">Efectivo</option>
                <option value="transferencia">Transferencia</option>
                <option value="mercadopago">Mercado Pago</option>
                <option value="tarjeta">Tarjeta</option>
              </select>
            </CampoFormulario>

            <CampoFormulario
              id="mov-monto"
              label="Monto del movimiento"
              obligatorio
              error={errorMonto}
            >
              <input
                id="mov-monto"
                type="number"
                step="0.01"
                value={montoMov}
                onChange={(e) => setMontoMov(e.target.value)}
                placeholder="0.00"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>

            <div className="sm:col-span-5 flex justify-end">
              <button
                type="submit"
                disabled={mutaciones.crearMovimiento.isPending}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              >
                Registrar movimiento
              </button>
            </div>
          </form>
        </section>
      )}

      {/* Listado de Movimientos con Filtros (2.2) */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-base font-bold text-slate-900">Movimientos Registrados</h2>
          <div className="flex flex-wrap gap-2">
            <CampoFormulario id="filtro-fecha-caja" label="Fecha">
              <input
                id="filtro-fecha-caja"
                type="date"
                value={fechaFiltro}
                onChange={(e) => setFechaFiltro(e.target.value)}
                className="rounded border border-slate-300 px-2.5 py-1 text-xs"
              />
            </CampoFormulario>
            <CampoFormulario id="filtro-medio-caja" label="Medio">
              <select
                id="filtro-medio-caja"
                value={medioFiltro}
                onChange={(e) => setMedioFiltro(e.target.value)}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs"
              >
                <option value="">Todos</option>
                <option value="efectivo">Efectivo</option>
                <option value="transferencia">Transferencia</option>
                <option value="mercadopago">Mercado Pago</option>
                <option value="tarjeta">Tarjeta</option>
              </select>
            </CampoFormulario>
            <CampoFormulario id="filtro-tipo-caja" label="Tipo">
              <select
                id="filtro-tipo-caja"
                value={tipoFiltro}
                onChange={(e) => setTipoFiltro(e.target.value)}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs"
              >
                <option value="">Todos</option>
                <option value="ingreso">Ingreso</option>
                <option value="egreso">Egreso</option>
              </select>
            </CampoFormulario>
          </div>
        </div>

        {movimientosQuery.isLoading && <EstadoCargando mensaje="Cargando movimientos de caja..." />}
        {movimientosQuery.error && <EstadoError error={movimientosQuery.error} />}

        {!movimientosQuery.isLoading && !movimientosQuery.error && movimientos.length === 0 && (
          <EstadoVacio
            titulo="Sin movimientos para los filtros seleccionados"
            descripcion="Registrá un ingreso o egreso o cobrá una atención para ver movimientos en la caja."
          />
        )}

        {movimientos.length > 0 && (
          <TablaAccesible
            caption="Movimientos de caja del día"
            columnas={["Tipo", "Concepto", "Medio", "Monto", "Cierre", "Registrado por"]}
          >
            {movimientos.map((m) => (
              <tr key={m.id}>
                <td className="px-3 py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
                      m.tipo === "ingreso"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-rose-100 text-rose-800"
                    }`}
                  >
                    {m.tipo}
                  </span>
                </td>
                <td className="px-3 py-2 font-medium">{m.concepto}</td>
                <td className="px-3 py-2 capitalize">{m.medio}</td>
                <td className="px-3 py-2 font-mono font-semibold">
                  {m.tipo === "egreso" ? `- ${formatearMontoARS(m.monto)}` : formatearMontoARS(m.monto)}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">
                  {m.cierre_id ? "En cierre abierto" : "Sin cierre"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">{m.created_by}</td>
              </tr>
            ))}
          </TablaAccesible>
        )}
      </section>

      {/* Gestión de Señas (3.3) */}
      <section className="space-y-3 border-t border-slate-200 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-slate-900">Señas del Consultorio</h2>
          <CampoFormulario id="filtro-estado-sena" label="Filtrar señas por estado">
            <select
              id="filtro-estado-sena"
              value={estadoSenaFiltro}
              onChange={(e) => setEstadoSenaFiltro(e.target.value)}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs"
            >
              <option value="">Todos los estados</option>
              <option value="pendiente">Pendiente</option>
              <option value="cobrada">Cobrada</option>
              <option value="aplicada">Aplicada</option>
              <option value="devuelta">Devuelta</option>
              <option value="vencida">Vencida</option>
            </select>
          </CampoFormulario>
        </div>

        {senas.length === 0 ? (
          <p className="text-xs text-slate-500">No hay señas registradas con ese estado.</p>
        ) : (
          <TablaAccesible
            caption="Señas de turnos"
            columnas={["Turno", "Monto", "Estado", "Vencimiento", "Acciones"]}
          >
            {senas.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2 text-xs font-medium">{s.turno_id}</td>
                <td className="px-3 py-2 font-mono font-semibold">
                  {formatearMontoARS(s.monto)}
                </td>
                <td className="px-3 py-2">
                  <span className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-semibold">
                    {s.estado}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">
                  {s.vence_at ? formatearFechaHora(s.vence_at) : "—"}
                </td>
                <td className="px-3 py-2">
                  {puedeActualizarCaja && s.estado === "pendiente" && (
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleCobrarSena(s)}
                        className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                      >
                        Cobrar seña
                      </button>
                      <button
                        type="button"
                        onClick={() => handleVencerSena(s)}
                        className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        Marcar vencida
                      </button>
                    </div>
                  )}
                  {puedeActualizarCaja && s.estado === "cobrada" && (
                    <button
                      type="button"
                      onClick={() => handleAusenciaSena(s)}
                      className="rounded border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                    >
                      Resolver por ausencia
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </TablaAccesible>
        )}
      </section>

      {/* Diálogo de confirmación de cierre con diferencia (2.6, D4) */}
      <DialogoConfirmacion
        abierto={Boolean(dialogoDiferencia?.abierto)}
        titulo="Confirmar cierre con diferencia"
        descripcion={
          dialogoDiferencia
            ? `El total contado (${formatearMontoARS(
                dialogoDiferencia.contadoNorm,
              )}) no coincide con el total del sistema (${formatearMontoARS(
                cierreDelDia?.total_sistema,
              )}). Se registrará un ${dialogoDiferencia.clasificacion} auditable (RN-PA-05).`
            : ""
        }
        textoConfirmar="Confirmar cierre con diferencia"
        destructivo
        onCancelar={() => setDialogoDiferencia(null)}
        onConfirmar={() => {
          if (dialogoDiferencia) {
            void ejecutarCierre(dialogoDiferencia.cierreId, dialogoDiferencia.contadoNorm);
          }
        }}
      />
    </div>
  );
}

export function CierreDetallePage() {
  const { id = "" } = useParams<{ id: string }>();
  const { data: cierreRaw, isLoading, error } = useCierreDetalle(id);
  const mutaciones = useMutacionesCaja();

  const [cierreOverride, setCierreOverride] = useState<CierreCajaRead | null>(null);
  const [motivoReapertura, setMotivoReapertura] = useState<string>("");
  const [errorMotivo, setErrorMotivo] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeReabrir = permite(roles, "caja", "reabrir_cierre");

  const cierre = cierreOverride ?? cierreRaw;

  if (isLoading) return <EstadoCargando mensaje="Cargando cierre de caja..." />;
  if (error || !cierre) return <EstadoError error={error} />;

  const handleReabrir = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMotivo(null);
    setErrorAccion(null);

    if (!motivoReapertura.trim()) {
      setErrorMotivo("El motivo de reapertura es obligatorio y queda auditado (RN-SE-01).");
      return;
    }

    try {
      const reabierto = await mutaciones.reabrirCierre.mutateAsync({
        id: cierre.id,
        datos: { motivo: motivoReapertura.trim() },
      });
      setCierreOverride(reabierto);
      setMotivoReapertura("");
    } catch (err) {
      setErrorAccion(
        err instanceof ErrorApi ? err.message : "No tenés permiso para reabrir el cierre.",
      );
    }
  };

  return (
    <div data-testid="cierre-detalle-page" className="space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Cierre de Caja · {cierre.fecha}
          </h1>
          <p className="text-sm text-slate-600">
            {cierre.estado === "cerrado"
              ? "Cierre cerrado (inmutable). No admite nuevos movimientos ni edición."
              : "Cierre abierto para operaciones del día."}
          </p>
        </div>
        <Link
          to="/app/caja"
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          Volver a Caja
        </Link>
      </div>

      {errorAccion && (
        <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorAccion}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-4">
        <div>
          <span className="block text-xs text-slate-500">Estado</span>
          <strong className="text-base uppercase text-slate-900">{cierre.estado}</strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Total Sistema</span>
          <strong className="text-base text-slate-900">
            {formatearMontoARS(cierre.total_sistema)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Total Contado</span>
          <strong className="text-base text-slate-900">
            {cierre.total_contado !== null && cierre.total_contado !== undefined
              ? formatearMontoARS(cierre.total_contado)
              : "—"}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-slate-500">Resultado / Diferencia</span>
          <strong className="text-base text-slate-900">
            {cierre.diferencia !== null && cierre.diferencia !== undefined
              ? etiquetaDiferencia(cierre.diferencia)
              : "—"}
          </strong>
        </div>
      </div>

      {cierre.reabierto_motivo && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Motivo de reapertura registrado: <strong>{cierre.reabierto_motivo}</strong>
        </div>
      )}

      {cierre.estado === "cerrado" && puedeReabrir && (
        <form
          onSubmit={handleReabrir}
          noValidate
          className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
        >
          <h2 className="text-sm font-bold text-slate-900">
            Reapertura de Cierre (Exclusivo Dueño · RN-SE-01)
          </h2>
          <CampoFormulario
            id="motivo-reapertura"
            label="Motivo de reapertura"
            obligatorio
            error={errorMotivo}
          >
            <input
              id="motivo-reapertura"
              type="text"
              value={motivoReapertura}
              onChange={(e) => setMotivoReapertura(e.target.value)}
              placeholder="Explicá por qué se reabre el cierre..."
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <button
            type="submit"
            disabled={mutaciones.reabrirCierre.isPending}
            className="rounded-md bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
          >
            Reabrir cierre
          </button>
        </form>
      )}
    </div>
  );
}
