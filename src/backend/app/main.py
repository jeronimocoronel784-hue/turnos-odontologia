"""App FastAPI: routers por dominio, handlers globales, session por request."""

from fastapi import FastAPI

from app.api.routers import (
    admin_catalogo,
    agenda,
    auth,
    caja,
    clinica,
    comunicaciones,
    health,
    liquidaciones,
    lista_espera,
    pacientes,
    presupuestos,
    reserva_publica,
    usuarios,
    webhooks_mercadopago,
)
from app.shared.exceptions import register_handlers

app = FastAPI(title="Turnos Odontología", version="0.1.0")
register_handlers(app)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(usuarios.router, prefix="/api")
app.include_router(admin_catalogo.router, prefix="/api")
app.include_router(pacientes.router, prefix="/api")
app.include_router(presupuestos.router, prefix="/api")
app.include_router(agenda.router, prefix="/api")
app.include_router(caja.router, prefix="/api")
app.include_router(clinica.router, prefix="/api")
app.include_router(liquidaciones.router, prefix="/api")
app.include_router(clinica.router_publico_firma)
app.include_router(clinica.router_publico_firma, prefix="/api")
app.include_router(lista_espera.router, prefix="/api")
app.include_router(comunicaciones.router, prefix="/api")
app.include_router(comunicaciones.router_webhook)
app.include_router(comunicaciones.router_webhook, prefix="/api")
app.include_router(webhooks_mercadopago.router, prefix="/api")
app.include_router(webhooks_mercadopago.router_webhook)
app.include_router(webhooks_mercadopago.router_webhook, prefix="/api")
app.include_router(lista_espera.router_publico)
app.include_router(lista_espera.router_publico, prefix="/api")
app.include_router(reserva_publica.router)
app.include_router(reserva_publica.router, prefix="/api")
