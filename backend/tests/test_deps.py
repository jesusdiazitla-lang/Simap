"""Pruebas de get_claims y get_db: autenticación y fijado del tenant (RNF-01, RNF-07).

No hacen falta PostgreSQL ni pytest-asyncio: se sustituye la fábrica de sesiones por una falsa que
anota las sentencias ejecutadas, y se conduce la dependencia con TestClient, que ya corre el bucle
asíncrono de la aplicación.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import COOKIE_ACCESO, ClaimsActuales
from app.core.security import Rol, crear_token_de_acceso, crear_token_de_refresco
from app.db import deps
from app.db.deps import SesionDB
from app.db.tenant import RowLevelSecurityPostgres

EMPRESA = UUID("11111111-1111-1111-1111-111111111111")
OTRA_EMPRESA = UUID("22222222-2222-2222-2222-222222222222")


# --- Doble de la sesión de SQLAlchemy ----------------------------------------


class _Transaccion:
    def __init__(self, sesion: "SesionFalsa") -> None:
        self._sesion = sesion

    async def __aenter__(self) -> "SesionFalsa":
        self._sesion.ejecutadas.append(("BEGIN", None))
        return self._sesion

    async def __aexit__(self, *_: object) -> bool:
        self._sesion.ejecutadas.append(("COMMIT", None))
        return False


class SesionFalsa:
    def __init__(self, registro: list[tuple[str, Any]]) -> None:
        self.ejecutadas = registro

    def begin(self) -> _Transaccion:
        return _Transaccion(self)

    async def execute(self, stmt: object, params: Any = None) -> None:
        self.ejecutadas.append((str(stmt), params))

    async def __aenter__(self) -> "SesionFalsa":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False


@pytest.fixture
def registro(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, Any]]]:
    """Sustituye la fábrica de sesiones y devuelve la lista de sentencias ejecutadas.

    La estrategia se fija a la de PostgreSQL para no depender de que exista un motor: estos tests
    comprueban el comportamiento con RLS, que es el del motor recomendado.
    """
    ejecutadas: list[tuple[str, Any]] = []
    monkeypatch.setattr(deps, "get_sessionmaker", lambda: (lambda: SesionFalsa(ejecutadas)))
    monkeypatch.setattr(deps, "get_estrategia_tenant", RowLevelSecurityPostgres)
    yield ejecutadas


# --- Aplicación de prueba ----------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/quien-soy")
    async def quien_soy(claims: ClaimsActuales) -> dict[str, str]:
        return {"empresa_id": str(claims.empresa_id), "rol": claims.rol.value}

    @app.get("/con-sesion")
    async def con_sesion(sesion: SesionDB) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app())


def _token(empresa: UUID = EMPRESA, rol: Rol = Rol.SUPERVISOR) -> str:
    return crear_token_de_acceso(uuid4(), empresa, rol)


# --- get_claims --------------------------------------------------------------


def test_rnf07_sin_token_responde_401(client: TestClient) -> None:
    resp = client.get("/quien-soy")
    assert resp.status_code == 401


def test_rnf07_token_en_cookie_httponly_autentica(client: TestClient) -> None:
    client.cookies.set(COOKIE_ACCESO, _token())
    resp = client.get("/quien-soy")
    assert resp.status_code == 200
    assert resp.json()["empresa_id"] == str(EMPRESA)


def test_rnf07_token_en_cabecera_bearer_autentica(client: TestClient) -> None:
    resp = client.get("/quien-soy", headers={"Authorization": f"Bearer {_token()}"})
    assert resp.status_code == 200
    assert resp.json()["rol"] == "supervisor"


def test_rnf07_la_cookie_tiene_prioridad_sobre_la_cabecera(client: TestClient) -> None:
    # Si llegan ambas, manda la cookie: es la via del navegador y la que no
    # puede fabricar un script inyectado por XSS.
    client.cookies.set(COOKIE_ACCESO, _token(EMPRESA))
    resp = client.get(
        "/quien-soy",
        headers={"Authorization": f"Bearer {_token(OTRA_EMPRESA)}"},
    )
    assert resp.json()["empresa_id"] == str(EMPRESA)


def test_rnf07_cabecera_sin_esquema_bearer_no_autentica(client: TestClient) -> None:
    resp = client.get("/quien-soy", headers={"Authorization": _token()})
    assert resp.status_code == 401


def test_rnf07_token_basura_responde_401(client: TestClient) -> None:
    resp = client.get("/quien-soy", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert resp.status_code == 401


def test_rnf07_un_refresh_token_no_abre_sesion(client: TestClient) -> None:
    refresco = crear_token_de_refresco(uuid4(), EMPRESA, Rol.ADMINISTRADOR)
    resp = client.get("/quien-soy", headers={"Authorization": f"Bearer {refresco}"})
    assert resp.status_code == 401


# --- get_db ------------------------------------------------------------------


def test_rnf01_get_db_fija_el_tenant_dentro_de_la_transaccion(
    client: TestClient, registro: list[tuple[str, Any]]
) -> None:
    client.cookies.set(COOKIE_ACCESO, _token(EMPRESA))
    assert client.get("/con-sesion").status_code == 200

    pasos = [sql for sql, _ in registro]
    assert pasos[0] == "BEGIN", "el set_config debe ir DENTRO de la transaccion"
    assert "set_config" in pasos[1]
    assert "COMMIT" in pasos

    _, params = registro[1]
    assert params["empresa_id"] == str(EMPRESA)


def test_rnf01_el_tenant_sale_del_token_no_del_cliente(
    client: TestClient, registro: list[tuple[str, Any]]
) -> None:
    # Aunque el cliente intente imponer otra empresa por cabecera o query, el
    # valor fijado es el firmado dentro del JWT.
    client.cookies.set(COOKIE_ACCESO, _token(EMPRESA))
    client.get(
        "/con-sesion",
        params={"empresa_id": str(OTRA_EMPRESA)},
        headers={"X-Empresa-Id": str(OTRA_EMPRESA)},
    )
    _, params = registro[1]
    assert params["empresa_id"] == str(EMPRESA)
    assert str(OTRA_EMPRESA) not in str(registro)


def test_rnf01_set_config_usa_parametro_enlazado_no_concatenacion(
    client: TestClient, registro: list[tuple[str, Any]]
) -> None:
    # El id no debe aparecer incrustado en el texto SQL: si se concatenara, el
    # contenido del token seria un vector de inyeccion.
    client.cookies.set(COOKIE_ACCESO, _token(EMPRESA))
    client.get("/con-sesion")
    sql, _ = registro[1]
    assert ":empresa_id" in sql
    assert str(EMPRESA) not in sql


def test_rnf01_sin_token_no_se_abre_ninguna_sesion(
    client: TestClient, registro: list[tuple[str, Any]]
) -> None:
    assert client.get("/con-sesion").status_code == 401
    assert registro == [], "no debe tocarse la base sin autenticar"
