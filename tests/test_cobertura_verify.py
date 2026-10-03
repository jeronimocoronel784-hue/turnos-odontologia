"""Cobertura Verify C-01: escenarios del spec sin test dedicado en Apply.

- Alta directa de tenant piloto con políticas (spec core-models-multitenant).
- Manifest PWA instalable + shell con estado de la API (spec foundation-setup,
  checks estáticos sobre fuentes: en el job backend de CI no existe `dist/`).
- CI con jobs backend/frontend en paralelo (spec foundation-setup, check
  estático del workflow; la ejecución real corre en CI con Postgres/Redis).

Datos 100% ficticios (R13). Solo tests/verificaciones, sin código de producción.
"""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant import Tenant
from app.infrastructure.seed import POLITICAS_SEED, TENANT_SEED, ejecutar_seed


def _raiz() -> Path:
    return Path(__file__).resolve().parents[1]


async def test_alta_directa_tenant_piloto_con_politicas(session: AsyncSession) -> None:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="consultorio-piloto",
        nombre="Consultorio Piloto Ficticio",
        politicas=dict(POLITICAS_SEED),
        activo=True,
    )
    session.add(tenant)
    await session.flush()

    leido = (
        await session.execute(select(Tenant).where(Tenant.slug == "consultorio-piloto"))
    ).scalar_one()
    assert leido.id == tenant.id
    assert leido.politicas == POLITICAS_SEED
    assert leido.activo is True


async def test_seed_persiste_politicas_por_defecto_del_tenant(session: AsyncSession) -> None:
    await ejecutar_seed(session)
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == TENANT_SEED["slug"]))
    ).scalar_one()
    assert tenant.slug == "consultorio-piloto"
    assert tenant.politicas == POLITICAS_SEED


def test_manifest_pwa_declarado_con_nombre_e_iconos() -> None:
    raiz = _raiz()
    config = (raiz / "src" / "vite.config.ts").read_text(encoding="utf-8")
    assert "Turnos Odontología" in config
    assert "icon-192.png" in config
    assert "icon-512.png" in config
    assert (raiz / "src" / "public" / "icons" / "icon-192.png").is_file()
    assert (raiz / "src" / "public" / "icons" / "icon-512.png").is_file()


def test_shell_raiz_muestra_estado_conectado_y_error_en_rioplatense() -> None:
    raiz = _raiz()
    estado = (raiz / "src" / "src" / "features" / "api-status" / "ApiStatus.tsx").read_text(
        encoding="utf-8"
    )
    assert "Conectado" in estado
    assert "no pudimos conectar" in estado  # rioplatense, sin tecnicismos
    home = (raiz / "src" / "src" / "pages" / "HomePage.tsx").read_text(encoding="utf-8")
    assert "ApiStatus" in home


def test_ci_con_jobs_backend_y_frontend_en_paralelo() -> None:
    raiz = _raiz()
    ci = (raiz / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "backend:" in ci
    assert "frontend:" in ci
    assert "pytest" in ci  # backend: suite contra DB real (R11)
    assert "mypy" in ci
    assert "npm run build" in ci  # frontend: tsc + build van en el script build
    paquete = (raiz / "src" / "package.json").read_text(encoding="utf-8")
    assert "tsc --noEmit" in paquete
