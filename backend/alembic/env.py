"""Entorno de Alembic para SIMAP.

La URL sale de `Settings.database_url_migraciones`, nunca de `alembic.ini`: así no hay credenciales
en un archivo versionado y las migraciones corren siempre con `simap_owner`.

POR QUÉ IMPORTA EL ROL: las tablas quedan en manos de quien las crea. Si las creara el superusuario,
`FORCE ROW LEVEL SECURITY` no le aplicaría y el aislamiento entre empresas sería decorativo
(ver `docs/contexto/04-fase1-fundamentos.md`, sección 6.3). Creándolas `simap_owner`, que no es
superusuario, nacen ya con el dueño correcto.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url_migraciones)


def _configurar(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detecta cambios de tipo y de server_default al autogenerar, no solo altas y bajas.
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    """Genera el SQL sin conectar, para revisarlo o aplicarlo a mano."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _ejecutar(connection: Connection) -> None:
    _configurar(connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_ejecutar)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
