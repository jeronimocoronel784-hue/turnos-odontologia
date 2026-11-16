import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/query-keys";
import {
  actualizarDebitosLiquidacionOS,
  anularLiquidacionOS,
  cerrarLiquidacionOS,
  consultarCoberturaOS,
  crearLiquidacionOS,
  listarLiquidacionesOS,
  obtenerLiquidacionOS,
  registrarResultadoLiquidacionOS,
  type FiltrosCoberturaLookup,
} from "./api";
import type {
  LiquidacionOSAnularInput,
  LiquidacionOSCerrarInput,
  LiquidacionOSCreateInput,
  LiquidacionOSDebitosInput,
  ResultadoOSInput,
} from "../../shared/api-types";

export function useCoberturaOS(filtros: FiltrosCoberturaLookup, habilitado: boolean) {
  return useQuery({
    queryKey: queryKeys.os.cobertura(filtros),
    queryFn: () => consultarCoberturaOS(filtros),
    enabled: habilitado && Boolean(filtros.prestacion_id || filtros.turno_id),
  });
}

export function useLiquidacionesOS(filtros?: {
  obra_social?: string;
  periodo?: string;
  estado?: string;
}) {
  return useQuery({
    queryKey: queryKeys.os.liquidaciones(filtros),
    queryFn: () => listarLiquidacionesOS(filtros),
  });
}

export function useLiquidacionOSDetalle(id: string) {
  return useQuery({
    queryKey: queryKeys.os.liquidacionDetalle(id),
    queryFn: () => obtenerLiquidacionOS(id),
    enabled: Boolean(id),
  });
}

export function useMutacionesOS() {
  const qc = useQueryClient();

  const crearLiquidacion = useMutation({
    mutationFn: (datos: LiquidacionOSCreateInput) => crearLiquidacionOS(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["os"] });
    },
  });

  const actualizarDebitos = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: LiquidacionOSDebitosInput }) =>
      actualizarDebitosLiquidacionOS(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["os"] });
    },
  });

  const cerrarLiquidacion = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos?: LiquidacionOSCerrarInput }) =>
      cerrarLiquidacionOS(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["os"] });
    },
  });

  const registrarResultado = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: ResultadoOSInput }) =>
      registrarResultadoLiquidacionOS(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["os"] });
    },
  });

  const anularLiquidacion = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: LiquidacionOSAnularInput }) =>
      anularLiquidacionOS(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["os"] });
    },
  });

  return {
    crearLiquidacion,
    actualizarDebitos,
    cerrarLiquidacion,
    registrarResultado,
    anularLiquidacion,
  };
}
