"""Base declarativa SQLAlchemy 2.0. Importa entidades para que Alembic las vea."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base de todos los modelos ORM del proyecto."""
