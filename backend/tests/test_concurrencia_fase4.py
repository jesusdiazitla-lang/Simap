"""Concurrencia real de la fase 4: varias conexiones a la vez contra PostgreSQL (07-fase4, 15.2).

Como en la fase 3, cada «persona» tiene su conexión y su transacción y `asyncio.gather` las lanza
juntas. Son las pruebas que la guía no pudo correr en PGlite (una sola conexión): el orden de
bloqueo de los repuestos, el FOR SHARE del trigger de líneas, la competencia por la última unidad y
el índice único de las alertas bajo carrera.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services import inventario, ordenes, ordenes_estados
from app.services.prediccion import alertas, riesgo
from tests.base_ordenes import Empresa, correr, fijar, fila_orden, insertar_ordenes, sembrar
from tests.conftest import URL_APP, URL_DUENO, requiere_base

pytestmark = requiere_base

T = TypeVar("T")


def _actor(e: Empresa) -> ordenes.Actor:
    return ordenes.Actor(empresa_id=e.empresa_id, usuario_id=e.usuario_id, rol="supervisor")


async def _a_la_vez(
    e: Empresa, tareas: list[Callable[[AsyncSession], Awaitable[T]]]
) -> list[T | Exception]:
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


async def _dueno(e: Empresa, sentencias: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    motor = create_async_engine(URL_DUENO)
    salida: list[Any] = []
    try:
        async with motor.begin() as conn:
            await fijar(conn, e.empresa_id)
            for sql, params in sentencias:
                resultado = await conn.execute(text(sql), params)
                if resultado.returns_rows:
                    salida.append(resultado.all())
    finally:
        await motor.dispose()
    return salida


async def _par_con_riesgo_alto(e: Empresa) -> None:
    await _dueno(
        e,
        [
            ("INSERT INTO configuracion_empresa (empresa_id) VALUES (:e)", {"e": e.empresa_id}),
            (
                "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                {"e": e.empresa_id, "a": e.activo_id, "c": e.componente_id},
            ),
            (
                "INSERT INTO riesgos (empresa_id, activo_id, componente_id, estado_calculo,"
                " edad_horas, horizonte_horas, beta, eta, riesgo_base, multiplicador, riesgo,"
                " confianza, fuente) VALUES (:e, :a, :c, 'ok', 900, 50, 2, 1000, 0.6, 1.00, 0.6,"
                " 'media', 'empresa')",
                {"e": e.empresa_id, "a": e.activo_id, "c": e.componente_id},
            ),
        ],
    )


def test_rf21_dos_calculos_simultaneos_crean_una_sola_alerta() -> None:
    """El índice único parcial decide: dos procesos a la vez, una sola alerta vigente."""

    async def escenario() -> tuple[list[Any], int]:
        (e,) = await sembrar("Empresa A")
        await _par_con_riesgo_alto(e)

        async def calcular(session: AsyncSession) -> int:
            return await riesgo.crear_alertas(session, e.empresa_id)

        resultados = await _a_la_vez(e, [calcular] * 4)
        (filas,) = await _dueno(
            e, [("SELECT count(*) FROM alertas_sistema WHERE tipo = 'riesgo'", {})]
        )
        return resultados, int(filas[0][0])

    resultados, total = correr(escenario())
    assert not any(isinstance(r, Exception) for r in resultados), resultados
    assert sum(r for r in resultados if isinstance(r, int)) == 1
    assert total == 1


def test_rf21_dos_supervisores_toman_la_alerta_uno_201_otro_409() -> None:
    async def escenario() -> tuple[list[Any], int]:
        (e,) = await sembrar("Empresa A")
        await _par_con_riesgo_alto(e)
        alerta = uuid4()
        await _dueno(
            e,
            [
                (
                    "INSERT INTO alertas_sistema (id, empresa_id, tipo, activo_id, componente_id,"
                    " riesgo, umbral) VALUES (:i, :e, 'riesgo', :a, :c, 0.6, 0.25)",
                    {"i": alerta, "e": e.empresa_id, "a": e.activo_id, "c": e.componente_id},
                )
            ],
        )

        async def tomar(session: AsyncSession) -> UUID:
            orden = await alertas.crear_orden_predictiva(session, _actor(e), alerta, None)
            return orden.id

        resultados = await _a_la_vez(e, [tomar, tomar])
        (filas,) = await _dueno(
            e, [("SELECT count(*) FROM ordenes_trabajo WHERE es_predictiva", {})]
        )
        return resultados, int(filas[0][0])

    resultados, ordenes_creadas = correr(escenario())
    ganadoras = [r for r in resultados if isinstance(r, UUID)]
    conflictos = [r for r in resultados if isinstance(r, ordenes.Conflicto)]
    assert len(ganadoras) == 1
    assert len(conflictos) == 1
    assert conflictos[0].codigo == "alerta_no_disponible"
    assert ordenes_creadas == 1


async def _repuesto(e: Empresa, stock: int, codigo: str) -> UUID:
    rid = uuid4()
    await _dueno(
        e,
        [
            (
                "INSERT INTO repuestos (id, empresa_id, nombre, codigo, stock_actual,"
                " costo_unitario) VALUES (:i, :e, :n, :c, :s, 10)",
                {"i": rid, "e": e.empresa_id, "n": f"Repuesto {codigo}", "c": codigo, "s": stock},
            ),
            (
                "INSERT INTO stock_movimientos (empresa_id, repuesto_id, tipo, delta,"
                " stock_resultante, usuario_id) VALUES (:e, :i, 'inicial', :s, :s, :u)",
                {"e": e.empresa_id, "i": rid, "s": stock, "u": e.usuario_id},
            ),
        ],
    )
    return rid


async def _orden_reparada(e: Empresa, numero: int, lineas: list[tuple[UUID, int]]) -> UUID:
    """Una orden Reparada sobre un componente propio (una abierta por componente), con líneas."""
    componente = uuid4()
    await _dueno(
        e,
        [
            (
                "INSERT INTO componentes (id, empresa_id, nombre) VALUES (:c, :e, :n)",
                {"c": componente, "e": e.empresa_id, "n": f"Componente {numero}"},
            )
        ],
    )
    fila = fila_orden(e, numero=numero, horas=100, estado="reparada", componente_id=componente)
    await insertar_ordenes(e, [fila])
    await _dueno(
        e,
        [
            (
                "INSERT INTO orden_repuesto (empresa_id, orden_id, repuesto_id, cantidad,"
                " registrado_por) VALUES (:e, :o, :r, :q, :u)",
                {"e": e.empresa_id, "o": fila["id"], "r": rid, "q": q, "u": e.usuario_id},
            )
            for rid, q in lineas
        ],
    )
    return UUID(str(fila["id"]))


def _cierre(e: Empresa, orden_id: UUID) -> Callable[[AsyncSession], Awaitable[str]]:
    async def tarea(session: AsyncSession) -> str:
        orden = await ordenes_estados.cerrar(session, _actor(e), orden_id)
        return orden.estado

    return tarea


def test_rf25_dos_cierres_por_la_ultima_unidad_uno_cierra_otro_409() -> None:
    async def escenario() -> tuple[list[Any], list[Any]]:
        (e,) = await sembrar("Empresa A")
        rid = await _repuesto(e, 1, "RP-ULT")
        x = await _orden_reparada(e, 1, [(rid, 1)])
        y = await _orden_reparada(e, 2, [(rid, 1)])
        resultados = await _a_la_vez(e, [_cierre(e, x), _cierre(e, y)])
        (stock,) = await _dueno(
            e, [("SELECT stock_actual FROM repuestos WHERE id = :i", {"i": rid})]
        )
        return resultados, stock

    resultados, stock = correr(escenario())
    assert sorted(type(r).__name__ for r in resultados) == ["StockInsuficiente", "str"]
    assert [r for r in resultados if isinstance(r, str)] == ["cerrada"]
    assert stock[0][0] == 0


def test_rf25_cierres_con_repuestos_en_comun_no_se_bloquean() -> None:
    """Dos órdenes que comparten dos repuestos y los anotaron en orden inverso: sin deadlock,
    porque el cierre los bloquea siempre en orden de id."""

    async def escenario() -> tuple[list[Any], list[Any]]:
        (e,) = await sembrar("Empresa A")
        r1 = await _repuesto(e, 10, "RP-1")
        r2 = await _repuesto(e, 10, "RP-2")
        x = await _orden_reparada(e, 1, [(r1, 1), (r2, 1)])
        y = await _orden_reparada(e, 2, [(r2, 1), (r1, 1)])
        resultados = await _a_la_vez(e, [_cierre(e, x), _cierre(e, y)] * 1)
        (stock,) = await _dueno(
            e,
            [
                (
                    "SELECT stock_actual FROM repuestos WHERE id IN (:a, :b) ORDER BY codigo",
                    {"a": r1, "b": r2},
                )
            ],
        )
        return resultados, stock

    resultados, stock = correr(escenario())
    assert resultados == ["cerrada", "cerrada"]
    assert [s[0] for s in stock] == [8, 8]


def test_rf25_linea_concurrente_con_cierre_no_queda_sin_descontar() -> None:
    """Una línea que llega mientras se cierra la orden: o entra antes y se descuenta, o espera al
    cierre (FOR SHARE del trigger) y se rechaza. Nunca queda una línea sin su consumo."""

    async def escenario() -> tuple[list[Any], int, int]:
        (e,) = await sembrar("Empresa A")
        r1 = await _repuesto(e, 10, "RP-1")
        r2 = await _repuesto(e, 10, "RP-2")
        orden = await _orden_reparada(e, 1, [(r1, 1)])

        async def linea(session: AsyncSession) -> str:
            await inventario.guardar_linea(session, _actor(e), orden, r2, 2)
            return "linea"

        resultados = await _a_la_vez(e, [_cierre(e, orden), linea])
        (lineas, consumos) = await _dueno(
            e,
            [
                ("SELECT count(*) FROM orden_repuesto WHERE orden_id = :o", {"o": orden}),
                (
                    "SELECT count(*) FROM stock_movimientos WHERE orden_id = :o"
                    " AND tipo = 'consumo'",
                    {"o": orden},
                ),
            ],
        )
        return resultados, int(lineas[0][0]), int(consumos[0][0])

    resultados, lineas, consumos = correr(escenario())
    assert "cerrada" in resultados
    assert lineas == consumos
