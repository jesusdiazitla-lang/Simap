"""Paneles por rol e indicadores contra PostgreSQL real (08-fase5, 6, 8 y 12; RF-27, RF-28).

- Cada rol recibe sus widgets; sin sesión 401; los roles sin derecho, 403; un periodo inválido, 422.
- Empresa y usuario salen de la sesión: mandarlos en la petición no cambia nada.
- Un indicador calculado a mano sobre datos sembrados con fechas conocidas.
- RNF-02: con el cálculo de riesgo «caído» (sin permiso sobre la vista) solo esos widgets se
  degradan, la pantalla no recibe el texto del error y una lectura se sigue registrando.
- La revisión 0011: horas acumuladas por trigger (marcada, confirmada, reinicio, captura tardía),
  `v_paradas` con `security_invoker`, vistas sin escritura y JIT apagado para los roles.
- La corrección del cierre predictivo (decisión 10).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.ordenes_estados import inicio_de_parada
from app.services.paneles.indicadores import TZ_PLATAFORMA
from tests.conftest import URL_SUPER, requiere_base
from tests.planta import Planta, montar_planta

pytestmark = requiere_base


def _super(sentencias: Iterable[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Ejecuta como superusuario: siembra datos con fechas conocidas y cambia permisos de prueba."""

    async def correr() -> list[Any]:
        motor = create_async_engine(URL_SUPER)
        resultados = []
        try:
            async with motor.begin() as conn:
                for sql, params in sentencias:
                    resultado = await conn.execute(text(sql), params)
                    resultados.append(resultado.fetchall() if resultado.returns_rows else None)
        finally:
            await motor.dispose()
        return resultados

    return asyncio.run(correr())


def panel(planta: Planta, quien: Any, **params: str) -> dict[str, Any]:
    resp = planta.pedir(quien, "GET", "/panel", params=params)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def sd(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ_PLATAFORMA)


# --- Rutas, roles y periodo -----------------------------------------------------------------------


def test_rf27_cada_rol_recibe_sus_widgets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    esperado = [
        (planta.operario, {"mis_lecturas", "mis_alertas"}),
        (planta.tecnico, {"cola_taller", "mis_trabajos"}),
        (planta.supervisor, {"contadores", "alertas_campo", "alertas_sistema", "ordenes_abiertas"}),
        (planta.gerente, {"indicadores", "repuestos_costo", "riesgo_top", "riesgo_cobertura"}),
    ]
    for persona, widgets in esperado:
        datos = panel(planta, persona)
        assert set(datos["widgets"]) == widgets
        assert datos["degradados"] == []
    admin = panel(planta, planta.admin)
    assert len(admin["widgets"]) == 9 and "salud" in admin["widgets"]


def test_rf27_sin_sesion_401_y_roles_sin_derecho_403(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    client.cookies.clear()
    for ruta in ("/api/v1/panel", "/api/v1/indicadores", "/api/v1/plantas"):
        assert client.get(ruta).status_code == 401
        assert client.get(ruta, headers={"Authorization": "Bearer inventado"}).status_code == 401
    for quien in (planta.operario, planta.supervisor, planta.tecnico):
        assert planta.pedir(quien, "GET", "/indicadores").status_code == 403
    for quien in (planta.operario, planta.tecnico):
        assert planta.pedir(quien, "GET", "/plantas").status_code == 403
    assert planta.pedir(planta.gerente, "GET", "/indicadores").status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"desde": "2026-09-01", "hasta": "2026-08-01"},
        {"desde": "2023-01-01", "hasta": "2026-09-30"},
        {"desde": "no-es-fecha"},
        {"planta": "x" * 81},
    ],
)
def test_periodo_o_planta_invalidos_son_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, str]
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    assert planta.pedir(planta.gerente, "GET", "/panel", params=params).status_code == 422


def test_rf27_empresa_y_usuario_salen_de_la_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El operario ve sus lecturas y no las de un compañero; mandar `empresa_id` o `usuario_id` en
    la URL no cambia nada; otra empresa no ve nada de esta."""
    a = montar_planta(client, monkeypatch, "Planta A")
    b = montar_planta(client, monkeypatch, "Planta B")
    activo = a.nuevo_activo("Prensa", horometro_inicial=100)
    assert a.lectura(activo["id"], 110).status_code in (200, 201)
    assert a.lectura(activo["id"], 120, quien=a.supervisor).status_code in (200, 201)
    assert a.alerta(activo["id"]).status_code in (200, 201)

    propias = panel(a, a.operario)["widgets"]["mis_lecturas"]["datos"]
    assert [x["valor"] for x in propias] == [110]
    intento = panel(a, a.operario, empresa_id=str(b.empresa_id), usuario_id=str(a.supervisor.id))[
        "widgets"
    ]["mis_lecturas"]["datos"]
    assert intento == propias
    assert panel(b, b.supervisor)["widgets"]["alertas_campo"]["datos"] == []
    assert panel(a, a.supervisor)["widgets"]["contadores"]["datos"]["alertas_campo"] == 1


# --- Indicadores calculados a mano ----------------------------------------------------------------


def _sembrar_historia(planta: Planta) -> str:
    """Un equipo observado desde el 1 de agosto (Santo Domingo), una falla de 48 h en agosto, una
    predictiva que esperó cuatro días su ventana y paró 24 h en septiembre, y tres lecturas."""
    activo = planta.nuevo_activo(f"Bomba {uuid4().hex[:4]}", ubicacion="Nave 9")
    comp = planta.componente("Motor")
    e, quien = planta.empresa_id, planta.supervisor.id
    orden = (
        "INSERT INTO ordenes_trabajo (id, empresa_id, numero, activo_id, componente_id,"
        " reportado_por, horometro_en_falla, horas_acumuladas_en_falla, descripcion, fecha_falla,"
        " estado, reparado_por, trabajo_realizado, tipo_intervencion, autorizado_por, en_taller_en,"
        " fecha_salida_taller, tiempo_fuera_servicio_min, es_predictiva)"
        " VALUES (:id, :e, :n, :a, :c, :u, 1000, 1000, 'Falla sembrada en la prueba', :falla,"
        " 'cerrada', :u, 'Trabajo hecho en la prueba.', 'reemplazo', :u, :taller, :salida, 0,"
        " :pred)"
    )
    lectura = (
        "INSERT INTO lecturas_horometro (empresa_id, activo_id, registrado_por, valor_horometro,"
        " capturado_en, fecha) VALUES (:e, :a, :u, :v, :t, :t)"
    )
    comun = {"e": e, "a": activo["id"], "c": comp, "u": quien}
    _super(
        [
            (
                "UPDATE activos SET creado_en = :t WHERE id = :a",
                {"t": sd(2026, 8, 1), "a": activo["id"]},
            ),
            (
                orden,
                {
                    **comun,
                    "id": uuid4(),
                    "n": 901,
                    "falla": sd(2026, 8, 10),
                    "taller": sd(2026, 8, 10, 1),
                    "salida": sd(2026, 8, 12),
                    "pred": False,
                },
            ),
            (
                orden,
                {
                    **comun,
                    "id": uuid4(),
                    "n": 902,
                    "falla": sd(2026, 9, 1),
                    "taller": sd(2026, 9, 5),
                    "salida": sd(2026, 9, 6),
                    "pred": True,
                },
            ),
            (lectura, {**comun, "v": 1000, "t": sd(2026, 8, 1, 1)}),
            # Justo en el límite de mes: es de septiembre (comparación estricta).
            (lectura, {**comun, "v": 1300, "t": sd(2026, 9, 1)}),
            (lectura, {**comun, "v": 1500, "t": sd(2026, 9, 20)}),
        ]
    )
    return str(activo["id"])


def test_rf28_indicadores_coinciden_con_el_calculo_a_mano(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    _sembrar_historia(planta)
    resp = planta.pedir(
        planta.gerente,
        "GET",
        "/indicadores",
        params={"desde": "2026-08-01", "hasta": "2026-09-30", "planta": "Nave 9"},
    )
    assert resp.status_code == 200, resp.text
    datos = resp.json()["widgets"]["indicadores"]["datos"]
    r = datos["resumen"]
    calendario = (31 + 30) * 24
    assert r["horas_calendario"] == pytest.approx(calendario)
    assert r["paradas_total_h"] == pytest.approx(72)
    assert r["paradas_falla_h"] == pytest.approx(48)
    assert r["paradas_planificadas_h"] == pytest.approx(24)
    assert r["disponibilidad"] == pytest.approx(1 - 72 / calendario, abs=1e-6)
    assert r["disponibilidad_sin_planificadas"] == pytest.approx(1 - 48 / calendario, abs=1e-6)
    assert (r["fallas"], r["fallas_cerradas"], r["planificadas_cerradas"]) == (1, 1, 1)
    assert r["mttr_h"] == pytest.approx(48)
    assert r["horas_operadas"] == 500
    assert r["mtbf_h"] == pytest.approx(500)
    assert [m["horas_operadas"] for m in datos["meses"]] == [0, 500]
    # Sin `Decimal` ni fechas crudas en el JSON.
    assert isinstance(r["costo_total"], str) and datos["desde"].startswith(
        "2026-08-01T00:00:00-04:00"
    )


# --- RNF-02 ---------------------------------------------------------------------------------------


def test_si_el_calculo_de_riesgo_falla_el_resto_del_panel_responde(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Compresor", horometro_inicial=10)
    _super([("REVOKE SELECT ON v_riesgo_activo FROM app_user", {})])
    try:
        resp = planta.pedir(planta.gerente, "GET", "/panel")
        assert resp.status_code == 200
        datos = resp.json()
        assert set(datos["degradados"]) == {"riesgo_top", "riesgo_cobertura"}
        assert datos["widgets"]["indicadores"]["estado"] == "ok"
        assert "permission" not in resp.text and "v_riesgo_activo" not in resp.text
        # El registro de lecturas no depende del cálculo de riesgo.
        assert planta.lectura(activo["id"], 20).status_code in (200, 201)
    finally:
        _super([("GRANT SELECT ON v_riesgo_activo TO app_user", {})])
    assert panel(planta, planta.gerente)["degradados"] == []


# --- Revisión 0011 --------------------------------------------------------------------------------


def test_horas_acumuladas_las_mantiene_el_trigger(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Marcada: sin horas. Confirmada: con horas. Reinicio: su propio offset. Una lectura capturada
    antes de un reinicio y llegada después: el offset de su momento, no el de hoy."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Torno", horometro_inicial=0)
    e, a, u = planta.empresa_id, activo["id"], planta.operario.id
    base = datetime.now(UTC) - timedelta(days=10)
    insertar = (
        "INSERT INTO lecturas_horometro (id, empresa_id, activo_id, registrado_por,"
        " valor_horometro,"
        " capturado_en, fecha, requiere_revision, motivo_revision, es_reinicio, offset_resultante)"
        " VALUES (:id, :e, :a, :u, :v, :t, :t, :rev, :motivo, :reinicio, :offset)"
    )
    ids = [uuid4() for _ in range(4)]

    def fila(
        i: int,
        v: int,
        dias: float,
        rev: bool = False,
        reinicio: bool = False,
        offset: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return insertar, {
            "id": ids[i],
            "e": e,
            "a": a,
            "u": u,
            "v": v,
            "t": base + timedelta(days=dias),
            "rev": rev,
            "motivo": "Prueba." if rev else None,
            "reinicio": reinicio,
            "offset": offset,
        }

    _super(
        [
            fila(0, 500, 1, rev=True),
            fila(1, 10, 5, reinicio=True, offset=4000),
            fila(2, 30, 6),
            fila(3, 900, 3),
        ]
    )

    def horas() -> dict[Any, Any]:
        sql = "SELECT id, horas_acumuladas FROM lecturas_horometro WHERE id = ANY(:ids)"
        return dict(_super([(sql, {"ids": ids})])[0])

    antes = horas()
    assert antes[ids[0]] is None
    assert (antes[ids[1]], antes[ids[2]], antes[ids[3]]) == (4010, 4030, 900)
    _super(
        [("UPDATE lecturas_horometro SET resolucion = 'confirmada' WHERE id = :i", {"i": ids[0]})]
    )
    assert horas()[ids[0]] == 500


def test_vistas_de_solo_lectura_con_security_invoker_y_jit_apagado() -> None:
    [opciones, escritura, roles] = _super(
        [
            (
                "SELECT relname, reloptions FROM pg_class WHERE relkind = 'v' AND relnamespace ="
                " 'public'::regnamespace",
                {},
            ),
            (
                "SELECT table_name, privilege_type FROM information_schema.table_privileges"
                " WHERE grantee = 'app_user' AND table_name IN ('v_paradas', 'v_vidas',"
                " 'v_riesgo_activo')"
                " AND privilege_type <> 'SELECT'",
                {},
            ),
            (
                "SELECT rolname, rolconfig FROM pg_roles WHERE rolname IN ('app_user', 'job_user')",
                {},
            ),
        ]
    )
    vistas = dict(opciones)
    assert "v_paradas" in vistas
    for nombre, reloptions in vistas.items():
        assert reloptions and "security_invoker=true" in reloptions, nombre
    assert escritura == []
    for rol, config in roles:
        assert config and "jit=off" in config, rol


def test_v_paradas_respeta_rls(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    a = montar_planta(client, monkeypatch, "Planta A")
    b = montar_planta(client, monkeypatch, "Planta B")
    _sembrar_historia(b)

    async def contar() -> int:
        from tests.base_ordenes import fijar, motor_app

        motor = motor_app()
        try:
            async with motor.connect() as conn:
                await fijar(conn, a.empresa_id)
                return int(await conn.scalar(text("SELECT count(*) FROM v_paradas")) or 0)
        finally:
            await motor.dispose()

    assert asyncio.run(contar()) == 0


# --- Decisión 10 ----------------------------------------------------------------------------------


def test_cierre_de_predictiva_mide_desde_la_entrada_al_taller() -> None:
    falla, taller = sd(2026, 9, 1), sd(2026, 9, 5)
    predictiva = SimpleNamespace(es_predictiva=True, en_taller_en=taller, fecha_falla=falla)
    sin_taller = SimpleNamespace(es_predictiva=True, en_taller_en=None, fecha_falla=falla)
    de_falla = SimpleNamespace(es_predictiva=False, en_taller_en=taller, fecha_falla=falla)
    assert inicio_de_parada(predictiva) == taller  # type: ignore[arg-type]
    assert inicio_de_parada(sin_taller) == falla  # type: ignore[arg-type]
    assert inicio_de_parada(de_falla) == falla  # type: ignore[arg-type]


def test_rf28_el_administrador_solo_puede_adelantar_desde_cuando_se_observa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decisión 8: adelantar la fecha carga historia de antes de usar SIMAP; posponerla o ponerla en
    el futuro escondería horas de calendario y subiría la disponibilidad sin que nada mejorara."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Molino", horometro_inicial=10)
    ruta = f"/activos/{activo['id']}"
    antes = datetime.now(UTC) - timedelta(days=90)
    resp = planta.pedir(planta.admin, "PATCH", ruta, json={"observado_desde": antes.isoformat()})
    assert resp.status_code == 200, resp.text
    assert datetime.fromisoformat(resp.json()["creado_en"]) == antes
    despues = (antes + timedelta(days=30)).isoformat()
    futuro = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    for valor in (despues, futuro):
        r = planta.pedir(planta.admin, "PATCH", ruta, json={"observado_desde": valor})
        assert r.status_code == 422
    assert (
        planta.pedir(
            planta.supervisor, "PATCH", ruta, json={"observado_desde": antes.isoformat()}
        ).status_code
        == 403
    )


def test_reinicio_resuelto_despues_recalcula_las_lecturas_posteriores(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revisión del 2026-10-29: un equipo en 100 h se reinicia; llegan 5 h y 20 h, las dos marcadas.
    Se confirma primero la de 20 h (todavía sin reinicio: 20) y después la de 5 h se registra como
    reinicio (offset 95). La de 20 h tiene que pasar a 115; antes se quedaba en 20 y el mes perdía
    horas que el siguiente ganaba."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Prensa", horometro_inicial=100)
    cinco = planta.lectura(activo["id"], 5).json()["lectura"]
    veinte = planta.lectura(activo["id"], 20).json()["lectura"]
    assert cinco["requiere_revision"] and veinte["requiere_revision"]
    ruta = "/lecturas/{}"
    r = planta.pedir(
        planta.supervisor, "PATCH", ruta.format(veinte["id"]), json={"resolucion": "confirmada"}
    )
    assert r.status_code == 200, r.text
    r = planta.pedir(
        planta.admin, "PATCH", ruta.format(cinco["id"]), json={"resolucion": "reinicio"}
    )
    assert r.status_code == 200, r.text
    sql = "SELECT id::text, horas_acumuladas FROM lecturas_horometro WHERE activo_id = :a"
    horas = dict(_super([(sql, {"a": activo["id"]})])[0])
    assert horas[cinco["id"]] == 100
    assert horas[veinte["id"]] == 115


def test_dato_anterior_al_alta_adelanta_desde_cuando_se_observa(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revisión del 2026-10-29 (decisión 8): la API acepta lecturas y fallas de hasta 14 días atrás
    en un equipo recién dado de alta. La observación empieza con el primer dato conocido; si no,
    las horas operadas caen fuera de las de calendario y la parada de la falla se recorta."""
    planta = montar_planta(client, monkeypatch, "Planta")
    activo = planta.nuevo_activo("Bomba", horometro_inicial=10)

    def observado() -> datetime:
        datos = planta.pedir(planta.admin, "GET", f"/activos/{activo['id']}").json()
        return datetime.fromisoformat(datos["creado_en"])

    alta = observado()
    lectura = datetime.now(UTC) - timedelta(days=10)
    r = planta.lectura(activo["id"], 12, capturado_en=lectura.isoformat())
    assert r.status_code in (200, 201), r.text
    assert observado() == lectura < alta
    falla = datetime.now(UTC) - timedelta(days=12)
    r = planta.falla(activo["id"], horometro=11, capturado_en=falla.isoformat())
    assert r.status_code == 201, r.text
    assert observado() == falla
    # Un dato posterior no la mueve.
    planta.lectura(activo["id"], 30)
    assert observado() == falla
