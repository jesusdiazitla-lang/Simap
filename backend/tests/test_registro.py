"""Registro estructurado y métricas (05-fase2-activos-y-campo.md, sección 9.7).

Se comprueba lo que se escribe y, sobre todo, lo que **no** se escribe: ni contraseñas, ni tokens,
ni el texto de las notas, ni el código de un equipo en la ruta.
"""

import json
import logging
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core import registro
from tests.conftest import requiere_base
from tests.planta import PASSWORD_ADMIN, hace, montar_planta


class Captura(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lineas: list[dict[str, object]] = []
        self.setFormatter(registro.FormatoJSON())

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(json.loads(self.format(record)))

    def eventos(self, nombre: str) -> list[dict[str, object]]:
        return [linea for linea in self.lineas if linea["evento"] == nombre]

    def texto(self) -> str:
        return json.dumps(self.lineas, ensure_ascii=False)


@pytest.fixture
def capturado(client: TestClient) -> Iterator[Captura]:
    captura = Captura()
    logger = logging.getLogger(registro.NOMBRE)
    logger.addHandler(captura)
    try:
        yield captura
    finally:
        logger.removeHandler(captura)


def test_formato_json_con_contexto() -> None:
    contexto = registro.nuevo_contexto("abcdef12")
    eid, uid = uuid4(), uuid4()
    registro.anotar_usuario(eid, uid)
    linea = registro.FormatoJSON().format(
        logging.LogRecord(registro.NOMBRE, logging.INFO, "", 0, "prueba", None, None)
    )
    datos = json.loads(linea)
    assert datos["request_id"] == contexto.request_id == "abcdef12"
    assert datos["empresa_id"] == str(eid)
    assert datos["usuario_id"] == str(uid)


@pytest.mark.parametrize("entrante", ["corto", "con espacios y más", "x" * 100, "a;b\nc"])
def test_un_request_id_entrante_raro_se_sustituye(entrante: str) -> None:
    assert registro.nuevo_contexto(entrante).request_id != entrante


pytestmark = requiere_base


def test_cada_peticion_deja_una_linea_y_devuelve_su_id(
    client: TestClient, capturado: Captura
) -> None:
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "prueba-123456"})
    assert resp.headers["X-Request-ID"] == "prueba-123456"
    linea = capturado.eventos("http")[-1]
    assert linea["request_id"] == "prueba-123456"
    assert linea["ruta"] == "/api/v1/health"
    assert linea["estado"] == 200


def test_la_linea_dice_de_que_empresa_y_usuario_es_y_no_lleva_valores_de_la_ruta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, capturado: Captura
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    planta.pedir(planta.operario, "GET", f"/activos/por-codigo/{activo['codigo']}")
    linea = next(x for x in reversed(capturado.eventos("http")) if "por-codigo" in str(x["ruta"]))
    assert linea["usuario_id"] == str(planta.operario.id)
    assert "empresa_id" in linea
    assert linea["ruta"] == "/api/v1/activos/por-codigo/{codigo}"
    assert activo["codigo"] not in capturado.texto()


def test_nunca_se_registran_contrasenas_tokens_ni_notas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, capturado: Captura
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    planta.alerta(activo["id"], nota="nota-secreta-de-prueba")
    texto = capturado.texto()
    assert PASSWORD_ADMIN not in texto
    assert planta.operario.token not in texto
    assert "nota-secreta-de-prueba" not in texto


def test_el_lote_emite_sus_metricas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, capturado: Captura
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    lectura = {
        "tipo": "lectura",
        "cliente_id": str(uuid4()),
        "activo_id": activo["id"],
        "valor": 5,
        "capturado_en": hace(minutes=5),
    }
    malo = {
        "tipo": "alerta",
        "cliente_id": str(uuid4()),
        "activo_id": activo["id"],
        "sintoma": "humo",
    }
    planta.pedir(planta.operario, "POST", "/campo/lotes", json={"items": [lectura, malo]})
    planta.pedir(planta.operario, "POST", "/campo/lotes", json={"items": [lectura]})
    primero, segundo = capturado.eventos("campo.lote")[-2:]
    assert (primero["recibidos"], primero["creados"], primero["rechazados"]) == (2, 1, 1)
    assert (segundo["recibidos"], segundo["duplicados"]) == (1, 1)


def test_una_lectura_marcada_deja_su_evento(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, capturado: Captura
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=1000)
    planta.lectura(activo["id"], 10)
    assert capturado.eventos("campo.lectura_marcada")[-1]["activo_id"] == activo["id"]
