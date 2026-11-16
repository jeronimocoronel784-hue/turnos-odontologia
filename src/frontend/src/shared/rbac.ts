import { RolUsuario } from "./api-types";

export type Recurso =
  | "configuracion"
  | "usuarios"
  | "pacientes"
  | "agenda"
  | "bloqueos"
  | "lista_espera"
  | "clinica"
  | "presupuestos"
  | "consentimientos"
  | "caja"
  | "liquidaciones"
  | "mensajes"
  | "auditoria"
  | "exportacion";

export type Accion =
  | "leer"
  | "crear"
  | "actualizar"
  | "borrar"
  | "reabrir_cierre"
  | "reenviar"
  | "exportar";

const CRUD: readonly Accion[] = ["leer", "crear", "actualizar", "borrar"];
const SOLO_LECTURA: readonly Accion[] = ["leer"];
const NINGUNO: readonly Accion[] = [];

// Espejo de la matriz declarativa de src/backend/app/domain/rbac.py (D4)
export const MATRIZ_RBAC: Record<Recurso, Record<string, readonly Accion[]>> = {
  configuracion: { dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: SOLO_LECTURA },
  usuarios: { dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: SOLO_LECTURA },
  pacientes: { dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA },
  agenda: {
    dueno: CRUD,
    recepcion: CRUD,
    odontologo: ["leer", "actualizar"],
  },
  bloqueos: { dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA },
  lista_espera: { dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA },
  clinica: { dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: CRUD },
  presupuestos: { dueno: CRUD, recepcion: CRUD, odontologo: CRUD },
  consentimientos: { dueno: CRUD, recepcion: CRUD, odontologo: CRUD },
  caja: {
    dueno: [...CRUD, "reabrir_cierre"],
    recepcion: CRUD,
    odontologo: SOLO_LECTURA,
  },
  liquidaciones: {
    dueno: [...CRUD, "exportar"],
    recepcion: [...CRUD, "exportar"],
    odontologo: SOLO_LECTURA,
  },
  mensajes: {
    dueno: CRUD,
    recepcion: ["leer", "reenviar"],
    odontologo: NINGUNO,
  },
  auditoria: { dueno: SOLO_LECTURA, recepcion: NINGUNO, odontologo: NINGUNO },
  exportacion: {
    dueno: ["exportar"],
    recepcion: ["exportar"],
    odontologo: ["exportar"],
  },
};

/**
 * Consulta si alguno de los roles del usuario tiene permiso para ejecutar la acción sobre el recurso.
 * Deniega por defecto ante roles desconocidos, nulos o vacíos.
 */
export function permite(
  roles: readonly RolUsuario[] | null | undefined,
  recurso: Recurso,
  accion: Accion,
): boolean {
  if (!roles || roles.length === 0) return false;

  const reglasRecurso = MATRIZ_RBAC[recurso];
  if (!reglasRecurso) return false;

  return roles.some((rol) => {
    const accionesPermitidas = reglasRecurso[rol];
    if (!accionesPermitidas) return false;
    return accionesPermitidas.includes(accion);
  });
}
