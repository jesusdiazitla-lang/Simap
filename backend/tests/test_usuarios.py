"""Personal de la empresa gestionado por su administrador (RF-03)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import PASSWORD_ADMIN, entrar, montar_planta

pytestmark = requiere_base


def test_rf03_el_administrador_da_de_alta_personal_con_su_rol(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    lista = planta.pedir(planta.admin, "GET", "/usuarios").json()
    roles = sorted(u["rol"] for u in lista)
    assert roles == ["administrador", "gerente", "operario", "supervisor"]
    assert all("password" not in str(u) and "hash" not in str(u) for u in lista)


def test_rf03_la_clave_la_genera_el_servidor(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(
        planta.admin,
        "POST",
        "/usuarios",
        json={
            "nombre": "Pedro",
            "correo": f"{uuid4().hex}@example.com",
            "rol": "operario",
            "password": "elegida-por-el-admin",
        },
    )
    assert resp.status_code == 422


def test_rf03_solo_el_administrador_gestiona_personal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    for quien in (planta.supervisor, planta.gerente, planta.operario):
        assert planta.pedir(quien, "GET", "/usuarios").status_code == 403


def test_rnf01_un_administrador_no_ve_ni_toca_personal_de_otra_empresa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    correos_b = {u["correo"] for u in b.pedir(b.admin, "GET", "/usuarios").json()}
    assert a.operario.correo not in correos_b
    resp = b.pedir(b.admin, "PATCH", f"/usuarios/{a.operario.id}", json={"activo": False})
    assert resp.status_code == 404


def test_dar_de_baja_impide_entrar_y_corta_la_renovacion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    clave = planta.pedir(
        planta.admin, "POST", f"/usuarios/{planta.operario.id}/restablecer-clave"
    ).json()["password_temporal"]

    # El operario tiene una sesión abierta con refresh token.
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"correo": planta.operario.correo, "password": clave})
    refresco = dict(client.cookies)

    baja = planta.pedir(
        planta.admin, "PATCH", f"/usuarios/{planta.operario.id}", json={"activo": False}
    )
    assert baja.status_code == 200
    assert baja.json()["activo"] is False

    client.cookies.clear()
    entrada = client.post(
        "/api/v1/auth/login", json={"correo": planta.operario.correo, "password": clave}
    )
    assert entrada.status_code == 403
    assert "baja" in entrada.json()["detail"]

    client.cookies.clear()
    for nombre, valor in refresco.items():
        client.cookies.set(nombre, valor)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_nadie_se_quita_a_si_mismo_el_rol_de_administrador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    for cambio in ({"rol": "operario"}, {"activo": False}):
        resp = planta.pedir(planta.admin, "PATCH", f"/usuarios/{planta.admin.id}", json=cambio)
        assert resp.status_code == 409
        assert "ti mismo" in resp.json()["detail"]


def test_la_empresa_nunca_se_queda_sin_administrador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    # Un segundo administrador intenta degradar al primero, que es el único además de él...
    correo = f"admin2-{uuid4().hex}@example.com"
    alta = planta.pedir(
        planta.admin,
        "POST",
        "/usuarios",
        json={"nombre": "Segunda", "correo": correo, "rol": "administrador"},
    )
    segunda = entrar(client, correo, alta.json()["password_temporal"])
    # ...con dos administradores sí puede.
    ok = planta.pedir(segunda, "PATCH", f"/usuarios/{planta.admin.id}", json={"rol": "gerente"})
    assert ok.status_code == 200
    # Ahora ella es la única. El primero ya es gerente, pero su token de acceso todavía dice
    # «administrador» durante unos minutos: es la única vía real de intentar dejar a la empresa sin
    # nadie, y la regla del servicio la cierra aunque el token pase el control de rol.
    huerfana = planta.pedir(
        planta.admin, "PATCH", f"/usuarios/{segunda.id}", json={"activo": False}
    )
    assert huerfana.status_code == 409
    assert "único administrador" in huerfana.json()["detail"]


def test_correo_repetido_es_un_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(
        planta.admin,
        "POST",
        "/usuarios",
        json={"nombre": "Copia", "correo": planta.operario.correo, "rol": "operario"},
    )
    assert resp.status_code == 409


def test_el_administrador_inicial_sigue_entrando(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    assert entrar(client, planta.admin.correo, PASSWORD_ADMIN).id == planta.admin.id
