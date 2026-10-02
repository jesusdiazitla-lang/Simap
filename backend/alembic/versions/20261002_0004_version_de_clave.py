"""Versión de la contraseña: cambiar o restablecer la clave echa a los demás aparatos.

Revision ID: 0004
Revises: 0003

POR QUÉ
-------
Un JWT es válido por sí mismo hasta que caduca. Sin esta columna, cambiar la contraseña no cerraba
ninguna sesión: un refresh token emitido con la clave vieja seguía renovando el acceso durante
siete días. Eso vacía de sentido justo los dos casos en que se cambia una clave por seguridad:

- el usuario sospecha que alguien la vio y la cambia él mismo;
- el operador de SIMAP la restablece porque el administrador de una planta perdió el control.

Cada cambio sube `version_clave`; el refresh token lleva la versión con la que se emitió; al
refrescar, si no coinciden, se rechaza. El token de acceso (30 minutos) no se comprueba contra la
base en cada petición —sería una consulta por request—, así que el intruso conserva como mucho lo
que le quede de esos 30 minutos.

PERMISOS
--------
No hacen falta `GRANT` nuevos: `app_user` y `operador_user` ya tienen UPDATE sobre `usuarios` a
nivel de tabla, y la política `operador_gestiona_administradores` limita al operador a las filas de
administradores, que son las únicas cuya clave puede restablecer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 0: coincide con el valor que se asume para los tokens emitidos antes de que
    # existiera la reclamación, así que desplegar esto no cierra ninguna sesión en curso.
    op.add_column(
        "usuarios",
        sa.Column("version_clave", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "version_clave")
