import React, { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { usePacientes, usePaciente, useMutacionesPacientes } from "./queries";
import { getIdentidad } from "../../shared/sesion";
import { permite } from "../../shared/rbac";
import { formatearDni, formatearFechaCorta } from "../../shared/formatters";
import { EstadoCargando, EstadoVacio, EstadoError } from "../../shared/ComponentesEstado";
import { ErrorApi } from "../../shared/api-client";

export function PacientesPage() {
  const navigate = useNavigate();
  const usuario = getIdentidad();
  const roles = usuario?.roles || [];
  const puedeCrear = permite(roles, "pacientes", "crear");

  const [terminoBusqueda, setTerminoBusqueda] = useState("");
  const [mostrarModalAlta, setMostrarModalAlta] = useState(false);

  // Form states alta
  const [nombre, setNombre] = useState("");
  const [dni, setDni] = useState("");
  const [telefono, setTelefono] = useState("");
  const [email, setEmail] = useState("");
  const [fechaNac, setFechaNac] = useState("");
  const [nroAfiliado, setNroAfiliado] = useState("");
  const [optinWa, setOptinWa] = useState(true);
  const [observaciones, setObservaciones] = useState("");

  const [errorAlta, setErrorAlta] = useState<string | null>(null);
  const [pacienteDuplicadoId, setPacienteDuplicadoId] = useState<string | null>(null);

  const { data: pacientes, isLoading, error, refetch } = usePacientes(terminoBusqueda);
  const { alta } = useMutacionesPacientes();

  async function handleCrearPaciente(e: React.FormEvent) {
    e.preventDefault();
    setErrorAlta(null);
    setPacienteDuplicadoId(null);

    const nomLimpio = nombre.trim();
    const dniLimpio = dni.trim().replace(/\D/g, "");
    const telLimpio = telefono.trim();

    if (!nomLimpio || !dniLimpio || !telLimpio) {
      setErrorAlta("Nombre, DNI y teléfono son obligatorios.");
      return;
    }

    try {
      const nuevo = await alta.mutateAsync({
        nombre: nomLimpio,
        dni: dniLimpio,
        telefono: telLimpio,
        email: email.trim() || undefined,
        fecha_nac: fechaNac || undefined,
        nro_afiliado: nroAfiliado.trim() || undefined,
        optin_wa: optinWa,
        observaciones: observaciones.trim() || undefined,
      });

      setMostrarModalAlta(false);
      navigate(`/app/pacientes/${nuevo.id}`);
    } catch (err) {
      if (err instanceof ErrorApi) {
        if (err.status === 409) {
          setErrorAlta("Ya existe un paciente registrado con ese número de DNI.");
          // Si la respuesta trae datos del existente, o simplemente indicamos abrirlo
        } else {
          setErrorAlta(err.detalle);
        }
      } else {
        setErrorAlta("No se pudo registrar el paciente. Verificá tu conexión.");
      }
    }
  }

  return (
    <div className="space-y-6" data-testid="pacientes-page">
      {/* Cabecera y Buscador */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex-1 max-w-md">
          <label htmlFor="buscar-paciente" className="sr-only">
            Buscar paciente
          </label>
          <div className="relative">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              🔍
            </span>
            <input
              id="buscar-paciente"
              type="search"
              value={terminoBusqueda}
              onChange={(e) => setTerminoBusqueda(e.target.value)}
              placeholder="Buscar por nombre, DNI o teléfono..."
              className="block w-full pl-9 pr-3 py-2 border border-slate-300 rounded-md text-sm placeholder-slate-400 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 bg-white"
            />
          </div>
        </div>

        {puedeCrear && (
          <button
            type="button"
            onClick={() => setMostrarModalAlta(true)}
            className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-emerald-600 hover:bg-emerald-700"
          >
            + Nuevo Paciente
          </button>
        )}
      </div>

      {/* Listado */}
      {isLoading ? (
        <EstadoCargando mensaje="Buscando pacientes..." />
      ) : error ? (
        <EstadoError error={error} alReintentar={() => refetch()} />
      ) : !pacientes || pacientes.length === 0 ? (
        <EstadoVacio
          titulo="No se encontraron pacientes"
          descripcion={
            terminoBusqueda
              ? `No hay coincidencias para "${terminoBusqueda}". Podés agregar un nuevo paciente con ese DNI o nombre.`
              : "Todavía no hay pacientes registrados en el consultorio."
          }
          accion={
            puedeCrear
              ? {
                  texto: "+ Registrar paciente",
                  onClick: () => setMostrarModalAlta(true),
                }
              : undefined
          }
        />
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-700 font-semibold">
              <tr>
                <th className="py-3 px-4">Paciente</th>
                <th className="py-3 px-4">DNI</th>
                <th className="py-3 px-4">Teléfono</th>
                <th className="py-3 px-4">WhatsApp</th>
                <th className="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {pacientes.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50 transition">
                  <td className="py-3 px-4 font-medium text-slate-900">
                    <Link
                      to={`/app/pacientes/${p.id}`}
                      className="text-emerald-700 hover:text-emerald-900 font-semibold"
                    >
                      {p.nombre}
                    </Link>
                    {p.email && <div className="text-xs text-slate-500 font-normal">{p.email}</div>}
                  </td>
                  <td className="py-3 px-4 text-slate-700">{formatearDni(p.dni)}</td>
                  <td className="py-3 px-4 text-slate-700">{p.telefono}</td>
                  <td className="py-3 px-4">
                    {p.optin_wa ? (
                      <span className="text-xs px-2 py-0.5 bg-emerald-100 text-emerald-800 font-medium rounded-full">
                        Opt-in Activo
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">
                        Sin Opt-in
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right space-x-2">
                    <Link
                      to={`/app/pacientes/${p.id}`}
                      className="text-xs font-medium text-slate-700 hover:text-slate-900 bg-slate-100 px-2.5 py-1 rounded border border-slate-300"
                    >
                      Ficha
                    </Link>
                    <Link
                      to={`/app/pacientes/${p.id}/clinica`}
                      className="text-xs font-medium text-emerald-700 hover:text-emerald-900 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200"
                    >
                      Clínica
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal Alta Paciente */}
      {mostrarModalAlta && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6 border border-slate-200 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Alta de Paciente</h3>

            {errorAlta && (
              <div
                role="alert"
                className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md"
              >
                {errorAlta}
                {pacienteDuplicadoId && (
                  <div className="mt-2">
                    <Link
                      to={`/app/pacientes/${pacienteDuplicadoId}`}
                      className="text-xs font-semibold text-red-800 underline"
                    >
                      Ver paciente registrado con este DNI
                    </Link>
                  </div>
                )}
              </div>
            )}

            <form onSubmit={handleCrearPaciente} className="space-y-4">
              <div>
                <label htmlFor="nombre-alta" className="block text-sm font-medium text-slate-700 mb-1">
                  Nombre completo *
                </label>
                <input
                  id="nombre-alta"
                  type="text"
                  required
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder="Ej: Laura Martínez"
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="dni-alta" className="block text-sm font-medium text-slate-700 mb-1">DNI *</label>
                  <input
                    id="dni-alta"
                    type="text"
                    required
                    value={dni}
                    onChange={(e) => setDni(e.target.value)}
                    placeholder="Solo números"
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="tel-alta" className="block text-sm font-medium text-slate-700 mb-1">Teléfono *</label>
                  <input
                    id="tel-alta"
                    type="tel"
                    required
                    value={telefono}
                    onChange={(e) => setTelefono(e.target.value)}
                    placeholder="Ej: 1122334455"
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="email-alta" className="block text-sm font-medium text-slate-700 mb-1">Email</label>
                  <input
                    id="email-alta"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="opcional@mail.com"
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="nac-alta" className="block text-sm font-medium text-slate-700 mb-1">
                    Fecha de nacimiento
                  </label>
                  <input
                    id="nac-alta"
                    type="date"
                    value={fechaNac}
                    onChange={(e) => setFechaNac(e.target.value)}
                    className="w-full border border-slate-300 rounded-md p-2 text-sm"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="afiliado-alta" className="block text-sm font-medium text-slate-700 mb-1">
                  N° Afiliado Obra Social
                </label>
                <input
                  id="afiliado-alta"
                  type="text"
                  value={nroAfiliado}
                  onChange={(e) => setNroAfiliado(e.target.value)}
                  placeholder="Ej: OSDE-123456"
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div className="pt-2 border-t border-slate-200">
                <label htmlFor="optin-alta" className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    id="optin-alta"
                    type="checkbox"
                    checked={optinWa}
                    onChange={(e) => setOptinWa(e.target.checked)}
                    className="rounded text-emerald-600 focus:ring-emerald-500"
                  />
                  <span>Consentimiento para avisos por WhatsApp (Opt-in)</span>
                </label>
              </div>

              <div>
                <label htmlFor="obs-alta" className="block text-sm font-medium text-slate-700 mb-1">
                  Observaciones administrativas
                </label>
                <textarea
                  id="obs-alta"
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  rows={2}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setMostrarModalAlta(false)}
                  className="px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={alta.isPending}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
                >
                  {alta.isPending ? "Guardando..." : "Guardar Paciente"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function PacienteDetallePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const usuario = getIdentidad();
  const roles = usuario?.roles || [];
  const puedeEditar = permite(roles, "pacientes", "actualizar");
  const puedeDarBaja = permite(roles, "pacientes", "borrar");

  const { data: paciente, isLoading, error, refetch } = usePaciente(id || "");
  const { edicion, cambiarOptin, baja } = useMutacionesPacientes();

  const [editando, setEditando] = useState(false);
  const [telefono, setTelefono] = useState("");
  const [email, setEmail] = useState("");
  const [nroAfiliado, setNroAfiliado] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  React.useEffect(() => {
    if (paciente) {
      setTelefono(paciente.telefono || "");
      setEmail(paciente.email || "");
      setNroAfiliado(paciente.nro_afiliado || "");
      setObservaciones(paciente.observaciones || "");
    }
  }, [paciente]);

  async function handleGuardarEdicion(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    try {
      await edicion.mutateAsync({
        id,
        input: {
          telefono: telefono.trim(),
          email: email.trim() || undefined,
          nro_afiliado: nroAfiliado.trim() || undefined,
          observaciones: observaciones.trim() || undefined,
        },
      });
      setEditando(false);
      setMensajeExito("Datos de contacto actualizados correctamente.");
      setTimeout(() => setMensajeExito(null), 3000);
    } catch {
      // Manejado por query state
    }
  }

  async function handleToggleOptin() {
    if (!id || !paciente) return;
    const nuevoValor = !paciente.optin_wa;
    await cambiarOptin.mutateAsync({ id, optin_wa: nuevoValor });
    setMensajeExito(
      nuevoValor
        ? "El paciente ahora recibirá notificaciones por WhatsApp."
        : "Se registró la baja de WhatsApp (STOP). No se enviarán mensajes automáticos.",
    );
    setTimeout(() => setMensajeExito(null), 4000);
  }

  async function handleBaja() {
    if (!id || !paciente) return;
    if (
      window.confirm(
        `¿Estás seguro de dar de baja lógica al paciente ${paciente.nombre}? Sus turnos históricos y fichas se conservarán.`,
      )
    ) {
      await baja.mutateAsync(id);
      navigate("/app/pacientes");
    }
  }

  if (isLoading) return <EstadoCargando mensaje="Cargando ficha del paciente..." />;
  if (error || !paciente) return <EstadoError error={error} alReintentar={() => refetch()} />;

  return (
    <div className="space-y-6" data-testid="paciente-detalle-page">
      {/* Barra superior con navegación y acceso a clínica */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link to="/app/pacientes" className="text-sm font-medium text-slate-500 hover:text-slate-800">
              ← Pacientes
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-sm font-semibold text-slate-900">{paciente.nombre}</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mt-1">{paciente.nombre}</h2>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to={`/app/pacientes/${paciente.id}/clinica`}
            className="inline-flex items-center px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-sm font-medium shadow-sm"
          >
            🦷 Historia Clínica y Odontograma
          </Link>
          {puedeDarBaja && (
            <button
              type="button"
              onClick={handleBaja}
              className="px-3 py-2 border border-red-200 text-red-600 hover:bg-red-50 rounded-md text-sm font-medium"
            >
              Dar de baja
            </button>
          )}
        </div>
      </div>

      {mensajeExito && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-md">
          {mensajeExito}
        </div>
      )}

      {/* Datos personales y contacto */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 space-y-6">
        <div className="flex justify-between items-center border-b border-slate-200 pb-3">
          <h3 className="text-base font-bold text-slate-900">Datos Personales y Contacto</h3>
          {puedeEditar && !editando && (
            <button
              type="button"
              onClick={() => setEditando(true)}
              className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 border border-emerald-300 px-3 py-1 rounded"
            >
              Editar Contacto
            </button>
          )}
        </div>

        {editando ? (
          <form onSubmit={handleGuardarEdicion} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Teléfono</label>
                <input
                  type="tel"
                  required
                  value={telefono}
                  onChange={(e) => setTelefono(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  N° Afiliado Obra Social
                </label>
                <input
                  type="text"
                  value={nroAfiliado}
                  onChange={(e) => setNroAfiliado(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Observaciones</label>
                <input
                  type="text"
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  className="w-full border border-slate-300 rounded-md p-2 text-sm"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3">
              <button
                type="button"
                onClick={() => setEditando(false)}
                className="px-3 py-1.5 border border-slate-300 rounded text-sm text-slate-700 hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={edicion.isPending}
                className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
              >
                {edicion.isPending ? "Guardando..." : "Guardar Cambios"}
              </button>
            </div>
          </form>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 text-sm">
            <div>
              <span className="block text-xs text-slate-500 font-medium">DNI</span>
              <span className="font-semibold text-slate-800">{formatearDni(paciente.dni)}</span>
            </div>

            <div>
              <span className="block text-xs text-slate-500 font-medium">Teléfono</span>
              <span className="font-semibold text-slate-800">{paciente.telefono}</span>
            </div>

            <div>
              <span className="block text-xs text-slate-500 font-medium">Email</span>
              <span className="font-semibold text-slate-800">{paciente.email || "No informado"}</span>
            </div>

            <div>
              <span className="block text-xs text-slate-500 font-medium">Fecha de Nacimiento</span>
              <span className="font-semibold text-slate-800">
                {paciente.fecha_nac ? formatearFechaCorta(paciente.fecha_nac) : "No informada"}
              </span>
            </div>

            <div>
              <span className="block text-xs text-slate-500 font-medium">N° de Afiliado</span>
              <span className="font-semibold text-slate-800">
                {paciente.nro_afiliado || "Particular"}
              </span>
            </div>

            <div>
              <span className="block text-xs text-slate-500 font-medium">Canal WhatsApp</span>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    paciente.optin_wa
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {paciente.optin_wa ? "Habilitado" : "Deshabilitado (STOP)"}
                </span>
                {puedeEditar && (
                  <button
                    type="button"
                    onClick={handleToggleOptin}
                    className="text-xs text-emerald-700 hover:underline"
                  >
                    {paciente.optin_wa ? "Desactivar" : "Activar"}
                  </button>
                )}
              </div>
            </div>

            {paciente.observaciones && (
              <div className="sm:col-span-2 md:col-span-3 bg-slate-50 p-3 rounded border border-slate-200">
                <span className="block text-xs text-slate-500 font-medium mb-1">
                  Observaciones Generales
                </span>
                <p className="text-slate-700 text-xs">{paciente.observaciones}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
