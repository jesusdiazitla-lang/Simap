"""Órdenes de trabajo por HTTP: reporte de falla, consulta, edición y corrección (RF-11..16).

Cada prueba lleva el nombre que le da `docs/contexto/06-fase3-ordenes-de-trabajo.md`, sección 13,
cuando el documento la nombra. Las transiciones están en `test_ordenes_estados.py`; las defensas de
la base, en `test_orden_trabajo.py`.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requiere_base
from tests.planta import hace, montar_planta

pytestmark = requiere_base


# --- RF-11 y RF-12: reporte de falla ---------------------------------------------------


def test_rf11_supervisor_reporta_falla_y_nace_orden_reportada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4800)
    resp = planta.falla(activo["id"], temperatura=94.5, codigo_error="E-14")
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["estado"] == "creado"
    orden = cuerpo["orden"]
    assert orden["numero"] == 1
    assert orden["estado"] == "reportada"
    assert orden["horometro_en_falla"] == 4801
    assert orden["horas_acumuladas_en_falla"] == 4801
    assert orden["temperatura"] == "94.50" or float(orden["temperatura"]) == 94.5
    assert orden["codigo_error"] == "E-14"
    assert orden["reportado_por"]["nombre"] == "Supervisor"
    # Registra además la lectura de horómetro de la falla (CU-02, paso 7).
    assert orden["lectura_id"] is not None
    assert [e["tipo"] for e in orden["eventos"]] == ["creada"]
    # Y el número sigue: la segunda orden de la empresa es la 2.
    otra = planta.falla(activo["id"], componente_id=planta.componente("Rodamientos"))
    assert otra.json()["orden"]["numero"] == 2


def test_rf11_operario_no_puede_reportar_falla(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    for quien in (planta.operario, planta.tecnico, planta.gerente):
        assert planta.falla(activo["id"], quien=quien).status_code == 403


def test_rf11_reenvio_con_mismo_cliente_id_crea_una_sola_orden(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    cliente_id = str(uuid4())
    primera = planta.falla(activo["id"], cliente_id=cliente_id)
    segunda = planta.falla(activo["id"], cliente_id=cliente_id)
    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["estado"] == "duplicado"
    assert segunda.json()["orden"]["id"] == primera.json()["orden"]["id"]
    # Una sola lectura de la falla: su cliente_id se deriva del de la falla.
    lecturas = planta.pedir(planta.admin, "GET", f"/activos/{activo['id']}/lecturas").json()
    assert len(lecturas["items"]) == 1


def test_rf11_segundo_reporte_mismo_componente_devuelve_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    primera = planta.orden(activo["id"])
    resp = planta.falla(activo["id"])
    assert resp.status_code == 409
    detalle = resp.json()["detail"]
    assert detalle["codigo"] == "orden_abierta_existente"
    assert detalle["numero"] == primera["numero"]
    assert detalle["orden_id"] == primera["id"]
    # Otro componente del mismo equipo sí abre otra orden.
    assert (
        planta.falla(activo["id"], componente_id=planta.componente("Rodamientos")).status_code
        == 201
    )


def test_rf11_lectura_inconsistente_marca_la_orden_para_revision(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La lectura de la falla queda marcada y la orden hereda la marca. Se confirma desde la orden,
    no desde la bandeja de lecturas (F3, 5.3), y eso confirma también la lectura."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=4800)
    orden = planta.orden(activo["id"], horometro=48000)  # un dígito de más
    assert orden["requiere_revision"] is True
    assert "dígito de más" in orden["motivo_revision"]

    por_lectura = planta.pedir(
        planta.supervisor,
        "PATCH",
        f"/lecturas/{orden['lectura_id']}",
        json={"resolucion": "confirmada"},
    )
    assert por_lectura.status_code == 409
    assert "OT-0001" in por_lectura.json()["detail"]

    resp = planta.pedir(planta.supervisor, "POST", f"/ordenes/{orden['id']}/confirmar-horometro")
    assert resp.status_code == 200, resp.text
    assert resp.json()["requiere_revision"] is False
    pendientes = planta.pedir(planta.supervisor, "GET", "/lecturas/por-revisar").json()["items"]
    assert orden["lectura_id"] not in [p["id"] for p in pendientes]


def test_campo_lote_con_fallas_sin_conexion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La falla encolada sin red (F3, 9.5): se crea una vez, el reenvío es duplicado, un segundo
    reporte del mismo componente vuelve con el número de la orden existente, y el operario recibe
    `sin_permiso` en ese ítem sin que se caiga el resto del lote."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    motor = planta.componente()
    falla = {
        "tipo": "falla",
        "activo_id": activo["id"],
        "componente_id": motor,
        "horometro": 120,
        "descripcion": "Humo en la caja de bornes",
        "capturado_en": hace(minutes=20),
    }
    primera = {**falla, "cliente_id": str(uuid4())}
    otra = {**falla, "cliente_id": str(uuid4())}
    resp = planta.pedir(
        planta.supervisor, "POST", "/campo/lotes", json={"items": [primera, primera, otra]}
    )
    assert resp.status_code == 200, resp.text
    r = resp.json()["resultados"]
    assert [x["estado"] for x in r] == ["creado", "duplicado", "rechazado"]
    assert r[0]["numero"] == 1
    assert r[2]["codigo"] == "orden_abierta_existente" and r[2]["numero"] == 1

    lectura = {
        "tipo": "lectura",
        "activo_id": activo["id"],
        "valor": 121,
        "capturado_en": hace(minutes=1),
        "cliente_id": str(uuid4()),
    }
    resp = planta.pedir(
        planta.operario,
        "POST",
        "/campo/lotes",
        json={"items": [{**falla, "cliente_id": str(uuid4())}, lectura]},
    )
    r = resp.json()["resultados"]
    assert r[0]["estado"] == "rechazado" and r[0]["codigo"] == "sin_permiso"
    assert r[1]["estado"] == "creado"


# --- Consulta y aislamiento ----------------------------------------------------------------


def test_rnf01_listado_y_detalle_de_ordenes_aislados_por_empresa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Planta A")
    b = montar_planta(client, monkeypatch, "Planta B")
    orden = a.orden(a.nuevo_activo()["id"])
    assert [o["id"] for o in a.pedir(a.supervisor, "GET", "/ordenes").json()["items"]] == [
        orden["id"]
    ]
    assert b.pedir(b.supervisor, "GET", "/ordenes").json()["items"] == []
    # Nunca 403 por empresa ajena: confirmaría que existe.
    assert b.pedir(b.supervisor, "GET", f"/ordenes/{orden['id']}").status_code == 404
    assert (
        b.mover(
            b.supervisor, orden["id"], "cancelar", motivo="Intento desde otra empresa"
        ).status_code
        == 404
    )


def test_el_operario_no_ve_ordenes_pero_si_que_el_equipo_esta_en_falla(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sección 8: para no registrar lecturas de rutina sobre una máquina que está en el taller."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    orden = planta.orden(activo["id"])
    assert planta.pedir(planta.operario, "GET", "/ordenes").status_code == 403
    assert planta.pedir(planta.operario, "GET", f"/ordenes/{orden['id']}").status_code == 403
    ficha = planta.pedir(planta.operario, "GET", f"/activos/{activo['id']}").json()
    assert ficha["en_falla"] is True
    assert [o["numero"] for o in ficha["ordenes_abiertas"]] == [1]
    lista = planta.pedir(planta.operario, "GET", "/activos").json()["items"]
    assert lista[0]["en_falla"] is True


def test_el_listado_responde_304_si_nada_cambio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sección 9.4: la bandeja se consulta cada 30 segundos; casi siempre no hay nada nuevo."""
    planta = montar_planta(client, monkeypatch, "Planta")
    planta.orden(planta.nuevo_activo()["id"])
    primera = planta.pedir(planta.supervisor, "GET", "/ordenes?estado=abiertas")
    etag = primera.headers["etag"]
    igual = planta.pedir(
        planta.supervisor, "GET", "/ordenes?estado=abiertas", headers={"If-None-Match": etag}
    )
    assert igual.status_code == 304
    assert planta.pedir(planta.supervisor, "GET", "/ordenes?estado=cerradas").json()["items"] == []


# --- RF-14: quién hizo cada cosa ----------------------------------------------------------


def test_rf14_historial_muestra_quien_reporto_reparo_y_autorizo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con nombre y rol de cada responsable, también si después lo dieron de baja (5.2)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    planta.llevar_a_reparada(orden["id"])
    assert planta.mover(planta.supervisor, orden["id"], "cerrar").status_code == 200
    baja = planta.pedir(
        planta.admin, "PATCH", f"/usuarios/{planta.tecnico.id}", json={"activo": False}
    )
    assert baja.status_code == 200, baja.text

    detalle = planta.pedir(planta.gerente, "GET", f"/ordenes/{orden['id']}").json()
    assert detalle["reportado_por"]["nombre"] == "Supervisor"
    assert detalle["reparado_por"]["nombre"] == "Tecnico_Taller"
    assert detalle["reparado_por"]["activo"] is False
    assert detalle["autorizado_por"]["nombre"] == "Supervisor"
    pasos = [
        (e["usuario"]["nombre"], e["rol_al_momento"], e["estado_nuevo"]) for e in detalle["eventos"]
    ]
    assert pasos == [
        ("Supervisor", "supervisor", "reportada"),
        ("Tecnico_Taller", "tecnico_taller", "en_taller"),
        ("Tecnico_Taller", "tecnico_taller", "reparada"),
        ("Supervisor", "supervisor", "cerrada"),
    ]


def test_un_usuario_dado_de_baja_no_puede_mover_una_orden(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Su token de acceso aún vale hasta 30 minutos; la transición lo comprueba contra la base."""
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    planta.pedir(planta.admin, "PATCH", f"/usuarios/{planta.tecnico.id}", json={"activo": False})
    resp = planta.mover(planta.tecnico, orden["id"], "en-taller")
    assert resp.status_code in (401, 403)


# --- RF-15 y RF-16 --------------------------------------------------------------------------


def test_rf15_cierre_calcula_tiempo_fuera_de_servicio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De la falla a la autorización, en minutos de calendario (decisión 5)."""
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"], capturado_en=hace(minutes=90))
    planta.llevar_a_reparada(orden["id"])
    cerrada = planta.mover(planta.supervisor, orden["id"], "cerrar").json()
    assert cerrada["estado"] == "cerrada"
    assert 89 <= cerrada["tiempo_fuera_servicio_min"] <= 91
    assert cerrada["fecha_salida_taller"] is not None


def test_rf16_alerta_se_convierte_una_vez_y_vuelve_a_revisada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    otro = planta.nuevo_activo("Compresor 2")
    alerta = planta.alerta(activo["id"], "vibracion").json()["alerta"]

    # Una alerta de otro equipo no puede originar la orden de este.
    assert planta.falla(otro["id"], alerta_id=alerta["id"]).status_code == 422

    orden = planta.orden(activo["id"], alerta_id=alerta["id"])
    assert orden["alerta_origen_id"] == alerta["id"]
    estado = lambda: next(  # noqa: E731
        a["estado"]
        for a in planta.pedir(planta.supervisor, "GET", "/alertas").json()["items"]
        if a["id"] == alerta["id"]
    )
    assert estado() == "convertida_en_orden"
    # Una alerta origina como mucho una orden vigente.
    otra = planta.falla(
        activo["id"], componente_id=planta.componente("Rodamientos"), alerta_id=alerta["id"]
    )
    assert otra.status_code == 409 and otra.json()["detail"]["codigo"] == "alerta_no_disponible"

    planta.mover(planta.supervisor, orden["id"], "cancelar", motivo="Era otra máquina, no esta.")
    assert estado() == "revisada"


# --- Edición, corrección y horómetro ----------------------------------------------------------


def test_editar_una_orden_abierta_deja_evento_y_respeta_la_unica_abierta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso típico: se reportó con «Otro (por identificar)» y en el taller se supo qué era."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo()
    por_identificar = planta.componente("Otro (por identificar)")
    orden = planta.orden(activo["id"], componente_id=por_identificar)
    planta.orden(activo["id"], componente_id=planta.componente("Rodamientos"))

    choque = planta.pedir(
        planta.supervisor,
        "PATCH",
        f"/ordenes/{orden['id']}",
        json={"componente_id": planta.componente("Rodamientos")},
    )
    assert choque.status_code == 409
    assert choque.json()["detail"]["codigo"] == "orden_abierta_existente"

    resp = planta.pedir(
        planta.supervisor,
        "PATCH",
        f"/ordenes/{orden['id']}",
        json={"componente_id": planta.componente()},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["componente_nombre"] == "Motor"
    assert (
        resp.json()["eventos"][-1]["datos"]["cambios"]["componente_id"]["antes"] == por_identificar
    )
    # Ni el técnico ni el gerente editan; y nadie envía el estado por el cuerpo.
    assert (
        planta.pedir(
            planta.tecnico, "PATCH", f"/ordenes/{orden['id']}", json={"descripcion": "Cambiada"}
        ).status_code
        == 403
    )
    assert (
        planta.pedir(
            planta.supervisor, "PATCH", f"/ordenes/{orden['id']}", json={"estado": "cerrada"}
        ).status_code
        == 422
    )


def test_rnf06_correccion_solo_administrador_con_nota_y_evento(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    orden = planta.orden(planta.nuevo_activo()["id"])
    ruta = f"/ordenes/{orden['id']}/correccion"
    cuerpo = {"nota": "El técnico eligió el tipo equivocado.", "tipo_intervencion": "ajuste"}

    # Abierta: no se corrige, se edita.
    assert planta.pedir(planta.admin, "POST", ruta, json=cuerpo).status_code == 409

    planta.llevar_a_reparada(orden["id"], tipo="reemplazo")
    planta.mover(planta.supervisor, orden["id"], "cerrar")
    assert planta.pedir(planta.supervisor, "POST", ruta, json=cuerpo).status_code == 403
    assert (
        planta.pedir(planta.admin, "POST", ruta, json={"tipo_intervencion": "ajuste"}).status_code
        == 422
    )
    # Nunca estado, número, fechas ni responsables.
    assert planta.pedir(planta.admin, "POST", ruta, json={**cuerpo, "numero": 7}).status_code == 422

    resp = planta.pedir(planta.admin, "POST", ruta, json=cuerpo)
    assert resp.status_code == 200, resp.text
    corregida = resp.json()
    assert corregida["tipo_intervencion"] == "ajuste"
    assert corregida["estado"] == "cerrada"
    evento = corregida["eventos"][-1]
    assert evento["tipo"] == "correccion"
    assert evento["datos"]["cambios"]["tipo_intervencion"] == {
        "antes": "reemplazo",
        "despues": "ajuste",
    }
    assert evento["nota"] == cuerpo["nota"]
    # Una nota posterior al cierre es un evento nuevo, no una modificación.
    nota = planta.pedir(
        planta.tecnico, "POST", f"/ordenes/{orden['id']}/notas", json={"nota": "Revisar en 500 h."}
    )
    assert nota.status_code == 200
    assert nota.json()["eventos"][-1]["tipo"] == "nota"


def test_horometro_reinicio_conserva_las_horas_acumuladas(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sección 5.1: el dial vuelve a cero, las horas del equipo no."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo(horometro_inicial=1000)
    ruta = f"/activos/{activo['id']}/reinicio-horometro"
    assert planta.pedir(planta.supervisor, "POST", ruta, json={"nuevo": 0}).status_code == 403
    # Un «reinicio» a un número mayor que las horas acumuladas no puede ser un reinicio.
    assert planta.pedir(planta.admin, "POST", ruta, json={"nuevo": 1001}).status_code == 409

    # Una lectura capturada antes del reinicio que llega después (cola sin conexión)...
    vieja = {"capturado_en": hace(minutes=10)}
    resp = planta.pedir(planta.admin, "POST", ruta, json={"nuevo": 0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["horometro_offset"] == 1000
    assert resp.json()["horometro_actual"] == 0

    # ...queda marcada: medirla con el offset nuevo la mediría mal.
    tarde = planta.lectura(activo["id"], 1002, **vieja).json()["lectura"]
    assert tarde["requiere_revision"] is True

    orden = planta.orden(activo["id"], horometro=1)
    assert orden["horometro_en_falla"] == 1
    assert orden["horas_acumuladas_en_falla"] == 1001
    assert orden["requiere_revision"] is False
