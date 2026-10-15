"""Lectura de horómetro: las horas de operación que anota el personal en la ronda (RF-08).

Es la materia prima del modelo predictivo: las horas entre fallas salen de aquí. Por eso la tabla es
de **solo adición**: la revisión 0005 le retira a `app_user` el permiso de borrar y de modificar,
salvo las dos columnas de revisión. Ni un error en el código puede reescribir una lectura.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

#: Cómo se resolvió una lectura marcada (revisión 0006). `None` mientras está pendiente.
RESOLUCIONES = ("confirmada", "descartada", "reinicio")


class LecturaHorometro(IdUUID, Base):
    """Una lectura.

    - `fecha` es cuándo la **recibió** el servidor; `capturado_en`, cuándo la tomó el operario, que
      puede ser horas antes si estaba sin cobertura. El modelo usa `capturado_en`.
    - `cliente_id` lo genera el teléfono antes del primer intento y lo repite en cada reintento: es
      la clave de idempotencia. Único dentro de la empresa, no en todo el sistema, y no es la llave
      primaria a propósito: un choque de llave primaria delataría que ese UUID existe en otra
      empresa.
    - `requiere_revision`: la lectura no cuadra con las demás (sección 5.1). Se guarda —el dato del
      operario nunca se pierde— pero no mueve el horómetro vigente del equipo.
    """

    __tablename__ = "lecturas_horometro"
    __table_args__ = (
        CheckConstraint("valor_horometro >= 0", name="valor_valido"),
        CheckConstraint(
            "resolucion IN (" + ", ".join(f"'{r}'" for r in RESOLUCIONES) + ")",
            name="resolucion_valida",
        ),
        CheckConstraint(
            "resolucion IS NULL OR requiere_revision", name="resolucion_solo_si_marcada"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "revisada_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_lecturas_horometro_revisor_mismo_tenant",
        ),
        Index(
            "ix_lecturas_horometro_por_revisar",
            "empresa_id",
            "capturado_en",
            postgresql_where=text("requiere_revision AND resolucion IS NULL"),
        ),
        UniqueConstraint("empresa_id", "cliente_id", name="uq_lecturas_horometro_idempotente"),
        # Clave candidata de la referencia compuesta desde las órdenes de trabajo (F3, 7.1).
        UniqueConstraint("empresa_id", "id", name="uq_lecturas_horometro_empresa_id_id"),
        # Referencias compuestas (sección 4.2): la base garantiza que equipo y autor son de la misma
        # empresa que la lectura. PostgreSQL comprueba las llaves foráneas ignorando RLS, así que
        # con una llave simple nada impediría colgar una lectura propia de un equipo ajeno.
        ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activos.empresa_id", "activos.id"],
            name="fk_lecturas_horometro_activo_mismo_tenant",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "registrado_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_lecturas_horometro_autor_mismo_tenant",
        ),
        # La consulta más frecuente del sistema: la última lectura de un equipo y su historial.
        Index("ix_lecturas_horometro_activo_captura", "empresa_id", "activo_id", "capturado_en"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    activo_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    registrado_por: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    valor_horometro: Mapped[int] = mapped_column(Integer, nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    capturado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motivo_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `confirmada`, `descartada` o `reinicio`; `None` mientras nadie la ha revisado.
    resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisada_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: La registró el administrador al cambiar o poner a cero el horómetro (F3, 5.1): empieza una
    #: serie nueva y no se compara con las anteriores.
    es_reinicio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<LecturaHorometro {self.valor_horometro} @ {self.capturado_en}>"
