"""Cobertura de obra social por prestación, arancel, copago y período de vigencia."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class CoberturaOS(Base, TenantMixin, AuditMixin):
    """Convenio con obra social para una prestación del consultorio."""

    __tablename__ = "cobertura_os"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    obra_social: Mapped[str] = mapped_column(String(160), nullable=False)
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prestacion.id", ondelete="RESTRICT"), nullable=False
    )
    arancel: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    copago: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("arancel >= 0 AND copago >= 0", name="ck_cobertura_montos_no_negativos"),
        CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde",
            name="ck_cobertura_vigencia_ordenada",
        ),
        Index("ix_cobertura_os_tenant_os", "tenant_id", "obra_social"),
        Index("ix_cobertura_os_tenant_prestacion", "tenant_id", "prestacion_id"),
    )
