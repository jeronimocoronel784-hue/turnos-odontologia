import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  useCoberturasAdmin,
  useMutacionesAdmin,
  usePoliticasAdmin,
  usePrestacionesAdmin,
  useSillonesAdmin,
  useUsuariosAdmin,
} from "./queries";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import {
  formatearMontoARS,
  normalizarDecimalDosPosiciones,
} from "../../shared/formattersMonto";
import { EstadoCargando, EstadoError, EstadoVacio } from "../../shared/ComponentesEstado";
import { CampoFormulario, TablaAccesible } from "../../shared/ComponentesUI";
import { ErrorApi } from "../../shared/api-client";
import type {
  CoberturaOSRead,
  PrestacionRead,
  RolUsuario,
  SillonRead,
  UsuarioRead,
} from "../../shared/api-types";

function NavAdmin() {
  return (
    <nav className="flex flex-wrap gap-2 border-b border-slate-200 pb-3 text-xs font-semibold">
      <Link
        to="/app/admin/prestaciones"
        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
      >
        Prestaciones
      </Link>
      <Link
        to="/app/admin/sillones"
        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
      >
        Sillones / Boxes
      </Link>
      <Link
        to="/app/admin/coberturas"
        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
      >
        Padrón Coberturas OS
      </Link>
      <Link
        to="/app/admin/politicas"
        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
      >
        Políticas
      </Link>
      <Link
        to="/app/admin/usuarios"
        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
      >
        Usuarios y Roles
      </Link>
    </nav>
  );
}

// ===========================================================================
// 5.2 PRESTACIONES
// ===========================================================================

export function PrestacionesPage() {
  const { data: listaRaw, isLoading, error } = usePrestacionesAdmin();
  const mutaciones = useMutacionesAdmin();

  const [nombre, setNombre] = useState("");
  const [duracionMin, setDuracionMin] = useState<number>(30);
  const [precioParticular, setPrecioParticular] = useState<string>("");
  const [requiereSena, setRequiereSena] = useState<boolean>(false);
  const [montoSena, setMontoSena] = useState<string>("");
  const [invasiva, setInvasiva] = useState<boolean>(false);

  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [exitoForm, setExitoForm] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, PrestacionRead>>({});
  const [agregadas, setAgregadas] = useState<PrestacionRead[]>([]);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEditar = permite(roles, "configuracion", "crear");

  const prestaciones = [
    ...(listaRaw ?? []),
    ...agregadas.filter((a) => !(listaRaw ?? []).some((r) => r.id === a.id)),
  ].map((p) => overrides[p.id] ?? p);

  const handleCrear = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);
    setExitoForm(null);

    if (!nombre.trim()) {
      setErrorForm("El nombre de la prestación es obligatorio.");
      return;
    }
    if (!Number.isInteger(Number(duracionMin)) || Number(duracionMin) <= 0) {
      setErrorForm("La duración debe ser un número entero positivo de minutos.");
      return;
    }
    const precioNum = Number(precioParticular);
    if (!precioParticular.trim() || Number.isNaN(precioNum) || precioNum < 0) {
      setErrorForm("El precio particular debe ser un importe mayor o igual a cero.");
      return;
    }
    if (requiereSena) {
      const senaNum = Number(montoSena);
      if (!montoSena.trim() || Number.isNaN(senaNum) || senaNum <= 0) {
        setErrorForm("Si requiere seña, debés informar un monto de seña mayor a cero.");
        return;
      }
    }

    try {
      const nueva = await mutaciones.crearPrestacion.mutateAsync({
        nombre: nombre.trim(),
        duracion_min: Number(duracionMin),
        precio_particular: normalizarDecimalDosPosiciones(precioParticular),
        requiere_sena: requiereSena,
        monto_sena: requiereSena ? normalizarDecimalDosPosiciones(montoSena) : null,
        invasiva,
        activa: true,
      });
      setAgregadas((prev) => [...prev, nueva]);
      setNombre("");
      setPrecioParticular("");
      setRequiereSena(false);
      setMontoSena("");
      setInvasiva(false);
      setExitoForm("Prestación creada con los importes confirmados por el servidor.");
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos crear la prestación.");
    }
  };

  const handleDesactivar = async (p: PrestacionRead) => {
    setErrorForm(null);
    try {
      const actualizada = await mutaciones.desactivarPrestacion.mutateAsync(p.id);
      setOverrides((prev) => ({ ...prev, [actualizada.id]: actualizada }));
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos desactivar la prestación.");
    }
  };

  return (
    <div data-testid="prestaciones-admin-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <NavAdmin />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Catálogo de Prestaciones</h1>
          <p className="text-sm text-slate-600">
            Configuración de servicios, duraciones, precios particulares, señas e indicador de invasividad.
          </p>
        </div>
        {!puedeEditar && (
          <span className="rounded border border-slate-300 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            Modo solo lectura
          </span>
        )}
      </div>

      {exitoForm && (
        <div role="status" className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {exitoForm}
        </div>
      )}
      {errorForm && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorForm}
        </div>
      )}

      {puedeEditar && (
        <form
          onSubmit={handleCrear}
          noValidate
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-xs"
        >
          <h2 className="text-base font-bold text-slate-900">Nueva Prestación</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <CampoFormulario id="pres-nombre" label="Nombre de la prestación" obligatorio>
              <input
                id="pres-nombre"
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>
            <CampoFormulario id="pres-duracion" label="Duración (min)" obligatorio>
              <input
                id="pres-duracion"
                type="number"
                value={duracionMin}
                onChange={(e) => setDuracionMin(Number(e.target.value))}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>
            <CampoFormulario id="pres-precio" label="Precio particular" obligatorio>
              <input
                id="pres-precio"
                type="number"
                step="0.01"
                value={precioParticular}
                onChange={(e) => setPrecioParticular(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </CampoFormulario>
            <CampoFormulario id="pres-monto-sena" label="Monto de la seña">
              <input
                id="pres-monto-sena"
                type="number"
                step="0.01"
                value={montoSena}
                disabled={!requiereSena}
                onChange={(e) => setMontoSena(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100"
              />
            </CampoFormulario>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-xs font-medium text-slate-700">
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={requiereSena}
                  onChange={(e) => setRequiereSena(e.target.checked)}
                />
                Requiere seña
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={invasiva}
                  onChange={(e) => setInvasiva(e.target.checked)}
                />
                Prestación invasiva (exige consentimiento)
              </label>
            </div>
            <button
              type="submit"
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Crear prestación
            </button>
          </div>
        </form>
      )}

      {isLoading && <EstadoCargando mensaje="Cargando prestaciones..." />}
      {error && <EstadoError error={error} />}

      {!isLoading && prestaciones.length > 0 && (
        <TablaAccesible
          caption="Prestaciones del consultorio"
          columnas={["Nombre", "Duración", "Precio Particular", "Seña", "Invasiva", "Estado", "Acción"]}
        >
          {prestaciones.map((p) => (
            <tr key={p.id}>
              <td className="px-3 py-2 font-semibold">{p.nombre}</td>
              <td className="px-3 py-2">{p.duracion_min} min</td>
              <td className="px-3 py-2 font-mono">{formatearMontoARS(p.precio_particular)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {p.requiere_sena && p.monto_sena ? formatearMontoARS(p.monto_sena) : "No requiere"}
              </td>
              <td className="px-3 py-2 text-xs">{p.invasiva ? "Invasiva" : "No"}</td>
              <td className="px-3 py-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-semibold ${
                    p.activa ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {p.activa ? "Activa" : "Inactiva"}
                </span>
              </td>
              <td className="px-3 py-2">
                {puedeEditar && p.activa && (
                  <button
                    type="button"
                    onClick={() => void handleDesactivar(p)}
                    className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Desactivar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </TablaAccesible>
      )}
    </div>
  );
}

// ===========================================================================
// 5.3 SILLONES
// ===========================================================================

export function SillonesPage() {
  const { data: sillonesRaw, isLoading, error } = useSillonesAdmin();
  const mutaciones = useMutacionesAdmin();

  const [nombre, setNombre] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [avisoDesactivado, setAvisoDesactivado] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, SillonRead>>({});
  const [agregados, setAgregados] = useState<SillonRead[]>([]);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEditar = permite(roles, "configuracion", "crear");

  const sillones = [
    ...(sillonesRaw ?? []),
    ...agregados.filter((a) => !(sillonesRaw ?? []).some((r) => r.id === a.id)),
  ].map((s) => overrides[s.id] ?? s);

  const handleCrear = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);
    if (!nombre.trim()) {
      setErrorForm("El nombre del sillón no puede estar vacío.");
      return;
    }

    try {
      const nuevo = await mutaciones.crearSillon.mutateAsync({
        nombre: nombre.trim(),
        sucursal: sucursal.trim() || "central",
        activo: true,
      });
      setAgregados((prev) => [...prev, nuevo]);
      setNombre("");
      setSucursal("");
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos crear el sillón.");
    }
  };

  const handleDesactivar = async (s: SillonRead) => {
    try {
      const inactivo = await mutaciones.desactivarSillon.mutateAsync(s.id);
      setOverrides((prev) => ({ ...prev, [inactivo.id]: inactivo }));
      setAvisoDesactivado(
        `El sillón ${inactivo.nombre} quedó inactivo (no disponible para agendar nuevos turnos).`,
      );
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos desactivar el sillón.");
    }
  };

  return (
    <div data-testid="sillones-admin-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <NavAdmin />
      <h1 className="text-2xl font-bold text-slate-900">Sillones y Sucursal</h1>

      {avisoDesactivado && (
        <div role="status" className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {avisoDesactivado}
        </div>
      )}
      {errorForm && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorForm}
        </div>
      )}

      {puedeEditar && (
        <form
          onSubmit={handleCrear}
          noValidate
          className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4"
        >
          <CampoFormulario id="sil-nombre" label="Nombre del sillón" obligatorio>
            <input
              id="sil-nombre"
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej: Box 2..."
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="sil-sucursal" label="Sucursal (por defecto central)">
            <input
              id="sil-sucursal"
              type="text"
              value={sucursal}
              onChange={(e) => setSucursal(e.target.value)}
              placeholder="central"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <button
            type="submit"
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            Crear sillón
          </button>
        </form>
      )}

      {isLoading && <EstadoCargando mensaje="Cargando sillones..." />}
      {error && <EstadoError error={error} />}

      {!isLoading && sillones.length > 0 && (
        <TablaAccesible caption="Sillones del consultorio" columnas={["Nombre", "Sucursal", "Estado", "Acción"]}>
          {sillones.map((s) => (
            <tr key={s.id}>
              <td className="px-3 py-2 font-semibold">{s.nombre}</td>
              <td className="px-3 py-2">{s.sucursal}</td>
              <td className="px-3 py-2">
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold">
                  {s.activo ? "Activo" : "Inactivo"}
                </span>
              </td>
              <td className="px-3 py-2">
                {puedeEditar && s.activo && (
                  <button
                    type="button"
                    onClick={() => void handleDesactivar(s)}
                    className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Desactivar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </TablaAccesible>
      )}
    </div>
  );
}

// ===========================================================================
// 5.4 PADRÓN DE COBERTURAS
// ===========================================================================

export function CoberturasPage() {
  const { data: coberturasRaw, isLoading, error } = useCoberturasAdmin();
  const mutaciones = useMutacionesAdmin();

  const [obraSocial, setObraSocial] = useState("");
  const [prestacionId, setPrestacionId] = useState("");
  const [arancel, setArancel] = useState("");
  const [copago, setCopago] = useState("0.00");
  const [vigenciaDesde, setVigenciaDesde] = useState("2026-01-01");
  const [vigenciaHasta, setVigenciaHasta] = useState("");
  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [avisoHistorico, setAvisoHistorico] = useState<string | null>(null);
  const [agregadas, setAgregadas] = useState<CoberturaOSRead[]>([]);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEditar = permite(roles, "configuracion", "crear");

  const coberturas = [
    ...(coberturasRaw ?? []),
    ...agregadas.filter((a) => !(coberturasRaw ?? []).some((r) => r.id === a.id)),
  ];

  const handleGuardar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);
    setAvisoHistorico(null);

    if (!obraSocial.trim() || !prestacionId.trim() || !arancel.trim()) {
      setErrorForm("Obra social, prestación y arancel son obligatorios.");
      return;
    }
    if (vigenciaHasta.trim() && vigenciaHasta.trim() < vigenciaDesde.trim()) {
      setErrorForm("La fecha de vigencia hasta no puede ser anterior a la fecha de vigencia desde.");
      return;
    }

    try {
      const nueva = await mutaciones.crearCobertura.mutateAsync({
        obra_social: obraSocial.trim(),
        prestacion_id: prestacionId.trim(),
        arancel: normalizarDecimalDosPosiciones(arancel),
        copago: normalizarDecimalDosPosiciones(copago || "0.00"),
        vigencia_desde: vigenciaDesde.trim(),
        vigencia_hasta: vigenciaHasta.trim() || null,
        activa: true,
      });
      setAgregadas((prev) => [...prev, nueva]);
      setAvisoHistorico(
        "Convenio registrado. Recordá que los cambios de arancel o copago no modifican liquidaciones ni cobros ya generados.",
      );
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos guardar la cobertura.");
    }
  };

  return (
    <div data-testid="coberturas-admin-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <NavAdmin />
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Padrón de Coberturas de Obra Social</h1>
        <p className="text-sm text-slate-600">
          Los cambios de arancel o copago aplican hacia adelante y no modifican liquidaciones ni cobros ya generados.
        </p>
      </div>

      {avisoHistorico && (
        <div role="status" className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {avisoHistorico}
        </div>
      )}
      {errorForm && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorForm}
        </div>
      )}

      {puedeEditar && (
        <form
          onSubmit={handleGuardar}
          noValidate
          className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-3"
        >
          <CampoFormulario id="cob-admin-os" label="Obra social del convenio" obligatorio>
            <input
              id="cob-admin-os"
              type="text"
              value={obraSocial}
              onChange={(e) => setObraSocial(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-admin-pres" label="ID prestación" obligatorio>
            <input
              id="cob-admin-pres"
              type="text"
              value={prestacionId}
              onChange={(e) => setPrestacionId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-admin-arancel" label="Arancel convenido" obligatorio>
            <input
              id="cob-admin-arancel"
              type="number"
              step="0.01"
              value={arancel}
              onChange={(e) => setArancel(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-admin-copago" label="Copago a cargo">
            <input
              id="cob-admin-copago"
              type="number"
              step="0.01"
              value={copago}
              onChange={(e) => setCopago(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-admin-desde" label="Vigencia desde" obligatorio>
            <input
              id="cob-admin-desde"
              type="date"
              value={vigenciaDesde}
              onChange={(e) => setVigenciaDesde(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="cob-admin-hasta" label="Vigencia hasta">
            <input
              id="cob-admin-hasta"
              type="date"
              value={vigenciaHasta}
              onChange={(e) => setVigenciaHasta(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <div className="sm:col-span-3 flex justify-end">
            <button
              type="submit"
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Guardar cobertura
            </button>
          </div>
        </form>
      )}

      {isLoading && <EstadoCargando mensaje="Cargando padrón de coberturas..." />}
      {error && <EstadoError error={error} />}

      {!isLoading && coberturas.length === 0 && (
        <EstadoVacio
          titulo="Sin coberturas registradas"
          descripcion="Cargá convenios por obra social y prestación para automatizar el cálculo de copagos."
        />
      )}

      {coberturas.length > 0 && (
        <TablaAccesible
          caption="Padrón de coberturas"
          columnas={["Obra Social", "Prestación", "Arancel", "Copago", "Vigencia", "Estado"]}
        >
          {coberturas.map((c) => (
            <tr key={c.id}>
              <td className="px-3 py-2 font-semibold">{c.obra_social}</td>
              <td className="px-3 py-2 text-xs">{c.prestacion_id}</td>
              <td className="px-3 py-2 font-mono">{formatearMontoARS(c.arancel)}</td>
              <td className="px-3 py-2 font-mono">{formatearMontoARS(c.copago)}</td>
              <td className="px-3 py-2 text-xs">
                {c.vigencia_desde} → {c.vigencia_hasta ?? "Sin vencimiento"}
              </td>
              <td className="px-3 py-2 text-xs">{c.activa ? "Activa" : "Inactiva"}</td>
            </tr>
          ))}
        </TablaAccesible>
      )}
    </div>
  );
}

// ===========================================================================
// 5.5 POLÍTICAS DEL CONSULTORIO
// ===========================================================================

export function PoliticasPage() {
  const { data: politicas, isLoading, error } = usePoliticasAdmin();
  const mutaciones = useMutacionesAdmin();

  const [anticipacionDias, setAnticipacionDias] = useState<number>(1);
  const [senaPct, setSenaPct] = useState<number>(30);
  const [cancelacionHoras, setCancelacionHoras] = useState<number>(24);
  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [avisoForm, setAvisoForm] = useState<string | null>(null);

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeEditar = permite(roles, "configuracion", "actualizar");

  useEffect(() => {
    if (politicas) {
      setAnticipacionDias(politicas.anticipacion_min_dias);
      setSenaPct(politicas.sena_default_pct);
      setCancelacionHoras(politicas.cancelacion_horas);
    }
  }, [politicas]);

  if (isLoading) return <EstadoCargando mensaje="Cargando políticas del consultorio..." />;
  if (error || !politicas) return <EstadoError error={error} />;

  const handleGuardar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);
    setAvisoForm(null);

    if (senaPct < 0 || senaPct > 100) {
      setErrorForm("El porcentaje de seña por defecto debe estar entre 0 y 100.");
      return;
    }
    if (cancelacionHoras < 0 || anticipacionDias < 0) {
      setErrorForm("Las horas y días deben ser valores mayores o iguales a cero.");
      return;
    }

    if (
      anticipacionDias === politicas.anticipacion_min_dias &&
      senaPct === politicas.sena_default_pct &&
      cancelacionHoras === politicas.cancelacion_horas
    ) {
      setAvisoForm("No hay cambios para guardar respecto de la configuración actual.");
      return;
    }

    try {
      await mutaciones.guardarPoliticas.mutateAsync({
        anticipacion_min_dias: anticipacionDias,
        sena_default_pct: senaPct,
        cancelacion_horas: cancelacionHoras,
      });
      setAvisoForm("Políticas actualizadas correctamente.");
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos actualizar las políticas.");
    }
  };

  return (
    <div data-testid="politicas-admin-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <NavAdmin />
      <h1 className="text-2xl font-bold text-slate-900">Políticas Operativas del Consultorio</h1>

      {avisoForm && (
        <div role="status" className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {avisoForm}
        </div>
      )}
      {errorForm && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorForm}
        </div>
      )}

      <form
        onSubmit={handleGuardar}
        noValidate
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <CampoFormulario id="pol-anticipacion" label="Anticipación mínima (días)" obligatorio>
            <input
              id="pol-anticipacion"
              type="number"
              disabled={!puedeEditar}
              value={anticipacionDias}
              onChange={(e) => setAnticipacionDias(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>

          <CampoFormulario id="pol-sena-pct" label="Porcentaje de seña por defecto (%)" obligatorio>
            <input
              id="pol-sena-pct"
              type="number"
              disabled={!puedeEditar}
              value={senaPct}
              onChange={(e) => setSenaPct(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>

          <CampoFormulario id="pol-cancelacion-hs" label="Horas de cancelación sin cargo" obligatorio>
            <input
              id="pol-cancelacion-hs"
              type="number"
              disabled={!puedeEditar}
              value={cancelacionHoras}
              onChange={(e) => setCancelacionHoras(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
        </div>

        {puedeEditar && (
          <div className="flex justify-end">
            <button
              type="submit"
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Guardar políticas
            </button>
          </div>
        )}
      </form>
    </div>
  );
}

// ===========================================================================
// 5.6 USUARIOS Y ROLES
// ===========================================================================

export function UsuariosPage() {
  const { data: usuariosRaw, isLoading, error } = useUsuariosAdmin();
  const mutaciones = useMutacionesAdmin();

  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rol, setRol] = useState<RolUsuario>("recepcion");
  const [matricula, setMatricula] = useState("");
  const [errorForm, setErrorForm] = useState<string | null>(null);
  const [avisoRol, setAvisoRol] = useState<string | null>(null);
  const [agregados, setAgregados] = useState<UsuarioRead[]>([]);
  const [overrides, setOverrides] = useState<Record<string, UsuarioRead>>({});

  const identidad = getIdentidad();
  const roles = identidad?.roles ?? [];
  const puedeGestionarUsuarios = permite(roles, "usuarios", "crear");

  const usuarios = [
    ...(usuariosRaw ?? []),
    ...agregados.filter((a) => !(usuariosRaw ?? []).some((r) => r.id === a.id)),
  ].map((u) => overrides[u.id] ?? u);

  const handleCrearUsuario = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm(null);

    if (!nombre.trim() || !email.trim() || !password.trim()) {
      setErrorForm("Nombre, correo electrónico y contraseña inicial son obligatorios.");
      return;
    }
    if (rol === "odontologo" && !matricula.trim()) {
      setErrorForm("La matrícula profesional es obligatoria para el rol odontólogo.");
      return;
    }

    try {
      const creado = await mutaciones.crearUsuario.mutateAsync({
        nombre: nombre.trim(),
        email: email.trim(),
        password,
        rol,
        matricula: rol === "odontologo" ? matricula.trim() : null,
      });
      // Descartar contraseña de la memoria inmediatamente (D8, R9)
      setPassword("");
      setNombre("");
      setEmail("");
      setMatricula("");
      setAgregados((prev) => [...prev, creado]);
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos crear el usuario.");
    }
  };

  const handleCambiarRol = async (u: UsuarioRead, nuevoRol: RolUsuario) => {
    setErrorForm(null);
    setAvisoRol(null);
    try {
      const actualizado = await mutaciones.cambiarRolUsuario.mutateAsync({
        id: u.id,
        datos: { rol: nuevoRol, matricula: u.matricula ?? "MN-AUTO" },
      });
      setOverrides((prev) => ({ ...prev, [actualizado.id]: actualizado }));
      setAvisoRol(
        `Rol de ${actualizado.nombre} actualizado a ${actualizado.rol}. Este cambio impacta de inmediato en sus permisos de acceso.`,
      );
    } catch (err) {
      setErrorForm(err instanceof ErrorApi ? err.message : "No pudimos cambiar el rol.");
    }
  };

  return (
    <div data-testid="usuarios-admin-page" className="w-full max-w-full space-y-6 p-4 md:p-6">
      <NavAdmin />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Usuarios y Roles del Consultorio</h1>
          <p className="text-sm text-slate-600">
            Gestión de personal y permisos RBAC. Por seguridad nunca se exponen contraseñas ni hashes (R9).
          </p>
        </div>
        {!puedeGestionarUsuarios && (
          <span className="rounded border border-slate-300 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            Modo solo lectura
          </span>
        )}
      </div>

      {avisoRol && (
        <div role="status" className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {avisoRol}
        </div>
      )}
      {errorForm && (
        <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {errorForm}
        </div>
      )}

      {puedeGestionarUsuarios && (
        <form
          onSubmit={handleCrearUsuario}
          noValidate
          className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-5"
        >
          <CampoFormulario id="usr-nombre" label="Nombre completo" obligatorio>
            <input
              id="usr-nombre"
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="usr-email" label="Correo electrónico" obligatorio>
            <input
              id="usr-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="usr-password" label="Contraseña inicial" obligatorio>
            <input
              id="usr-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <CampoFormulario id="usr-rol" label="Rol en el consultorio" obligatorio>
            <select
              id="usr-rol"
              value={rol}
              onChange={(e) => setRol(e.target.value as RolUsuario)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="recepcion">Recepción</option>
              <option value="odontologo">Odontólogo</option>
              <option value="dueno">Dueño</option>
            </select>
          </CampoFormulario>
          <CampoFormulario
            id="usr-matricula"
            label="Matrícula profesional"
            obligatorio={rol === "odontologo"}
          >
            <input
              id="usr-matricula"
              type="text"
              value={matricula}
              onChange={(e) => setMatricula(e.target.value)}
              placeholder="Ej: MN-1234"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </CampoFormulario>
          <div className="sm:col-span-5 flex justify-end">
            <button
              type="submit"
              className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Crear usuario
            </button>
          </div>
        </form>
      )}

      {isLoading && <EstadoCargando mensaje="Cargando usuarios..." />}
      {error && <EstadoError error={error} />}

      {!isLoading && usuarios.length > 0 && (
        <TablaAccesible
          caption="Usuarios del consultorio"
          columnas={["Nombre", "Email", "Rol", "Matrícula", "Estado", "Cambiar Rol"]}
        >
          {usuarios.map((u) => (
            <tr key={u.id}>
              <td className="px-3 py-2 font-semibold">{u.nombre}</td>
              <td className="px-3 py-2 text-xs">{u.email}</td>
              <td className="px-3 py-2">
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase">
                  {u.rol}
                </span>
              </td>
              <td className="px-3 py-2 text-xs">{u.matricula ?? "—"}</td>
              <td className="px-3 py-2 text-xs">{u.activo ? "Activo" : "Inactivo"}</td>
              <td className="px-3 py-2">
                {puedeGestionarUsuarios && (
                  <select
                    aria-label={`Cambiar rol de ${u.nombre}`}
                    value={u.rol}
                    onChange={(e) => void handleCambiarRol(u, e.target.value as RolUsuario)}
                    className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                  >
                    <option value="recepcion">recepcion</option>
                    <option value="odontologo">odontologo</option>
                    <option value="dueno">dueno</option>
                  </select>
                )}
              </td>
            </tr>
          ))}
        </TablaAccesible>
      )}
    </div>
  );
}
