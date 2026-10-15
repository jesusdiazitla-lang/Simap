"""Orden de trabajo, su historial y el contador por empresa (RF-11 a RF-16, RNF-06).

Es el dato con más valor del sistema: la lista de fallas cerradas con las horas en que ocurrieron es
lo que la fase 4 usa para ajustar Weibull. Por eso la base impone casi todo lo que importa
(`docs/contexto/06-fase3-ordenes-de-trabajo.md`, sección 7, revisión 0007):

- **Estados coherentes**: CHECK que impiden una orden Reparada sin reparador o Cerrada sin quien
  autorizó.
- **Inmutable al cerrar**: el trigger `ot_inmutable` rechaza cualquier cambio a una orden cerrada o
  cancelada salvo la corrección administrativa.
- **Una abierta por equipo y componente**, y una por alerta: índices únicos parciales.
- **Historial de solo adición**: `app_user` no puede modificar ni borrar `orden_eventos`.

El trigger y la vista `v_intervalos_entre_fallas` son de PostgreSQL y viven solo en la migración:
el modelo no los declara porque SQLAlchemy no los representa.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

ESTADOS = ("reportada", "en_taller", "reparada", "cerrada", "cancelada")
#: Estados desde los que la orden todavía se mueve. Cerrada y Cancelada son terminales.
ABIERTOS = ("reportada", "en_taller", "reparada")
#: Solo `reemplazo` renueva la vida del componente (decisión 4 de la fase).
TIPOS_INTERVENCION = ("reemplazo", "reparacion", "ajuste")
TIPOS_EVENTO = ("creada", "transicion", "nota", "correccion")

#: Condición SQL de «orden abierta», la de los índices parciales.
CONDICION_ABIERTA = "estado IN (" + ", ".join(f"'{e}'" for e in ABIERTOS) + ")"


def _lista(valores: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


def _mismo_tenant(columna: str, tabla: str, nombre: str) -> ForeignKeyConstraint:
    """Referencia compuesta (sección 7.4): hijo y padre siempre de la misma empresa.

    PostgreSQL comprueba las llaves foráneas ignorando RLS; con una llave simple, una orden de la
    empresa A podría apuntar a un equipo de la B y la base la aceptaría.
    """
    return ForeignKeyConstraint(
        ["empresa_id", columna], [f"{tabla}.empresa_id", f"{tabla}.id"], name=nombre
    )


class OrdenTrabajo(IdUUID, Base):
    """Una orden. Nunca se borra: lo que se reportó por error se cancela, con motivo.

    - `numero` es correlativo por empresa (OT-0001) y lo asigna `ordenes_contador` en la misma
      transacción que la inserta, así que no quedan huecos.
    - `horometro_en_falla` es el dial que vio quien reportó; `horas_acumuladas_en_falla` es el dial
      más el offset del equipo, y es lo que mide la fase 4 (sección 5.1).
    - `fecha_falla` es cuándo ocurrió según el dispositivo; `reportada_en`, cuándo llegó.
    """

    __tablename__ = "ordenes_trabajo"
    __table_args__ = (
        CheckConstraint(f"estado IN {_lista(ESTADOS)}", name="estado_valido"),
        CheckConstraint(
            f"tipo_intervencion IN {_lista(TIPOS_INTERVENCION)}", name="tipo_intervencion_valido"
        ),
        CheckConstraint("char_length(descripcion) BETWEEN 5 AND 1000", name="descripcion_valida"),
        CheckConstraint("temperatura BETWEEN -100 AND 999", name="temperatura_rango"),
        CheckConstraint("char_length(codigo_error) <= 50", name="codigo_error_acotado"),
        CheckConstraint("horometro_en_falla >= 0", name="horometro_no_negativo"),
        CheckConstraint("horas_acumuladas_en_falla >= 0", name="horas_no_negativas"),
        CheckConstraint("tiempo_fuera_servicio_min >= 0", name="tiempo_fuera_no_negativo"),
        CheckConstraint(
            "estado NOT IN ('reparada', 'cerrada') OR (reparado_por IS NOT NULL"
            " AND trabajo_realizado IS NOT NULL AND tipo_intervencion IS NOT NULL)",
            name="reparada_completa",
        ),
        CheckConstraint(
            "estado <> 'cerrada' OR (autorizado_por IS NOT NULL"
            " AND fecha_salida_taller IS NOT NULL AND tiempo_fuera_servicio_min IS NOT NULL)",
            name="cierre_completo",
        ),
        CheckConstraint(
            "estado <> 'cancelada' OR motivo_cancelacion IS NOT NULL", name="cancelada_con_motivo"
        ),
        CheckConstraint(
            "NOT requiere_revision OR motivo_revision IS NOT NULL", name="revision_con_motivo"
        ),
        UniqueConstraint("empresa_id", "numero", name="uq_ordenes_trabajo_numero"),
        UniqueConstraint("empresa_id", "cliente_id", name="uq_ordenes_trabajo_idempotente"),
        UniqueConstraint("empresa_id", "id", name="uq_ordenes_trabajo_empresa_id_id"),
        _mismo_tenant("activo_id", "activos", "fk_ordenes_trabajo_activo_mismo_tenant"),
        _mismo_tenant("componente_id", "componentes", "fk_ordenes_trabajo_componente_mismo_tenant"),
        _mismo_tenant("alerta_origen_id", "alertas", "fk_ordenes_trabajo_alerta_mismo_tenant"),
        _mismo_tenant(
            "lectura_id", "lecturas_horometro", "fk_ordenes_trabajo_lectura_mismo_tenant"
        ),
        _mismo_tenant("reportado_por", "usuarios", "fk_ordenes_trabajo_reportado_mismo_tenant"),
        _mismo_tenant("reparado_por", "usuarios", "fk_ordenes_trabajo_reparado_mismo_tenant"),
        _mismo_tenant("autorizado_por", "usuarios", "fk_ordenes_trabajo_autorizado_mismo_tenant"),
        Index(
            "ix_ordenes_trabajo_una_abierta_por_componente",
            "empresa_id",
            "activo_id",
            "componente_id",
            unique=True,
            postgresql_where=text(CONDICION_ABIERTA),
        ),
        Index(
            "ix_ordenes_trabajo_una_por_alerta",
            "empresa_id",
            "alerta_origen_id",
            unique=True,
            postgresql_where=text("alerta_origen_id IS NOT NULL AND estado <> 'cancelada'"),
        ),
        Index(
            "ix_ordenes_trabajo_activo_fecha", "empresa_id", "activo_id", text("fecha_falla DESC")
        ),
        Index(
            "ix_ordenes_trabajo_abiertas",
            "empresa_id",
            text("fecha_falla DESC"),
            postgresql_where=text(CONDICION_ABIERTA),
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    activo_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    alerta_origen_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    lectura_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reportado_por: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reparado_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    autorizado_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    horometro_en_falla: Mapped[int] = mapped_column(Integer, nullable=False)
    horas_acumuladas_en_falla: Mapped[int] = mapped_column(Integer, nullable=False)
    temperatura: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    codigo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="reportada")
    trabajo_realizado: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_intervencion: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motivo_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_falla: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reportada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )
    en_taller_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reparada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_salida_taller: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tiempo_fuera_servicio_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<OrdenTrabajo OT-{self.numero:04d} {self.estado}>"


class OrdenContador(Base):
    """Último número de orden emitido por empresa (sección 6.3).

    Un contador y no una secuencia nativa: la secuencia consume el número aunque la transacción se
    revierta y dejaría huecos; el contador se incrementa en la misma transacción que la orden y
    vuelve atrás con ella. El precio es que dos fallas de la misma empresa se numeran una tras otra.
    """

    __tablename__ = "ordenes_contador"

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), primary_key=True)
    ultimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OrdenEvento(IdUUID, Base):
    """Un paso del historial de una orden (RF-14, RNF-06). Solo se agrega, nunca se modifica.

    Guarda el rol **con el que actuó** la persona (`rol_al_momento`), no el que tiene hoy: si a un
    técnico lo ascienden a supervisor, el historial sigue diciendo que reparó como técnico.
    """

    __tablename__ = "orden_eventos"
    __table_args__ = (
        CheckConstraint(f"tipo IN {_lista(TIPOS_EVENTO)}", name="tipo_valido"),
        CheckConstraint("char_length(nota) <= 1000", name="nota_acotada"),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_orden_eventos_orden_mismo_tenant"),
        _mismo_tenant("usuario_id", "usuarios", "fk_orden_eventos_usuario_mismo_tenant"),
        Index("ix_orden_eventos_orden", "empresa_id", "orden_id", "creado_en"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    orden_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    rol_al_momento: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: JSON portable; en PostgreSQL, JSONB.
    datos: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),  # type: ignore[no-untyped-call]
        nullable=True,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )
