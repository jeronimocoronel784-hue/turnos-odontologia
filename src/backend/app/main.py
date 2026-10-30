"""App FastAPI: routers por dominio, handlers globales, session por request."""

from fastapi import FastAPI

from app.api.routers import admin_catalogo, auth, health, pacientes, usuarios
from app.shared.exceptions import register_handlers

app = FastAPI(title="Turnos Odontología", version="0.1.0")
register_handlers(app)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(usuarios.router, prefix="/api")
app.include_router(admin_catalogo.router, prefix="/api")
app.include_router(pacientes.router, prefix="/api")
