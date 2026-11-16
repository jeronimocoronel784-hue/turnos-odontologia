import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/query-keys";
import {
  crearPlantilla,
  listarMensajes,
  listarPlantillas,
  reenviarMensaje,
  type FiltrosMensajes,
} from "./api";
import type { PlantillaCreateInput } from "../../shared/api-types";

export function useMensajes(filtros: FiltrosMensajes = {}) {
  return useQuery({
    queryKey: queryKeys.comunicaciones.mensajes(filtros),
    queryFn: () => listarMensajes(filtros),
  });
}

export function usePlantillas() {
  return useQuery({
    queryKey: queryKeys.comunicaciones.plantillas,
    queryFn: listarPlantillas,
  });
}

export function useReenviarMensaje() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mensajeId: string) => reenviarMensaje(mensajeId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["comunicaciones", "mensajes"] });
    },
  });
}

export function useCrearPlantilla() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datos: PlantillaCreateInput) => crearPlantilla(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.comunicaciones.plantillas });
    },
  });
}
