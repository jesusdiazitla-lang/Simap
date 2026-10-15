"""Sincronización en lote de la cola sin conexión (RF-10; sección 5.3)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import ahora, hace, montar_planta

pytestmark = requiere_base


def _lote(planta, items):  # type: ignore[no-untyped-def]
    return planta.pedir(planta.operario, "POST", "/campo/lotes", json={"items": items})


def test_rf10_lote_con_item_invalido_no_afecta_a_los_demas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    buena, mala, alerta = str(uuid4()), str(uuid4()), str(uuid4())
    resp = _lote(
        planta,
        [
            {
                "tipo": "lectura",
                "cliente_id": buena,
                "activo_id": activo["id"],
                "valor": 10,
                "capturado_en": hace(hours=2),
            },
            # Síntoma que una versión vieja de la app escribía distinto.
            {
                "tipo": "alerta",
                "cliente_id": mala,
                "activo_id": activo["id"],
                "sintoma": "humo",
                "capturado_en": hace(hours=1),
            },
            {
                "tipo": "alerta",
                "cliente_id": alerta,
                "activo_id": activo["id"],
                "sintoma": "ruido",
                "nota": "Golpeteo",
                "capturado_en": hace(hours=1),
            },
        ],
    )
    assert resp.status_code == 200, resp.text
    resultados = {r["cliente_id"]: r for r in resp.json()["resultados"]}
    assert resultados[buena]["estado"] == "creado"
    assert resultados[mala]["estado"] == "rechazado"
    assert "sintoma" in resultados[mala]["motivo"]
    assert resultados[alerta]["estado"] == "creado"


def test_rf10_reenviar_el_mismo_lote_no_duplica_nada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La red se corta justo después de que el servidor guardó y el teléfono reenvía todo."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    items = [
        {
            "tipo": "lectura",
            "cliente_id": str(uuid4()),
            "activo_id": activo["id"],
            "valor": 20,
            "capturado_en": hace(minutes=30),
        },
        {
            "tipo": "alerta",
            "cliente_id": str(uuid4()),
            "activo_id": activo["id"],
            "sintoma": "calor",
            "capturado_en": hace(minutes=20),
        },
    ]
    primero = _lote(planta, items).json()["resultados"]
    segundo = _lote(planta, items).json()["resultados"]
    assert [r["estado"] for r in primero] == ["creado", "creado"]
    assert [r["estado"] for r in segundo] == ["duplicado", "duplicado"]
    historial = planta.pedir(planta.supervisor, "GET", f"/activos/{activo['id']}/lecturas").json()
    assert len(historial["items"]) == 1


def test_rf10_item_de_equipo_ajeno_se_rechaza_sin_revelarlo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    ajeno = a.nuevo_activo()
    resp = _lote(
        b,
        [
            {
                "tipo": "lectura",
                "cliente_id": str(uuid4()),
                "activo_id": ajeno["id"],
                "valor": 5,
                "capturado_en": ahora().isoformat(),
            }
        ],
    )
    resultado = resp.json()["resultados"][0]
    assert resultado["estado"] == "rechazado"
    assert resultado["motivo"] == "Ese equipo no existe."


def test_rf10_item_sin_cliente_id_se_identifica_por_su_indice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = _lote(planta, [{"tipo": "lectura", "valor": 1}])
    resultado = resp.json()["resultados"][0]
    assert resultado == {
        "indice": 0,
        "cliente_id": None,
        "estado": "rechazado",
        "motivo": resultado["motivo"],
        # Solo las fallas (F3) los rellenan: el código estable y la orden afectada.
        "codigo": None,
        "orden_id": None,
        "numero": None,
    }


def test_rf10_el_lote_tiene_tope_de_items(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    item = {
        "tipo": "alerta",
        "activo_id": activo["id"],
        "sintoma": "otro",
        "capturado_en": ahora().isoformat(),
    }
    resp = _lote(planta, [{**item, "cliente_id": str(uuid4())} for _ in range(51)])
    assert resp.status_code == 422


def test_rf10_solo_operario_y_supervisor_envian_lotes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    resp = planta.pedir(planta.gerente, "POST", "/campo/lotes", json={"items": [{}]})
    assert resp.status_code == 403
