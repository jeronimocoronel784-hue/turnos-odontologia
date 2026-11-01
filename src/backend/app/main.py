"""App FastAPI: routers por dominio, handlers globales, session por request."""

from fastapi import FastAPI

from app.api.routers import (
    admin_catalogo,
    agenda,
    auth,
    comunicaciones,
    health,
    lista_espera,
    pacientes,
    reserva_publica,
    usuarios,
)
from app.shared.exceptions import register_handlers

app = FastAPI(title="Turnos Odontología", version="0.1.0")
register_handlers(app)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(usuarios.router, prefix="/api")
app.include_router(admin_catalogo.router, prefix="/api")
app.include_router(pacientes.router, prefix="/api")
app.include_router(agenda.router, prefix="/api")
app.include_router(lista_espera.router, prefix="/api")
app.include_router(comunicaciones.router, prefix="/api")
app.include_router(comunicaciones.router_webhook)
app.include_router(comunicaciones.router_webhook, prefix="/api")
app.include_router(lista_espera.router_publico)
app.include_router(reserva_publica.router)
app.include_router(reserva_publica.router, prefix="/api")
