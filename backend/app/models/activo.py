"""Activo: un equipo industrial de una empresa, identificado por su código QR (RF-04, RF-05)."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

CRITICIDADES = ("alta", "media", "baja")
ESTADOS = ("activo", "baja")


class Activo(IdUUID, Base):
    """Un equipo.

    `qr_code` es único en **todo** el sistema, no por empresa: el QR impreso solo lleva el código, y
    al escanearlo hay que poder resolverlo sin saber de qué empresa es. Quien lo resuelve sigue
    pasando por RLS, así que un código de otra empresa da 404 igual que uno inexistente.

    `horometro_actual` es el valor vigente, desnormalizado a propósito (sección 9.2): los listados
    lo leen sin JOIN contra las lecturas. Solo lo mueven las lecturas no marcadas para revisión.

    Los equipos no se borran, se dan de baja: su historial de lecturas y fallas es justo lo que
    alimenta el modelo de riesgo, y la etiqueta vieja tiene que seguir explicando qué pasó.
    """

    __tablename__ = "activos"
    __table_args__ = (
        CheckConstraint(
            "criticidad IN (" + ", ".join(f"'{c}'" for c in CRITICIDADES) + ")",
            name="criticidad_valida",
        ),
        CheckConstraint(
            "estado IN (" + ", ".join(f"'{e}'" for e in ESTADOS) + ")", name="estado_valido"
        ),
        CheckConstraint("horometro_actual >= 0", name="horometro_no_negativo"),
        # Clave candidata de las referencias compuestas (sección 4.2): las lecturas y alertas
        # apuntan a (empresa_id, id) y no solo a id, para que la base impida que una fila de la
        # empresa A cuelgue de un equipo de la empresa B.
        UniqueConstraint("empresa_id", "id", name="uq_activos_empresa_id_id"),
        Index("ix_activos_empresa_id_estado", "empresa_id", "estado"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ubicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    criticidad: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    horometro_actual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    horometro_actualizado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_ultima_falla: Mapped[date | None] = mapped_column(Date, nullable=True)
    marca: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo: Mapped[str | None] = mapped_column(Text, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_instalacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="activo")
    dado_de_baja_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<Activo {self.nombre!r} {self.qr_code}>"
