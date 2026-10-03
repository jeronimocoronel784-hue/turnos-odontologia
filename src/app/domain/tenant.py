"""Entidad raíz Tenant: cada consultorio es un tenant con slug único global."""

import uuid

from sqlalchemy import JSON, Boolean, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin
from app.infrastructure.db.base import Base


class Tenant(Base, AuditMixin):
    """Consultorio piloto o futuro cliente SaaS. Raíz del aislamiento (sin tenant_id propio)."""

    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    politicas: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_tenant_slug", "slug"),)
