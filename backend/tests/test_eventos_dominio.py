"""Eventos de dominio: se publican después del commit y nunca si la transacción se revierte.

`orden_cerrada` es la frontera entre órdenes y predicción (06-fase3, 12.3). Si se publicara dentro
de la transacción, la fase 4 podría reajustar el modelo con una orden que al final no se cerró.
"""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import eventos_dominio
from tests.conftest import URL_APP, requiere_base

pytestmark = requiere_base


def _escenario(confirmar: bool) -> list[dict[str, Any]]:
    recibidos: list[dict[str, Any]] = []

    async def correr() -> None:
        motor = create_async_engine(URL_APP)
        baja = eventos_dominio.suscribir("prueba", recibidos.append)
        try:
            async with async_sessionmaker(motor)() as session:
                transaccion = await session.begin()
                eventos_dominio.emitir_al_confirmar(session, "prueba", orden_id="x")
                # Aún dentro de la transacción: nadie se ha enterado.
                assert recibidos == []
                if confirmar:
                    await transaccion.commit()
                else:
                    await transaccion.rollback()
        finally:
            baja()
            await motor.dispose()

    asyncio.run(correr())
    return recibidos


def test_se_publica_al_confirmar() -> None:
    assert _escenario(confirmar=True) == [{"orden_id": "x"}]


def test_se_descarta_si_la_transaccion_se_revierte() -> None:
    assert _escenario(confirmar=False) == []
