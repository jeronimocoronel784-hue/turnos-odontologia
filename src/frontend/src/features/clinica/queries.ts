import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  obtenerFicha,
  actualizarFicha,
  obtenerEvoluciones,
  crearEvolucion,
  obtenerOdontograma,
  crearEventoPieza,
  obtenerHistorialPieza,
  obtenerAdjuntos,
  crearAdjunto,
  obtenerConsentimientos,
  crearConsentimiento,
  firmarConsentimiento,
  revocarConsentimiento,
  obtenerPresupuestos,
  crearPresupuesto,
  transicionarPresupuesto,
  vincularTurnoPresupuesto,
} from "./api";
import { queryKeys } from "../../shared/query-keys";
import {
  FichaClinicaUpdateInput,
  EvolucionCreateInput,
  PiezaEventoCreateInput,
  AdjuntoCreateInput,
  ConsentimientoCreateInput,
  ConsentimientoFirmaInput,
  PresupuestoCreateInput,
  PresupuestoVincularTurnoInput,
} from "../../shared/api-types";

export function useClinica(pacienteId: string) {
  const fichaQuery = useQuery({
    queryKey: queryKeys.pacientes.ficha(pacienteId),
    queryFn: () => obtenerFicha(pacienteId),
    enabled: Boolean(pacienteId),
  });

  const evolucionesQuery = useQuery({
    queryKey: queryKeys.clinica.evoluciones(pacienteId),
    queryFn: () => obtenerEvoluciones(pacienteId),
    enabled: Boolean(pacienteId),
  });

  const odontogramaQuery = useQuery({
    queryKey: queryKeys.clinica.odontograma(pacienteId),
    queryFn: () => obtenerOdontograma(pacienteId),
    enabled: Boolean(pacienteId),
  });

  const adjuntosQuery = useQuery({
    queryKey: queryKeys.clinica.adjuntos(pacienteId),
    queryFn: () => obtenerAdjuntos(pacienteId),
    enabled: Boolean(pacienteId),
  });

  const consentimientosQuery = useQuery({
    queryKey: queryKeys.clinica.consentimientos(pacienteId),
    queryFn: () => obtenerConsentimientos(pacienteId),
    enabled: Boolean(pacienteId),
  });

  const presupuestosQuery = useQuery({
    queryKey: queryKeys.clinica.presupuestos(pacienteId),
    queryFn: () => obtenerPresupuestos(pacienteId),
    enabled: Boolean(pacienteId),
  });

  return {
    ficha: fichaQuery.data,
    evoluciones: evolucionesQuery.data ?? [],
    odontograma: odontogramaQuery.data,
    adjuntos: adjuntosQuery.data ?? [],
    consentimientos: consentimientosQuery.data ?? [],
    presupuestos: presupuestosQuery.data ?? [],
    cargando:
      fichaQuery.isLoading ||
      evolucionesQuery.isLoading ||
      odontogramaQuery.isLoading ||
      consentimientosQuery.isLoading ||
      presupuestosQuery.isLoading,
    error:
      fichaQuery.error ||
      evolucionesQuery.error ||
      odontogramaQuery.error ||
      consentimientosQuery.error,
  };
}

export function useHistorialPieza(pacienteId: string, pieza: number | null) {
  return useQuery({
    queryKey: pieza ? queryKeys.clinica.historialPieza(pacienteId, pieza) : [],
    queryFn: () => (pieza ? obtenerHistorialPieza(pacienteId, pieza) : Promise.resolve([])),
    enabled: Boolean(pacienteId && pieza),
  });
}

export function useMutacionesClinica(pacienteId: string) {
  const queryClient = useQueryClient();

  const guardarFicha = useMutation({
    mutationFn: (input: FichaClinicaUpdateInput) => actualizarFicha(pacienteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.ficha(pacienteId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.evoluciones(pacienteId) });
    },
  });

  const registrarEvolucion = useMutation({
    mutationFn: (input: EvolucionCreateInput) => crearEvolucion(pacienteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.evoluciones(pacienteId) });
    },
  });

  const registrarEventoPieza = useMutation({
    mutationFn: (input: PiezaEventoCreateInput) => crearEventoPieza(pacienteId, input),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.odontograma(pacienteId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clinica.historialPieza(pacienteId, vars.pieza_fdi),
      });
    },
  });

  const subirAdjunto = useMutation({
    mutationFn: (input: AdjuntoCreateInput) => crearAdjunto(pacienteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.adjuntos(pacienteId) });
    },
  });

  const altaConsentimiento = useMutation({
    mutationFn: (input: ConsentimientoCreateInput) => crearConsentimiento(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.consentimientos(pacienteId) });
    },
  });

  const registrarFirma = useMutation({
    mutationFn: ({ id, input }: { id: string; input: ConsentimientoFirmaInput }) =>
      firmarConsentimiento(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.consentimientos(pacienteId) });
    },
  });

  const anularConsentimiento = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      revocarConsentimiento(id, motivo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.consentimientos(pacienteId) });
    },
  });

  const altaPresupuesto = useMutation({
    mutationFn: (input: PresupuestoCreateInput) => crearPresupuesto(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.presupuestos(pacienteId) });
    },
  });

  const cambiarEstadoPresupuesto = useMutation({
    mutationFn: ({
      id,
      accion,
    }: {
      id: string;
      accion: "presentar" | "aceptar" | "rechazar" | "finalizar";
    }) => transicionarPresupuesto(id, accion),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.presupuestos(pacienteId) });
    },
  });

  const asociarTurno = useMutation({
    mutationFn: ({
      presupuestoId,
      input,
    }: {
      presupuestoId: string;
      input: PresupuestoVincularTurnoInput;
    }) => vincularTurnoPresupuesto(presupuestoId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clinica.presupuestos(pacienteId) });
    },
  });

  return {
    guardarFicha,
    registrarEvolucion,
    registrarEventoPieza,
    subirAdjunto,
    altaConsentimiento,
    registrarFirma,
    anularConsentimiento,
    altaPresupuesto,
    cambiarEstadoPresupuesto,
    asociarTurno,
  };
}
