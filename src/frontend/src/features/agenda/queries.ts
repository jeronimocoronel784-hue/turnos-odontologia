import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  obtenerAgenda,
  obtenerPoliticas,
  obtenerProfesionales,
  obtenerPrestaciones,
  obtenerSillones,
  obtenerPacientes,
  crearTurno,
  actualizarEstadoTurno,
  reprogramarTurno,
  crearBloqueo,
  eliminarBloqueo,
  FiltrosAgenda,
} from "./api";
import { queryKeys } from "../../shared/query-keys";
import {
  TurnoCreateInput,
  TurnoEstadoUpdateInput,
  TurnoReprogramarInputInternal,
  BloqueoCreateInput,
} from "../../shared/api-types";

export function useAgenda(filtros: FiltrosAgenda) {
  return useQuery({
    queryKey: queryKeys.agenda.rango(filtros),
    queryFn: () => obtenerAgenda(filtros),
    enabled: Boolean(filtros.desde && filtros.hasta),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    staleTime: 30000,
  });
}

export function useCatalogosAgenda() {
  const profesionalesQuery = useQuery({
    queryKey: queryKeys.catalogos.profesionales,
    queryFn: obtenerProfesionales,
    staleTime: 5 * 60 * 1000,
  });

  const prestacionesQuery = useQuery({
    queryKey: queryKeys.catalogos.prestaciones,
    queryFn: obtenerPrestaciones,
    staleTime: 5 * 60 * 1000,
  });

  const sillonesQuery = useQuery({
    queryKey: queryKeys.catalogos.sillones,
    queryFn: obtenerSillones,
    staleTime: 5 * 60 * 1000,
  });

  const politicasQuery = useQuery({
    queryKey: queryKeys.catalogos.politicas,
    queryFn: obtenerPoliticas,
    staleTime: 5 * 60 * 1000,
  });

  const pacientesQuery = useQuery({
    queryKey: queryKeys.pacientes.lista(),
    queryFn: obtenerPacientes,
    staleTime: 30 * 1000,
  });

  return {
    profesionales: profesionalesQuery.data ?? [],
    prestaciones: prestacionesQuery.data ?? [],
    sillones: sillonesQuery.data ?? [],
    politicas: politicasQuery.data,
    pacientes: pacientesQuery.data ?? [],
    cargando:
      profesionalesQuery.isLoading ||
      prestacionesQuery.isLoading ||
      sillonesQuery.isLoading ||
      pacientesQuery.isLoading,
  };
}

export function useMutacionesAgenda() {
  const queryClient = useQueryClient();

  const altaTurno = useMutation({
    mutationFn: (input: TurnoCreateInput) => crearTurno(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agenda.todas });
    },
  });

  const cambiarEstado = useMutation({
    mutationFn: ({ id, input }: { id: string; input: TurnoEstadoUpdateInput }) =>
      actualizarEstadoTurno(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agenda.todas });
    },
  });

  const reprogramar = useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: TurnoReprogramarInputInternal;
    }) => reprogramarTurno(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agenda.todas });
    },
  });

  const altaBloqueo = useMutation({
    mutationFn: (input: BloqueoCreateInput) => crearBloqueo(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agenda.todas });
    },
  });

  const bajaBloqueo = useMutation({
    mutationFn: (id: string) => eliminarBloqueo(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agenda.todas });
    },
  });

  return {
    altaTurno,
    cambiarEstado,
    reprogramar,
    altaBloqueo,
    bajaBloqueo,
  };
}
