"""Detecta divergencia entre los modelos y el esquema que crean las migraciones.

Es el fallo silencioso más fácil de cometer con Alembic: alguien añade una columna al modelo, olvida
la migración, y todo funciona en su máquina (donde la tabla ya existía) hasta que alguien despliega
en limpio. Este test compara `Base.metadata` con la base real y falla si no coinciden.

Exige una base migrada (`docker compose up -d db` y `alembic upgrade head`).
"""

import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.models import Base
from tests.conftest import URL_DUENO, requiere_base

T = TypeVar("T")


def _correr(corutina: Awaitable[T]) -> T:
    return asyncio.run(corutina)  # type: ignore[arg-type]


pytestmark = requiere_base


def _diferencias(connection: Connection) -> list[Any]:
    contexto = MigrationContext.configure(
        connection,
        opts={"compare_type": True, "compare_server_default": False},
    )
    # Ignora tablas de fases posteriores que aun no existen y la propia tabla de Alembic.
    conocidas = set(Base.metadata.tables)

    def incluir(nombre: str | None, tipo: str, *_: object) -> bool:
        if tipo == "table":
            return nombre in conocidas
        return True

    contexto.opts["include_name"] = incluir  # type: ignore[index]
    return list(compare_metadata(contexto, Base.metadata))


def test_los_modelos_coinciden_con_el_esquema_migrado() -> None:
    async def comparar() -> list[Any]:
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.connect() as conn:
                return await conn.run_sync(_diferencias)
        finally:
            await motor.dispose()

    diffs = _correr(comparar())
    assert diffs == [], (
        "Los modelos y la base no coinciden. Falta una migracion: generarla con\n"
        "  alembic revision --autogenerate -m 'descripcion'\n"
        f"Diferencias detectadas: {diffs}"
    )


def test_la_base_esta_en_la_ultima_revision() -> None:
    """La base tiene aplicada la ultima revision que existe en el repositorio.

    La revision esperada se lee de `alembic/versions`, no se escribe a mano: con un numero fijo,
    cada migracion nueva obligaba a editar esta prueba, y una prueba que hay que retocar en cada
    cambio acaba retocandose sin pensar.
    """

    async def revision() -> str | None:
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.connect() as conn:
                fila = await conn.execute(text("SELECT version_num FROM alembic_version"))
                return str(fila.scalar_one())
        finally:
            await motor.dispose()

    guiones = ScriptDirectory.from_config(Config("alembic.ini"))
    cabeza = guiones.get_current_head()
    assert _correr(revision()) == cabeza
