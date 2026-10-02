"""El plano de control y su frontera con el plano de datos.

Las pruebas de este archivo no comprueban que la consola del operador funcione —eso lo hacen las de
sesión al final— sino que **no pueda hacer lo que no debe**. Es la misma idea que
`test_aislamiento_tenant.py`: una separación que solo existe en la intención del código no es una
separación, así que aquí se comprueba contra PostgreSQL de verdad.

Las cuatro afirmaciones que sostienen el diseño:

1. `operador_user` no puede leer los usuarios de planta de ninguna empresa, solo administradores.
2. `app_user` —el rol que atiende a los clientes— no puede leer la tabla de operadores ni la
   bitácora, así que un fallo en el plano de datos no expone quién opera SIMAP.
3. El token de un usuario de empresa no abre la consola, y el de un operador no abre la API de
   cliente.
4. Los permisos del rol del operador se conceden tabla por tabla: una tabla nueva de negocio queda
   fuera de su alcance sin que nadie tenga que acordarse de nada.
"""

import asyncio
import io
import sys
from collections.abc import Awaitable, Iterator
from typing import TypeVar
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.almacen import AlmacenMemoria, get_almacen
from app.core.auth import (
    COOKIE_ACCESO,
    COOKIE_OPERADOR_ACCESO,
    COOKIE_PISTA_OPERADOR,
    COOKIE_PISTA_SESION,
)
from app.core.config import get_settings
from app.db.session import (
    get_engine,
    get_engine_operador,
    get_estrategia_tenant,
    get_sessionmaker,
    get_sessionmaker_operador,
)
from app.main import app
from tests.conftest import URL_APP, URL_DUENO, dar_de_alta, requiere_base

T = TypeVar("T")

#: El rol del plano de control. Ni superusuario, ni dueño de las tablas, ni app_user.
URL_OPERADOR = "postgresql+asyncpg://operador_user:changeme_operador@localhost:5432/simap"

PASSWORD_OPERADOR = "contrasena-larga-de-operador"
PASSWORD_USUARIO = "contrasena-larga-de-prueba"

pytestmark = requiere_base


def _correr(corutina: Awaitable[T]) -> T:
    return asyncio.run(corutina)  # type: ignore[arg-type]


def _limpiar_motores() -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_estrategia_tenant.cache_clear()
    get_engine_operador.cache_clear()
    get_sessionmaker_operador.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()
    # TestClient abre un bucle de eventos nuevo en cada test y asyncpg no sobrevive a que se
    # reutilicen sus conexiones entre bucles distintos. Ver tests/test_auth.py.
    _limpiar_motores()

    almacen = AlmacenMemoria()
    app.dependency_overrides[get_almacen] = lambda: almacen
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpiar_motores()
    get_settings.cache_clear()


def _crear_operador(monkeypatch: pytest.MonkeyPatch) -> str:
    """Siembra un operador por el camino real: el comando de consola."""
    from app import cli

    correo = f"op-{uuid4().hex}@simap.do"
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{PASSWORD_OPERADOR}\n"))
    salida = cli.main(
        ["crear-operador", "--nombre", "Operador de prueba", "--correo", correo, "--password-stdin"]
    )
    assert salida == 0
    return correo


def _entrar_como_operador(client: TestClient, correo: str) -> httpx.Response:
    return client.post(
        "/api/v1/operador/login", json={"correo": correo, "password": PASSWORD_OPERADOR}
    )


# --- 1. Lo que el operador NO puede ver --------------------------------------


async def _leer_como(url: str, sql: str) -> list[object] | str:
    """Ejecuta una consulta con el rol de la URL. Devuelve las filas, o el error si lo hubo."""
    motor = create_async_engine(url)
    try:
        async with motor.begin() as conn:
            filas = await conn.execute(text(sql))
            return list(filas.scalars().all())
    except Exception as exc:  # noqa: BLE001 - el mensaje del error ES el resultado
        return type(exc).__name__
    finally:
        await motor.dispose()


def test_el_operador_no_ve_al_personal_de_planta() -> None:
    """Solo administradores. Un operario o un supervisor no son asunto del plano de control.

    Se siembra un operario con el rol dueño (que sí puede) y se comprueba que el rol del operador
    no lo encuentra, aunque tenga GRANT SELECT sobre la tabla: lo tapa su política RLS.
    """

    async def sembrar_operario() -> str:
        correo = f"{uuid4().hex}@planta.example.com"
        # El id se genera aquí y NO se pide con RETURNING. Con `RETURNING`, PostgreSQL aplica
        # además la política de LECTURA a la fila devuelta, y `tenant_isolation_empresas` la
        # oculta mientras no haya tenant fijado: el INSERT se hace y aun así la sentencia falla.
        # Es la misma razón por la que el ORM funciona aquí, porque genera el UUID en Python.
        empresa_id = uuid4()
        motor = create_async_engine(URL_DUENO)
        try:
            async with motor.begin() as conn:
                await conn.execute(
                    text("INSERT INTO empresas (id, nombre) VALUES (:i, :n)"),
                    {"i": empresa_id, "n": f"Planta {uuid4().hex[:8]}"},
                )
                await conn.execute(
                    text("SELECT set_config('app.empresa_id', :v, true)"),
                    {"v": str(empresa_id)},
                )
                await conn.execute(
                    text(
                        "INSERT INTO usuarios (empresa_id, nombre, correo, password_hash, rol)"
                        " VALUES (:e, 'Un operario', :c, 'x', 'operario')"
                    ),
                    {"e": empresa_id, "c": correo},
                )
        finally:
            await motor.dispose()
        return correo

    correo = _correr(sembrar_operario())
    visibles = _correr(
        _leer_como(URL_OPERADOR, f"SELECT correo FROM usuarios WHERE correo = '{correo}'")
    )
    assert visibles == [], "el plano de control no debe ver al personal de planta"

    # Y para que la prueba no pase por accidente: el mismo rol SÍ ve a los administradores.
    admins = _correr(
        _leer_como(URL_OPERADOR, "SELECT correo FROM usuarios WHERE rol = 'administrador' LIMIT 1")
    )
    assert isinstance(admins, list) and len(admins) == 1


def test_el_rol_de_los_clientes_no_ve_el_plano_de_control() -> None:
    """Un fallo en la API de clientes no puede exponer quién opera SIMAP ni la bitácora.

    `app_user` no tiene GRANT sobre esas tablas, así que PostgreSQL rechaza la consulta antes
    incluso de mirar las políticas.
    """
    for tabla in ("operadores", "operador_bitacora"):
        resultado = _correr(_leer_como(URL_APP, f"SELECT id FROM {tabla}"))
        assert isinstance(resultado, str), (
            f"app_user pudo leer {tabla}; el plano de control queda expuesto"
        )


def test_el_operador_no_puede_leer_los_intentos_de_login() -> None:
    """Ejemplo concreto de la regla de permisos tabla por tabla.

    `intentos_login` no es una tabla del plano de control y nadie le concedió permiso sobre ella,
    así que el operador no la ve. Lo mismo valdrá para activos, órdenes y lecturas cuando existan:
    quedan fuera **por omisión**, sin que nadie tenga que acordarse de excluirlas.
    """
    resultado = _correr(_leer_como(URL_OPERADOR, "SELECT id FROM intentos_login"))
    assert isinstance(resultado, str), (
        "el operador pudo leer intentos_login; revisar que no se le hayan dado permisos por defecto"
    )


def test_el_rol_del_operador_no_puede_saltarse_rls() -> None:
    async def comprobar() -> tuple[bool, bool]:
        motor = create_async_engine(URL_OPERADOR)
        try:
            async with motor.begin() as conn:
                fila = await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='operador_user'"
                    )
                )
                super_, bypass = fila.one()
                return bool(super_), bool(bypass)
        finally:
            await motor.dispose()

    es_super, salta_rls = _correr(comprobar())
    assert es_super is False
    assert salta_rls is False


# --- 2. Los tokens no son intercambiables ------------------------------------


def test_el_token_de_un_usuario_de_empresa_no_abre_la_consola(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = f"{uuid4().hex}@example.com"
    assert dar_de_alta(monkeypatch, correo=correo, password=PASSWORD_USUARIO) == 0
    entrada = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": PASSWORD_USUARIO}
    )
    assert entrada.status_code == 200
    token = client.cookies.get(COOKIE_ACCESO)
    assert token is not None

    # Ni por cookie del plano de control ni por cabecera.
    client.cookies.set(COOKIE_OPERADOR_ACCESO, token)
    assert client.get("/api/v1/operador/yo").status_code == 401
    client.cookies.clear()
    cabecera = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/operador/yo", headers=cabecera).status_code == 401


def test_el_token_de_un_operador_no_abre_la_api_de_cliente(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo).status_code == 200
    token = client.cookies.get(COOKIE_OPERADOR_ACCESO)
    assert token is not None

    client.cookies.clear()
    client.cookies.set(COOKIE_ACCESO, token)
    assert client.get("/api/v1/auth/yo").status_code == 401


# --- 3. La consola hace su trabajo -------------------------------------------


def test_el_operador_da_de_alta_una_empresa_y_su_administrador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    correo_admin = f"{uuid4().hex}@cliente.example.com"
    alta = client.post(
        "/api/v1/operador/empresas",
        json={
            "empresa": f"Cliente {uuid4().hex[:6]}",
            "admin_nombre": "Admin del cliente",
            "admin_correo": correo_admin,
        },
    )
    assert alta.status_code == 201, alta.text
    clave = alta.json()["password_temporal"]
    # La contrasena la genera el servidor: quien opera SIMAP no la elige, y por eso no puede
    # dejarse una que ya conozca de antemano en la cuenta de su cliente.
    assert len(clave) >= 16

    # Y sirve de verdad: el administrador entra con ella por el plano de datos.
    client.cookies.clear()
    entrada = client.post(
        "/api/v1/auth/login", json={"correo": correo_admin, "password": clave}
    )
    assert entrada.status_code == 200, entrada.text
    assert entrada.json()["usuario"]["rol"] == "administrador"


def test_suspender_una_empresa_deja_fuera_a_su_gente(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RF del plano de control: una empresa que deja de pagar se suspende, no se borra."""
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    correo_admin = f"{uuid4().hex}@cliente.example.com"
    alta = client.post(
        "/api/v1/operador/empresas",
        json={
            "empresa": f"Cliente {uuid4().hex[:6]}",
            "admin_nombre": "Admin del cliente",
            "admin_correo": correo_admin,
        },
    )
    assert alta.status_code == 201
    clave = alta.json()["password_temporal"]

    empresas = client.get("/api/v1/operador/empresas").json()
    empresa = next(e for e in empresas if e["admin_correo"] == correo_admin)

    assert client.post(f"/api/v1/operador/empresas/{empresa['id']}/suspender").status_code == 200

    cookies_operador = dict(client.cookies)
    client.cookies.clear()
    rechazado = client.post(
        "/api/v1/auth/login", json={"correo": correo_admin, "password": clave}
    )
    assert rechazado.status_code == 403, rechazado.text

    # Y reactivar la deja como estaba: los datos nunca se fueron a ningun sitio.
    for nombre, valor in cookies_operador.items():
        client.cookies.set(nombre, valor)
    assert client.post(f"/api/v1/operador/empresas/{empresa['id']}/reactivar").status_code == 200
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo_admin, "password": clave}
        ).status_code
        == 200
    )


def test_restablecer_la_clave_del_administrador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    correo_admin = f"{uuid4().hex}@cliente.example.com"
    alta = client.post(
        "/api/v1/operador/empresas",
        json={
            "empresa": f"Cliente {uuid4().hex[:6]}",
            "admin_nombre": "Admin del cliente",
            "admin_correo": correo_admin,
        },
    )
    clave_vieja = alta.json()["password_temporal"]
    empresas = client.get("/api/v1/operador/empresas").json()
    empresa = next(e for e in empresas if e["admin_correo"] == correo_admin)

    reset = client.post(f"/api/v1/operador/empresas/{empresa['id']}/restablecer-clave")
    assert reset.status_code == 200, reset.text
    clave_nueva = reset.json()["password_temporal"]
    assert clave_nueva != clave_vieja

    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo_admin, "password": clave_vieja}
        ).status_code
        == 401
    ), "la clave anterior debe dejar de servir"
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo_admin, "password": clave_nueva}
        ).status_code
        == 200
    )


def test_toda_accion_queda_en_la_bitacora(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin bitácora, restablecer la contraseña de un cliente sería indistinguible de no hacerlo."""
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    nombre_empresa = f"Cliente {uuid4().hex[:6]}"
    alta = client.post(
        "/api/v1/operador/empresas",
        json={
            "empresa": nombre_empresa,
            "admin_nombre": "Admin del cliente",
            "admin_correo": f"{uuid4().hex}@cliente.example.com",
        },
    )
    assert alta.status_code == 201

    asientos = client.get("/api/v1/operador/bitacora").json()
    reciente = asientos[0]
    assert reciente["accion"] == "alta_empresa"
    assert nombre_empresa in (reciente["detalle"] or "")
    assert reciente["operador_nombre"] == "Operador de prueba"


def test_la_consola_exige_sesion(client: TestClient) -> None:
    client.cookies.clear()
    for metodo, ruta in (
        ("get", "/api/v1/operador/yo"),
        ("get", "/api/v1/operador/empresas"),
        ("get", "/api/v1/operador/bitacora"),
        ("post", "/api/v1/operador/empresas"),
    ):
        respuesta = getattr(client, metodo)(ruta)
        assert respuesta.status_code == 401, f"{metodo.upper()} {ruta} no exige sesión"


# --- La cuenta del propio operador -------------------------------------------


def test_el_login_del_operador_tiene_limite_de_intentos(client: TestClient) -> None:
    # Es la cuenta con mas poder del sistema: si el login de una planta tiene limite, el de la
    # consola con mas razon.
    cuerpo = {"correo": f"op-{uuid4().hex}@simap.do", "password": "clave-equivocada-larga"}
    for _ in range(get_settings().login_max_attempts):
        assert client.post("/api/v1/operador/login", json=cuerpo).status_code == 401

    bloqueado = client.post("/api/v1/operador/login", json=cuerpo)
    assert bloqueado.status_code == 429
    assert "Retry-After" in bloqueado.headers


def test_el_limite_del_operador_no_comparte_contador_con_el_de_las_plantas(
    client: TestClient,
) -> None:
    # Los fallos en la consola no deben bloquear el login de una planta con el mismo correo, ni al
    # reves: son dos puertas distintas y un atacante no deberia poder cerrar una golpeando la otra.
    correo = f"op-{uuid4().hex}@simap.do"
    cuerpo = {"correo": correo, "password": "clave-equivocada-larga"}
    for _ in range(get_settings().login_max_attempts):
        client.post("/api/v1/operador/login", json=cuerpo)
    assert client.post("/api/v1/auth/login", json=cuerpo).status_code == 401


def test_el_login_del_operador_deja_su_propia_pista(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200
    assert client.cookies.get(COOKIE_PISTA_OPERADOR) == "1"
    # Y no la del plano de datos: el proxy no debe dejar pasar a /panel a quien solo es operador.
    assert not client.cookies.get(COOKIE_PISTA_SESION)

    client.post("/api/v1/operador/logout")
    assert not client.cookies.get(COOKIE_PISTA_OPERADOR)


def _cambiar_clave_operador(client: TestClient, actual: str, nueva: str) -> httpx.Response:
    return client.post(
        "/api/v1/operador/cambiar-clave",
        json={"password_actual": actual, "password_nueva": nueva},
    )


def test_el_operador_cambia_su_propia_clave(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    nueva = "clave-nueva-del-operador-larga"
    resp = _cambiar_clave_operador(client, PASSWORD_OPERADOR, nueva)
    assert resp.status_code == 200, resp.text
    assert client.get("/api/v1/operador/yo").status_code == 200, "este aparato sigue dentro"

    # Queda en la bitacora, sin empresa: no es una accion sobre ningun cliente.
    reciente = client.get("/api/v1/operador/bitacora").json()[0]
    assert reciente["accion"] == "cambio_clave_propia"
    assert reciente["empresa_id"] is None

    client.cookies.clear()
    assert _entrar_como_operador(client, correo_op).status_code == 401
    assert (
        client.post(
            "/api/v1/operador/login", json={"correo": correo_op, "password": nueva}
        ).status_code
        == 200
    )


def test_el_operador_no_cambia_su_clave_sin_la_actual(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200
    resp = _cambiar_clave_operador(client, "no-es-la-contrasena", "clave-nueva-del-operador")
    assert resp.status_code == 400, resp.text
    client.cookies.clear()
    assert _entrar_como_operador(client, correo_op).status_code == 200


def test_restablecer_la_clave_cierra_las_sesiones_del_administrador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Restablecer la clave suele pedirse porque alguien perdio el control de la cuenta. Si las
    # sesiones abiertas con la clave vieja siguieran renovandose siete dias, el restablecimiento no
    # echaria a nadie.
    correo_op = _crear_operador(monkeypatch)
    assert _entrar_como_operador(client, correo_op).status_code == 200

    correo_admin = f"{uuid4().hex}@cliente.example.com"
    alta = client.post(
        "/api/v1/operador/empresas",
        json={
            "empresa": f"Cliente {uuid4().hex[:6]}",
            "admin_nombre": "Admin del cliente",
            "admin_correo": correo_admin,
        },
    )
    clave = alta.json()["password_temporal"]
    # El administrador abre sesion en el mismo navegador: sus cookies van a otras rutas y conviven
    # con las del operador sin pisarse.
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo_admin, "password": clave}
        ).status_code
        == 200
    )

    empresa = next(
        e for e in client.get("/api/v1/operador/empresas").json()
        if e["admin_correo"] == correo_admin
    )
    reset = client.post(f"/api/v1/operador/empresas/{empresa['id']}/restablecer-clave")
    assert reset.status_code == 200, reset.text

    assert client.post("/api/v1/auth/refresh").status_code == 401
