import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  buscarPacientes,
  obtenerPaciente,
  crearPaciente,
  actualizarPaciente,
  actualizarOptinWA,
  darDeBajaPaciente,
} from "./api";
import { queryKeys } from "../../shared/query-keys";
import { PacienteCreateInput, PacienteUpdateInput } from "../../shared/api-types";

export function usePacientes(q?: string, incluirInactivos = false) {
  return useQuery({
    queryKey: queryKeys.pacientes.lista(q),
    queryFn: () => buscarPacientes(q, incluirInactivos),
    staleTime: 30 * 1000,
  });
}

export function usePaciente(id: string) {
  return useQuery({
    queryKey: queryKeys.pacientes.detalle(id),
    queryFn: () => obtenerPaciente(id),
    enabled: Boolean(id),
  });
}

export function useMutacionesPacientes() {
  const queryClient = useQueryClient();

  const alta = useMutation({
    mutationFn: (input: PacienteCreateInput) => crearPaciente(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.todos });
    },
  });

  const edicion = useMutation({
    mutationFn: ({ id, input }: { id: string; input: PacienteUpdateInput }) =>
      actualizarPaciente(id, input),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.todos });
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.detalle(vars.id) });
    },
  });

  const cambiarOptin = useMutation({
    mutationFn: ({ id, optin_wa }: { id: string; optin_wa: boolean }) =>
      actualizarOptinWA(id, optin_wa),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.todos });
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.detalle(vars.id) });
    },
  });

  const baja = useMutation({
    mutationFn: (id: string) => darDeBajaPaciente(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pacientes.todos });
    },
  });

  return { alta, edicion, cambiarOptin, baja };
}
