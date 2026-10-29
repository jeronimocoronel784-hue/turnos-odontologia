"""Matriz RBAC declarativa: espejo de `03_actores_y_roles.md` (C-03, R4).

Se evalua en el backend, no en la UI: un rol sin permiso recibe 403 aunque el
cliente lo intente. `roles` es una lista para no romper el contrato cuando
aparezca multi-rol real; en v1 tiene un solo elemento.
"""

import enum
from collections.abc import Iterable


class Recurso(enum.StrEnum):
    """Recursos protegidos por la matriz (filas de §03)."""

    CONFIGURACION = "configuracion"
    USUARIOS = "usuarios"
    PACIENTES = "pacientes"
    AGENDA = "agenda"
    BLOQUEOS = "bloqueos"
    LISTA_ESPERA = "lista_espera"
    CLINICA = "clinica"
    PRESUPUESTOS = "presupuestos"
    CONSENTIMIENTOS = "consentimientos"
    CAJA = "caja"
    LIQUIDACIONES = "liquidaciones"
    MENSAJES = "mensajes"
    AUDITORIA = "auditoria"
    EXPORTACION = "exportacion"


class Accion(enum.StrEnum):
    """Acciones posibles sobre un recurso."""

    LEER = "leer"
    CREAR = "crear"
    ACTUALIZAR = "actualizar"
    BORRAR = "borrar"
    REABRIR_CIERRE = "reabrir_cierre"
    REENVIAR = "reenviar"
    EXPORTAR = "exportar"


def _permisos(*acciones: Accion) -> frozenset[Accion]:
    return frozenset(acciones)


CRUD = _permisos(Accion.LEER, Accion.CREAR, Accion.ACTUALIZAR, Accion.BORRAR)
SOLO_LECTURA = _permisos(Accion.LEER)
NINGUNO: frozenset[Accion] = frozenset()


def _matriz() -> dict[Recurso, dict[str, frozenset[Accion]]]:
    from app.domain.usuario import RolUsuario

    dueno = RolUsuario.DUENO.value
    recepcion = RolUsuario.RECEPCION.value
    odontologo = RolUsuario.ODONTOLOGO.value

    return {
        Recurso.CONFIGURACION: {dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: SOLO_LECTURA},
        Recurso.USUARIOS: {dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: SOLO_LECTURA},
        Recurso.PACIENTES: {dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA},
        Recurso.AGENDA: {
            dueno: CRUD,
            recepcion: CRUD,
            odontologo: _permisos(Accion.LEER, Accion.ACTUALIZAR),
        },
        Recurso.BLOQUEOS: {dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA},
        Recurso.LISTA_ESPERA: {dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA},
        Recurso.CLINICA: {dueno: CRUD, recepcion: SOLO_LECTURA, odontologo: CRUD},
        Recurso.PRESUPUESTOS: {dueno: CRUD, recepcion: CRUD, odontologo: CRUD},
        Recurso.CONSENTIMIENTOS: {dueno: CRUD, recepcion: CRUD, odontologo: CRUD},
        Recurso.CAJA: {
            dueno: _permisos(*CRUD, Accion.REABRIR_CIERRE),
            recepcion: CRUD,
            odontologo: SOLO_LECTURA,
        },
        Recurso.LIQUIDACIONES: {dueno: CRUD, recepcion: CRUD, odontologo: SOLO_LECTURA},
        Recurso.MENSAJES: {
            dueno: CRUD,
            recepcion: _permisos(Accion.LEER, Accion.REENVIAR),
            odontologo: NINGUNO,
        },
        Recurso.AUDITORIA: {dueno: SOLO_LECTURA, recepcion: NINGUNO, odontologo: NINGUNO},
        Recurso.EXPORTACION: {
            dueno: _permisos(Accion.EXPORTAR),
            recepcion: _permisos(Accion.EXPORTAR),
            odontologo: _permisos(Accion.EXPORTAR),
        },
    }


MATRIZ: dict[Recurso, dict[str, frozenset[Accion]]] = _matriz()


def permite(roles: Iterable[str], recurso: Recurso, accion: Accion) -> bool:
    """True si alguno de los roles del usuario tiene la accion sobre el recurso."""
    por_rol = MATRIZ[recurso]
    return any(accion in por_rol.get(str(rol), NINGUNO) for rol in roles)
