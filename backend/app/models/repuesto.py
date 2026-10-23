"""Inventario de repuestos: catálogo, libro de movimientos y líneas por orden (RF-23 a RF-26).

`docs/contexto/07-fase4-prediccion-e-inventario.md`, secciones 6.5 y 7.2 (revisión 0009). El stock
de cada repuesto vive en dos sitios que deben coincidir:

- `Repuesto.stock_actual`, para consultarlo rápido;
- `StockMovimiento`, el libro: **solo se agrega**. Cada fila guarda el delta, el stock resultante y
  el costo unitario del momento. `stock_actual` es la suma de sus deltas, y la conciliación lo
  comprueba.

La base refuerza el negocio: el signo del delta depende del tipo, un consumo siempre tiene orden y
costo, un ajuste siempre lleva nota, `stock_actual` nunca es negativo, y una orden no puede
descontar dos veces el mismo repuesto. Un trigger (solo en la migración) impide tocar las líneas de
una orden cerrada o cancelada.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

TIPOS_MOVIMIENTO = ("inicial", "ingreso", "consumo", "ajuste")


def _mismo_tenant(columna: str, tabla: str, nombre: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["empresa_id", columna], [f"{tabla}.empresa_id", f"{tabla}.id"], name=nombre
    )


class Repuesto(IdUUID, Base):
    """Un repuesto del almacén de una empresa. No se borra: se desactiva."""

    __tablename__ = "repuestos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "codigo", name="uq_repuestos_codigo"),
        UniqueConstraint("empresa_id", "id", name="uq_repuestos_empresa_id_id"),
        CheckConstraint("char_length(nombre) BETWEEN 2 AND 120", name="nombre_valido"),
        CheckConstraint("char_length(codigo) BETWEEN 1 AND 60", name="codigo_valido"),
        CheckConstraint("stock_actual >= 0", name="stock_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="minimo_no_negativo"),
        CheckConstraint("costo_unitario >= 0", name="costo_no_negativo"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    codigo: Mapped[str] = mapped_column(Text, nullable=False)
    #: Solo lo mueve el libro (ingreso, consumo, ajuste); ningún cuerpo de petición lo trae.
    stock_actual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock_minimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_unitario: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<Repuesto {self.codigo} stock={self.stock_actual}>"


class StockMovimiento(IdUUID, Base):
    """Un asiento del libro de movimientos. Nunca se modifica ni se borra."""

    __tablename__ = "stock_movimientos"
    __table_args__ = (
        CheckConstraint(
            "tipo IN (" + ", ".join(f"'{t}'" for t in TIPOS_MOVIMIENTO) + ")", name="tipo_valido"
        ),
        CheckConstraint("delta <> 0 AND delta BETWEEN -1000000 AND 1000000", name="delta_valido"),
        CheckConstraint("stock_resultante >= 0", name="resultante_no_negativo"),
        CheckConstraint("costo_unitario >= 0", name="costo_no_negativo"),
        CheckConstraint("char_length(nota) <= 500", name="nota_acotada"),
        CheckConstraint(
            "(tipo IN ('inicial', 'ingreso') AND delta > 0) OR (tipo = 'consumo' AND delta < 0)"
            " OR tipo = 'ajuste'",
            name="signo",
        ),
        CheckConstraint("(tipo = 'consumo') = (orden_id IS NOT NULL)", name="consumo_con_orden"),
        CheckConstraint(
            "tipo <> 'consumo' OR costo_unitario IS NOT NULL", name="consumo_con_costo"
        ),
        CheckConstraint("tipo <> 'ajuste' OR nota IS NOT NULL", name="ajuste_con_nota"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_stock_movimientos_repuesto_mismo_tenant"),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_stock_movimientos_orden_mismo_tenant"),
        _mismo_tenant("usuario_id", "usuarios", "fk_stock_movimientos_usuario_mismo_tenant"),
        Index(
            "ix_stock_movimientos_consumo_unico",
            "empresa_id",
            "orden_id",
            "repuesto_id",
            unique=True,
            postgresql_where=text("tipo = 'consumo'"),
        ),
        Index("ix_stock_movimientos_repuesto", "empresa_id", "repuesto_id", text("creado_en DESC")),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    repuesto_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_resultante: Mapped[int] = mapped_column(Integer, nullable=False)
    #: El costo **del momento**: la fase 5 calcula con él el gasto en repuestos.
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    orden_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )


class OrdenRepuesto(Base):
    """Un repuesto usado en una orden (RF-24). Su llave ya impone «una vez por orden»."""

    __tablename__ = "orden_repuesto"
    __table_args__ = (
        PrimaryKeyConstraint("empresa_id", "orden_id", "repuesto_id", name="pk_orden_repuesto"),
        CheckConstraint("cantidad BETWEEN 1 AND 10000", name="cantidad_valida"),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_orden_repuesto_orden_mismo_tenant"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_orden_repuesto_repuesto_mismo_tenant"),
        _mismo_tenant("registrado_por", "usuarios", "fk_orden_repuesto_usuario_mismo_tenant"),
        Index("ix_orden_repuesto_repuesto", "empresa_id", "repuesto_id"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    orden_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    repuesto_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    registrado_por: Mapped[UUID] = mapped_column(Uuid, nullable=False)
