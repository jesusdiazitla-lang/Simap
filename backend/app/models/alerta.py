"""Alerta de campo: un síntoma que alguien notó en un equipo que sigue funcionando (RF-09)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

#: Se guardan sin tildes y la interfaz los traduce (sección 4.1).
SINTOMAS = ("ruido", "vibracion", "calor", "olor", "fuga", "otro")
#: `convertida_en_orden`: la alerta originó una orden de trabajo (RF-16). Si la orden se cancela,
#: vuelve a `revisada`.
ESTADOS = ("pendiente", "revisada", "descartada", "convertida_en_orden")
MAX_NOTA = 500


class Alerta(IdUUID, Base):
    """Una alerta. **Nunca se borra**: la revisión 0005 le retira a `app_user` el permiso de borrar.

    `revisada_por` y `revisada_en` no están en el documento de la fase; se añaden porque decidir que
    una alerta no importa es una decisión con consecuencias (en la fase 4 las alertas pendientes
    suben el riesgo del equipo), y tiene que constar quién la tomó.
    """

    __tablename__ = "alertas"
    __table_args__ = (
        CheckConstraint(
            "sintoma IN (" + ", ".join(f"'{s}'" for s in SINTOMAS) + ")", name="sintoma_valido"
        ),
        CheckConstraint(
            "estado IN (" + ", ".join(f"'{e}'" for e in ESTADOS) + ")", name="estado_valido"
        ),
        CheckConstraint(f"char_length(nota) <= {MAX_NOTA}", name="nota_acotada"),
        UniqueConstraint("empresa_id", "cliente_id", name="uq_alertas_idempotente"),
        # Clave candidata de la referencia compuesta desde las órdenes de trabajo (F3, 7.1).
        UniqueConstraint("empresa_id", "id", name="uq_alertas_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activos.empresa_id", "activos.id"],
            name="fk_alertas_activo_mismo_tenant",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "reportado_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_alertas_autor_mismo_tenant",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "revisada_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_alertas_revisor_mismo_tenant",
        ),
        Index("ix_alertas_activo_fecha", "empresa_id", "activo_id", "fecha"),
        # Índice parcial: la bandeja de pendientes del supervisor sigue siendo barata aunque la
        # tabla acumule años de alertas ya revisadas.
        Index(
            "ix_alertas_pendientes",
            "empresa_id",
            "fecha",
            postgresql_where=text("estado = 'pendiente'"),
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    activo_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reportado_por: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sintoma: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="pendiente")
    cliente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    capturado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora)
    revisada_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Alerta {self.sintoma} {self.estado}>"
