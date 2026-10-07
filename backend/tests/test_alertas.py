"""Alertas de campo: deduplicación, visibilidad por rol y revisión (RF-09).

Cada prueba lleva el nombre que le da `docs/contexto/05-fase2-activos-y-campo.md`, sección 10.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import hace, montar_planta

pytestmark = requiere_base


def test_rf09_el_operario_reporta_una_alerta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    resp = planta.alerta(activo["id"], "vibracion", nota="Golpeteo al arrancar")
    assert resp.status_code == 201, resp.text
    alerta = resp.json()["alerta"]
    assert alerta["estado"] == "pendiente"
    assert alerta["sintoma"] == "vibracion"
    assert alerta["nota"] == "Golpeteo al arrancar"


def test_rf09_alerta_duplicada_en_ventana_no_se_crea(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un botón atascado no infla el riesgo del equipo en la fase 4 (sección 5.2)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    primera = planta.alerta(activo["id"], "ruido", capturado_en=hace(minutes=4))
    segunda = planta.alerta(activo["id"], "ruido")
    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["estado"] == "duplicado"
    assert segunda.json()["alerta"]["id"] == primera.json()["alerta"]["id"]


def test_rf09_otro_sintoma_u_otra_persona_no_es_duplicado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dos testigos independientes son justo la señal que el modelo quiere ver."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    assert planta.alerta(activo["id"], "ruido").status_code == 201
    assert planta.alerta(activo["id"], "calor").status_code == 201
    assert planta.alerta(activo["id"], "ruido", quien=planta.supervisor).status_code == 201


def test_rf09_fuera_de_la_ventana_si_es_una_alerta_nueva(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    assert planta.alerta(activo["id"], "fuga", capturado_en=hace(minutes=30)).status_code == 201
    assert planta.alerta(activo["id"], "fuga").status_code == 201


def test_rf09_sintoma_fuera_de_la_lista_y_nota_larga_se_rechazan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    assert planta.alerta(activo["id"], "humo").status_code == 422
    assert planta.alerta(activo["id"], "ruido", nota="x" * 501).status_code == 422


def test_rf09_operario_no_ve_alertas_ajenas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    propia = planta.alerta(activo["id"], "ruido").json()["alerta"]["id"]
    ajena = planta.alerta(activo["id"], "calor", quien=planta.supervisor).json()["alerta"]["id"]

    del_operario = planta.pedir(planta.operario, "GET", "/alertas").json()["items"]
    assert {a["id"] for a in del_operario} == {propia}

    del_supervisor = planta.pedir(planta.supervisor, "GET", "/alertas").json()["items"]
    assert {propia, ajena} <= {a["id"] for a in del_supervisor}


def test_rf09_solo_supervisor_o_administrador_revisan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    alerta_id = planta.alerta(activo["id"]).json()["alerta"]["id"]

    for quien in (planta.operario, planta.gerente):
        resp = planta.pedir(quien, "PATCH", f"/alertas/{alerta_id}", json={"estado": "revisada"})
        assert resp.status_code == 403

    resp = planta.pedir(
        planta.supervisor, "PATCH", f"/alertas/{alerta_id}", json={"estado": "descartada"}
    )
    assert resp.status_code == 200
    revisada = resp.json()
    assert revisada["estado"] == "descartada"
    assert revisada["revisada_por"] == str(planta.supervisor.id)
    assert revisada["revisada_en"] is not None


def test_una_alerta_ya_atendida_no_se_vuelve_a_revisar(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    alerta_id = planta.alerta(activo["id"]).json()["alerta"]["id"]
    planta.pedir(planta.supervisor, "PATCH", f"/alertas/{alerta_id}", json={"estado": "revisada"})
    otra = planta.pedir(
        planta.admin, "PATCH", f"/alertas/{alerta_id}", json={"estado": "descartada"}
    )
    assert otra.status_code == 409


def test_convertida_en_orden_no_se_alcanza_en_esta_fase(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    alerta_id = planta.alerta(activo["id"]).json()["alerta"]["id"]
    resp = planta.pedir(
        planta.supervisor, "PATCH", f"/alertas/{alerta_id}", json={"estado": "convertida_en_orden"}
    )
    assert resp.status_code == 422


def test_la_bandeja_filtra_por_estado(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    a = planta.alerta(activo["id"], "ruido").json()["alerta"]["id"]
    b = planta.alerta(activo["id"], "olor").json()["alerta"]["id"]
    planta.pedir(planta.supervisor, "PATCH", f"/alertas/{a}", json={"estado": "revisada"})
    pendientes = planta.pedir(
        planta.supervisor, "GET", "/alertas", params={"estado": "pendiente"}
    ).json()["items"]
    assert [x["id"] for x in pendientes] == [b]


def test_el_tecnico_de_taller_no_ve_la_bandeja(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    from uuid import uuid4

    from tests.planta import entrar

    correo = f"tecnico-{uuid4().hex}@example.com"
    alta = planta.pedir(
        planta.admin,
        "POST",
        "/usuarios",
        json={"nombre": "Técnico", "correo": correo, "rol": "tecnico_taller"},
    )
    tecnico = entrar(client, correo, alta.json()["password_temporal"])
    assert planta.pedir(tecnico, "GET", "/alertas").status_code == 403


def test_la_bandeja_trae_el_nombre_y_el_codigo_del_equipo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Compresor de la nave 2")
    planta.alerta(activo["id"])
    fila = planta.pedir(planta.supervisor, "GET", "/alertas").json()["items"][0]
    assert fila["activo_nombre"] == "Compresor de la nave 2"
    assert fila["activo_codigo"] == activo["codigo"]
