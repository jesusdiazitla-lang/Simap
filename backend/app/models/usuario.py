"""Entidad Usuario: una persona dentro de una empresa, con un rol."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import Rol
from app.models.base import Base, IdUUID, _ahora

#: Valores admitidos en la columna `rol`. Se derivan del enum para que no puedan divergir: añadir un
#: rol en `app.core.security.Rol` lo añade también aquí y a la restricción de la base.
ROLES_VALIDOS = tuple(r.value for r in Rol)


class Usuario(IdUUID, Base):
    """Usuario de una empresa.

    `password_hash` guarda un hash Argon2id (`app.core.security.hash_password`), nunca la
    contraseña. `correo` es único en todo el sistema, no solo dentro de la empresa: es la
    credencial de login y el usuario todavía no ha declarado su empresa cuando la introduce.
    """

    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "rol IN (" + ", ".join(f"'{r}'" for r in ROLES_VALIDOS) + ")",
            name="rol_valido",
        ),
        # 04-fase1-fundamentos.md, seccion 7.2: indice en empresa_id desde el primer commit. Es
        # gratis ahora y muy costoso anadirlo con la tabla ya en produccion.
        Index("ix_usuarios_empresa_id", "empresa_id"),
    )

    empresa_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("empresas.id"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    correo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rol: Mapped[str] = mapped_column(Text, nullable=False)
    #: Sube cada vez que cambia la contraseña. Los refresh tokens llevan la versión con la que se
    #: emitieron y dejan de servir cuando no coincide: así cambiar la clave echa a los demás
    #: aparatos. Ver `app.core.security.CLAIM_VERSION_CLAVE` y la revisión 0004.
    version_clave: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_ahora
    )

    def __repr__(self) -> str:
        return f"<Usuario {self.correo!r} rol={self.rol}>"
