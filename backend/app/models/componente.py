"""Catálogo de componentes de una empresa (tren motriz, sistema hidráulico, bomba de aceite…).

Sobre cada componente se ajusta en la fase 4 una distribución de Weibull, y en la fase 3 cada
orden de trabajo dice qué componente falló. Por eso **no se borran nunca**: se desactivan. Borrar
uno dejaría órdenes apuntando a nada y un modelo de riesgo sin historia.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora

#: Catálogo con el que nace toda empresa (05-fase2-activos-y-campo.md, sección 2). Genérico a
#: propósito: cubre lo que falla en la mayoría de equipos industriales con horómetro, y el
#: administrador lo ajusta a su planta. Cambiarlo aquí solo afecta a las empresas nuevas.
#: Nombre del componente comodín. La fase 4 lo excluye del ajuste por su nombre.
COMPONENTE_POR_IDENTIFICAR = "Otro (por identificar)"

PLANTILLA_INICIAL: tuple[tuple[str, str], ...] = (
    ("Motor", "Motor eléctrico o de combustión que acciona el equipo."),
    ("Tren motriz", "Transmisión, caja de cambios, ejes y acoplamientos."),
    ("Sistema hidráulico", "Bombas, cilindros, mangueras y válvulas hidráulicas."),
    ("Bomba de aceite", "Bomba del circuito de lubricación."),
    ("Rodamientos", "Rodamientos y cojinetes."),
    ("Correas y cadenas", "Elementos de transmisión flexibles."),
    ("Sistema de refrigeración", "Radiador, ventiladores, intercambiadores y refrigerante."),
    ("Sistema eléctrico y de control", "Cableado, tableros, sensores y autómatas."),
    # Para reportar una falla sin saber aún qué la causó (F3, 6.2). Se corrige en la orden mientras
    # esté abierta, y la fase 4 no ajusta modelo con él.
    (COMPONENTE_POR_IDENTIFICAR, "Falla cuyo componente aún no se conoce; se corrige en la orden."),
)


class Componente(IdUUID, Base):
    __tablename__ = "componentes"
    __table_args__ = (
        # Nombre único dentro de la empresa, no en todo el sistema: dos plantas pueden tener cada
        # una su «Motor». Sirve además de índice por empresa_id, que es su primera columna.
        UniqueConstraint("empresa_id", "nombre", name="uq_componentes_empresa_id_nombre"),
        # Clave candidata para las referencias compuestas de la fase 3 (ordenes_trabajo).
        UniqueConstraint("empresa_id", "id", name="uq_componentes_empresa_id_id"),
        CheckConstraint("vida_nominal_horas BETWEEN 10 AND 1000000", name="vida_nominal_rango"),
    )

    empresa_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("empresas.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Vida nominal declarada por el administrador (F4, decisión 6): el centro del conocimiento
    #: previo del modelo. Sin ella y con menos de dos fallas, el componente queda «sin modelo».
    vida_nominal_horas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<Componente {self.nombre!r}>"
