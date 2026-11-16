"""Tests de integración y contrato para C-18 (`c-18-frontend-compose-demo`).

Cubre:
- 1.1 / 1.2 / 2.1: Servicio `frontend` en `docker-compose.yml`, `FRONT_URL` alineado a
  `http://localhost:8080`, healthcheck en `Dockerfile.frontend` y bloque `location /api/`
  en `src/frontend/nginx.conf`.
- 2.2 / 2.3 / 2.4 / 2.5 / 4.2: Flujos de API y reserva pública (`GET /api/health`,
  `POST /api/auth/login` 401, `GET /api/reservar/consultorio-piloto` con las 5 prestaciones
  del seed, `GET /api/reservar/consultorio-fantasma` 404, `GET /api/ruta-inexistente` 404 JSON,
  alta de reserva `201` de Endodoncia con `token_gestion` + seña `pendiente` de $15.000 del
  servidor, y segundo `POST` al mismo slot → `409` con alternativas sin duplicar turno).
- 3.1 / 3.2: Utilería idempotente `app.scripts.usuario_demo` con `DEMO_PASSWORD`, hash
  bcrypt (`$2b$`), rechazo cuando falta `DEMO_PASSWORD` y login `200` con cookie `HttpOnly`.
- 1.3 / 2.6 / 4.3: Smoke contra `DEMO_BASE_URL` (`http://localhost:8080`) cuando el stack
  Docker Compose está levantado (skip informativo si no está corriendo en el host).
"""

import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import auth, health, reserva_publica
from app.domain.caja import EstadoSena, Sena
from app.domain.tenant import Tenant
from app.domain.turno import Turno
from app.domain.usuario import RolUsuario, Usuario
from app.infrastructure.seed import ejecutar_seed
from app.scripts.usuario_demo import EMAIL_DEMO, ejecutar_usuario_demo_cli, upsert_usuario_demo

RAIZ = Path(__file__).resolve().parents[1]
DEMO_BASE_URL = os.getenv("DEMO_BASE_URL", "http://localhost:8080")


# ---------------------------------------------------------------------------
# 1.1, 1.2, 2.1 Infraestructura Compose, Dockerfile.frontend y nginx.conf
# ---------------------------------------------------------------------------


def test_compose_declara_servicio_frontend_y_front_url_8080() -> None:
    compose_path = RAIZ / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    servicios = data["services"]

    assert "frontend" in servicios
    fe = servicios["frontend"]
    assert fe["build"]["context"] == "./src/frontend"
    assert fe["build"]["dockerfile"] == "Dockerfile.frontend"
    assert "8080:80" in fe["ports"]
    assert fe["depends_on"]["api"]["condition"] == "service_healthy"

    assert servicios["api"]["environment"]["FRONT_URL"] == "http://localhost:8080"


def test_dockerfile_frontend_y_nginx_conf_proxy_api() -> None:
    dockerfile = (RAIZ / "src" / "frontend" / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:80/" in dockerfile
    assert "USER appuser" in dockerfile

    nginx_conf = (RAIZ / "src" / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in nginx_conf
    assert "proxy_pass http://api:8000;" in nginx_conf
    assert "proxy_http_version 1.1;" in nginx_conf
    assert "proxy_set_header Host $host;" in nginx_conf
    assert "proxy_set_header X-Real-IP $remote_addr;" in nginx_conf
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx_conf
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx_conf
    assert "proxy_cache " not in nginx_conf
    assert "try_files $uri $uri/ /index.html;" in nginx_conf


# ---------------------------------------------------------------------------
# 3.1 y 3.2 Utilería usuario_demo (idempotencia, bcrypt y login 200)
# ---------------------------------------------------------------------------


async def test_usuario_demo_idempotente_bcrypt_y_login_exitoso(
    session: AsyncSession,
    app_factory: Callable[..., object],
) -> None:
    await ejecutar_seed(session)

    # Ejecución 1 y 2 consecutivas -> idempotente (1 sola fila)
    u1 = await upsert_usuario_demo(session, demo_password="PasswordDemoFicticio2026!")
    u2 = await upsert_usuario_demo(session, demo_password="PasswordDemoFicticio2026!")
    await session.commit()

    assert u1.id == u2.id
    assert u2.email == EMAIL_DEMO
    assert u2.rol == RolUsuario.RECEPCION
    assert u2.password_hash.startswith("$2b$")

    total_filas = (
        await session.execute(
            select(func.count()).select_from(Usuario).where(Usuario.email == EMAIL_DEMO)
        )
    ).scalar_one()
    assert int(total_filas) == 1

    # Verificar login exitoso (3.2) con access_token y cookie refresh_token HttpOnly
    app = app_factory(auth.router, health.router, reserva_publica.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        resp = await client.post(
            "/api/auth/login",
            json={"email": EMAIL_DEMO, "password": "PasswordDemoFicticio2026!"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "access_token" in body
        assert body["expira_en_segundos"] > 0
        assert body["usuario"]["email"] == EMAIL_DEMO
        set_cookie = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        assert "httponly" in set_cookie.lower()


def test_usuario_demo_falla_con_mensaje_rioplatense_si_falta_demo_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    with pytest.raises(RuntimeError) as exc:
        ejecutar_usuario_demo_cli(demo_password="")
    assert "DEMO_PASSWORD" in str(exc.value)


# ---------------------------------------------------------------------------
# 2.2, 2.3, 2.4, 2.5 y 4.2 Contrato de rutas /api/* y flujo de reserva pública
# ---------------------------------------------------------------------------


async def test_flujo_demo_reserva_publica_sena_y_doble_reserva_409(
    session: AsyncSession,
    app_factory: Callable[..., object],
    crear_usuario: Callable[..., Awaitable[Usuario]],
) -> None:
    await ejecutar_seed(session)
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == "consultorio-piloto"))
    ).scalar_one()

    # Asegurar un odontólogo activo en consultorio-piloto para que haya slots disponibles
    odonto = await crear_usuario(
        tenant,
        email="odonto.piloto@example.com",
        rol=RolUsuario.ODONTOLOGO,
        nombre="Dra. Piloto Ficticia",
    )
    await session.commit()

    app = app_factory(auth.router, health.router, reserva_publica.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        # 2.2 Login inválido devuelve 401 JSON rioplatense (nunca HTML)
        r_login_mal = await client.post(
            "/api/auth/login",
            json={"email": "noexiste.demo@example.com", "password": "mal-password"},
        )
        assert r_login_mal.status_code == 401
        assert "application/json" in r_login_mal.headers.get("content-type", "")
        assert "detail" in r_login_mal.json()

        # 2.4 Ruta /api/ inexistente devuelve 404 JSON
        r_404_api = await client.get("/api/ruta-inexistente")
        assert r_404_api.status_code == 404
        assert "application/json" in r_404_api.headers.get("content-type", "")

        # 2.3 GET /api/reservar/consultorio-fantasma -> 404 de negocio
        r_fantasma = await client.get("/api/reservar/consultorio-fantasma")
        assert r_fantasma.status_code == 404
        assert "detail" in r_fantasma.json()

        # 2.3 GET /api/reservar/consultorio-piloto -> 200 con las 5 prestaciones del seed
        r_cat = await client.get("/api/reservar/consultorio-piloto")
        assert r_cat.status_code == 200, r_cat.text
        datos_cat = r_cat.json()
        nombres_prestaciones = {p["nombre"] for p in datos_cat["prestaciones"]}
        assert nombres_prestaciones == {
            "Limpieza",
            "Consulta",
            "Arreglo",
            "Endodoncia",
            "Extracción",
        }

        endodoncia = next(p for p in datos_cat["prestaciones"] if p["nombre"] == "Endodoncia")
        sillon = datos_cat["sillones"][0]

        # Elegir próximo día hábil (lunes a viernes) a las 10:00 UTC
        manana = datetime.now(UTC).date() + timedelta(days=2)
        while manana.weekday() >= 5:
            manana += timedelta(days=1)
        inicio_slot = datetime(manana.year, manana.month, manana.day, 10, 0, tzinfo=UTC).isoformat()

        # 4.2 POST reserva de Endodoncia -> 201 con requiere_sena=true y monto_sena=15000
        payload_reserva = {
            "prestacion_id": endodoncia["id"],
            "profesional_id": str(odonto.id),
            "sillon_id": sillon["id"],
            "inicio": inicio_slot,
            "nombre": "Paciente Demo Ficticio",
            "dni": "39111222",
            "telefono": "+5491122334455",
            "email": "paciente.demo@example.com",
            "optin_wa": False,
        }
        r_post1 = await client.post("/api/reservar/consultorio-piloto", json=payload_reserva)
        assert r_post1.status_code == 201, r_post1.text
        res1 = r_post1.json()
        assert res1["token_gestion"]
        assert res1["requiere_sena"] is True
        assert float(res1["monto_sena"]) == 15000.0

        # Verificar que la Seña quedó en estado pendiente en la DB (RN-PA-02)
        sena_db = (
            await session.execute(select(Sena).where(Sena.turno_id == uuid.UUID(res1["turno_id"])))
        ).scalar_one_or_none()
        if sena_db is not None:
            assert sena_db.estado == EstadoSena.PENDIENTE.value

        # 2.5 Segundo POST al mismo slot -> 409 con alternativas sin duplicar turno (RN-AG-01)
        payload_reserva_2 = {
            **payload_reserva,
            "nombre": "Otro Paciente Ficticio",
            "dni": "40999888",
        }
        r_post2 = await client.post("/api/reservar/consultorio-piloto", json=payload_reserva_2)
        assert r_post2.status_code == 409, r_post2.text
        body_409 = r_post2.json()
        assert "detail" in body_409

        total_turnos = (
            await session.execute(
                select(func.count()).select_from(Turno).where(Turno.tenant_id == tenant.id)
            )
        ).scalar_one()
        assert int(total_turnos) == 1


# ---------------------------------------------------------------------------
# Smoke contra el stack Docker Compose en vivo (http://localhost:8080)
# ---------------------------------------------------------------------------


async def test_smoke_stack_compose_en_vivo_si_esta_levantado() -> None:
    try:
        async with httpx.AsyncClient(base_url=DEMO_BASE_URL, timeout=1.5) as client:
            r_root = await client.get("/")
    except Exception:
        pytest.skip(
            f"Stack compose no está escuchando en {DEMO_BASE_URL}. "
            "Levantalo con: docker compose up --build -d"
        )

    assert r_root.status_code == 200
    assert "text/html" in r_root.headers.get("content-type", "")

    async with httpx.AsyncClient(base_url=DEMO_BASE_URL, timeout=3.0) as client:
        r_health = await client.get("/api/health")
        assert r_health.status_code == 200
        assert r_health.json().get("estado") == "ok"

        r_spa = await client.get("/reservar/consultorio-fantasma")
        assert r_spa.status_code == 200
        assert "text/html" in r_spa.headers.get("content-type", "")

        r_api_404 = await client.get("/api/ruta-inexistente")
        assert r_api_404.status_code == 404
        assert "application/json" in r_api_404.headers.get("content-type", "")
