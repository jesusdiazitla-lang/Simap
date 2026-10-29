"""Predicción de fallas: configuración, componentes por equipo, modelos, riesgos y alertas.

`docs/contexto/07-fase4-prediccion-e-inventario.md`, secciones 5 a 7 (revisión 0009).

- `ActivoComponente`: qué componentes tiene cada equipo y a qué horas del equipo se instaló la
  unidad actual. Sin esa edad no hay riesgo (decisión 7): inventarla produciría alarmas falsas.
- `ModeloComponente`: la Weibull vigente de cada componente (β, η), con cuántas fallas la respaldan.
  `ModeloHistorial` guarda una fila cada vez que cambia ese número: la curva de aprendizaje. Solo se
  agrega.
- `ReajustePendiente`: la marca durable «este componente tiene datos nuevos» (decisión 13). La
  escribe el cierre de una orden en su misma transacción; `generacion` impide perder un cierre que
  llegue mientras se ajusta.
- `Riesgo`: resultado derivado, se puede borrar y recalcular. `AlertaSistema`: tabla aparte de las
  alertas de campo, para que una alerta del sistema nunca alimente el multiplicador que la originó.

Las vistas `v_vidas` y `v_riesgo_activo` se declaran en un `MetaData` propio (`VISTAS`): son de solo
lectura y no forman parte de lo que Alembic compara ni crea.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

FUENTES = ("previo", "mixto", "empresa")
CONFIANZAS = ("baja", "media", "alta")
ESTADOS_CALCULO = ("ok", "sin_edad", "sin_modelo")
ESTADOS_ALERTA = ("activa", "reconocida", "atendida", "resuelta", "descartada")
#: Estados en que una alerta de riesgo sigue vigente: impiden crear otra para el mismo par.
VIGENTES_RIESGO = ("activa", "reconocida", "atendida")
VIGENTES_REORDEN = ("activa", "reconocida")


def _lista(valores: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


def _mismo_tenant(columna: str, tabla: str, nombre: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["empresa_id", columna], [f"{tabla}.empresa_id", f"{tabla}.id"], name=nombre
    )


class ConfiguracionEmpresa(Base):
    """Parámetros de la predicción de una empresa (decisión 5). Los ajusta el administrador."""

    __tablename__ = "configuracion_empresa"
    __table_args__ = (
        CheckConstraint("umbral_riesgo BETWEEN 0.05 AND 0.95", name="umbral_rango"),
        CheckConstraint("horizonte_horas BETWEEN 1 AND 2000", name="horizonte_rango"),
        CheckConstraint("alertas_minimas BETWEEN 1 AND 20", name="alertas_minimas_rango"),
        CheckConstraint("ventana_alertas_dias BETWEEN 1 AND 90", name="ventana_rango"),
        CheckConstraint("multiplicador_alertas BETWEEN 1.00 AND 2.00", name="multiplicador_rango"),
        CheckConstraint("descarte_silencio_dias BETWEEN 1 AND 90", name="silencio_rango"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), primary_key=True)
    umbral_riesgo: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.250")
    )
    horizonte_horas: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    alertas_minimas: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    ventana_alertas_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    multiplicador_alertas: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.30")
    )
    descarte_silencio_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=7)


class ActivoComponente(Base):
    """Un componente de un equipo, con las horas del equipo en que se instaló la unidad actual."""

    __tablename__ = "activo_componentes"
    __table_args__ = (
        PrimaryKeyConstraint(
            "empresa_id", "activo_id", "componente_id", name="pk_activo_componentes"
        ),
        CheckConstraint("horas_instalacion_inicial >= 0", name="horas_instalacion_validas"),
        _mismo_tenant("activo_id", "activos", "fk_activo_componentes_activo_mismo_tenant"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_activo_componentes_componente_mismo_tenant"
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    activo_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    #: Horas acumuladas (dial + offset) del equipo al instalar la unidad actual. `None`: no se sabe.
    horas_instalacion_inicial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )


class AlertaSistema(IdUUID, Base):
    """Alerta generada por el sistema: riesgo sobre el umbral o repuesto bajo el mínimo.

    Guarda el umbral y la confianza **del día**: dentro de un año debe poder explicarse con las
    cifras con que se creó.
    """

    __tablename__ = "alertas_sistema"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_alertas_sistema_empresa_id_id"),
        CheckConstraint("tipo IN ('riesgo', 'reorden')", name="tipo_valido"),
        CheckConstraint(f"confianza IN {_lista(CONFIANZAS)}", name="confianza_valida"),
        CheckConstraint(f"fuente IN {_lista(FUENTES)}", name="fuente_valida"),
        CheckConstraint(f"estado IN {_lista(ESTADOS_ALERTA)}", name="estado_valido"),
        CheckConstraint("char_length(nota) <= 500", name="nota_acotada"),
        CheckConstraint(
            "(tipo = 'riesgo' AND activo_id IS NOT NULL AND componente_id IS NOT NULL"
            " AND repuesto_id IS NULL AND riesgo IS NOT NULL AND umbral IS NOT NULL)"
            " OR (tipo = 'reorden' AND repuesto_id IS NOT NULL AND activo_id IS NULL"
            " AND componente_id IS NULL AND stock_al_alertar IS NOT NULL)",
            name="forma_por_tipo",
        ),
        CheckConstraint("estado <> 'descartada' OR nota IS NOT NULL", name="descartada_con_nota"),
        _mismo_tenant("activo_id", "activos", "fk_alertas_sistema_activo_mismo_tenant"),
        _mismo_tenant("componente_id", "componentes", "fk_alertas_sistema_componente_mismo_tenant"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_alertas_sistema_repuesto_mismo_tenant"),
        _mismo_tenant("gestionada_por", "usuarios", "fk_alertas_sistema_gestor_mismo_tenant"),
        Index(
            "ix_alertas_sistema_riesgo_vigente",
            "empresa_id",
            "activo_id",
            "componente_id",
            unique=True,
            postgresql_where=text(f"tipo = 'riesgo' AND estado IN {_lista(VIGENTES_RIESGO)}"),
        ),
        Index(
            "ix_alertas_sistema_reorden_vigente",
            "empresa_id",
            "repuesto_id",
            unique=True,
            postgresql_where=text(f"tipo = 'reorden' AND estado IN {_lista(VIGENTES_REORDEN)}"),
        ),
        Index(
            "ix_alertas_sistema_bandeja",
            "empresa_id",
            text("creada_en DESC"),
            postgresql_where=text(f"estado IN {_lista(VIGENTES_RIESGO)}"),
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    activo_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    componente_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    repuesto_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    riesgo: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    umbral: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    confianza: Mapped[str | None] = mapped_column(Text, nullable=True)
    fuente: Mapped[str | None] = mapped_column(Text, nullable=True)
    stock_al_alertar: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_minimo_al_alertar: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False, default="activa")
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )
    gestionada_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    gestionada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModeloComponente(Base):
    """La Weibull vigente de un componente en una empresa."""

    __tablename__ = "modelos_componente"
    __table_args__ = (
        PrimaryKeyConstraint("empresa_id", "componente_id", name="pk_modelos_componente"),
        CheckConstraint("beta BETWEEN 0.3 AND 10", name="beta_rango"),
        CheckConstraint("eta > 0", name="eta_positiva"),
        CheckConstraint("n_eventos >= 0", name="eventos_no_negativos"),
        CheckConstraint("n_vidas >= 0", name="vidas_no_negativas"),
        CheckConstraint("exposicion_horas >= 0", name="exposicion_no_negativa"),
        CheckConstraint(f"fuente IN {_lista(FUENTES)}", name="fuente_valida"),
        CheckConstraint(f"confianza IN {_lista(CONFIANZAS)}", name="confianza_valida"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_modelos_componente_componente_mismo_tenant"
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    beta: Mapped[float] = mapped_column(Double, nullable=False)
    eta: Mapped[float] = mapped_column(Double, nullable=False)
    n_eventos: Mapped[int] = mapped_column(Integer, nullable=False)
    n_vidas: Mapped[int] = mapped_column(Integer, nullable=False)
    exposicion_horas: Mapped[float] = mapped_column(Double, nullable=False)
    fuente: Mapped[str] = mapped_column(Text, nullable=False)
    confianza: Mapped[str] = mapped_column(Text, nullable=False)
    convergio: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ajustado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )


class ModeloHistorial(IdUUID, Base):
    """Una versión del modelo, guardada cuando cambia el número de fallas. Solo se agrega."""

    __tablename__ = "modelos_historial"
    __table_args__ = (
        _mismo_tenant(
            "componente_id", "componentes", "fk_modelos_historial_componente_mismo_tenant"
        ),
        Index("ix_modelos_historial_componente", "empresa_id", "componente_id", "ajustado_en"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    beta: Mapped[float] = mapped_column(Double, nullable=False)
    eta: Mapped[float] = mapped_column(Double, nullable=False)
    n_eventos: Mapped[int] = mapped_column(Integer, nullable=False)
    fuente: Mapped[str] = mapped_column(Text, nullable=False)
    confianza: Mapped[str] = mapped_column(Text, nullable=False)
    ajustado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )


class ReajustePendiente(Base):
    """Marca durable de reajuste. Quien la procesa la borra solo si `generacion` no cambió."""

    __tablename__ = "reajustes_pendientes"
    __table_args__ = (
        PrimaryKeyConstraint("empresa_id", "componente_id", name="pk_reajustes_pendientes"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_reajustes_pendientes_componente_mismo_tenant"
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    generacion: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class Riesgo(Base):
    """Riesgo vigente de un componente de un equipo. Derivado: se reescribe en cada cálculo.

    `n_eventos` (las fallas que respaldan el modelo) no está en el documento: se guarda para que la
    pantalla diga «12 fallas registradas» sin otra consulta (10.2).
    """

    __tablename__ = "riesgos"
    __table_args__ = (
        PrimaryKeyConstraint("empresa_id", "activo_id", "componente_id", name="pk_riesgos"),
        CheckConstraint(
            f"estado_calculo IN {_lista(ESTADOS_CALCULO)}", name="estado_calculo_valido"
        ),
        CheckConstraint(
            "estado_calculo <> 'ok' OR (riesgo IS NOT NULL AND riesgo_base IS NOT NULL"
            " AND edad_horas IS NOT NULL AND beta IS NOT NULL AND eta IS NOT NULL"
            " AND horizonte_horas IS NOT NULL)",
            name="ok_completo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "activo_id", "componente_id"],
            [
                "activo_componentes.empresa_id",
                "activo_componentes.activo_id",
                "activo_componentes.componente_id",
            ],
            name="fk_riesgos_par_registrado",
            ondelete="CASCADE",
        ),
        Index(
            "ix_riesgos_altos",
            "empresa_id",
            text("riesgo DESC"),
            postgresql_where=text("estado_calculo = 'ok'"),
        ),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    activo_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    componente_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    estado_calculo: Mapped[str] = mapped_column(Text, nullable=False)
    edad_horas: Mapped[float | None] = mapped_column(Double, nullable=True)
    horizonte_horas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    beta: Mapped[float | None] = mapped_column(Double, nullable=True)
    eta: Mapped[float | None] = mapped_column(Double, nullable=True)
    riesgo_base: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    multiplicador: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    riesgo: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    n_eventos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuente: Mapped[str | None] = mapped_column(Text, nullable=True)
    confianza: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )


#: Las vistas, fuera de `Base.metadata`: Alembic no debe compararlas ni crearlas.
VISTAS = MetaData()

#: Una fila por vida de un componente en un equipo (7.7): los estadísticos suficientes del ajuste.
v_vidas = Table(
    "v_vidas",
    VISTAS,
    Column("empresa_id", Uuid),
    Column("activo_id", Uuid),
    Column("componente_id", Uuid),
    Column("vida", Integer),
    Column("abierta", Boolean),
    Column("inicio", Double),
    Column("n_eventos", Integer),
    Column("suma_ln_edades", Double),
    Column("exposicion", Double),
)

#: Una fila por parada de equipo (F5, 6.2): una falla desde que ocurre; una intervención predictiva
#: desde que el equipo entra al taller. `fin` nulo = sigue parado. Las canceladas no cuentan.
v_paradas = Table(
    "v_paradas",
    VISTAS,
    Column("empresa_id", Uuid),
    Column("orden_id", Uuid),
    Column("numero", Integer),
    Column("activo_id", Uuid),
    Column("componente_id", Uuid),
    Column("planificada", Boolean),
    Column("inicio", DateTime(timezone=True)),
    Column("fin", DateTime(timezone=True)),
    Column("estado", Text),
    Column("requiere_revision", Boolean),
)

#: Riesgo del equipo = el de su componente más riesgoso (CU-04).
v_riesgo_activo = Table(
    "v_riesgo_activo",
    VISTAS,
    Column("empresa_id", Uuid),
    Column("activo_id", Uuid),
    Column("componente_critico", Uuid),
    Column("riesgo", Numeric(6, 5)),
    Column("confianza", Text),
    Column("fuente", Text),
    Column("calculado_en", DateTime(timezone=True)),
)
