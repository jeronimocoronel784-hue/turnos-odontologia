import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/query-keys";
import {
  abrirCierreCaja,
  cerrarCierreCaja,
  cobrarSena,
  cobrarTurno,
  crearMovimientoCaja,
  listarCierresCaja,
  listarMovimientosCaja,
  listarSenas,
  obtenerCierreCaja,
  obtenerLiquidacionTurno,
  reabrirCierreCaja,
  resolverCancelacionSena,
  vencerSena,
  type FiltrosMovimientosCaja,
} from "./api";
import type {
  CierreCajaAbrirInput,
  CierreCajaCerrarInput,
  CierreCajaReabrirInput,
  CobrarTurnoInput,
  MovimientoCajaCreateInput,
  SenaCobrarInput,
  SenaResolverCancelacionInput,
} from "../../shared/api-types";

export function useMovimientosCaja(filtros: FiltrosMovimientosCaja) {
  const tieneRangoOCierre = Boolean((filtros.desde && filtros.hasta) || filtros.cierre_id);
  return useQuery({
    queryKey: queryKeys.caja.movimientos(filtros),
    queryFn: () => listarMovimientosCaja(filtros),
    enabled: tieneRangoOCierre,
  });
}

export function useCierresCaja(filtros?: { fecha?: string; estado?: string }) {
  return useQuery({
    queryKey: queryKeys.caja.cierres(filtros),
    queryFn: () => listarCierresCaja(filtros),
  });
}

export function useCierreDetalle(cierreId: string) {
  return useQuery({
    queryKey: queryKeys.caja.cierreDetalle(cierreId),
    queryFn: () => obtenerCierreCaja(cierreId),
    enabled: Boolean(cierreId),
  });
}

export function useLiquidacionTurno(turnoId: string, obraSocial?: string) {
  return useQuery({
    queryKey: queryKeys.caja.liquidacionTurno(turnoId, obraSocial),
    queryFn: () => obtenerLiquidacionTurno(turnoId, obraSocial),
    enabled: Boolean(turnoId),
  });
}

export function useSenas(filtros?: { turno_id?: string; estado?: string }) {
  return useQuery({
    queryKey: queryKeys.caja.senas(filtros),
    queryFn: () => listarSenas(filtros),
  });
}

export function useMutacionesCaja() {
  const qc = useQueryClient();

  const crearMovimiento = useMutation({
    mutationFn: (datos: MovimientoCajaCreateInput) => crearMovimientoCaja(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
  });

  const abrirCierre = useMutation({
    mutationFn: (datos: CierreCajaAbrirInput) => abrirCierreCaja(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
  });

  const cerrarCierre = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: CierreCajaCerrarInput }) =>
      cerrarCierreCaja(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
  });

  const reabrirCierre = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: CierreCajaReabrirInput }) =>
      reabrirCierreCaja(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
  });

  const cobrarSaldoTurno = useMutation({
    mutationFn: ({ turnoId, datos }: { turnoId: string; datos: CobrarTurnoInput }) =>
      cobrarTurno(turnoId, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
  });

  const cobrarSenaMut = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: SenaCobrarInput }) => cobrarSena(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja", "senas"] });
      qc.invalidateQueries({ queryKey: ["caja", "movimientos"] });
    },
  });

  const cancelarSenaMut = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: SenaResolverCancelacionInput }) =>
      resolverCancelacionSena(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja", "senas"] });
    },
  });

  const vencerSenaMut = useMutation({
    mutationFn: (id: string) => vencerSena(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["caja", "senas"] });
    },
  });

  return {
    crearMovimiento,
    abrirCierre,
    cerrarCierre,
    reabrirCierre,
    cobrarSaldoTurno,
    cobrarSenaMut,
    cancelarSenaMut,
    vencerSenaMut,
  };
}
