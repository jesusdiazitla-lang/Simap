"""Ensamblador de paneles (08-fase5, 8.3 y 8.5; RF-27, RNF-02), sin base de datos.

Un widget que falla o tarda no tumba el panel; el texto del error no sale en la respuesta pero sí
queda en el registro; la concurrencia se acota; la cancelación se propaga; la clave de caché no se
puede construir sin la empresa.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.paneles.ensamblador import (
    Contexto,
    Widget,
    armar_panel,
    clave_cache,
    correr_widget,
    widgets_del_rol,
)
from app.services.paneles.widgets import WIDGETS

AHORA = datetime(2026, 10, 28, tzinfo=UTC)


def ctx(rol: str = "gerente") -> Contexto:
    return Contexto(uuid4(), uuid4(), rol, AHORA, AHORA, AHORA)


def w(nombre: str, consulta, *roles: str, timeout: float = 1.0) -> Widget:  # type: ignore[no-untyped-def]
    return Widget(nombre, consulta, frozenset(roles or ("gerente",)), timeout)


async def _bien(_: Contexto) -> dict[str, int]:
    return {"n": 1}


async def _falla(_: Contexto) -> None:
    raise RuntimeError("permission denied for view v_riesgo_activo (secreto-interno)")


async def _lento(_: Contexto) -> None:
    await asyncio.sleep(5)


def test_rnf02_un_widget_que_falla_no_tumba_a_los_demas(caplog: pytest.LogCaptureFixture) -> None:
    widgets = [w("a", _bien), w("riesgo", _falla), w("c", _bien)]
    # El registro de SIMAP no propaga a la raíz (`app.core.registro`): se escucha directamente.
    registro = logging.getLogger("simap.paneles")
    registro.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="simap.paneles"):
            panel = asyncio.run(armar_panel(ctx(), widgets))
    finally:
        registro.removeHandler(caplog.handler)
    assert panel["degradados"] == ["riesgo"]
    assert panel["widgets"]["a"] == {
        "estado": "ok",
        "datos": {"n": 1},
        "ms": panel["widgets"]["a"]["ms"],
    }
    riesgo = panel["widgets"]["riesgo"]
    assert (riesgo["estado"], riesgo["motivo"], riesgo["datos"]) == ("degradado", "error", None)
    # El detalle va al registro del servidor, nunca a la respuesta.
    assert "secreto-interno" not in str(panel)
    assert "secreto-interno" in caplog.text


def test_rnf02_un_widget_lento_se_marca_degradado_por_tiempo() -> None:
    panel = asyncio.run(armar_panel(ctx(), [w("lento", _lento, timeout=0.05), w("b", _bien)]))
    assert panel["widgets"]["lento"]["motivo"] == "tiempo_agotado"
    assert panel["widgets"]["b"]["estado"] == "ok"


def test_la_concurrencia_se_acota() -> None:
    activos = 0
    maximo = 0

    async def contar(_: Contexto) -> None:
        nonlocal activos, maximo
        activos += 1
        maximo = max(maximo, activos)
        await asyncio.sleep(0.02)
        activos -= 1

    asyncio.run(armar_panel(ctx(), [w(f"w{i}", contar) for i in range(9)], max_paralelos=3))
    assert maximo == 3


def test_la_cancelacion_se_propaga() -> None:
    """`CancelledError` no se captura: si el usuario cierra la pestaña, se libera la conexión."""

    async def principal() -> None:
        tarea = asyncio.create_task(correr_widget(w("lento", _lento), ctx()))
        await asyncio.sleep(0.01)
        tarea.cancel()
        await tarea

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(principal())


def test_clave_de_cache_sin_empresa_se_rechaza() -> None:
    with pytest.raises(ValueError):
        clave_cache(None, "indicadores", planta="Nave 1")
    with pytest.raises(ValueError):
        clave_cache("", "indicadores")
    a = clave_cache(uuid4(), "indicadores", planta="Nave 1")
    b = clave_cache(uuid4(), "indicadores", planta="Nave 1")
    assert a != b and a.startswith("simap:v1:")


@pytest.mark.parametrize(
    ("rol", "esperados"),
    [
        ("operario", {"mis_lecturas", "mis_alertas"}),
        ("tecnico_taller", {"cola_taller", "mis_trabajos"}),
        ("supervisor", {"contadores", "alertas_campo", "alertas_sistema", "ordenes_abiertas"}),
        ("gerente", {"indicadores", "repuestos_costo", "riesgo_top", "riesgo_cobertura"}),
    ],
)
def test_rf27_cada_rol_tiene_sus_widgets(rol: str, esperados: set[str]) -> None:
    assert {x.nombre for x in widgets_del_rol(rol, WIDGETS)} == esperados


def test_rf27_el_administrador_ve_supervisor_gerente_y_salud() -> None:
    nombres = {x.nombre for x in widgets_del_rol("administrador", WIDGETS)}
    assert len(nombres) == 9 and "salud" in nombres
    assert not widgets_del_rol("rol_inventado", WIDGETS)


def test_los_indicadores_tienen_3_s_y_el_resto_2_s() -> None:
    limites = {x.nombre: x.timeout_s for x in WIDGETS}
    assert limites.pop("indicadores") == 3.0
    assert set(limites.values()) == {2.0}
