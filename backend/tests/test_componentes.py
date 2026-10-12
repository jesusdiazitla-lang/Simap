"""Catálogo de componentes: plantilla inicial, nombre único por empresa, sin borrado."""

import pytest
from fastapi.testclient import TestClient

from app.models.componente import PLANTILLA_INICIAL
from tests.conftest import requiere_base
from tests.planta import montar_planta

pytestmark = requiere_base


def test_toda_empresa_nace_con_el_catalogo_inicial(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    nombres = {c["nombre"] for c in planta.pedir(planta.operario, "GET", "/componentes").json()}
    assert nombres == {nombre for nombre, _ in PLANTILLA_INICIAL}


def test_el_administrador_crea_renombra_y_desactiva(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    nuevo = planta.pedir(planta.admin, "POST", "/componentes", json={"nombre": "Embrague"})
    assert nuevo.status_code == 201
    cid = nuevo.json()["id"]

    renombrado = planta.pedir(
        planta.admin, "PATCH", f"/componentes/{cid}", json={"nombre": "Embrague hidráulico"}
    )
    assert renombrado.json()["nombre"] == "Embrague hidráulico"

    planta.pedir(planta.admin, "PATCH", f"/componentes/{cid}", json={"activo": False})
    visibles = {c["id"] for c in planta.pedir(planta.operario, "GET", "/componentes").json()}
    assert cid not in visibles
    todos = planta.pedir(
        planta.admin, "GET", "/componentes", params={"incluir_inactivos": True}
    ).json()
    assert cid in {c["id"] for c in todos}


def test_solo_el_administrador_ve_los_inactivos(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    cid = planta.pedir(planta.admin, "POST", "/componentes", json={"nombre": "Viejo"}).json()["id"]
    planta.pedir(planta.admin, "PATCH", f"/componentes/{cid}", json={"activo": False})
    resp = planta.pedir(planta.operario, "GET", "/componentes", params={"incluir_inactivos": True})
    assert cid not in {c["id"] for c in resp.json()}


def test_nombre_repetido_es_un_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(planta.admin, "POST", "/componentes", json={"nombre": "Motor"})
    assert resp.status_code == 409


def test_el_mismo_nombre_en_otra_empresa_si_vale(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    assert a.pedir(a.admin, "POST", "/componentes", json={"nombre": "Molino"}).status_code == 201
    assert b.pedir(b.admin, "POST", "/componentes", json={"nombre": "Molino"}).status_code == 201


def test_no_existe_ruta_para_borrar_componentes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    cid = planta.pedir(planta.operario, "GET", "/componentes").json()[0]["id"]
    assert planta.pedir(planta.admin, "DELETE", f"/componentes/{cid}").status_code == 405


def test_solo_el_administrador_edita_el_catalogo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(planta.supervisor, "POST", "/componentes", json={"nombre": "Otro"})
    assert resp.status_code == 403


def test_cargar_la_plantilla_solo_anade_lo_que_falta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Para empresas anteriores a la plantilla, o que perdieron alguno de su lista."""
    planta = montar_planta(client, monkeypatch, "Planta")
    assert planta.pedir(planta.admin, "POST", "/componentes/plantilla").json() == []

    motor = next(
        c
        for c in planta.pedir(planta.admin, "GET", "/componentes").json()
        if c["nombre"] == "Motor"
    )
    planta.pedir(
        planta.admin, "PATCH", f"/componentes/{motor['id']}", json={"nombre": "Motor diésel"}
    )
    anadidos = planta.pedir(planta.admin, "POST", "/componentes/plantilla").json()
    assert [c["nombre"] for c in anadidos] == ["Motor"]
    assert planta.pedir(planta.supervisor, "POST", "/componentes/plantilla").status_code == 403


def test_editar_un_componente_con_nombre_nulo_es_un_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    creado = planta.pedir(planta.admin, "POST", "/componentes", json={"nombre": "Rodamiento"})
    assert creado.status_code == 201, creado.text
    for campo in ("nombre", "activo"):
        resp = planta.pedir(
            planta.admin, "PATCH", f"/componentes/{creado.json()['id']}", json={campo: None}
        )
        assert resp.status_code == 422, (campo, resp.text)
