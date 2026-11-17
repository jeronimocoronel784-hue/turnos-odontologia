import { useQuery } from "@tanstack/react-query";
import {
  listarAuditoria,
  listarUsuariosAuditoria,
  obtenerEstadoJob,
  AuditoriaFiltros,
} from "./api";

export function useAuditoriaTrail(filtros: AuditoriaFiltros, cursor: string | null) {
  return useQuery({
    queryKey: ["auditoria", "trail", filtros, cursor],
    queryFn: () => listarAuditoria({ ...filtros, cursor }),
    staleTime: 0,
  });
}

export function useUsuariosAuditoria() {
  return useQuery({
    queryKey: ["auditoria", "usuarios"],
    queryFn: () => listarUsuariosAuditoria(),
    staleTime: 60 * 1000,
  });
}

export function useEstadoJob(jobId: string | null) {
  return useQuery({
    queryKey: ["auditoria", "job", jobId],
    queryFn: () => obtenerEstadoJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: false,
  });
}
