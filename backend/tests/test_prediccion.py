"""Predicción de fallas por HTTP, con el personal de una planta (07-fase4, sección 15.2).

Las tareas en segundo plano (`BackgroundTasks`) corren dentro del mismo `TestClient`, después del
commit y antes de que la llamada vuelva: al terminar una petición, su recálculo ya ocurrió.

Las lecturas no pueden sumar más horas de operación que las que pasan en el reloj (F2, 5.1), así que
los equipos se dan de alta con horas y la edad de la pieza se declara (6.1).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import get_engine_job, get_sessionmaker_job
from app.jobs.recalculo_riesgo import correr
from app.services.prediccion import tareas
from tests.conftest import URL_APP, URL_DUENO, URL_JOB, requiere_base
from tests.planta import Planta, ahora, montar_planta

pytestmark = requiere_base


def preparar(
    planta: Planta,
    *,
    horas: int = 3000,
    edad: int | None = 1000,
    vida: int | None = 1000,
    componente: str = "Motor",
    nombre: str = "Compresor",
) -> tuple[str, str]:
    """Un equipo con `horas` en el horómetro y su componente con edad y vida nominal declaradas."""
    activo = planta.nuevo_activo(f"{nombre} {uuid4().hex[:4]}", horometro_inicial=horas)
    comp = planta.componente(componente)
    if vida is not None:
        assert planta.vida_nominal(comp, vida).status_code == 200
    if edad is not None:
        assert planta.edad(activo["id"], comp, horas - edad).status_code == 200
    return str(activo["id"]), comp


def riesgo_alto(planta: Planta) -> tuple[str, str]:
    """Un equipo cuyo riesgo supera el umbral por defecto (25 %): pieza de 3000 h, vida nominal de
    1000 h y horizonte de 1000 h. Sin fallas, la censura empuja η hacia arriba (η ≈ 2860 h) y el
    riesgo queda en torno al 56 %; tras un reemplazo baja a un 12 %."""
    configurar(planta, horizonte_horas=1000)
    return preparar(planta, edad=3000, vida=1000)


def del_componente(riesgo: dict[str, Any], componente_id: str) -> dict[str, Any]:
    return next(c for c in riesgo["componentes"] if c["componente_id"] == componente_id)


def modelo(planta: Planta, componente_id: str) -> dict[str, Any]:
    resp = planta.pedir(planta.supervisor, "GET", f"/componentes/{componente_id}/modelo")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def bandeja(planta: Planta, activo_id: str, estado: str = "vigentes") -> list[dict[str, Any]]:
    resp = planta.pedir(
        planta.supervisor,
        "GET",
        "/alertas-sistema",
        params={"tipo": "riesgo", "estado": estado, "activo_id": activo_id},
    )
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def configurar(planta: Planta, **cambios: Any) -> None:
    resp = planta.pedir(
        planta.admin,
        "PUT",
        "/configuracion/prediccion",
        json={k: str(v) if isinstance(v, Decimal) else v for k, v in cambios.items()},
    )
    assert resp.status_code == 200, resp.text


def _sql(url: str, sentencia: str, empresa_id: Any, **params: Any) -> list[Any]:
    async def correr_sql() -> list[Any]:
        motor = create_async_engine(url)
        try:
            async with motor.begin() as conn:
                await conn.execute(
                    text("SELECT set_config('app.empresa_id', :v, true)"), {"v": str(empresa_id)}
                )
                resultado = await conn.execute(text(sentencia), params)
                return list(resultado.all()) if resultado.returns_rows else []
        finally:
            await motor.dispose()

    return asyncio.run(correr_sql())


# --- RF-17: el modelo aprende de las órdenes cerradas ---------------------------------------------


def test_rf17_cierre_de_orden_reajusta_el_modelo_y_deja_historial(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD: cerrar una orden reajusta el modelo (versión nueva y fila de historial) sin intervención
    humana y sin que la petición de cierre espere."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta)
    inicial = modelo(planta, comp)
    assert inicial["n_eventos"] == 0
    assert inicial["fuente"] == "previo"

    planta.ciclo(activo, comp, 3000)
    tras_una = modelo(planta, comp)
    assert tras_una["n_eventos"] == 1
    assert tras_una["fuente"] == "mixto"
    assert tras_una["version"] > inicial["version"]

    planta.ciclo(activo, comp, 3001)
    tras_dos = modelo(planta, comp)
    assert tras_dos["n_eventos"] == 2
    assert tras_dos["version"] > tras_una["version"]
    assert [h["n_eventos"] for h in tras_dos["historial"]] == [0, 1, 2]


def test_rf17_sin_vida_nominal_ni_dos_fallas_no_hay_modelo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta, vida=None)
    assert del_componente(planta.riesgo(activo), comp)["estado_calculo"] == "sin_modelo"
    planta.ciclo(activo, comp, 3000)
    tras_una = del_componente(planta.riesgo(activo), comp)
    assert tras_una["estado_calculo"] == "sin_modelo"
    assert tras_una["riesgo"] is None
    planta.ciclo(activo, comp, 3001)
    assert del_componente(planta.riesgo(activo), comp)["estado_calculo"] == "ok"


def test_rf18_equipo_sin_edad_o_sin_modelo_no_muestra_riesgo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Sin edad» y «sin modelo» llegan como estado, nunca como un 0 % (10.2)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta, edad=None, vida=None)
    # La falla registra el componente en el equipo con edad desconocida (6.1).
    planta.orden(activo, componente_id=comp, horometro=3000)
    sin_edad = del_componente(planta.riesgo(activo), comp)
    assert sin_edad["estado_calculo"] == "sin_edad"
    assert sin_edad["riesgo"] is None
    assert sin_edad["riesgo_base"] is None

    otro, comp2 = preparar(planta, vida=None, componente="Rodamientos")
    sin_modelo = del_componente(planta.riesgo(otro), comp2)
    assert sin_modelo["estado_calculo"] == "sin_modelo"
    assert sin_modelo["riesgo"] is None


def test_la_edad_declarada_no_puede_superar_las_horas_del_equipo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Prensa", horometro_inicial=500)
    comp = planta.componente("Motor")
    resp = planta.edad(activo["id"], comp, 501)
    assert resp.status_code == 422
    assert resp.json()["detail"]["codigo"] == "edad_invalida"
    assert planta.edad(activo["id"], comp, 500).status_code == 200
    comodin = planta.componente("Otro (por identificar)")
    assert planta.edad(activo["id"], comodin, 0).status_code == 422


def test_la_falla_no_pisa_una_edad_declarada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta, edad=400)
    planta.orden(activo, componente_id=comp, horometro=3000)
    resp = planta.pedir(planta.supervisor, "GET", f"/activos/{activo}/componentes")
    par = next(c for c in resp.json()["componentes"] if c["componente_id"] == comp)
    assert par["horas_instalacion_inicial"] == 2600


# --- RF-19 y RF-20: cuándo se recalcula y el multiplicador ----------------------------------------


def test_rf19_lectura_de_horometro_recalcula_solo_ese_equipo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    a, comp = preparar(planta, nombre="A")
    b, _ = preparar(planta, nombre="B")
    antes_a = del_componente(planta.riesgo(a), comp)["calculado_en"]
    antes_b = del_componente(planta.riesgo(b), comp)["calculado_en"]
    assert planta.lectura(a, 3001).status_code == 201
    assert del_componente(planta.riesgo(a), comp)["calculado_en"] != antes_a
    assert del_componente(planta.riesgo(b), comp)["calculado_en"] == antes_b


def test_rf20_dos_alertas_en_ventana_aplican_multiplicador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con dos alertas de campo en la ventana el riesgo sube ×1,30; con una sola, no. Las
    descartadas dejan de contar."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta)
    base = del_componente(planta.riesgo(activo), comp)
    assert Decimal(base["multiplicador"]) == Decimal("1.00")

    assert planta.alerta(activo, "ruido").status_code == 201
    assert Decimal(del_componente(planta.riesgo(activo), comp)["multiplicador"]) == Decimal("1.00")

    segunda = planta.alerta(activo, "vibracion", quien=planta.supervisor)
    assert segunda.status_code == 201
    con_dos = del_componente(planta.riesgo(activo), comp)
    assert Decimal(con_dos["multiplicador"]) == Decimal("1.30")
    assert Decimal(con_dos["riesgo"]) > Decimal(con_dos["riesgo_base"])

    descarte = planta.pedir(
        planta.supervisor,
        "PATCH",
        f"/alertas/{segunda.json()['alerta']['id']}",
        json={"estado": "descartada"},
    )
    assert descarte.status_code == 200, descarte.text
    assert Decimal(del_componente(planta.riesgo(activo), comp)["multiplicador"]) == Decimal("1.00")


def test_rf20_alerta_del_sistema_no_alimenta_el_multiplicador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin lazo de realimentación: las alertas del sistema viven en otra tabla (7.4)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    riesgo = del_componente(planta.riesgo(activo), comp)
    assert Decimal(riesgo["riesgo"]) > Decimal("0.5")
    assert len(bandeja(planta, activo)) == 1
    assert planta.lectura(activo, 3000).status_code == 201
    assert Decimal(del_componente(planta.riesgo(activo), comp)["multiplicador"]) == Decimal("1.00")


def test_rnf02_falla_del_calculo_no_afecta_lectura_ni_reporte(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El cálculo va después del commit: si lanza, la lectura y la falla ya están guardadas."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta)

    def rompe() -> None:
        raise RuntimeError("el modelo se cayó")

    monkeypatch.setattr(tareas, "antes_de_calcular", rompe)
    assert planta.lectura(activo, 3001).status_code == 201
    falla = planta.falla(activo, componente_id=comp, horometro=3001)
    assert falla.status_code == 201
    planta.llevar_a_reparada(falla.json()["orden"]["id"])
    assert planta.mover(planta.supervisor, falla.json()["orden"]["id"], "cerrar").status_code == 200
    # La marca sigue ahí para el job de la madrugada (6.2).
    marcas = _sql(
        URL_APP,
        "SELECT count(*) FROM reajustes_pendientes WHERE componente_id = :c",
        planta.empresa_id,
        c=comp,
    )
    assert marcas[0][0] == 1


# --- RF-21: alertas del sistema -------------------------------------------------------------------


def test_rf21_alerta_al_superar_umbral_sin_duplicados(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    planta.riesgo(activo)
    for _ in range(3):
        assert planta.lectura(activo, 3000).status_code == 201
    vigentes = bandeja(planta, activo)
    assert len(vigentes) == 1
    assert vigentes[0]["estado"] == "activa"
    assert vigentes[0]["componente_id"] == comp
    assert Decimal(vigentes[0]["umbral"]) == Decimal("0.250")


def test_rf21_histeresis_y_silencio_tras_descartar(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La alerta se resuelve sola bajo el 80 % del umbral, no bajo el umbral; un descarte con nota
    silencia el componente y, vencido el plazo, la siguiente corrida crea otra."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = preparar(planta, edad=900, vida=1000)
    configurar(planta, horizonte_horas=300)
    r0 = Decimal(del_componente(planta.riesgo(activo), comp)["riesgo"])
    assert Decimal("0.08") < r0 < Decimal("0.7"), r0

    debajo = (r0 - Decimal("0.02")).quantize(Decimal("0.001"))
    configurar(planta, umbral_riesgo=debajo)
    assert [a["estado"] for a in bandeja(planta, activo)] == ["activa"]

    # Por encima del umbral, pero no por debajo del 80 % de él: sigue vigente.
    apenas_encima = (r0 / Decimal("0.85")).quantize(Decimal("0.001"))
    configurar(planta, umbral_riesgo=apenas_encima)
    assert len(bandeja(planta, activo)) == 1

    lejos = (r0 / Decimal("0.7")).quantize(Decimal("0.001"))
    configurar(planta, umbral_riesgo=min(lejos, Decimal("0.95")))
    assert bandeja(planta, activo) == []
    assert [a["estado"] for a in bandeja(planta, activo, "historial")] == ["resuelta"]

    configurar(planta, umbral_riesgo=debajo)
    nueva = bandeja(planta, activo)
    assert len(nueva) == 1
    sin_nota = planta.pedir(
        planta.supervisor, "POST", f"/alertas-sistema/{nueva[0]['id']}/descartar", json={}
    )
    assert sin_nota.status_code == 422
    descartada = planta.pedir(
        planta.supervisor,
        "POST",
        f"/alertas-sistema/{nueva[0]['id']}/descartar",
        json={"nota": "Se cambia en la parada de diciembre."},
    )
    assert descartada.status_code == 200, descartada.text
    assert planta.lectura(activo, 3000).status_code == 201
    assert bandeja(planta, activo) == []

    # Vencido el silencio (7 días), la siguiente corrida vuelve a avisar.
    _sql(
        URL_DUENO,
        "UPDATE alertas_sistema SET gestionada_en = now() - interval '8 days' WHERE id = :i",
        planta.empresa_id,
        i=nueva[0]["id"],
    )
    assert planta.lectura(activo, 3000).status_code == 201
    assert len(bandeja(planta, activo)) == 1


def test_rf21_orden_predictiva_desde_alerta_y_cierre_resuelve(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ciclo completo con tres personas: el supervisor crea la orden desde la alerta, el técnico
    cambia la pieza y el supervisor cierra. La alerta queda resuelta, el riesgo vuelve a casi cero
    y el reemplazo predictivo cuenta como censura: el modelo no gana ninguna falla."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    antes = del_componente(planta.riesgo(activo), comp)
    alerta = bandeja(planta, activo)[0]
    reconocida = planta.pedir(
        planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/reconocer"
    )
    assert reconocida.status_code == 200
    assert reconocida.json()["estado"] == "reconocida"

    resp = planta.pedir(planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/orden")
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert orden["es_predictiva"] is True
    assert orden["alerta_sistema_id"] == alerta["id"]
    assert orden["horas_acumuladas_en_falla"] == 3000
    otra = planta.pedir(planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/orden")
    assert otra.status_code == 409
    assert otra.json()["detail"]["codigo"] == "alerta_no_disponible"
    atendida = bandeja(planta, activo)[0]
    assert atendida["estado"] == "atendida"
    assert atendida["orden_numero"] == orden["numero"]
    no_se_descarta = planta.pedir(
        planta.supervisor,
        "POST",
        f"/alertas-sistema/{alerta['id']}/descartar",
        json={"nota": "Ya tiene orden."},
    )
    assert no_se_descarta.status_code == 409

    planta.llevar_a_reparada(orden["id"], "reemplazo")
    assert planta.mover(planta.supervisor, orden["id"], "cerrar").status_code == 200
    assert bandeja(planta, activo) == []
    assert [a["estado"] for a in bandeja(planta, activo, "historial")] == ["resuelta"]
    despues = del_componente(planta.riesgo(activo), comp)
    assert despues["edad_horas"] == 0
    assert Decimal(despues["riesgo"]) < Decimal(antes["riesgo"]) / 3
    assert modelo(planta, comp)["n_eventos"] == 0


def test_rf21_cancelar_la_orden_predictiva_devuelve_la_alerta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, _ = riesgo_alto(planta)
    planta.riesgo(activo)
    alerta = bandeja(planta, activo)[0]
    orden = planta.pedir(planta.admin, "POST", f"/alertas-sistema/{alerta['id']}/orden").json()
    cancelada = planta.mover(
        planta.supervisor, orden["id"], "cancelar", motivo="El repuesto no llegó todavía."
    )
    assert cancelada.status_code == 200
    assert [a["estado"] for a in bandeja(planta, activo)] == ["reconocida"]


def test_rf21_orden_predictiva_con_una_falla_abierta_es_409_y_no_toca_la_alerta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    planta.riesgo(activo)
    alerta = bandeja(planta, activo)[0]
    falla = planta.orden(activo, componente_id=comp, horometro=3000)
    resp = planta.pedir(planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/orden")
    assert resp.status_code == 409
    assert resp.json()["detail"]["codigo"] == "orden_abierta_existente"
    assert resp.json()["detail"]["numero"] == falla["numero"]
    assert bandeja(planta, activo)[0]["estado"] == "activa"


def test_rf21_convertir_en_falla_cambia_el_dato_del_modelo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el equipo falla antes de la intervención, la orden deja de ser censura y cuenta como
    falla (decisión 9)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    planta.riesgo(activo)
    alerta = bandeja(planta, activo)[0]
    orden = planta.pedir(planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/orden").json()
    cuerpo = {"horometro": 3000, "fecha_falla": (ahora() - timedelta(minutes=5)).isoformat()}
    tecnico = planta.pedir(
        planta.tecnico, "POST", f"/ordenes/{orden['id']}/convertir-en-falla", json=cuerpo
    )
    assert tecnico.status_code == 403
    resp = planta.pedir(
        planta.supervisor, "POST", f"/ordenes/{orden['id']}/convertir-en-falla", json=cuerpo
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["es_predictiva"] is False
    otra_vez = planta.pedir(
        planta.supervisor, "POST", f"/ordenes/{orden['id']}/convertir-en-falla", json=cuerpo
    )
    assert otra_vez.status_code == 409
    assert otra_vez.json()["detail"]["codigo"] == "estado_cambiado"

    planta.llevar_a_reparada(orden["id"], "reemplazo")
    assert planta.mover(planta.supervisor, orden["id"], "cerrar").status_code == 200
    assert modelo(planta, comp)["n_eventos"] == 1


@pytest.mark.parametrize("horometro", [1, 999_999], ids=["digitos_de_menos", "digitos_de_mas"])
def test_rf21_convertir_en_falla_con_horometro_incoherente_queda_en_revision(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, horometro: int
) -> None:
    """La conversión en falla registra la lectura con las reglas de la fase 2, como un reporte de
    falla (F3, 6.2). Un horómetro que no cuadra deja la orden marcada y fuera del modelo hasta que
    alguien lo confirme (07-fase4, 12.2): un error al teclear no puede estropear la curva del
    componente para toda la empresa."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, comp = riesgo_alto(planta)
    planta.riesgo(activo)
    alerta = bandeja(planta, activo)[0]
    orden = planta.pedir(planta.supervisor, "POST", f"/alertas-sistema/{alerta['id']}/orden").json()
    # La falla es de ahora: después de la lectura inicial de 3000 h con la que se creó el equipo.
    cuerpo = {"horometro": horometro, "fecha_falla": ahora().isoformat()}
    resp = planta.pedir(
        planta.supervisor, "POST", f"/ordenes/{orden['id']}/convertir-en-falla", json=cuerpo
    )
    assert resp.status_code == 200, resp.text
    convertida = resp.json()
    assert convertida["es_predictiva"] is False
    assert convertida["requiere_revision"] is True
    assert convertida["motivo_revision"]
    assert convertida["lectura_id"] is not None
    # La lectura quedó marcada y no movió el horómetro del equipo.
    ficha = planta.pedir(planta.supervisor, "GET", f"/activos/{activo}").json()
    assert ficha["horometro_actual"] == 3000
    # Cerrada sin confirmar, la falla no entra al modelo.
    planta.llevar_a_reparada(orden["id"], "reemplazo")
    assert planta.mover(planta.supervisor, orden["id"], "cerrar").status_code == 200
    assert modelo(planta, comp)["n_eventos"] == 0


def test_configuracion_solo_la_cambia_el_administrador_y_respeta_los_limites(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    leida = planta.pedir(planta.gerente, "GET", "/configuracion/prediccion")
    assert leida.status_code == 200
    assert leida.json()["horizonte_horas"] == 50
    assert Decimal(leida.json()["multiplicador_alertas"]) == Decimal("1.30")
    ruta = "/configuracion/prediccion"
    assert (
        planta.pedir(planta.supervisor, "PUT", ruta, json={"umbral_riesgo": "0.3"}).status_code
        == 403
    )
    assert planta.pedir(planta.admin, "PUT", ruta, json={"umbral_riesgo": "0"}).status_code == 422
    assert (
        planta.pedir(planta.admin, "PUT", ruta, json={"horizonte_horas": 5000}).status_code == 422
    )
    assert (
        planta.pedir(planta.admin, "PUT", ruta, json={"empresa_id": str(uuid4())}).status_code
        == 422
    )


# --- RF-22: el job nocturno -----------------------------------------------------------------------


def _correr_job() -> Any:
    async def una_pasada() -> Any:
        try:
            return await correr()
        finally:
            # Solo el motor del job: el de la aplicación es del bucle del TestClient.
            await get_engine_job().dispose()
            get_engine_job.cache_clear()
            get_sessionmaker_job.cache_clear()

    return asyncio.run(una_pasada())


def test_rf22_job_reajusta_pendientes_sin_modelo_y_viejos(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, viejo = preparar(planta)
    _, sin_modelo = preparar(planta, componente="Rodamientos")
    version = modelo(planta, viejo)["version"]
    _sql(
        URL_DUENO,
        "UPDATE modelos_componente SET ajustado_en = now() - interval '8 days'"
        " WHERE componente_id = :c",
        planta.empresa_id,
        c=viejo,
    )
    _sql(
        URL_DUENO,
        "DELETE FROM modelos_componente WHERE componente_id = :c",
        planta.empresa_id,
        c=sin_modelo,
    )
    _sql(
        URL_DUENO,
        "INSERT INTO reajustes_pendientes (empresa_id, componente_id) VALUES (:e, :c)",
        planta.empresa_id,
        e=planta.empresa_id,
        c=sin_modelo,
    )
    resumen = _correr_job()
    propia = next(e for e in resumen.empresas if e.empresa_id == planta.empresa_id)
    assert propia.error is None
    assert propia.reajustados >= 2
    assert modelo(planta, viejo)["version"] == version + 1
    assert modelo(planta, sin_modelo)["n_eventos"] == 0
    pendientes = _sql(URL_APP, "SELECT count(*) FROM reajustes_pendientes", planta.empresa_id)
    assert pendientes[0][0] == 0
    # Una segunda corrida no duplica nada: ni alertas ni modelos.
    _correr_job()
    assert modelo(planta, viejo)["version"] == version + 1


def test_rnf01_job_nocturno_no_cruza_empresas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """job_user sin tenant no ve ninguna fila de empresa; app_user no puede listar empresas."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo, _ = riesgo_alto(planta)
    planta.riesgo(activo)

    async def comprobar() -> tuple[list[int], int, str]:
        motor_job = create_async_engine(URL_JOB)
        motor_app = create_async_engine(URL_APP)
        try:
            async with motor_job.connect() as conn:
                conteos = [
                    int((await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one())
                    for t in ("ordenes_trabajo", "riesgos", "alertas_sistema", "activos", "v_vidas")
                ]
                empresas = len((await conn.execute(text("SELECT empresas_activas()"))).all())
            async with motor_app.connect() as conn:
                try:
                    await conn.execute(text("SELECT empresas_activas()"))
                    error = ""
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
            return conteos, empresas, error
        finally:
            await motor_job.dispose()
            await motor_app.dispose()

    conteos, empresas, error = asyncio.run(comprobar())
    assert conteos == [0, 0, 0, 0, 0]
    assert empresas >= 1
    assert "permission denied" in error


# --- Tabla 12.1 -----------------------------------------------------------------------------------

S, T, G, A, OP = "supervisor", "tecnico_taller", "gerente", "administrador", "operario"

#: (método, ruta, cuerpo, roles que pasan). Ids inventados: el rol se comprueba antes que nada, así
#: que un rol sin permiso recibe 403 y uno con permiso, cualquier otra cosa (404, 409, 422).
MATRIZ: list[tuple[str, str, dict[str, Any] | None, set[str]]] = [
    ("GET", "/activos/{x}/riesgo", None, {S, T, G, A}),
    ("GET", "/riesgos", None, {S, G, A}),
    ("GET", "/activos/{x}/componentes", None, {S, G, A}),
    ("PUT", "/activos/{x}/componentes/{x}", {"horas_instalacion_inicial": 0}, {A}),
    ("GET", "/componentes/{x}/modelo", None, {S, G, A}),
    ("PATCH", "/componentes/{x}", {"vida_nominal_horas": 500}, {A}),
    ("GET", "/configuracion/prediccion", None, {S, G, A}),
    ("PUT", "/configuracion/prediccion", {"horizonte_horas": 50}, {A}),
    ("GET", "/alertas-sistema", None, {S, G, A}),
    ("POST", "/alertas-sistema/{x}/reconocer", None, {S, A}),
    ("POST", "/alertas-sistema/{x}/descartar", {"nota": "No ahora."}, {S, A}),
    ("POST", "/alertas-sistema/{x}/orden", None, {S, A}),
    (
        "POST",
        "/ordenes/{x}/convertir-en-falla",
        {"horometro": 1, "fecha_falla": "2026-01-01T00:00:00Z"},
        {S, A},
    ),
    ("GET", "/repuestos", None, {S, T, G, A}),
    ("GET", "/repuestos/{x}", None, {S, G, A}),
    ("POST", "/repuestos", {"nombre": "Filtro", "codigo": "{x}"}, {A}),
    ("PATCH", "/repuestos/{x}", {"stock_minimo": 2}, {A}),
    ("POST", "/repuestos/{x}/ingresos", {"cantidad": 1}, {S, A}),
    ("POST", "/repuestos/{x}/ajuste", {"conteo": 1, "nota": "Conteo de cierre."}, {A}),
    ("GET", "/repuestos/{x}/movimientos", None, {S, G, A}),
    ("GET", "/ordenes/{x}/repuestos", None, {S, T, G, A}),
    ("PUT", "/ordenes/{x}/repuestos/{x}", {"cantidad": 1}, {S, T, A}),
    ("DELETE", "/ordenes/{x}/repuestos/{x}", None, {S, T, A}),
    ("GET", "/inventario/conciliacion", None, {A}),
    ("POST", "/ordenes/{x}/cerrar", None, {S, A}),
]


def test_roles_matriz_12_1_todas_las_combinaciones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    personas = {
        S: planta.supervisor,
        T: planta.tecnico,
        G: planta.gerente,
        A: planta.admin,
        OP: planta.operario,
    }
    errores = []
    for metodo, ruta, cuerpo, permitidos in MATRIZ:
        for rol, persona in personas.items():
            x = str(uuid4())
            json = (
                None
                if cuerpo is None
                else {
                    k: (v.replace("{x}", x[:8]) if isinstance(v, str) else v)
                    for k, v in cuerpo.items()
                }
            )
            resp = planta.pedir(persona, metodo, ruta.replace("{x}", x), json=json)
            denegado = resp.status_code == 403
            if denegado == (rol in permitidos):
                errores.append(f"{metodo} {ruta} como {rol}: {resp.status_code}")
    assert errores == []
