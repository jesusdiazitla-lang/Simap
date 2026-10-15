"""Concurrencia real sobre las órdenes: varias sesiones a la vez contra PostgreSQL (06-fase3, 13.2).

Con un solo cliente HTTP las peticiones van en fila y una carrera nunca ocurre. Aquí cada «persona»
tiene su propia conexión y su propia transacción, y `asyncio.gather` las lanza juntas: es la base
la que decide quién gana, con el bloqueo de fila del UPDATE condicionado, el índice único parcial o
la fila del contador. Las pruebas comprueban que el resultado es siempre uno que gana y los demás
reciben un 409 (o un «duplicado»), nunca un estado corrupto.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.orden_trabajo import OrdenTrabajo
from app.services import ordenes, ordenes_estados
from tests.base_ordenes import Empresa, correr, fijar, fila_orden, insertar_ordenes, sembrar
from tests.conftest import URL_APP, URL_DUENO, requiere_base

pytestmark = requiere_base

T = TypeVar("T")


def _actor(e: Empresa) -> ordenes.Actor:
    return ordenes.Actor(empresa_id=e.empresa_id, usuario_id=e.usuario_id, rol="supervisor")


async def _a_la_vez(
    e: Empresa, tareas: list[Callable[[AsyncSession], Awaitable[T]]]
) -> list[T | Exception]:
    """Cada tarea en su sesión y su transacción, todas a la vez. Como en `get_db`: si la tarea
    lanza, su transacción se revierte entera."""
    motor = create_async_engine(URL_APP, pool_size=len(tareas) + 2)
    sesiones = async_sessionmaker(motor, expire_on_commit=False)

    async def una(tarea: Callable[[AsyncSession], Awaitable[T]]) -> T | Exception:
        async with sesiones() as session:
            try:
                async with session.begin():
                    await session.execute(
                        text("SELECT set_config('app.empresa_id', :v, true)"),
                        {"v": str(e.empresa_id)},
                    )
                    return await tarea(session)
            except Exception as exc:  # noqa: BLE001 — la prueba inspecciona qué se lanzó.
                return exc

    try:
        return await asyncio.gather(*(una(t) for t in tareas))
    finally:
        await motor.dispose()


def _reporte(
    e: Empresa, *, activo_id: UUID | None = None, cliente_id: UUID | None = None
) -> Callable[[AsyncSession], Awaitable[tuple[str, OrdenTrabajo]]]:
    cliente = cliente_id or uuid4()

    async def tarea(session: AsyncSession) -> tuple[str, OrdenTrabajo]:
        return await ordenes.reportar_falla(
            session,
            _actor(e),
            activo_id=activo_id or e.activo_id,
            componente_id=e.componente_id,
            horometro=10,
            descripcion="Ruido metálico al arrancar",
            capturado_en=datetime.now(UTC),
            cliente_id=cliente,
        )

    return tarea


def test_concurrencia_dos_cierres_simultaneos_uno_gana_otro_409() -> None:
    async def escenario() -> list[Any]:
        (e,) = await sembrar("Empresa A")
        fila = fila_orden(e, numero=1, horas=300, estado="reparada")
        await insertar_ordenes(e, [fila])

        def cerrar(session: AsyncSession) -> Awaitable[OrdenTrabajo]:
            return ordenes_estados.cerrar(session, _actor(e), fila["id"])

        return await _a_la_vez(e, [cerrar, cerrar])

    resultados = correr(escenario())
    ganadoras = [r for r in resultados if isinstance(r, OrdenTrabajo)]
    conflictos = [r for r in resultados if isinstance(r, ordenes.Conflicto)]
    assert len(ganadoras) == 1 and len(conflictos) == 1, resultados
    assert conflictos[0].codigo == "estado_cambiado"


def test_concurrencia_cerrar_y_cancelar_a_la_vez_gana_solo_una() -> None:
    """Un supervisor autoriza el cierre mientras otro la cancela (sección 6.4)."""

    async def escenario() -> tuple[list[Any], str]:
        (e,) = await sembrar("Empresa A")
        fila = fila_orden(e, numero=1, horas=300, estado="reparada")
        await insertar_ordenes(e, [fila])

        def cerrar(session: AsyncSession) -> Awaitable[OrdenTrabajo]:
            return ordenes_estados.cerrar(session, _actor(e), fila["id"])

        def cancelar(session: AsyncSession) -> Awaitable[OrdenTrabajo]:
            return ordenes_estados.cancelar(
                session, _actor(e), fila["id"], motivo="Duplicada, se cancela."
            )

        resultados = await _a_la_vez(e, [cerrar, cancelar])
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.begin() as conn:
                await fijar(conn, e.empresa_id)
                estado = await conn.scalar(
                    text("SELECT estado FROM ordenes_trabajo WHERE id = :i"), {"i": fila["id"]}
                )
        finally:
            await motor.dispose()
        return resultados, str(estado)

    resultados, estado = correr(escenario())
    ganadoras = [r for r in resultados if isinstance(r, OrdenTrabajo)]
    assert len(ganadoras) == 1, resultados
    assert estado == ganadoras[0].estado


def test_concurrencia_dos_reportes_de_la_misma_falla_uno_201_otro_409() -> None:
    async def escenario() -> list[Any]:
        (e,) = await sembrar("Empresa A")
        return await _a_la_vez(e, [_reporte(e), _reporte(e)])

    resultados = correr(escenario())
    creadas = [r for r in resultados if isinstance(r, tuple) and r[0] == "creado"]
    conflictos = [r for r in resultados if isinstance(r, ordenes.Conflicto)]
    assert len(creadas) == 1 and len(conflictos) == 1, resultados
    assert conflictos[0].codigo == "orden_abierta_existente"


def test_concurrencia_reenvio_simultaneo_crea_una_sola_orden() -> None:
    async def escenario() -> list[Any]:
        (e,) = await sembrar("Empresa A")
        cliente = uuid4()
        return await _a_la_vez(
            e, [_reporte(e, cliente_id=cliente), _reporte(e, cliente_id=cliente)]
        )

    resultados = correr(escenario())
    assert all(isinstance(r, tuple) for r in resultados), resultados
    assert sorted(r[0] for r in resultados) == ["creado", "duplicado"]  # type: ignore[index]
    assert len({r[1].id for r in resultados}) == 1  # type: ignore[index]


def test_concurrencia_veinte_reportes_numeros_unicos_y_consecutivos() -> None:
    """La fila del contador serializa la numeración: 1 a 20 sin repetir ni saltar (6.3)."""

    async def escenario() -> list[Any]:
        (e,) = await sembrar("Empresa A")
        activos = [uuid4() for _ in range(20)]
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.begin() as conn:
                await fijar(conn, e.empresa_id)
                for i, activo in enumerate(activos):
                    await conn.execute(
                        text(
                            "INSERT INTO activos (id, empresa_id, nombre, qr_code)"
                            " VALUES (:i, :e, :n, :q)"
                        ),
                        {"i": activo, "e": e.empresa_id, "n": f"Equipo {i}", "q": uuid4().hex[:8]},
                    )
        finally:
            await motor.dispose()
        return await _a_la_vez(e, [_reporte(e, activo_id=a) for a in activos])

    resultados = correr(escenario())
    assert all(isinstance(r, tuple) and r[0] == "creado" for r in resultados), resultados
    assert sorted(r[1].numero for r in resultados) == list(range(1, 21))  # type: ignore[index]
