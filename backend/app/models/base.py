"""Base declarativa de SQLAlchemy y convenciones comunes a todas las entidades.

Los tipos se eligen pensando en portabilidad (ver `app.db.tenant`): `Uuid` y `Text` los traduce
SQLAlchemy al tipo nativo de cada motor, y los valores por defecto se generan en Python en lugar de
depender de funciones del servidor como `gen_random_uuid()`, que solo existe en PostgreSQL.

Las migraciones sí declaran además el `server_default` de PostgreSQL, para que un `INSERT` en SQL
crudo (scripts de mantenimiento, semillas de prueba) siga funcionando sin pasar por el ORM.
"""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Nombres deterministas para índices y restricciones. Sin esto, Alembic genera nombres distintos en
#: cada motor y un `downgrade` puede no encontrar lo que creó el `upgrade`.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


def _ahora() -> datetime:
    return datetime.now(UTC)


def _hoy() -> date:
    return datetime.now(UTC).date()


class IdUUID:
    """Clave primaria UUID, no entero autoincremental.

    04-fase1-fundamentos.md, sección 7.2: evita colisiones al migrar o fusionar datos entre
    entornos y no revela cuántos registros existen.
    """

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
