"""Lo que la base impone sobre las órdenes, probado contra la base (06-fase3, secciones 7 y 11.3).

Cada prueba ataca como `app_user`, el rol del backend, sin pasar por el servicio: si la defensa de
la base se cayera, el servicio podría seguir tapándola y nadie se enteraría.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.orden_trabajo import OrdenContador
from app.services import ordenes
from tests.base_ordenes import (
    INSERT_ORDEN,
    correr,
    fijar,
    fila_orden,
    insertar_ordenes,
    motor_app,
    sembrar,
)
from tests.conftest import URL_DUENO, requiere_base

pytestmark = requiere_base


def test_rnf01_orden_con_referencias_de_otra_empresa_es_rechazada() -> None:
    """Llaves compuestas (7.4): equipo, componente y usuario de otra empresa dan 23503.

    PostgreSQL comprueba las llaves foráneas ignorando RLS. Con llaves simples, una orden de A
    apuntando a un equipo de B se aceptaría; es el hueco que cierran las compuestas.
    """

    async def escenario() -> list[str]:
        a, b = await sembrar("Empresa A", "Empresa B")
        motor = motor_app()
        rechazos: list[str] = []
        try:
            for cambio in (
                {"activo": b.activo_id},
                {"componente": b.componente_id},
                {"autor": b.usuario_id},
            ):
                async with motor.connect() as conn:
                    trans = await conn.begin()
                    await fijar(conn, a.empresa_id)
                    fila = {**fila_orden(a, numero=1, horas=100, estado="reportada"), **cambio}
                    with pytest.raises(IntegrityError) as error:
                        await conn.execute(INSERT_ORDEN, fila)
                    assert "mismo_tenant" in str(error.value.orig)
                    rechazos.append(next(iter(cambio)))
                    await trans.rollback()
        finally:
            await motor.dispose()
        return rechazos

    assert correr(escenario()) == ["activo", "componente", "autor"]


def test_rnf06_orden_cerrada_y_eventos_no_se_modifican_ni_se_borran() -> None:
    """Trigger (7.7) y permisos (7.10): una cerrada no cambia, el historial no se toca, nada se
    borra."""

    async def escenario() -> None:
        (a,) = await sembrar("Empresa A")
        fila = fila_orden(a, numero=1, horas=500)
        await insertar_ordenes(a, [fila])
        motor = motor_app()
        try:
            # La orden cerrada: el trigger la protege aunque el permiso de columna lo permita.
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                with pytest.raises(IntegrityError) as error:
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET descripcion = 'Otra cosa' WHERE id = :i"),
                        {"i": fila["id"]},
                    )
                assert "no se puede modificar" in str(error.value.orig)
                await trans.rollback()
            # Ni borrarla.
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                with pytest.raises(DBAPIError, match="permission denied"):
                    await conn.execute(
                        text("DELETE FROM ordenes_trabajo WHERE id = :i"), {"i": fila["id"]}
                    )
                await trans.rollback()
            # El historial: se puede añadir, no modificar ni borrar.
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                evento = uuid4()
                await conn.execute(
                    text(
                        "INSERT INTO orden_eventos (id, empresa_id, orden_id, tipo, usuario_id,"
                        " rol_al_momento) VALUES (:i, :e, :o, 'nota', :u, 'supervisor')"
                    ),
                    {"i": evento, "e": a.empresa_id, "o": fila["id"], "u": a.usuario_id},
                )
                for sentencia in (
                    "UPDATE orden_eventos SET nota = 'reescrita' WHERE id = :i",
                    "DELETE FROM orden_eventos WHERE id = :i",
                ):
                    punto = await conn.begin_nested()
                    with pytest.raises(DBAPIError, match="permission denied"):
                        await conn.execute(text(sentencia), {"i": evento})
                    await punto.rollback()
                await trans.rollback()
        finally:
            await motor.dispose()

    correr(escenario())


def test_rnf06_columnas_que_no_se_reescriben_nunca() -> None:
    """Número, empresa y quién reportó no tienen permiso de UPDATE para `app_user`, ni con la
    orden abierta (revisión 0007). Horas, dial y fecha de la falla tienen su propio cerrojo, el
    trigger `ot_datos_de_falla` (revisiones 0008 y 0009)."""

    async def escenario() -> None:
        (a,) = await sembrar("Empresa A")
        fila = fila_orden(a, numero=1, horas=500, estado="reportada")
        await insertar_ordenes(a, [fila])
        motor = motor_app()
        try:
            for columna, valor in (
                ("numero", 99),
                ("reportado_por", a.usuario_id),
            ):
                async with motor.connect() as conn:
                    trans = await conn.begin()
                    await fijar(conn, a.empresa_id)
                    with pytest.raises(DBAPIError, match="permission denied"):
                        await conn.execute(
                            text(f"UPDATE ordenes_trabajo SET {columna} = :v WHERE id = :i"),
                            {"v": valor, "i": fila["id"]},
                        )
                    await trans.rollback()
        finally:
            await motor.dispose()

    correr(escenario())


def test_horas_acumuladas_solo_cambian_al_confirmar_el_horometro() -> None:
    """Revisión 0008: el trigger `ot_horas_solo_al_confirmar` deja cambiar las horas solo en la
    misma escritura que quita la marca de revisión. Una cifra confirmada no se reescribe."""

    async def escenario() -> None:
        (a,) = await sembrar("Empresa A")
        normal = fila_orden(a, numero=1, horas=500, estado="reportada")
        await insertar_ordenes(a, [normal])
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                with pytest.raises(DBAPIError, match="solo cambian al confirmar"):
                    await conn.execute(
                        text(
                            "UPDATE ordenes_trabajo SET horas_acumuladas_en_falla = 1"
                            " WHERE id = :i"
                        ),
                        {"i": normal["id"]},
                    )
                await trans.rollback()
        finally:
            await motor.dispose()
        # La marcada, en otra empresa de prueba para no chocar con la única abierta por componente.
        (b,) = await sembrar("Empresa B")
        fila = fila_orden(b, numero=1, horas=500, estado="reportada", requiere_revision=True)
        await insertar_ordenes(b, [fila])
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, b.empresa_id)
                # Sin quitar la marca, tampoco.
                with pytest.raises(DBAPIError, match="solo cambian al confirmar"):
                    await conn.execute(
                        text(
                            "UPDATE ordenes_trabajo SET horas_acumuladas_en_falla = 1"
                            " WHERE id = :i"
                        ),
                        {"i": fila["id"]},
                    )
                await trans.rollback()
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, b.empresa_id)
                await conn.execute(
                    text(
                        "UPDATE ordenes_trabajo SET horas_acumuladas_en_falla = 1,"
                        " requiere_revision = false WHERE id = :i"
                    ),
                    {"i": fila["id"]},
                )
                await trans.rollback()
        finally:
            await motor.dispose()

    correr(escenario())


def test_estado_a_medias_es_rechazado() -> None:
    """CHECK de coherencia (7.3): cerrar sin quien autorizó es un 23514, lo intente quien lo
    intente."""

    async def escenario() -> None:
        (a,) = await sembrar("Empresa A")
        fila = fila_orden(a, numero=1, horas=500, estado="reparada")
        await insertar_ordenes(a, [fila])
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                with pytest.raises(IntegrityError, match="cierre_completo"):
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET estado = 'cerrada' WHERE id = :i"),
                        {"i": fila["id"]},
                    )
                await trans.rollback()
        finally:
            await motor.dispose()

    correr(escenario())


def test_la_correccion_no_se_filtra_a_la_siguiente_transaccion() -> None:
    """`set_config(..., true)` dura una transacción: la siguiente vuelve a encontrar el trigger."""

    async def escenario() -> None:
        (a,) = await sembrar("Empresa A")
        fila = fila_orden(a, numero=1, horas=500)
        await insertar_ordenes(a, [fila])
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                async with conn.begin():
                    await fijar(conn, a.empresa_id)
                    await conn.execute(text("SELECT set_config('app.correccion', 'on', true)"))
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET descripcion = 'Corregida' WHERE id = :i"),
                        {"i": fila["id"]},
                    )
                # Misma conexión, transacción siguiente: el parámetro ya no está.
                trans = await conn.begin()
                await fijar(conn, a.empresa_id)
                with pytest.raises(IntegrityError, match="no se puede modificar"):
                    await conn.execute(
                        text("UPDATE ordenes_trabajo SET descripcion = 'Otra' WHERE id = :i"),
                        {"i": fila["id"]},
                    )
                await trans.rollback()
        finally:
            await motor.dispose()

    correr(escenario())


def test_rf12_numeros_correlativos_sin_huecos_tras_rollback() -> None:
    """El número vuelve al contador si la transacción se revierte (6.3): no quedan huecos."""

    async def escenario() -> list[int]:
        (a,) = await sembrar("Empresa A")
        motor = motor_app()
        numeros: list[int] = []
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            sesiones = async_sessionmaker(motor, expire_on_commit=False)
            for confirmar in (True, False, True):
                async with sesiones() as session:
                    async with session.begin() as trans:
                        await session.execute(
                            text("SELECT set_config('app.empresa_id', :v, true)"),
                            {"v": str(a.empresa_id)},
                        )
                        numeros.append(await ordenes._siguiente_numero(session, a.empresa_id))
                        if not confirmar:
                            await trans.rollback()
            async with sesiones() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('app.empresa_id', :v, true)"),
                    {"v": str(a.empresa_id)},
                )
                ultimo = await session.get(OrdenContador, a.empresa_id)
                assert ultimo is not None and ultimo.ultimo == 2
        finally:
            await motor.dispose()
        return numeros

    # El 2 se pidió y se revirtió: la siguiente transacción vuelve a recibir el 2.
    assert correr(escenario()) == [1, 2, 2]


def test_vista_de_vidas_con_la_secuencia_de_la_fase_3() -> None:
    """La secuencia de la sección 6.6 de la fase 3, leída con `v_vidas` (F4, decisión 10).

    Una vida termina en un reemplazo; un ajuste o una reparación quedan dentro de la misma vida. Las
    canceladas y las que tienen el horómetro en revisión no cuentan. La pieza instalada hoy es la
    vida abierta.
    """

    async def escenario() -> list[tuple[int, bool, int, float]]:
        (a,) = await sembrar("Empresa A")
        secuencia = [
            fila_orden(a, numero=1, horas=1000, tipo="reemplazo"),
            fila_orden(a, numero=2, horas=1500, tipo="ajuste"),
            fila_orden(a, numero=3, horas=2200, tipo="reemplazo"),
            fila_orden(a, numero=4, horas=2500, tipo="reemplazo", estado="cancelada"),
            fila_orden(a, numero=5, horas=2600, tipo="ajuste", requiere_revision=True),
            fila_orden(a, numero=6, horas=2900, tipo="reparacion"),
        ]
        await insertar_ordenes(a, secuencia)
        motor_dueno = create_async_engine(URL_DUENO)
        try:
            async with motor_dueno.begin() as conn:
                await fijar(conn, a.empresa_id)
                await conn.execute(
                    text(
                        "INSERT INTO activo_componentes"
                        " (empresa_id, activo_id, componente_id, horas_instalacion_inicial)"
                        " VALUES (:e, :a, :c, 0)"
                    ),
                    {"e": a.empresa_id, "a": a.activo_id, "c": a.componente_id},
                )
        finally:
            await motor_dueno.dispose()
        motor = motor_app()
        try:
            async with motor.connect() as conn, conn.begin():
                await fijar(conn, a.empresa_id)
                filas = await conn.execute(
                    text(
                        "SELECT vida, abierta, n_eventos, exposicion FROM v_vidas"
                        " ORDER BY abierta, vida"
                    )
                )
                return [(int(v), bool(ab), int(n), float(x)) for v, ab, n, x in filas.all()]
        finally:
            await motor.dispose()

    assert correr(escenario()) == [
        (0, False, 1, 1000.0),  # reemplazo a las 1000 h
        (1, False, 2, 1200.0),  # ajuste a las 1500 y reemplazo a las 2200
        (2, True, 1, 700.0),  # abierta: la reparación de las 2900 h, sin renovar la pieza
    ]
