"""App FastAPI: routers por dominio, handlers globales, session por request."""

from fastapi import FastAPI

from app.api.routers import health
from app.shared.exceptions import register_handlers

app = FastAPI(title="Turnos Odontología", version="0.1.0")
register_handlers(app)
app.include_router(health.router, prefix="/api")
