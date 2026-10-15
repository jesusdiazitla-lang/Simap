"""Máquina de estados de la orden (RF-13, RNF-06; 06-fase3-ordenes-de-trabajo.md, 6.1 y 11.1).

`test_rf13_roles_correctos_en_cada_transicion` es la tabla 11.1 del documento convertida en prueba:
recorre cada acción con cada uno de los cinco roles. Si alguien cambia un `requiere_roles`, falla.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.ordenes_estados import minutos_fuera_de_servicio
from tests.conftest import requiere_base
from tests.planta import Persona, Planta, montar_planta

pytestmark = requiere_base

ROLES = ("operario", "supervisor", "tecnico_taller", "gerente", "administrador")


def _persona(planta: Planta, rol: str) -> Persona:
    return planta.admin if rol == "administrador" else planta.personas[rol]


def test_minutos_fuera_de_servicio_nunca_es_negativo() -> None:
    """Un teléfono con el reloj adelantado no produce un tiempo imposible (RF-15)."""
    falla = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
    assert minutos_fuera_de_servicio(falla, falla + timedelta(hours=2, minutes=5)) == 125
    assert minutos_fuera_de_servicio(falla, falla - timedelta(minutes=3)) == 0


def test_rf13_flujo_completo_reportada_a_cerrada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tres usuarios, tres roles: supervisor reporta, técnico repara, supervisor autoriza."""
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    assert orden["estado"] == "reportada"

    taller = planta.mover(planta.tecnico, orden["id"], "en-taller").json()
    assert taller["estado"] == "en_taller" and taller["en_taller_en"] is not None

    reparada = planta.reparar(orden["id"], tipo="reparacion").json()
    assert reparada["estado"] == "reparada"
    assert reparada["tipo_intervencion"] == "reparacion"
    assert reparada["reparado_por"]["id"] == str(planta.tecnico.id)

    cerrada = planta.mover(
        planta.supervisor, orden["id"], "cerrar", nota="Probado en vacío."
    ).json()
    assert cerrada["estado"] == "cerrada"
    assert cerrada["autorizado_por"]["id"] == str(planta.supervisor.id)
    assert cerrada["tiempo_fuera_servicio_min"] >= 0
    # El equipo ya no está en falla.
    ficha = planta.pedir(planta.operario, "GET", f"/activos/{orden['activo_id']}").json()
    assert ficha["en_falla"] is False


def test_rf13_transicion_desde_estado_incorrecto_devuelve_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    # Cerrar una orden recién reportada: el UPDATE condicionado no encuentra la fila.
    resp = planta.mover(planta.supervisor, orden["id"], "cerrar")
    assert resp.status_code == 409
    assert resp.json()["detail"]["codigo"] == "estado_cambiado"
    assert "Reportada" in resp.json()["detail"]["mensaje"]
    # Cerrada y Cancelada son terminales.
    planta.mover(
        planta.supervisor, orden["id"], "cancelar", motivo="Reportada por error, era otra."
    )
    for accion, cuerpo in (
        ("en-taller", {}),
        ("cancelar", {"motivo": "Otra vez, por si acaso."}),
    ):
        resp = planta.mover(planta.supervisor, orden["id"], accion, **cuerpo)
        assert resp.status_code == 409, accion
        assert "Cancelada" in resp.json()["detail"]["mensaje"]


def test_rf13_rechazo_exige_nota_y_conserva_trabajo_anterior(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    planta.llevar_a_reparada(orden["id"], tipo="ajuste")

    assert planta.mover(planta.supervisor, orden["id"], "rechazar-cierre").status_code == 422
    assert (
        planta.mover(planta.supervisor, orden["id"], "rechazar-cierre", nota="corto").status_code
        == 422
    )

    resp = planta.mover(
        planta.supervisor, orden["id"], "rechazar-cierre", nota="Sigue vibrando a plena carga."
    )
    assert resp.status_code == 200, resp.text
    devuelta = resp.json()
    assert devuelta["estado"] == "en_taller"
    # La orden ya no muestra como hecho un trabajo rechazado...
    assert devuelta["trabajo_realizado"] is None and devuelta["reparado_por"] is None
    # ...pero el historial lo conserva.
    rechazo = devuelta["eventos"][-1]
    assert rechazo["nota"] == "Sigue vibrando a plena carga."
    anterior = rechazo["datos"]["trabajo_rechazado"]
    assert anterior["tipo_intervencion"] == "ajuste"
    assert "rodamiento" in anterior["trabajo_realizado"]
    assert anterior["reparado_por"] == str(planta.tecnico.id)

    # El técnico la vuelve a reparar; queda la versión nueva.
    assert planta.reparar(orden["id"], tipo="reemplazo").json()["tipo_intervencion"] == "reemplazo"


def test_rf13_cancelar_libera_componente_y_alerta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Los dos índices parciales: el componente admite otra orden, la alerta otra conversión."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    alerta = planta.alerta(activo["id"], "calor").json()["alerta"]
    orden = planta.orden(activo["id"], alerta_id=alerta["id"])

    assert (
        planta.mover(planta.supervisor, orden["id"], "cancelar", motivo="corto").status_code == 422
    )
    cancelada = planta.mover(
        planta.supervisor,
        orden["id"],
        "cancelar",
        motivo="Duplicada: ya la reportó el turno de noche.",
    ).json()
    assert cancelada["estado"] == "cancelada"
    assert cancelada["motivo_cancelacion"].startswith("Duplicada")

    nueva = planta.falla(activo["id"], alerta_id=alerta["id"])
    assert nueva.status_code == 201, nueva.text
    assert nueva.json()["orden"]["numero"] == 2


def test_rnf06_toda_transicion_deja_evento_con_usuario_y_rol(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    planta.llevar_a_reparada(orden["id"])
    planta.mover(
        planta.supervisor, orden["id"], "rechazar-cierre", nota="Falta apretar los pernos."
    )
    planta.reparar(orden["id"])
    detalle = planta.mover(planta.admin, orden["id"], "cerrar").json()

    transiciones = [
        (e["estado_anterior"], e["estado_nuevo"], e["rol_al_momento"])
        for e in detalle["eventos"]
        if e["tipo"] == "transicion"
    ]
    assert transiciones == [
        ("reportada", "en_taller", "tecnico_taller"),
        ("en_taller", "reparada", "tecnico_taller"),
        ("reparada", "en_taller", "supervisor"),
        ("en_taller", "reparada", "tecnico_taller"),
        ("reparada", "cerrada", "administrador"),
    ]
    assert all(e["usuario"]["nombre"] for e in detalle["eventos"])


def test_rf13_roles_correctos_en_cada_transicion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La tabla 11.1, entera: cada acción con cada rol.

    Para los roles permitidos se prepara una orden en el estado de origen y se espera éxito; para
    los demás, 403 —el rol se comprueba antes que el estado, así que no hace falta una orden en el
    estado correcto—. Un 404 o un 409 en un rol no permitido delataría que la comprobación de rol
    llega tarde.
    """
    monkeypatch.setenv("FALLA_MAX_POR_MINUTO", "1000")
    monkeypatch.setenv("TRANSICION_MAX_POR_MINUTO", "1000")
    get_settings.cache_clear()
    planta = montar_planta(client, monkeypatch, "Planta")

    def reportada() -> str:
        return str(planta.orden(planta.nuevo_activo()["id"], quien=planta.admin)["id"])

    def en_taller() -> str:
        orden = reportada()
        planta.mover(planta.admin, orden, "en-taller")
        return orden

    def reparada() -> str:
        orden = en_taller()
        assert planta.reparar(orden).status_code == 200
        return orden

    def cerrada() -> str:
        orden = reparada()
        planta.mover(planta.admin, orden, "cerrar")
        return orden

    componente = planta.componente()

    acciones: list[
        tuple[str, set[str], Callable[[], str], Callable[[Persona, str], httpx.Response]]
    ] = [
        (
            "reportar falla",
            {"supervisor", "administrador"},
            lambda: str(planta.nuevo_activo()["id"]),
            lambda p, activo: planta.falla(activo, quien=p, componente_id=componente),
        ),
        (
            "ver órdenes",
            {"supervisor", "tecnico_taller", "gerente", "administrador"},
            reportada,
            lambda p, orden: planta.pedir(p, "GET", f"/ordenes/{orden}"),
        ),
        (
            "editar orden abierta",
            {"supervisor", "administrador"},
            reportada,
            lambda p, orden: planta.pedir(
                p, "PATCH", f"/ordenes/{orden}", json={"codigo_error": "E-22"}
            ),
        ),
        (
            "pasar a en taller",
            {"supervisor", "tecnico_taller", "administrador"},
            reportada,
            lambda p, orden: planta.mover(p, orden, "en-taller"),
        ),
        (
            "marcar reparada",
            {"tecnico_taller"},
            en_taller,
            lambda p, orden: planta.mover(
                p,
                orden,
                "reparada",
                trabajo_realizado="Cambio completo del rodamiento.",
                tipo_intervencion="reemplazo",
            ),
        ),
        (
            "autorizar cierre",
            {"supervisor", "administrador"},
            reparada,
            lambda p, orden: planta.mover(p, orden, "cerrar"),
        ),
        (
            "rechazar cierre",
            {"supervisor", "administrador"},
            reparada,
            lambda p, orden: planta.mover(p, orden, "rechazar-cierre", nota="No pasó la prueba."),
        ),
        (
            "cancelar",
            {"supervisor", "administrador"},
            reportada,
            lambda p, orden: planta.mover(p, orden, "cancelar", motivo="Reportada por error."),
        ),
        (
            "agregar nota",
            {"supervisor", "tecnico_taller", "administrador"},
            reportada,
            lambda p, orden: planta.pedir(
                p, "POST", f"/ordenes/{orden}/notas", json={"nota": "Ok"}
            ),
        ),
        (
            "corregir orden cerrada",
            {"administrador"},
            cerrada,
            lambda p, orden: planta.pedir(
                p,
                "POST",
                f"/ordenes/{orden}/correccion",
                json={"nota": "Código de error mal copiado.", "codigo_error": "E-31"},
            ),
        ),
        (
            "reiniciar horómetro",
            {"administrador"},
            lambda: str(planta.nuevo_activo(horometro_inicial=100)["id"]),
            lambda p, activo: planta.pedir(
                p, "POST", f"/activos/{activo}/reinicio-horometro", json={"nuevo": 0}
            ),
        ),
    ]

    fallos: list[str] = []
    for nombre, permitidos, preparar, hacer in acciones:
        compartido = preparar()
        for rol in ROLES:
            objetivo = preparar() if rol in permitidos else compartido
            resp = hacer(_persona(planta, rol), objetivo)
            esperado: Any = (200, 201) if rol in permitidos else (403,)
            if resp.status_code not in esperado:
                fallos.append(f"{nombre} / {rol}: {resp.status_code} {resp.text[:120]}")
    assert fallos == []
