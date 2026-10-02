"""Entidad Empresa: el tenant. Cada fila es un cliente distinto de SIMAP."""

from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _hoy


class Empresa(IdUUID, Base):
    """Una empresa cliente.

    No lleva columna `empresa_id`: la fila **es** la empresa, así que su política RLS filtra por
    `id` en lugar de por `empresa_id` (ver `backend/db/rls_policies.sql`).
    """

    __tablename__ = "empresas"

    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_registro: Mapped[date] = mapped_column(nullable=False, default=_hoy)

    #: Una empresa que deja de pagar se suspende, no se borra: sus datos siguen ahí y su gente deja
    #: de poder entrar. El login lo comprueba antes de abrir sesión.
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    suspendida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Empresa {self.nombre!r}>"
