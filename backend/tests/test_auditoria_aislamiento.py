"""Auditoría de aislamiento entre empresas (08-fase5, sección 11; RNF-01).

Dos auditorías que no usan listas escritas a mano, para que una tabla, vista o ruta nueva quede
cubierta sola:

1. **Catálogo** (11.2): lee `pg_class`, `pg_policy`, `pg_proc`, `pg_roles` y los privilegios,
   y aplica los controles C1–C13 de la guía. No toca datos.
2. **Rutas de la API** (11.3): recorre las rutas registradas en la aplicación.
   - Sin credenciales, toda ruta no pública responde 401.
   - Con cada persona de la empresa A y los recursos de la empresa B, la respuesta debe ser
     **indistinguible** de la que da un identificador que no existe (mismo estado, nunca 2xx) y no
     contener ninguna marca de los datos de B. Un 403 que solo aparece con el recurso de B
     confirmaría que existe; uno de rol, igual para los dos, no.

El plano de control (`/operador`) no es de ningún tenant: tiene sus propias pruebas.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import app
from tests.conftest import URL_SUPER, requiere_base
from tests.planta import Planta, montar_planta

pytestmark = requiere_base

#: Tablas sin `empresa_id` por diseño: la propia `empresas`, el plano de control y la bitácora de
#: intentos de acceso (que es por correo, antes de saber la empresa).
GLOBALES = {"empresas", "operadores", "intentos_login", "alembic_version"}
#: Funciones SECURITY DEFINER autorizadas (C7).
DEFINER_AUTORIZADAS = {"empresas_activas"}
#: Tablas de solo agregar (C10).
SOLO_AGREGAR = {"orden_eventos", "stock_movimientos", "modelos_historial", "operador_bitacora"}
ROLES_APP = ("app_user", "job_user")


def _consultar(sql: str) -> list[Any]:
    async def correr() -> list[Any]:
        motor = create_async_engine(URL_SUPER)
        try:
            async with motor.connect() as conn:
                return list((await conn.execute(text(sql))).fetchall())
        finally:
            await motor.dispose()

    return asyncio.run(correr())


def _tablas_de_empresa() -> set[str]:
    return {
        f[0]
        for f in _consultar(
            "SELECT c.relname FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid"
            " WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
            " AND a.attname = 'empresa_id' AND NOT a.attisdropped"
        )
    }


# --- Catálogo -------------------------------------------------------------------------------------


def test_rnf01_c1_toda_tabla_de_negocio_tiene_empresa_id_no_nulo() -> None:
    tablas = {
        f[0]
        for f in _consultar(
            "SELECT relname FROM pg_class WHERE relkind = 'r'"
            " AND relnamespace = 'public'::regnamespace"
        )
    }
    sin_columna = tablas - _tablas_de_empresa() - GLOBALES
    assert sin_columna == set()
    nulas = _consultar(
        "SELECT c.table_name FROM information_schema.columns c"
        " JOIN information_schema.tables t ON t.table_name = c.table_name"
        " AND t.table_schema = c.table_schema AND t.table_type = 'BASE TABLE'"
        " WHERE c.table_schema = 'public' AND c.column_name = 'empresa_id' AND c.is_nullable ="
        " 'YES'"
        " AND c.table_name NOT IN ('operador_bitacora')"
    )
    assert nulas == []


def test_rnf01_c2_rls_activa_y_forzada() -> None:
    malas = _consultar(
        "SELECT c.relname FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid"
        " WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
        " AND a.attname = 'empresa_id' AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"
    )
    assert malas == []


def test_rnf01_c3_toda_politica_de_la_aplicacion_filtra_por_app_empresa_id() -> None:
    """Las políticas de `app_user` (o de PUBLIC) filtran con `app_empresa_id()` en USING y en WITH
    CHECK. Las del operador y la del job sobre `empresas` son de otros roles y se revisan aparte."""
    filas = _consultar(
        "SELECT c.relname, p.polname, pg_get_expr(p.polqual, p.polrelid),"
        " pg_get_expr(p.polwithcheck, p.polrelid), p.polroles::regrole[]::text"
        " FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid"
        " WHERE c.relnamespace = 'public'::regnamespace"
    )
    sin_politica = _tablas_de_empresa() - {f[0] for f in filas}
    assert sin_politica == set()
    for tabla, nombre, usando, chequeo, roles in filas:
        if "app_user" not in roles and "public" not in roles:
            continue
        for expr in (usando, chequeo):
            if expr is not None:
                assert "app_empresa_id()" in expr, (tabla, nombre, expr)


def test_rnf01_c5_toda_fk_entre_tablas_de_empresa_incluye_empresa_id() -> None:
    filas = _consultar(
        "SELECT c.conname, t.relname, r.relname,"
        " ARRAY(SELECT attname FROM pg_attribute WHERE attrelid = c.conrelid AND attnum ="
        " ANY(c.conkey))"
        " FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_class r ON r.oid ="
        " c.confrelid"
        " WHERE c.contype = 'f' AND t.relnamespace = 'public'::regnamespace"
    )
    empresa = _tablas_de_empresa()
    for nombre, tabla, referida, columnas in filas:
        if tabla in empresa and referida in empresa:
            assert "empresa_id" in columnas, (nombre, tabla, referida, columnas)


def test_rnf01_c6_c11_vistas_con_security_invoker_y_sin_escritura() -> None:
    sin_invoker = _consultar(
        "SELECT relname FROM pg_class WHERE relkind = 'v' AND relnamespace = 'public'::regnamespace"
        " AND NOT COALESCE(reloptions::text LIKE '%security_invoker=true%', false)"
    )
    assert sin_invoker == []
    escritura = _consultar(
        "SELECT p.table_name, p.grantee, p.privilege_type FROM"
        " information_schema.table_privileges p"
        " JOIN information_schema.views v ON v.table_name = p.table_name AND v.table_schema ="
        " 'public'"
        " WHERE p.grantee IN ('app_user', 'job_user') AND p.privilege_type <> 'SELECT'"
    )
    assert escritura == []


def test_rnf01_c7_funciones_security_definer_autorizadas_con_search_path_y_sin_public() -> None:
    filas = _consultar(
        "SELECT p.proname, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE')"
        " FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND p.prosecdef"
    )
    for nombre, config, publica in filas:
        assert nombre in DEFINER_AUTORIZADAS, nombre
        assert config and any(c.startswith("search_path=") for c in config), nombre
        assert not publica, nombre
    assert not _consultar(
        "SELECT has_function_privilege('app_user', 'empresas_activas()', 'EXECUTE')"
    )[0][0]


def test_rnf01_c8_c9_roles_de_la_aplicacion_sin_privilegios_ni_propiedad() -> None:
    roles = _consultar(
        "SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles"
        " WHERE rolname IN ('app_user', 'job_user')"
    )
    assert len(roles) == 2
    for nombre, *privilegios in roles:
        assert not any(privilegios), nombre
    duenos = _consultar(
        "SELECT c.relname, r.rolname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner"
        " WHERE c.relnamespace = 'public'::regnamespace AND r.rolname IN ('app_user', 'job_user')"
    )
    assert duenos == []


def test_rnf01_c10_tablas_de_solo_agregar_y_ordenes_sin_borrado() -> None:
    filas = _consultar(
        "SELECT table_name, privilege_type FROM information_schema.table_privileges"
        " WHERE grantee = 'app_user' AND ("
        f" (table_name IN ({', '.join(repr(t) for t in SOLO_AGREGAR)})"
        "   AND privilege_type IN ('UPDATE', 'DELETE'))"
        " OR (table_name = 'ordenes_trabajo' AND privilege_type = 'DELETE'))"
    )
    assert filas == []


def test_rnf01_c12_nada_para_public_y_c13_app_empresa_id_estable() -> None:
    publicos = _consultar(
        "SELECT table_name, privilege_type FROM information_schema.table_privileges"
        " WHERE grantee = 'PUBLIC' AND table_schema = 'public'"
    )
    assert publicos == []
    [(volatilidad,)] = _consultar(
        "SELECT provolatile::text FROM pg_proc WHERE proname = 'app_empresa_id'"
    )
    assert volatilidad == "s"


# --- Rutas de la API ------------------------------------------------------------------------------

#: Rutas que se usan sin sesión a propósito.
PUBLICAS = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/operador/login"),
    ("POST", "/api/v1/operador/logout"),
}
PARAMETRO = re.compile(r"{(\w+)}")


def _rutas() -> list[tuple[str, str]]:
    return sorted(
        (metodo, r.path)
        for r in app.routes
        if isinstance(r, APIRoute)
        for metodo in r.methods
        if metodo not in ("HEAD", "OPTIONS")
    )


def test_rnf01_toda_ruta_no_publica_exige_sesion(client: TestClient) -> None:
    client.cookies.clear()
    hallazgos = []
    for metodo, ruta in _rutas():
        if (metodo, ruta) in PUBLICAS:
            continue
        url = PARAMETRO.sub(lambda m: "ABCD2345" if m.group(1) == "codigo" else str(uuid4()), ruta)
        resp = client.request(metodo, url, json={})
        if resp.status_code != 401:
            hallazgos.append((metodo, ruta, resp.status_code))
    assert hallazgos == []


def _recursos_de_b(b: Planta, marca: str) -> dict[str, str]:
    """Un recurso de cada tipo en la empresa B, todos con la marca en su texto."""
    activo = b.nuevo_activo(f"Equipo {marca}", horometro_inicial=100)
    comp = b.componente("Motor")
    lectura = b.lectura(activo["id"], 110).json()
    alerta = b.alerta(activo["id"], nota=f"Nota {marca}").json()
    orden = b.falla(activo["id"]) if hasattr(b, "falla") else None
    repuesto = b.pedir(
        b.admin, "POST", "/repuestos", json={"nombre": f"Repuesto {marca}", "codigo": marca[:20]}
    ).json()
    sistema = uuid4()

    async def alerta_sistema() -> None:
        motor = create_async_engine(URL_SUPER)
        try:
            async with motor.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO alertas_sistema (id, empresa_id, tipo, repuesto_id,"
                        " stock_al_alertar,"
                        " stock_minimo_al_alertar) VALUES (:i, :e, 'reorden', :r, 0, 1)"
                    ),
                    {"i": sistema, "e": b.empresa_id, "r": repuesto["id"]},
                )
        finally:
            await motor.dispose()

    asyncio.run(alerta_sistema())
    orden_id = orden.json()["orden"]["id"] if orden is not None else str(uuid4())
    return {
        "activo_id": activo["id"],
        "codigo": activo["codigo"],
        "componente_id": comp,
        "lectura_id": lectura["lectura"]["id"]
        if "lectura" in lectura
        else lectura.get("id", str(uuid4())),
        "alerta_id": alerta["alerta"]["id"]
        if "alerta" in alerta
        else alerta.get("id", str(uuid4())),
        "alerta_sistema_id": str(sistema),
        "orden_id": orden_id,
        "repuesto_id": repuesto["id"],
        "usuario_id": str(b.operario.id),
    }


def _url(ruta: str, ids: dict[str, str]) -> str:
    def poner(m: re.Match[str]) -> str:
        nombre = m.group(1)
        if nombre == "alerta_id" and "/alertas-sistema/" in ruta:
            nombre = "alerta_sistema_id"
        return ids[nombre]

    return PARAMETRO.sub(poner, ruta)


def test_rnf01_ninguna_ruta_distingue_un_recurso_de_otra_empresa_de_uno_inexistente(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = montar_planta(client, monkeypatch, "Planta A")
    b = montar_planta(client, monkeypatch, "Planta B")
    marca = f"MARCA-B-{uuid4().hex[:8]}"
    de_b = _recursos_de_b(b, marca)
    inexistentes = {k: ("ZZZZ2345" if k == "codigo" else str(uuid4())) for k in de_b}
    personas = [a.admin, a.supervisor, a.operario, a.gerente, a.tecnico]
    hallazgos = []
    for metodo, ruta in _rutas():
        if not PARAMETRO.search(ruta) or ruta.startswith("/api/v1/operador"):
            continue
        for persona in personas:
            con_b = a.pedir(persona, metodo, _url(ruta, de_b).removeprefix("/api/v1"), json={})
            sin = a.pedir(
                persona, metodo, _url(ruta, inexistentes).removeprefix("/api/v1"), json={}
            )
            if con_b.status_code != sin.status_code or 200 <= con_b.status_code < 300:
                hallazgos.append(
                    (metodo, ruta, persona.correo.split("-")[0], con_b.status_code, sin.status_code)
                )
            if marca in con_b.text:
                hallazgos.append((metodo, ruta, "fuga_de_datos", con_b.status_code, 0))
    assert hallazgos == []
