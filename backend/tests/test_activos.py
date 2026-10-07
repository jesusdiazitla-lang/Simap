"""Equipos: alta con QR, aislamiento, baja lógica, resolución del código y etiqueta (RF-04..07).

Contra PostgreSQL real y por HTTP: la resolución del código depende de RLS, y una base falsa no lo
demostraría.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services import activos as servicio
from app.services import qr
from tests.conftest import requiere_base
from tests.planta import montar_planta

pytestmark = requiere_base


def test_rf04_el_administrador_da_de_alta_un_equipo_con_su_codigo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(
        "Compresor de tornillo", tipo="Compresor", ubicacion="Nave 2", criticidad="alta"
    )
    assert qr.normalizar(activo["codigo"]) == activo["codigo"]
    assert activo["codigo_corto"] == f"{activo['codigo'][:4]}-{activo['codigo'][4:]}"
    assert activo["url_qr"].endswith(f"/a/{activo['codigo']}")
    assert activo["estado"] == "activo"


def test_rf04_solo_el_administrador_da_de_alta_equipos(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    for quien in (planta.supervisor, planta.operario, planta.gerente):
        resp = planta.pedir(quien, "POST", "/activos", json={"nombre": "Prensa"})
        assert resp.status_code == 403, quien.correo


def test_el_cliente_no_puede_elegir_el_codigo_ni_la_empresa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    for campo, valor in (("qr_code", "AAAAAAAA"), ("empresa_id", str(uuid4()))):
        resp = planta.pedir(planta.admin, "POST", "/activos", json={"nombre": "X", campo: valor})
        assert resp.status_code == 422, campo


def test_el_horometro_inicial_queda_como_primera_lectura(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Generador", horometro_inicial=1200)
    assert activo["horometro_actual"] == 1200
    lecturas = planta.pedir(planta.supervisor, "GET", f"/activos/{activo['id']}/lecturas").json()
    assert [lectura["valor_horometro"] for lectura in lecturas["items"]] == [1200]


def test_rnf01_codigo_qr_de_otra_empresa_devuelve_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    activo = a.nuevo_activo()

    propio = a.pedir(a.operario, "GET", f"/activos/por-codigo/{activo['codigo']}")
    assert propio.status_code == 200

    ajeno = b.pedir(b.operario, "GET", f"/activos/por-codigo/{activo['codigo']}")
    inexistente = b.pedir(b.operario, "GET", "/activos/por-codigo/ZZZZZZZZ")
    mal_formado = b.pedir(b.operario, "GET", "/activos/por-codigo/hola")
    # El mismo 404 y el mismo cuerpo: nada distingue «es de otra empresa» de «no existe».
    assert ajeno.status_code == inexistente.status_code == mal_formado.status_code == 404
    assert ajeno.json() == inexistente.json() == mal_formado.json()

    por_id = b.pedir(b.admin, "GET", f"/activos/{activo['id']}")
    assert por_id.status_code == 404


def test_rnf01_listado_de_activos_aislado_por_http(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    a.nuevo_activo("Solo de A")
    nombres = [x["nombre"] for x in b.pedir(b.admin, "GET", "/activos").json()["items"]]
    assert "Solo de A" not in nombres


def test_el_codigo_se_resuelve_tecleado_a_mano(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    tecleado = f" {activo['codigo_corto'].lower()} "
    resp = planta.pedir(planta.operario, "GET", f"/activos/por-codigo/{tecleado}")
    assert resp.status_code == 200
    assert resp.json()["id"] == activo["id"]


def test_rf06_activo_dado_de_baja_sigue_resolviendo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    baja = planta.pedir(planta.admin, "POST", f"/activos/{activo['id']}/baja")
    assert baja.status_code == 200
    assert baja.json()["estado"] == "baja"

    resuelto = planta.pedir(planta.operario, "GET", f"/activos/por-codigo/{activo['codigo']}")
    assert resuelto.status_code == 200
    assert resuelto.json()["estado"] == "baja"

    # Pero ya no admite registros, y lo dice con un motivo que se entiende.
    lectura = planta.lectura(activo["id"], 10)
    assert lectura.status_code == 409
    assert "baja" in lectura.json()["detail"]


def test_regenerar_el_codigo_invalida_el_anterior(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    nuevo = planta.pedir(planta.admin, "POST", f"/activos/{activo['id']}/regenerar-codigo").json()
    assert nuevo["codigo"] != activo["codigo"]
    viejo = planta.pedir(planta.operario, "GET", f"/activos/por-codigo/{activo['codigo']}")
    assert viejo.status_code == 404


def test_rf05_un_choque_de_codigo_se_reintenta_sin_que_lo_note_nadie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    existente = planta.nuevo_activo("Primero")["codigo"]
    secuencia = iter([existente, existente, qr.generar_codigo()])
    monkeypatch.setattr(servicio.qr, "generar_codigo", lambda: next(secuencia))
    segundo = planta.nuevo_activo("Segundo")
    assert segundo["codigo"] != existente


def test_editar_no_permite_cambiar_el_codigo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    resp = planta.pedir(
        planta.admin, "PATCH", f"/activos/{activo['id']}", json={"qr_code": "AAAAAAAA"}
    )
    assert resp.status_code == 422
    ok = planta.pedir(
        planta.admin, "PATCH", f"/activos/{activo['id']}", json={"ubicacion": "Nave 3"}
    )
    assert ok.status_code == 200
    assert ok.json()["ubicacion"] == "Nave 3"


def test_listado_paginado_por_cursor_sin_repetir_ni_saltar(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    nombres = [f"Equipo {i:02d}" for i in range(7)]
    for nombre in nombres:
        planta.nuevo_activo(nombre)
    vistos: list[str] = []
    cursor: str | None = None
    while True:
        params = {"limite": 3, **({"cursor": cursor} if cursor else {})}
        pagina = planta.pedir(planta.gerente, "GET", "/activos", params=params).json()
        vistos += [x["nombre"] for x in pagina["items"]]
        cursor = pagina["next_cursor"]
        if cursor is None:
            break
    assert vistos == nombres


def test_cursor_manipulado_es_un_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(planta.admin, "GET", "/activos", params={"cursor": "no-es-un-cursor"})
    assert resp.status_code == 422


def test_la_etiqueta_es_un_svg_con_el_codigo_y_sin_cache_compartida(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Bomba <script>alert(1)</script>")
    resp = planta.pedir(planta.supervisor, "GET", f"/activos/{activo['id']}/etiqueta.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["content-security-policy"].startswith("default-src 'none'")
    assert activo["codigo_corto"] in resp.text
    assert "<script>" not in resp.text, "el nombre del equipo tiene que ir escapado"

    otra_vez = planta.pedir(
        planta.supervisor,
        "GET",
        f"/activos/{activo['id']}/etiqueta.svg",
        headers={"If-None-Match": resp.headers["etag"]},
    )
    assert otra_vez.status_code == 304

    assert (
        planta.pedir(planta.operario, "GET", f"/activos/{activo['id']}/etiqueta.svg").status_code
        == 403
    )


def test_la_resolucion_del_codigo_tiene_limite_por_usuario(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODIGO_MAX_PETICIONES_POR_MINUTO", "3")
    from app.core.config import get_settings

    get_settings.cache_clear()
    planta = montar_planta(client, monkeypatch, "Planta")
    for _ in range(3):
        planta.pedir(planta.operario, "GET", "/activos/por-codigo/ZZZZZZZZ")
    resp = planta.pedir(planta.operario, "GET", "/activos/por-codigo/ZZZZZZZZ")
    assert resp.status_code == 429
    # El límite es por persona: el supervisor de la misma planta sigue pudiendo.
    otro = planta.pedir(planta.supervisor, "GET", "/activos/por-codigo/ZZZZZZZZ")
    assert otro.status_code == 404
