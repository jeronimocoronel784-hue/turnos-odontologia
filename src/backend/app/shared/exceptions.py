"""Errores custom + handlers globales. Mensajes en rioplatense (RN-GL-02), sin stack traces (R9)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Error de negocio: mensaje seguro para mostrar al cliente."""

    status_code: int = 400

    def __init__(self, mensaje: str, status_code: int | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        if status_code is not None:
            self.status_code = status_code


class ServicioNoDisponible(AppError):
    """Dependencia (DB/Redis) caída: 503 con indicación de qué revisar."""

    status_code = 503

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje, 503)


class NoAutenticado(AppError):
    """Falta token, venció o es inválido: 401 sin filtrar el motivo real."""

    status_code = 401

    def __init__(
        self, mensaje: str = "Che, tu sesión no es válida. Iniciá sesión de nuevo."
    ) -> None:
        super().__init__(mensaje, 401)


class CredencialesInvalidas(AppError):
    """Login fallido: mismo mensaje para email inexistente, password mal o inactivo."""

    status_code = 401

    def __init__(
        self, mensaje: str = "El email o la contraseña no son correctos. Probá de nuevo."
    ) -> None:
        super().__init__(mensaje, 401)


class PermisoInsuficiente(AppError):
    """Rol sin permiso sobre el recurso: 403 sin revelar si el recurso existe."""

    status_code = 403

    def __init__(
        self,
        mensaje: str = "No tenés permiso para esta acción. Si la necesitás, pedísela al dueño.",
    ) -> None:
        super().__init__(mensaje, 403)


class DemasiadosIntentos(AppError):
    """Rate limit de login superado: 429 con indicación de espera."""

    status_code = 429

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje, 429)


class SolicitudInvalida(AppError):
    """Input válido en forma pero imposible de resolver (ej. email en 2 consultorios)."""

    status_code = 400

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje, 400)


class NoEncontrado(AppError):
    """El recurso no existe en el tenant del actor: 404 sin datos de terceros."""

    status_code = 404

    def __init__(self, mensaje: str = "No encontramos lo que buscabas.") -> None:
        super().__init__(mensaje, 404)


class Conflicto(AppError):
    """Choque con una regla de unicidad (ej. email ya usado en el tenant): 409."""

    status_code = 409

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje, 409)


class EntidadInvalida(AppError):
    """Regla de validación semántica violada en tiempo de ejecución: 422."""

    status_code = 422

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje, 422)


def register_handlers(app: FastAPI) -> None:
    """Registra handlers globales: ningún error expone stack trace ni PHI."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensaje})

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "¡Uh! Algo salió mal de nuestro lado. Probá de nuevo en un rato."},
        )
