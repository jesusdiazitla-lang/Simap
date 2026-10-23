"""Inventario de repuestos por HTTP (RF-23 a RF-26; 07-fase4, secciones 6.5, 6.6 y 15.2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import Planta, montar_planta

pytestmark = requiere_base


def repuesto(
    planta: Planta,
    *,
    stock: int = 10,
    minimo: int = 2,
    costo: str = "125.50",
    codigo: str | None = None,
) -> dict[str, Any]:
    resp = planta.pedir(
        planta.admin,
        "POST",
        "/repuestos",
        json={
            "nombre": "Rodamiento 6205",
            "codigo": codigo or f"RP-{uuid4().hex[:6]}",
            "stock_inicial": stock,
            "stock_minimo": minimo,
            "costo_unitario": costo,
        },
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def libro(planta: Planta, repuesto_id: str) -> list[dict[str, Any]]:
    resp = planta.pedir(planta.admin, "GET", f"/repuestos/{repuesto_id}/movimientos")
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def stock(planta: Planta, repuesto_id: str) -> int:
    resp = planta.pedir(planta.admin, "GET", f"/repuestos/{repuesto_id}")
    assert resp.status_code == 200, resp.text
    return int(resp.json()["stock_actual"])


def reorden(planta: Planta, estado: str = "vigentes") -> list[dict[str, Any]]:
    resp = planta.pedir(
        planta.supervisor, "GET", "/alertas-sistema", params={"tipo": "reorden", "estado": estado}
    )
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def orden_reparada(planta: Planta, lineas: dict[str, int]) -> str:
    """Una orden en Reparada con las líneas de repuestos dadas, lista para cerrar."""
    activo = planta.nuevo_activo(f"Equipo {uuid4().hex[:4]}", horometro_inicial=100)
    orden = planta.orden(activo["id"], componente_id=planta.componente("Motor"), horometro=100)
    assert planta.mover(planta.tecnico, orden["id"], "en-taller").status_code == 200
    for repuesto_id, cantidad in lineas.items():
        resp = planta.pedir(
            planta.tecnico,
            "PUT",
            f"/ordenes/{orden['id']}/repuestos/{repuesto_id}",
            json={"cantidad": cantidad},
        )
        assert resp.status_code == 200, resp.text
    assert planta.reparar(orden["id"]).status_code == 200
    return str(orden["id"])


def test_rf23_repuestos_roles_y_codigo_unico(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alta del administrador, código único por empresa, y el stock inicial entra al libro."""
    planta = montar_planta(client, monkeypatch, "Planta")
    r = repuesto(planta, stock=10, codigo="RP-014")
    assert r["stock_actual"] == 10
    assert r["bajo_minimo"] is False
    asientos = libro(planta, r["id"])
    assert [(m["tipo"], m["delta"], m["stock_resultante"]) for m in asientos] == [
        ("inicial", 10, 10)
    ]
    assert Decimal(asientos[0]["costo_unitario"]) == Decimal("125.50")

    repetido = planta.pedir(
        planta.admin, "POST", "/repuestos", json={"nombre": "Otro", "codigo": "RP-014"}
    )
    assert repetido.status_code == 409
    assert repetido.json()["detail"]["codigo"] == "codigo_repuesto_duplicado"
    # Otra empresa puede usar el mismo código.
    otra = montar_planta(client, monkeypatch, "Otra")
    repuesto(otra, codigo="RP-014")

    sin_stock = planta.pedir(
        planta.admin, "POST", "/repuestos", json={"nombre": "Filtro", "codigo": "F-1"}
    )
    assert sin_stock.status_code == 201
    assert libro(planta, sin_stock.json()["id"]) == []

    # El stock no se puede editar ni colar en un alta con otro nombre.
    editar = planta.pedir(planta.admin, "PATCH", f"/repuestos/{r['id']}", json={"stock_actual": 99})
    assert editar.status_code == 422
    assert (
        planta.pedir(
            planta.supervisor, "POST", "/repuestos", json={"nombre": "X", "codigo": "X"}
        ).status_code
        == 403
    )

    # El técnico consulta existencias pero no costos ni el libro.
    tecnico = planta.pedir(planta.tecnico, "GET", "/repuestos")
    assert tecnico.status_code == 200
    assert "costo_unitario" not in tecnico.json()["items"][0]
    assert (
        planta.pedir(planta.tecnico, "GET", f"/repuestos/{r['id']}/movimientos").status_code == 403
    )


def test_rf24_lineas_solo_en_orden_abierta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    r = repuesto(planta, stock=10)
    orden = orden_reparada(planta, {r["id"]: 2})
    corregir = planta.pedir(
        planta.tecnico, "PUT", f"/ordenes/{orden}/repuestos/{r['id']}", json={"cantidad": 3}
    )
    assert corregir.status_code == 200
    assert [(linea["cantidad"], linea["costo_unitario"]) for linea in corregir.json()] == [
        (3, None)
    ]
    assert planta.mover(planta.supervisor, orden, "cerrar").status_code == 200
    cerrada = planta.pedir(
        planta.tecnico, "PUT", f"/ordenes/{orden}/repuestos/{r['id']}", json={"cantidad": 1}
    )
    assert cerrada.status_code == 409
    assert cerrada.json()["detail"]["codigo"] == "estado_cambiado"
    quitar = planta.pedir(planta.supervisor, "DELETE", f"/ordenes/{orden}/repuestos/{r['id']}")
    assert quitar.status_code == 409
    assert (
        planta.pedir(
            planta.gerente, "PUT", f"/ordenes/{orden}/repuestos/{r['id']}", json={"cantidad": 1}
        ).status_code
        == 403
    )


def test_rf25_cierre_descuenta_stock_y_asienta_libro(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El descuento ocurre al cerrar, no al marcar Reparada, con el costo del momento."""
    planta = montar_planta(client, monkeypatch, "Planta")
    r = repuesto(planta, stock=10, costo="80.00")
    orden = orden_reparada(planta, {r["id"]: 3})
    assert stock(planta, r["id"]) == 10  # Reparada todavía no descuenta (decisión 1).
    assert (
        planta.pedir(
            planta.admin, "PATCH", f"/repuestos/{r['id']}", json={"costo_unitario": "95.00"}
        ).status_code
        == 200
    )
    assert planta.mover(planta.supervisor, orden, "cerrar").status_code == 200
    assert stock(planta, r["id"]) == 7
    consumo = libro(planta, r["id"])[0]
    assert (consumo["tipo"], consumo["delta"], consumo["stock_resultante"]) == ("consumo", -3, 7)
    assert consumo["orden_id"] == orden
    assert Decimal(consumo["costo_unitario"]) == Decimal("95.00")


def test_rf25_stock_insuficiente_revierte_el_cierre_con_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    alcanza = repuesto(planta, stock=10, codigo="RP-001")
    falta = repuesto(planta, stock=1, codigo="RP-014")
    orden = orden_reparada(planta, {alcanza["id"]: 2, falta["id"]: 3})
    resp = planta.mover(planta.supervisor, orden, "cerrar")
    assert resp.status_code == 409
    detalle = resp.json()["detail"]
    assert detalle["codigo"] == "stock_insuficiente"
    assert detalle["faltantes"] == [
        {"codigo": "RP-014", "nombre": "Rodamiento 6205", "disponible": 1, "requerido": 3}
    ]
    # Nada se descontó y la orden sigue Reparada.
    assert stock(planta, alcanza["id"]) == 10
    assert stock(planta, falta["id"]) == 1
    estado = planta.pedir(planta.supervisor, "GET", f"/ordenes/{orden}").json()["estado"]
    assert estado == "reparada"
    # Con un ingreso, el cierre pasa.
    ingreso = planta.pedir(
        planta.supervisor, "POST", f"/repuestos/{falta['id']}/ingresos", json={"cantidad": 5}
    )
    assert ingreso.status_code == 200
    assert planta.mover(planta.supervisor, orden, "cerrar").status_code == 200
    assert stock(planta, falta["id"]) == 3


def test_rf26_reorden_al_bajar_del_minimo_y_se_resuelve_con_ingreso(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Estrictamente menor (decisión 12): con el stock igual al mínimo todavía no se alerta."""
    planta = montar_planta(client, monkeypatch, "Planta")
    r = repuesto(planta, stock=5, minimo=3)
    orden = orden_reparada(planta, {r["id"]: 2})
    assert planta.mover(planta.supervisor, orden, "cerrar").status_code == 200
    assert stock(planta, r["id"]) == 3
    assert reorden(planta) == []

    otra = orden_reparada(planta, {r["id"]: 1})
    assert planta.mover(planta.supervisor, otra, "cerrar").status_code == 200
    vigentes = reorden(planta)
    assert len(vigentes) == 1
    assert (vigentes[0]["stock_al_alertar"], vigentes[0]["stock_minimo_al_alertar"]) == (2, 3)
    assert vigentes[0]["repuesto_codigo"] == r["codigo"]
    # Otra baja no crea una segunda alerta.
    tercera = orden_reparada(planta, {r["id"]: 1})
    assert planta.mover(planta.supervisor, tercera, "cerrar").status_code == 200
    assert len(reorden(planta)) == 1

    assert (
        planta.pedir(
            planta.supervisor, "POST", f"/repuestos/{r['id']}/ingresos", json={"cantidad": 2}
        ).status_code
        == 200
    )
    assert reorden(planta) == []
    assert [a["estado"] for a in reorden(planta, "historial")] == ["resuelta"]


def test_inventario_ajuste_solo_administrador_con_nota(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    r = repuesto(planta, stock=10, minimo=0)
    ruta = f"/repuestos/{r['id']}/ajuste"
    assert (
        planta.pedir(
            planta.supervisor, "POST", ruta, json={"conteo": 8, "nota": "Conteo."}
        ).status_code
        == 403
    )
    assert planta.pedir(planta.admin, "POST", ruta, json={"conteo": 8}).status_code == 422
    ajuste = planta.pedir(
        planta.admin, "POST", ruta, json={"conteo": 8, "nota": "Conteo de octubre."}
    )
    assert ajuste.status_code == 200
    assert ajuste.json()["stock_actual"] == 8
    asiento = libro(planta, r["id"])[0]
    assert (asiento["tipo"], asiento["delta"], asiento["nota"]) == (
        "ajuste",
        -2,
        "Conteo de octubre.",
    )
    # Si el conteo coincide, no asienta nada.
    igual = planta.pedir(planta.admin, "POST", ruta, json={"conteo": 8, "nota": "Igual."})
    assert igual.status_code == 200
    assert len(libro(planta, r["id"])) == 2


def test_rf26_conciliacion_devuelve_cero_filas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tras una secuencia mixta de movimientos, el stock de cada repuesto es la suma de su libro."""
    planta = montar_planta(client, monkeypatch, "Planta")
    a = repuesto(planta, stock=10, codigo="A-1")
    b = repuesto(planta, stock=0, codigo="B-1")
    planta.pedir(planta.supervisor, "POST", f"/repuestos/{b['id']}/ingresos", json={"cantidad": 4})
    orden = orden_reparada(planta, {a["id"]: 3, b["id"]: 1})
    assert planta.mover(planta.supervisor, orden, "cerrar").status_code == 200
    planta.pedir(
        planta.admin,
        "POST",
        f"/repuestos/{a['id']}/ajuste",
        json={"conteo": 9, "nota": "Apareció uno."},
    )
    resp = planta.pedir(planta.admin, "GET", "/inventario/conciliacion")
    assert resp.status_code == 200
    assert resp.json() == []
    assert stock(planta, a["id"]) == 9
    assert stock(planta, b["id"]) == 3


def test_rnf01_repuestos_de_otra_empresa_no_existen(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "A")
    b = montar_planta(client, monkeypatch, "B")
    r = repuesto(a)
    assert b.pedir(b.admin, "GET", f"/repuestos/{r['id']}").status_code == 404
    assert (
        b.pedir(
            b.supervisor, "POST", f"/repuestos/{r['id']}/ingresos", json={"cantidad": 1}
        ).status_code
        == 404
    )
    assert b.pedir(b.admin, "GET", "/repuestos").json()["items"] == []
    orden_b = orden_reparada(b, {})
    linea = b.pedir(
        b.tecnico, "PUT", f"/ordenes/{orden_b}/repuestos/{r['id']}", json={"cantidad": 1}
    )
    assert linea.status_code == 404
