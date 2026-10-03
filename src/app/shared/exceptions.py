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
