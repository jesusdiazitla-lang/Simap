"""Lo que la base impone en la fase 4, probado contra PostgreSQL (07-fase4, secciones 7 y 15.2).

Como en la fase 3, cada prueba ataca como `app_user` sin pasar por el servicio: si una defensa de la
base se cayera, el servicio podría seguir tapándola y nadie se enteraría. Las que comprueban el
cálculo (vidas, ajuste, rendimiento) llaman al servicio sobre datos sembrados directamente.
"""

from __future__ import annotations

import math
import random
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.db.deps import sesion_de_empresa
from app.db.session import dispose_engine
from app.services.prediccion import ajuste, riesgo, weibull
from tests.base_ordenes import (
    Empresa,
    correr,
    fijar,
    fila_orden,
    insertar_ordenes,
    motor_app,
    sembrar,
)
from tests.conftest import URL_DUENO, requiere_base

pytestmark = requiere_base

TABLAS_NUEVAS = (
    "configuracion_empresa",
    "repuestos",
    "stock_movimientos",
    "orden_repuesto",
    "activo_componentes",
    "alertas_sistema",
    "modelos_componente",
    "modelos_historial",
    "reajustes_pendientes",
    "riesgos",
)
VISTAS = ("v_vidas", "v_riesgo_activo")


async def _como_dueno(e: Empresa, sentencias: list[tuple[str, dict[str, Any]]]) -> None:
    motor = create_async_engine(URL_DUENO)
    try:
        async with motor.begin() as conn:
            await fijar(conn, e.empresa_id)
            for sql, params in sentencias:
                await conn.execute(text(sql), params)
    finally:
        await motor.dispose()


async def _sembrar_fase4(e: Empresa) -> dict[str, UUID]:
    """Una fila en cada tabla nueva de la empresa, sembrada como dueño con su tenant fijado."""
    ids = {"repuesto": uuid4(), "orden": uuid4(), "abierta": uuid4(), "alerta": uuid4()}
    cerrada = fila_orden(e, numero=1, horas=500)
    cerrada["id"] = ids["orden"]
    abierta = fila_orden(e, numero=2, horas=600, estado="reportada")
    abierta["id"] = ids["abierta"]
    abierta["componente"] = e.componente_id
    await insertar_ordenes(e, [cerrada])
    otro_componente = uuid4()
    await _como_dueno(
        e,
        [
            (
                "INSERT INTO componentes (id, empresa_id, nombre) VALUES (:c, :e, 'Bomba')",
                {"c": otro_componente, "e": e.empresa_id},
            ),
        ],
    )
    abierta["componente"] = otro_componente
    await insertar_ordenes(e, [abierta])
    p = {"e": e.empresa_id, "a": e.activo_id, "c": e.componente_id, "u": e.usuario_id, **ids}
    await _como_dueno(
        e,
        [
            ("INSERT INTO configuracion_empresa (empresa_id) VALUES (:e)", p),
            (
                "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                p,
            ),
            (
                "INSERT INTO repuestos (id, empresa_id, nombre, codigo, stock_actual)"
                " VALUES (:repuesto, :e, 'Filtro', 'F-1', 5)",
                p,
            ),
            (
                "INSERT INTO stock_movimientos (empresa_id, repuesto_id, tipo, delta,"
                " stock_resultante, usuario_id) VALUES (:e, :repuesto, 'inicial', 5, 5, :u)",
                p,
            ),
            (
                "INSERT INTO orden_repuesto (empresa_id, orden_id, repuesto_id, cantidad,"
                " registrado_por) VALUES (:e, :abierta, :repuesto, 1, :u)",
                p,
            ),
            (
                "INSERT INTO alertas_sistema (id, empresa_id, tipo, activo_id, componente_id,"
                " riesgo, umbral) VALUES (:alerta, :e, 'riesgo', :a, :c, 0.5, 0.25)",
                p,
            ),
            (
                "INSERT INTO modelos_componente (empresa_id, componente_id, beta, eta, n_eventos,"
                " n_vidas, exposicion_horas, fuente, confianza, convergio)"
                " VALUES (:e, :c, 2, 1000, 1, 1, 500, 'mixto', 'baja', true)",
                p,
            ),
            (
                "INSERT INTO modelos_historial (empresa_id, componente_id, version, beta, eta,"
                " n_eventos, fuente, confianza) VALUES (:e, :c, 1, 2, 1000, 1, 'mixto', 'baja')",
                p,
            ),
            ("INSERT INTO reajustes_pendientes (empresa_id, componente_id) VALUES (:e, :c)", p),
            (
                "INSERT INTO riesgos (empresa_id, activo_id, componente_id, estado_calculo,"
                " edad_horas, horizonte_horas, beta, eta, riesgo_base, multiplicador, riesgo)"
                " VALUES (:e, :a, :c, 'ok', 100, 50, 2, 1000, 0.1, 1.00, 0.1)",
                p,
            ),
        ],
    )
    return ids


async def _contar(empresa_id: UUID, tabla: str) -> int:
    motor = motor_app()
    try:
        async with motor.connect() as conn, conn.begin():
            await fijar(conn, empresa_id)
            return int((await conn.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one())
    finally:
        await motor.dispose()


def test_rnf01_tablas_nuevas_aisladas_por_empresa() -> None:
    """La empresa B ve cero filas de A en cada tabla y vista nueva; sin tenant, nadie ve nada."""

    async def escenario() -> tuple[list[int], list[int], list[int]]:
        a, b = await sembrar("Empresa A", "Empresa B")
        await _sembrar_fase4(a)
        todas = (*TABLAS_NUEVAS, *VISTAS)
        de_a = [await _contar(a.empresa_id, t) for t in todas]
        de_b = [await _contar(b.empresa_id, t) for t in todas]
        sin = []
        motor = motor_app()
        try:
            async with motor.connect() as conn, conn.begin():
                await fijar(conn, None)
                for t in todas:
                    sin.append(
                        int((await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one())
                    )
        finally:
            await motor.dispose()
        return de_a, de_b, sin

    de_a, de_b, sin = correr(escenario())
    assert all(n > 0 for n in de_a), de_a
    assert de_b == [0] * len(de_b)
    assert sin == [0] * len(sin)


def test_rnf01_referencias_cruzadas_rechazadas_en_tablas_nuevas() -> None:
    """Una fila de A no puede apuntar a datos de B: las llaves compuestas lo rechazan (23503)."""

    async def escenario() -> list[str]:
        a, b = await sembrar("Empresa A", "Empresa B")
        de_b = await _sembrar_fase4(b)
        intentos = [
            (
                "INSERT INTO orden_repuesto (empresa_id, orden_id, repuesto_id, cantidad,"
                " registrado_por) VALUES (:e, :orden_b, :repuesto_b, 1, :u)",
            ),
            (
                "INSERT INTO stock_movimientos (empresa_id, repuesto_id, tipo, delta,"
                " stock_resultante, usuario_id) VALUES (:e, :repuesto_b, 'ingreso', 1, 1, :u)",
            ),
            (
                "INSERT INTO alertas_sistema (empresa_id, tipo, activo_id, componente_id, riesgo,"
                " umbral) VALUES (:e, 'riesgo', :activo_b, :componente_b, 0.5, 0.25)",
            ),
            (
                "INSERT INTO modelos_componente (empresa_id, componente_id, beta, eta, n_eventos,"
                " n_vidas, exposicion_horas, fuente, confianza, convergio)"
                " VALUES (:e, :componente_b, 2, 100, 0, 0, 0, 'previo', 'baja', true)",
            ),
            (
                "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id)"
                " VALUES (:e, :activo_b, :componente_b)",
            ),
        ]
        params = {
            "e": a.empresa_id,
            "u": a.usuario_id,
            "orden_b": de_b["abierta"],
            "repuesto_b": de_b["repuesto"],
            "activo_b": b.activo_id,
            "componente_b": b.componente_id,
        }
        codigos = []
        motor = motor_app()
        try:
            for (sql,) in intentos:
                async with motor.connect() as conn:
                    trans = await conn.begin()
                    await fijar(conn, a.empresa_id)
                    try:
                        await conn.execute(text(sql), params)
                        codigos.append("aceptada")
                    except IntegrityError as exc:
                        codigos.append(getattr(exc.orig, "sqlstate", "") or "23503")
                    await trans.rollback()
        finally:
            await motor.dispose()
        return codigos

    assert correr(escenario()) == ["23503"] * 5


def test_rnf01_guardias_fk_compuestas_y_solo_agregar() -> None:
    """Las dos consultas de guardia de la sección 7.9 devuelven cero filas."""

    async def escenario() -> tuple[list[Any], list[Any]]:
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.connect() as conn:
                simples = (
                    await conn.execute(
                        text(
                            "SELECT conrelid::regclass::text FROM pg_constraint"
                            " WHERE contype = 'f' AND array_length(conkey, 1) = 1"
                            " AND confrelid::regclass::text IN ('activos', 'componentes',"
                            " 'repuestos', 'usuarios', 'ordenes_trabajo', 'alertas_sistema')"
                            " AND conrelid::regclass::text IN ('activo_componentes',"
                            " 'alertas_sistema', 'modelos_componente', 'modelos_historial',"
                            " 'reajustes_pendientes', 'riesgos', 'repuestos', 'stock_movimientos',"
                            " 'orden_repuesto')"
                        )
                    )
                ).all()
                politicas = (
                    await conn.execute(
                        text(
                            "SELECT tablename, cmd FROM pg_policies"
                            " WHERE tablename IN ('stock_movimientos', 'modelos_historial')"
                            " AND cmd NOT IN ('SELECT', 'INSERT')"
                        )
                    )
                ).all()
                return list(simples), list(politicas)
        finally:
            await motor.dispose()

    simples, politicas = correr(escenario())
    assert simples == []
    assert politicas == []


def test_libro_e_historial_del_modelo_solo_se_agregan() -> None:
    """`app_user` no puede modificar ni borrar el libro ni la curva de aprendizaje (42501)."""

    async def escenario() -> list[bool]:
        (a,) = await sembrar("Empresa A")
        await _sembrar_fase4(a)
        negadas = []
        motor = motor_app()
        try:
            for sql in (
                "UPDATE stock_movimientos SET delta = 99",
                "DELETE FROM stock_movimientos",
                "UPDATE modelos_historial SET beta = 9",
                "DELETE FROM modelos_historial",
                "DELETE FROM repuestos",
                "DELETE FROM alertas_sistema",
            ):
                async with motor.connect() as conn:
                    trans = await conn.begin()
                    await fijar(conn, a.empresa_id)
                    try:
                        await conn.execute(text(sql))
                        negadas.append(False)
                    except DBAPIError as exc:
                        negadas.append("permission denied" in str(exc))
                    await trans.rollback()
        finally:
            await motor.dispose()
        return negadas

    assert correr(escenario()) == [True] * 6


def test_rf24_lineas_de_una_orden_cerrada_no_se_tocan() -> None:
    """El trigger `orden_repuesto_inmutable` rechaza agregar líneas a una orden cerrada (23514)."""

    async def escenario() -> str:
        (a,) = await sembrar("Empresa A")
        ids = await _sembrar_fase4(a)
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                try:
                    await conn.execute(
                        text(
                            "INSERT INTO orden_repuesto (empresa_id, orden_id, repuesto_id,"
                            " cantidad, registrado_por) VALUES (:e, :o, :r, 1, :u)"
                        ),
                        {
                            "e": a.empresa_id,
                            "o": ids["orden"],
                            "r": ids["repuesto"],
                            "u": a.usuario_id,
                        },
                    )
                    return "aceptada"
                except DBAPIError as exc:
                    return str(exc)
                finally:
                    await trans.rollback()
        finally:
            await motor.dispose()

    assert "no se pueden modificar" in correr(escenario())


def test_rf25_doble_descuento_imposible_y_stock_nunca_negativo() -> None:
    async def escenario() -> tuple[str, str]:
        (a,) = await sembrar("Empresa A")
        ids = await _sembrar_fase4(a)
        consumo = text(
            "INSERT INTO stock_movimientos (empresa_id, repuesto_id, tipo, delta,"
            " stock_resultante, costo_unitario, orden_id, usuario_id)"
            " VALUES (:e, :r, 'consumo', -1, 4, 10, :o, :u)"
        )
        params = {"e": a.empresa_id, "r": ids["repuesto"], "o": ids["orden"], "u": a.usuario_id}
        motor = motor_app()
        resultados = []
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                await conn.execute(consumo, params)
                try:
                    await conn.execute(consumo, params)
                    resultados.append("aceptado")
                except IntegrityError as exc:
                    resultados.append(str(exc))
                await trans.rollback()
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                try:
                    await conn.execute(text("UPDATE repuestos SET stock_actual = -1"))
                    resultados.append("aceptado")
                except IntegrityError as exc:
                    resultados.append(str(exc))
                await trans.rollback()
        finally:
            await motor.dispose()
        return resultados[0], resultados[1]

    doble, negativo = correr(escenario())
    assert "ix_stock_movimientos_consumo_unico" in doble
    assert "stock_no_negativo" in negativo


def test_datos_de_la_falla_solo_cambian_al_convertir_en_falla() -> None:
    """Dial, horas, fecha y lectura de una orden solo se reescriben en la escritura que apaga
    `es_predictiva` (trigger `ot_datos_de_falla`, revisiones 0009 y 0010)."""

    async def escenario() -> tuple[str, str, str]:
        (a,) = await sembrar("Empresa A")
        fila = fila_orden(a, numero=1, horas=500, estado="reportada")
        await insertar_ordenes(a, [fila])
        await _como_dueno(
            a,
            [("UPDATE ordenes_trabajo SET es_predictiva = true WHERE id = :i", {"i": fila["id"]})],
        )
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                try:
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET fecha_falla = now() WHERE id = :i"),
                        {"i": fila["id"]},
                    )
                    sin_convertir = "aceptada"
                except DBAPIError as exc:
                    sin_convertir = str(exc)
                await trans.rollback()
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                try:
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET lectura_id = :l WHERE id = :i"),
                        {"i": fila["id"], "l": uuid4()},
                    )
                    reenlazar = "aceptada"
                except DBAPIError as exc:
                    reenlazar = str(exc)
                await trans.rollback()
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                await conn.execute(
                    text(
                        "UPDATE ordenes_trabajo SET fecha_falla = now(), horometro_en_falla = 510,"
                        " horas_acumuladas_en_falla = 510, es_predictiva = false WHERE id = :i"
                    ),
                    {"i": fila["id"]},
                )
                await trans.rollback()
                convirtiendo = "aceptada"
        finally:
            await motor.dispose()
        return sin_convertir, reenlazar, convirtiendo

    sin_convertir, reenlazar, convirtiendo = correr(escenario())
    assert "solo cambian al convertirla" in sin_convertir
    assert "solo se fija al convertirla" in reenlazar
    assert convirtiendo == "aceptada"


async def _marcar_predictiva(e: Empresa, orden_id: UUID) -> None:
    """Las órdenes sembradas ya están cerradas: el dueño abre el trigger como la corrección."""
    await _como_dueno(
        e,
        [
            ("SELECT set_config('app.correccion', 'on', true)", {}),
            ("UPDATE ordenes_trabajo SET es_predictiva = true WHERE id = :i", {"i": orden_id}),
        ],
    )


def test_rf17_reemplazo_predictivo_cuenta_como_censura() -> None:
    """La secuencia de la sección 5.1, fila por fila.

    Vida 0: fallas a las 400 h (reparación) y 700 h (reemplazo). Vida 1: un ajuste a las 1100 h y
    un reemplazo **predictivo** a las 1300 h: termina sin falla. Vida 2: abierta; el equipo marca
    1500 h. No cuentan: una orden cancelada, una con el horómetro en revisión y una intervención
    predictiva que no reemplazó la pieza.
    """

    async def escenario() -> list[tuple[int, bool, int, float, float]]:
        (a,) = await sembrar("Empresa A")
        inicio = datetime(2026, 1, 1, tzinfo=UTC)
        secuencia = [
            fila_orden(
                a, numero=1, horas=400, tipo="reparacion", fecha=inicio + timedelta(hours=400)
            ),
            fila_orden(
                a, numero=2, horas=700, tipo="reemplazo", fecha=inicio + timedelta(hours=700)
            ),
            fila_orden(
                a, numero=3, horas=1100, tipo="ajuste", fecha=inicio + timedelta(hours=1100)
            ),
            fila_orden(
                a, numero=4, horas=1300, tipo="reemplazo", fecha=inicio + timedelta(hours=1300)
            ),
            fila_orden(
                a,
                numero=5,
                horas=1350,
                tipo="reemplazo",
                estado="cancelada",
                fecha=inicio + timedelta(hours=1350),
            ),
            fila_orden(
                a,
                numero=6,
                horas=1400,
                tipo="reemplazo",
                requiere_revision=True,
                fecha=inicio + timedelta(hours=1400),
            ),
            fila_orden(
                a, numero=7, horas=1450, tipo="reparacion", fecha=inicio + timedelta(hours=1450)
            ),
        ]
        await insertar_ordenes(a, secuencia)
        await _marcar_predictiva(a, secuencia[3]["id"])
        await _marcar_predictiva(a, secuencia[6]["id"])
        await _como_dueno(
            a,
            [
                (
                    "UPDATE activos SET horometro_actual = 1500 WHERE id = :a",
                    {"a": a.activo_id},
                ),
                (
                    "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                    " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                    {"e": a.empresa_id, "a": a.activo_id, "c": a.componente_id},
                ),
            ],
        )
        motor = motor_app()
        try:
            async with motor.connect() as conn, conn.begin():
                await fijar(conn, a.empresa_id)
                filas = await conn.execute(
                    text(
                        "SELECT vida, abierta, n_eventos, suma_ln_edades, exposicion FROM v_vidas"
                        " ORDER BY vida"
                    )
                )
                return [(int(v), bool(ab), int(n), float(s), float(x)) for v, ab, n, s, x in filas]
        finally:
            await motor.dispose()

    filas = correr(escenario())
    assert [(v, ab, n, x) for v, ab, n, _, x in filas] == [
        (0, False, 2, 700.0),
        (1, False, 1, 600.0),
        (2, True, 0, 200.0),
    ]
    assert filas[0][3] == pytest.approx(math.log(400) + math.log(700))
    assert filas[1][3] == pytest.approx(math.log(400))
    assert filas[2][3] == 0.0


async def _flota(
    e: Empresa, *, equipos: int, horizonte: float, beta: float, eta: float, semilla: int
) -> weibull.Datos:
    """Siembra una flota con vidas de una Weibull conocida, solo reemplazos, y devuelve los
    estadísticos que **debería** dar `v_vidas` calculados aquí, sin la vista."""
    azar = random.Random(semilla)
    inicio = datetime(2026, 1, 1, tzinfo=UTC)
    filas, sentencias = [], []
    n, s1, t = 0, 0.0, []
    numero = 0
    for i in range(equipos):
        activo = uuid4()
        sentencias += [
            (
                "INSERT INTO activos (id, empresa_id, nombre, qr_code, horometro_actual)"
                " VALUES (:a, :e, :n, :q, :h)",
                {
                    "a": activo,
                    "e": e.empresa_id,
                    "n": f"Equipo {i}",
                    "q": uuid4().hex[:8].upper(),
                    "h": int(horizonte),
                },
            ),
            (
                "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                {"e": e.empresa_id, "a": activo, "c": e.componente_id},
            ),
        ]
        horas = 0
        while True:
            vida = max(1, round(azar.weibullvariate(eta, beta)))
            if horas + vida >= horizonte:
                t.append(horizonte - horas)
                break
            horas += vida
            numero += 1
            n += 1
            s1 += math.log(vida)
            t.append(vida)
            filas.append(
                fila_orden(
                    e,
                    numero=numero,
                    horas=horas,
                    activo_id=activo,
                    fecha=inicio + timedelta(hours=horas),
                )
            )
    await _como_dueno(e, sentencias)
    await insertar_ordenes(e, filas)
    return weibull.Datos(n, s1, np.asarray(t, dtype=float))


def test_rf17_ajuste_recupera_parametros_de_flota_simulada() -> None:
    """Vista, Python y guardado de punta a punta (15.2). 14 equipos con piezas de una Weibull
    conocida (β = 2,5; η = 1000 h): `v_vidas` entrega exactamente los estadísticos del simulador, y
    el modelo guardado queda cerca de la verdad."""

    async def escenario() -> tuple[weibull.Datos, list[Any], dict[str, Any] | None, int]:
        (a,) = await sembrar("Flota")
        esperado = await _flota(a, equipos=14, horizonte=3000, beta=2.5, eta=1000, semilla=2026)
        try:
            async with sesion_de_empresa(a.empresa_id) as session:
                filas = await ajuste.datos_ajuste(session, a.componente_id)
                pendiente = ajuste.Pendiente(a.componente_id, 1000, 0)
                modelo = await ajuste.reajustar(session, a.empresa_id, pendiente)
                version = await session.scalar(
                    text("SELECT version FROM modelos_componente WHERE componente_id = :c"),
                    {"c": a.componente_id},
                )
        finally:
            await dispose_engine()
        return esperado, filas, modelo, int(version or 0)

    esperado, filas, modelo, version = correr(escenario())
    vista = weibull.Datos.de_vidas(filas)
    assert vista.n == esperado.n
    assert vista.s1 == pytest.approx(esperado.s1)
    assert sorted(vista.t) == pytest.approx(sorted(esperado.t))
    assert modelo is not None
    assert modelo["n_eventos"] == esperado.n >= 20
    assert modelo["confianza"] == "alta"
    assert 1.8 < modelo["beta"] < 3.6
    assert modelo["eta"] == pytest.approx(1000, rel=0.2)
    assert version == 1


def test_rf22_cierre_durante_el_ajuste_no_pierde_la_marca() -> None:
    """La generación: si llega otro cierre mientras se ajusta, liberar la marca vieja no la
    borra."""

    async def escenario() -> tuple[bool, int]:
        (a,) = await sembrar("Empresa A")
        await _como_dueno(
            a,
            [
                (
                    "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                    " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                    {"e": a.empresa_id, "a": a.activo_id, "c": a.componente_id},
                )
            ],
        )
        try:
            async with sesion_de_empresa(a.empresa_id) as session:
                await ajuste.marcar(session, a.empresa_id, a.componente_id)
            async with sesion_de_empresa(a.empresa_id) as session:
                (pendiente,) = await ajuste.a_reajustar(session)
            # Mientras «se ajusta», otro cierre marca de nuevo y confirma.
            async with sesion_de_empresa(a.empresa_id) as session:
                await ajuste.marcar(session, a.empresa_id, a.componente_id)
            async with sesion_de_empresa(a.empresa_id) as session:
                liberada = await ajuste.liberar(session, a.componente_id, pendiente.generacion)
            async with sesion_de_empresa(a.empresa_id) as session:
                quedan = len(await ajuste.a_reajustar(session))
        finally:
            await dispose_engine()
        return liberada, quedan

    liberada, quedan = correr(escenario())
    assert liberada is False
    assert quedan == 1


def test_rnf04_riesgo_de_un_equipo_en_menos_de_2s_con_60000_ordenes() -> None:
    """RNF-04 en PostgreSQL real (9.4): 4000 equipos, 5 componentes por equipo y 3 fallas cerradas
    por par. El recálculo de un equipo (riesgo y alertas) tarda menos de 2 s."""

    async def escenario() -> tuple[float, int]:
        (a,) = await sembrar("RNF-04")
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.begin() as conn:
                await fijar(conn, a.empresa_id)
                await _sembrar_grande(conn, a)
            try:
                async with sesion_de_empresa(a.empresa_id) as session:
                    inicio = time.perf_counter()
                    resultado = await riesgo.recalcular_y_alertar(
                        session, a.empresa_id, a.activo_id
                    )
                    duracion = time.perf_counter() - inicio
            finally:
                await dispose_engine()
            return duracion, resultado["calculados"]
        finally:
            async with motor.begin() as conn:
                await fijar(conn, a.empresa_id)
                for tabla in (
                    "alertas_sistema",
                    "riesgos",
                    "modelos_componente",
                    "ordenes_trabajo",
                    "activo_componentes",
                    "activos",
                    "componentes",
                    "configuracion_empresa",
                ):
                    await conn.execute(
                        text(f"DELETE FROM {tabla} WHERE empresa_id = :e"), {"e": a.empresa_id}
                    )
            await motor.dispose()

    duracion, calculados = correr(escenario())
    assert calculados == 5
    print(f"RNF-04: {duracion * 1000:.1f} ms")
    assert duracion < 2.0, f"{duracion:.3f} s"


async def _sembrar_grande(conn: AsyncConnection, a: Empresa) -> None:
    """60 000 órdenes cerradas con `generate_series`, en segundos. Datos sintéticos de prueba."""
    p = {"e": a.empresa_id, "u": a.usuario_id, "a": a.activo_id}
    await conn.execute(
        text(
            "INSERT INTO componentes (id, empresa_id, nombre)"
            " SELECT gen_random_uuid(), :e, 'Componente ' || g FROM generate_series(1, 4) g"
        ),
        p,
    )
    await conn.execute(
        text(
            "INSERT INTO activos (id, empresa_id, nombre, qr_code, horometro_actual)"
            " SELECT gen_random_uuid(), :e, 'Equipo ' || g,"
            " upper(substr(md5(random()::text), 1, 8)), 5000 FROM generate_series(1, 3999) g"
        ),
        p,
    )
    await conn.execute(text("UPDATE activos SET horometro_actual = 5000 WHERE id = :a"), p)
    await conn.execute(
        text(
            "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
            " horas_instalacion_inicial)"
            " SELECT :e, a.id, c.id, 0 FROM activos a CROSS JOIN componentes c"
            " WHERE a.empresa_id = :e AND c.empresa_id = :e"
        ),
        p,
    )
    await conn.execute(
        text(
            "INSERT INTO ordenes_trabajo (id, empresa_id, numero, cliente_id, activo_id,"
            " componente_id, reportado_por, reparado_por, autorizado_por, horometro_en_falla,"
            " horas_acumuladas_en_falla, descripcion, estado, trabajo_realizado,"
            " tipo_intervencion, fecha_falla, fecha_salida_taller, tiempo_fuera_servicio_min)"
            " SELECT gen_random_uuid(), :e,"
            " row_number() OVER (), gen_random_uuid(), ac.activo_id, ac.componente_id, :u, :u, :u,"
            " k * 1000, k * 1000, 'Falla sintetica', 'cerrada', 'Reemplazo', 'reemplazo',"
            " timestamptz '2026-01-01' + k * interval '1 day',"
            " timestamptz '2026-01-01' + k * interval '1 day', 60"
            " FROM activo_componentes ac CROSS JOIN generate_series(1, 3) k"
            " WHERE ac.empresa_id = :e"
        ),
        p,
    )
    await conn.execute(
        text(
            "INSERT INTO modelos_componente (empresa_id, componente_id, beta, eta, n_eventos,"
            " n_vidas, exposicion_horas, fuente, confianza, convergio)"
            " SELECT :e, id, 2.5, 1000, 12000, 16000, 5000000, 'empresa', 'alta', true"
            " FROM componentes WHERE empresa_id = :e"
        ),
        p,
    )
    total = await conn.scalar(text("SELECT count(*) FROM ordenes_trabajo WHERE empresa_id = :e"), p)
    assert total == 60_000, total


def test_el_umbral_y_la_histeresis_leen_la_configuracion_de_la_empresa() -> None:
    """Dos empresas con umbrales distintos: el mismo riesgo alerta en una y no en la otra."""

    async def escenario() -> tuple[int, int]:
        a, b = await sembrar("Empresa A", "Empresa B")
        creadas = []
        for e, umbral in ((a, Decimal("0.30")), (b, Decimal("0.60"))):
            await _como_dueno(
                e,
                [
                    (
                        "INSERT INTO configuracion_empresa (empresa_id, umbral_riesgo)"
                        " VALUES (:e, :u)",
                        {"e": e.empresa_id, "u": umbral},
                    ),
                    (
                        "INSERT INTO activo_componentes (empresa_id, activo_id, componente_id,"
                        " horas_instalacion_inicial) VALUES (:e, :a, :c, 0)",
                        {"e": e.empresa_id, "a": e.activo_id, "c": e.componente_id},
                    ),
                    (
                        "INSERT INTO riesgos (empresa_id, activo_id, componente_id, estado_calculo,"
                        " edad_horas, horizonte_horas, beta, eta, riesgo_base, multiplicador,"
                        " riesgo, confianza, fuente) VALUES (:e, :a, :c, 'ok', 900, 50, 2, 1000,"
                        " 0.45, 1.00, 0.45, 'media', 'empresa')",
                        {"e": e.empresa_id, "a": e.activo_id, "c": e.componente_id},
                    ),
                ],
            )
            try:
                async with sesion_de_empresa(e.empresa_id) as session:
                    creadas.append(await riesgo.crear_alertas(session, e.empresa_id))
            finally:
                await dispose_engine()
        return creadas[0], creadas[1]

    assert correr(escenario()) == (1, 0)
