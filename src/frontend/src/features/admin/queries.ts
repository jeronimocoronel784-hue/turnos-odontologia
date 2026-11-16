import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/query-keys";
import {
  actualizarCoberturaAdmin,
  actualizarPoliticasAdmin,
  actualizarPrestacionAdmin,
  actualizarSillonAdmin,
  cambiarRolUsuarioAdmin,
  crearCoberturaAdmin,
  crearPrestacionAdmin,
  crearSillonAdmin,
  crearUsuarioAdmin,
  desactivarCoberturaAdmin,
  desactivarPrestacionAdmin,
  desactivarSillonAdmin,
  listarCoberturasAdmin,
  listarPrestacionesAdmin,
  listarSillonesAdmin,
  listarUsuariosAdmin,
  obtenerPoliticasAdmin,
} from "./api";
import type {
  CoberturaOSCreateInput,
  CoberturaOSUpdateInput,
  PoliticasUpdateInput,
  PrestacionCreateInput,
  PrestacionUpdateInput,
  SillonCreateInput,
  SillonUpdateInput,
  UsuarioCreateInput,
  UsuarioRolUpdateInput,
} from "../../shared/api-types";

export function usePrestacionesAdmin() {
  return useQuery({
    queryKey: queryKeys.admin.prestaciones,
    queryFn: listarPrestacionesAdmin,
  });
}

export function useSillonesAdmin() {
  return useQuery({
    queryKey: queryKeys.admin.sillones,
    queryFn: listarSillonesAdmin,
  });
}

export function useCoberturasAdmin() {
  return useQuery({
    queryKey: queryKeys.admin.coberturas,
    queryFn: listarCoberturasAdmin,
  });
}

export function usePoliticasAdmin() {
  return useQuery({
    queryKey: queryKeys.admin.politicas,
    queryFn: obtenerPoliticasAdmin,
  });
}

export function useUsuariosAdmin() {
  return useQuery({
    queryKey: queryKeys.admin.usuarios,
    queryFn: listarUsuariosAdmin,
  });
}

export function useMutacionesAdmin() {
  const qc = useQueryClient();

  const crearPrestacion = useMutation({
    mutationFn: (datos: PrestacionCreateInput) => crearPrestacionAdmin(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.prestaciones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.prestaciones });
    },
  });

  const editarPrestacion = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: PrestacionUpdateInput }) =>
      actualizarPrestacionAdmin(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.prestaciones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.prestaciones });
    },
  });

  const desactivarPrestacion = useMutation({
    mutationFn: (id: string) => desactivarPrestacionAdmin(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.prestaciones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.prestaciones });
    },
  });

  const crearSillon = useMutation({
    mutationFn: (datos: SillonCreateInput) => crearSillonAdmin(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.sillones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.sillones });
    },
  });

  const editarSillon = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: SillonUpdateInput }) =>
      actualizarSillonAdmin(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.sillones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.sillones });
    },
  });

  const desactivarSillon = useMutation({
    mutationFn: (id: string) => desactivarSillonAdmin(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.sillones });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.sillones });
    },
  });

  const crearCobertura = useMutation({
    mutationFn: (datos: CoberturaOSCreateInput) => crearCoberturaAdmin(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.coberturas });
    },
  });

  const editarCobertura = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: CoberturaOSUpdateInput }) =>
      actualizarCoberturaAdmin(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.coberturas });
    },
  });

  const desactivarCobertura = useMutation({
    mutationFn: (id: string) => desactivarCoberturaAdmin(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.coberturas });
    },
  });

  const guardarPoliticas = useMutation({
    mutationFn: (datos: PoliticasUpdateInput) => actualizarPoliticasAdmin(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.politicas });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.politicas });
    },
  });

  const crearUsuario = useMutation({
    mutationFn: (datos: UsuarioCreateInput) => crearUsuarioAdmin(datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.usuarios });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.profesionales });
    },
  });

  const cambiarRolUsuario = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: UsuarioRolUpdateInput }) =>
      cambiarRolUsuarioAdmin(id, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.usuarios });
      qc.invalidateQueries({ queryKey: queryKeys.catalogos.profesionales });
    },
  });

  return {
    crearPrestacion,
    editarPrestacion,
    desactivarPrestacion,
    crearSillon,
    editarSillon,
    desactivarSillon,
    crearCobertura,
    editarCobertura,
    desactivarCobertura,
    guardarPoliticas,
    crearUsuario,
    cambiarRolUsuario,
  };
}
