"""Plano de control: quién opera SIMAP, y qué ha hecho.

Un operador **no pertenece a ninguna empresa**, y por eso no vive en `usuarios` ni tiene
`empresa_id`. Es la diferencia entre el plano de control (dar de alta clientes) y el plano de datos
(trabajar dentro de un cliente), y mantenerlos en tablas distintas es lo que impide que una consulta
descuidada mezcle los dos.

Quien atiende estas tablas es el rol de base de datos `operador_user`, que tiene permisos concedidos
tabla por tabla y **ninguno sobre las tablas de negocio**. Ver la revisión 0003 de Alembic.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdUUID, _ahora


class Operador(IdUUID, Base):
    """Una persona que opera SIMAP: da de alta empresas clientes y sus administradores."""

    __tablename__ = "operadores"

    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    #: Único en todo el sistema. Puede coincidir con el de un usuario de empresa sin ambigüedad:
    #: son tablas distintas y se entra por pantallas distintas.
    correo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    #: Un operador que se va se desactiva, no se borra: su rastro en la bitácora tiene que seguir
    #: apuntando a alguien con nombre.
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<Operador {self.correo!r}>"


class AccionOperador:
    """Valores de `operador_bitacora.accion`.

    Cadenas y no un enum de base de datos: añadir una acción en una fase posterior no debe exigir
    una migración que altere un tipo, y la bitácora tiene que poder guardar acciones que este
    código todavía no conoce sin rechazarlas.
    """

    ALTA_EMPRESA = "alta_empresa"
    SUSPENSION = "suspension"
    REACTIVACION = "reactivacion"
    RESTABLECER_CLAVE = "restablecer_clave"
    EDICION_EMPRESA = "edicion_empresa"
    #: El operador cambió su propia contraseña. Sin empresa: no es una acción sobre un cliente.
    CAMBIO_CLAVE_PROPIA = "cambio_clave_propia"


class BitacoraOperador(IdUUID, Base):
    """Qué hizo cada operador, cuándo y sobre qué empresa.

    Crear un cliente, suspenderlo o restablecer la contraseña de su administrador son acciones
    sensibles por definición: quien las hace tiene poder sobre el acceso de otros, y eso no puede
    ocurrir sin dejar rastro.
    """

    __tablename__ = "operador_bitacora"
    __table_args__ = (
        Index("ix_bitacora_creado_en", "creado_en"),
        Index("ix_bitacora_empresa_id", "empresa_id"),
    )

    #: RESTRICT, no CASCADE: no se puede borrar un operador que dejó rastro. Es lo que impide que
    #: alguien borre su propia cuenta para hacer desaparecer lo que hizo.
    operador_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("operadores.id", ondelete="RESTRICT"), nullable=False
    )
    accion: Mapped[str] = mapped_column(Text, nullable=False)
    #: Sin clave foránea a propósito: si algún día se borra una empresa, el asiento tiene que
    #: sobrevivir para decir que existió.
    empresa_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<BitacoraOperador {self.accion!r}>"
