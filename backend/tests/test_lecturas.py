"""Lecturas de horómetro: idempotencia, marca de revisión y valor vigente que no retrocede (RF-08).

Cada prueba lleva el nombre que le da `docs/contexto/05-fase2-activos-y-campo.md`, sección 10.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import ahora, hace, montar_planta

pytestmark = requiere_base


def _vigente(planta, activo_id: str) -> int:  # type: ignore[no-untyped-def]
    return int(
        planta.pedir(planta.admin, "GET", f"/activos/{activo_id}").json()["horometro_actual"]
    )


def test_rf08_lectura_con_mismo_cliente_id_crea_una_sola_fila(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=100)
    cliente_id = str(uuid4())
    primera = planta.lectura(activo["id"], 105, cliente_id=cliente_id)
    segunda = planta.lectura(activo["id"], 105, cliente_id=cliente_id)
    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["estado"] == "duplicado"
    assert segunda.json()["lectura"]["id"] == primera.json()["lectura"]["id"]

    historial = planta.pedir(planta.supervisor, "GET", f"/activos/{activo['id']}/lecturas").json()
    assert [x["valor_horometro"] for x in historial["items"]] == [105, 100]


def test_rf08_lectura_valida_mueve_el_horometro_vigente(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=100)
    # Una hora de reloj después del alta... se simula capturando «ahora» y con margen de 2 h.
    resp = planta.lectura(activo["id"], 101)
    assert resp.status_code == 201, resp.text
    assert resp.json()["lectura"]["requiere_revision"] is False
    assert _vigente(planta, activo["id"]) == 101


def test_rf08_lectura_menor_queda_marcada_y_no_mueve_el_valor(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4800)
    resp = planta.lectura(activo["id"], 480)
    assert resp.status_code == 201, "el dato del operario se guarda siempre"
    lectura = resp.json()["lectura"]
    assert lectura["requiere_revision"] is True
    assert "Menor que la lectura anterior" in lectura["motivo_revision"]
    assert _vigente(planta, activo["id"]) == 4800


def test_rf08_un_digito_de_mas_queda_marcado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una máquina no puede sumar más horas de operación que las que han pasado en el reloj."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4821)
    resp = planta.lectura(activo["id"], 48210)
    lectura = resp.json()["lectura"]
    assert lectura["requiere_revision"] is True
    assert "más horas de operación" in lectura["motivo_revision"]
    assert _vigente(planta, activo["id"]) == 4821


def test_rf08_llegada_fuera_de_orden_no_retrocede_el_horometro(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una lectura de esta mañana que llega después de una de esta tarde (cola sin conexión).

    Cuadra con el historial —está entre sus vecinas— así que se guarda sin marca, pero el valor
    vigente sigue siendo el de la tarde: el UPDATE condicionado no lo deja retroceder.
    """
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    planta.lectura(activo["id"], 1000, capturado_en=hace(hours=10))
    tarde = planta.lectura(activo["id"], 1008, capturado_en=hace(hours=1))
    assert tarde.json()["lectura"]["requiere_revision"] is False

    manana = planta.lectura(activo["id"], 1004, capturado_en=hace(hours=5))
    assert manana.status_code == 201
    assert manana.json()["lectura"]["requiere_revision"] is False
    assert _vigente(planta, activo["id"]) == 1008


def test_rf08_llegada_tarde_que_no_cuadra_queda_marcada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    planta.lectura(activo["id"], 1000, capturado_en=hace(hours=10))
    planta.lectura(activo["id"], 1008, capturado_en=hace(hours=1))
    vieja = planta.lectura(activo["id"], 1050, capturado_en=hace(hours=5))
    assert vieja.json()["lectura"]["requiere_revision"] is True
    assert "posterior" in vieja.json()["lectura"]["motivo_revision"]


@pytest.mark.parametrize(
    ("capturado_en", "fragmento"),
    [
        (lambda: (ahora() + timedelta(hours=2)).isoformat(), "futuro"),
        (lambda: hace(days=30), "días"),
    ],
)
def test_rf08_captura_fuera_de_ventana_se_rechaza(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capturado_en,
    fragmento: str,  # type: ignore[no-untyped-def]
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    resp = planta.lectura(activo["id"], 10, capturado_en=capturado_en())
    assert resp.status_code == 422
    assert fragmento in resp.json()["detail"]


def test_rf08_valor_por_encima_del_maximo_se_rechaza(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    assert planta.lectura(activo["id"], 1_000_001).status_code == 422
    assert planta.lectura(activo["id"], -1).status_code == 422


def test_rf08_captura_sin_zona_horaria_se_rechaza(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    resp = planta.lectura(activo["id"], 10, capturado_en="2026-10-06T14:00:00")
    assert resp.status_code == 422


def test_rnf01_no_puede_registrar_lecturas_en_equipos_de_otra_empresa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    activo = a.nuevo_activo()
    resp = b.lectura(activo["id"], 10)
    assert resp.status_code == 404


def test_solo_operario_y_supervisor_registran_y_el_operario_no_ve_el_historial(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    assert planta.lectura(activo["id"], 1, quien=planta.gerente).status_code == 403
    assert planta.lectura(activo["id"], 1, quien=planta.admin).status_code == 403
    assert planta.lectura(activo["id"], 1, quien=planta.supervisor).status_code == 201
    historial = planta.pedir(planta.operario, "GET", f"/activos/{activo['id']}/lecturas")
    assert historial.status_code == 403


def test_el_cuerpo_no_puede_declarar_empresa_ni_autor(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`empresa_id` y `usuario_id` salen del token, nunca del cuerpo (sección 8.3)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    for campo in ("empresa_id", "registrado_por", "usuario_id"):
        resp = planta.lectura(activo["id"], 1, **{campo: str(uuid4())})
        assert resp.status_code == 422, campo


# --- Revisión de lecturas marcadas (revisión 0006) ------------------------------


def _marcada(planta, activo_id: str, valor: int) -> str:  # type: ignore[no-untyped-def]
    lectura = planta.lectura(activo_id, valor).json()["lectura"]
    assert lectura["requiere_revision"] is True
    return str(lectura["id"])


def test_rf08_confirmar_una_lectura_marcada_mueve_el_horometro(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=100)
    # Un salto real que el reloj no explica: el equipo trabajó en un turno no registrado.
    lid = _marcada(planta, activo["id"], 160)
    pendientes = planta.pedir(planta.supervisor, "GET", "/lecturas/por-revisar").json()["items"]
    fila = next(p for p in pendientes if p["id"] == lid)
    assert fila["activo_nombre"] == activo["nombre"]
    assert fila["horometro_vigente"] == 100

    resp = planta.pedir(
        planta.supervisor, "PATCH", f"/lecturas/{lid}", json={"resolucion": "confirmada"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["resolucion"] == "confirmada"
    assert resp.json()["revisada_por"] == str(planta.supervisor.id)
    assert _vigente(planta, activo["id"]) == 160
    pendientes = planta.pedir(planta.supervisor, "GET", "/lecturas/por-revisar").json()["items"]
    assert lid not in {p["id"] for p in pendientes}


def test_rf08_descartar_conserva_la_lectura_sin_que_cuente(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4821)
    lid = _marcada(planta, activo["id"], 48210)
    planta.pedir(planta.supervisor, "PATCH", f"/lecturas/{lid}", json={"resolucion": "descartada"})
    assert _vigente(planta, activo["id"]) == 4821
    historial = planta.pedir(planta.supervisor, "GET", f"/activos/{activo['id']}/lecturas").json()
    assert 48210 in [x["valor_horometro"] for x in historial["items"]]
    # Y no sirve de referencia: la siguiente lectura normal no aparece como «menor que la anterior».
    assert planta.lectura(activo["id"], 4822).json()["lectura"]["requiere_revision"] is False


def test_rf08_reinicio_del_horometro_empieza_una_serie_nueva(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4800)
    lid = _marcada(planta, activo["id"], 3)
    # El supervisor no puede: cambia la serie de horas del equipo.
    nego = planta.pedir(
        planta.supervisor, "PATCH", f"/lecturas/{lid}", json={"resolucion": "reinicio"}
    )
    assert nego.status_code == 403
    ok = planta.pedir(planta.admin, "PATCH", f"/lecturas/{lid}", json={"resolucion": "reinicio"})
    assert ok.status_code == 200
    assert _vigente(planta, activo["id"]) == 3
    # Las lecturas siguientes se comparan con el reinicio, no con las 4.800 h de antes.
    siguiente = planta.lectura(activo["id"], 4).json()["lectura"]
    assert siguiente["requiere_revision"] is False
    assert _vigente(planta, activo["id"]) == 4


def test_una_lectura_resuelta_no_se_vuelve_a_resolver(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=100)
    lid = _marcada(planta, activo["id"], 50)
    planta.pedir(planta.supervisor, "PATCH", f"/lecturas/{lid}", json={"resolucion": "descartada"})
    otra = planta.pedir(
        planta.admin, "PATCH", f"/lecturas/{lid}", json={"resolucion": "confirmada"}
    )
    assert otra.status_code == 409
    # Ni una que nunca estuvo marcada.
    normal = planta.lectura(activo["id"], 101).json()["lectura"]["id"]
    resp = planta.pedir(
        planta.admin, "PATCH", f"/lecturas/{normal}", json={"resolucion": "confirmada"}
    )
    assert resp.status_code == 409


def test_el_operario_no_resuelve_lecturas_ni_ve_la_bandeja(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=100)
    lid = _marcada(planta, activo["id"], 50)
    assert planta.pedir(planta.operario, "GET", "/lecturas/por-revisar").status_code == 403
    resp = planta.pedir(
        planta.operario, "PATCH", f"/lecturas/{lid}", json={"resolucion": "confirmada"}
    )
    assert resp.status_code == 403


def test_rnf01_no_se_resuelven_lecturas_de_otra_empresa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Empresa A")
    b = montar_planta(client, monkeypatch, "Empresa B")
    activo = a.nuevo_activo(horometro_inicial=100)
    lid = _marcada(a, activo["id"], 50)
    assert lid not in {
        p["id"] for p in b.pedir(b.admin, "GET", "/lecturas/por-revisar").json()["items"]
    }
    resp = b.pedir(b.admin, "PATCH", f"/lecturas/{lid}", json={"resolucion": "confirmada"})
    assert resp.status_code == 404
