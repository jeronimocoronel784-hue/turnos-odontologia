"""GET /api/health: 200 sano, 503 con rioplatense si cae una dependencia (spec 1.1)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.api.routers import health
from app.api.schemas import HealthEstado
from app.shared.exceptions import register_handlers
from app.shared.settings import Settings

SETTINGS_TEST = Settings(
    database_url="sqlite+aiosqlite:///:memory:",
    redis_url="redis://localhost:6379/0",
    jwt_secret="secreto-de-test-con-mas-de-32-caracteres-ok",
)


def _cliente(db_ok: bool, redis_ok: bool) -> TestClient:
    async def _db(_url: str) -> bool:
        return db_ok

    async def _redis(_url: str) -> bool:
        return redis_ok

    monkey_db = pytest.MonkeyPatch()
    monkey_db.setattr(health, "_chequear_db", _db)
    monkey_db.setattr(health, "_chequear_redis", _redis)

    app = FastAPI()
    register_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.dependency_overrides[deps.settings_cacheados] = lambda: SETTINGS_TEST
    cliente = TestClient(app, raise_server_exceptions=False)
    cliente.monkey_db = monkey_db  # type: ignore[attr-defined]
    return cliente


def test_api_sana_responde_ok() -> None:
    cliente = _cliente(db_ok=True, redis_ok=True)
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 200
    cuerpo = HealthEstado.model_validate(respuesta.json())
    assert cuerpo.estado == "ok"
    assert cuerpo.base_de_datos == "ok"
    assert cuerpo.redis == "ok"
    cliente.monkey_db.undo()  # type: ignore[attr-defined]


def test_db_caida_responde_503_en_rioplatense_sin_stack() -> None:
    cliente = _cliente(db_ok=False, redis_ok=True)
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 503
    cuerpo = HealthEstado.model_validate(respuesta.json())
    assert "base de datos" in cuerpo.detalle
    assert "traceback" not in respuesta.text.lower()
    assert "Traceback" not in respuesta.text
    cliente.monkey_db.undo()  # type: ignore[attr-defined]


def test_redis_caido_responde_503_que_nombra_redis() -> None:
    cliente = _cliente(db_ok=True, redis_ok=False)
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 503
    assert "redis" in HealthEstado.model_validate(respuesta.json()).detalle
    cliente.monkey_db.undo()  # type: ignore[attr-defined]
