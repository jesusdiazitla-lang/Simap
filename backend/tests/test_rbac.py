"""Pruebas del control de acceso por rol (sección 4.5 de 04-fase1-fundamentos.md)."""

from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import COOKIE_ACCESO
from app.core.rbac import RolNoDeclarado, requiere_roles
from app.core.security import Claims, Rol, crear_token_de_acceso

EMPRESA = uuid4()


def _app() -> FastAPI:
    app = FastAPI()

    SoloGerencia = Annotated[Claims, Depends(requiere_roles(Rol.GERENTE, Rol.ADMINISTRADOR))]

    @app.get("/solo-gerencia")
    async def solo_gerencia(claims: SoloGerencia) -> dict[str, str]:
        return {"rol": claims.rol.value}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app())


def _entrar(client: TestClient, rol: Rol) -> None:
    client.cookies.set(COOKIE_ACCESO, crear_token_de_acceso(uuid4(), EMPRESA, rol))


@pytest.mark.parametrize("rol", [Rol.GERENTE, Rol.ADMINISTRADOR])
def test_un_rol_permitido_entra(client: TestClient, rol: Rol) -> None:
    _entrar(client, rol)
    resp = client.get("/solo-gerencia")
    assert resp.status_code == 200
    assert resp.json()["rol"] == rol.value


@pytest.mark.parametrize("rol", [Rol.OPERARIO, Rol.SUPERVISOR, Rol.TECNICO_TALLER])
def test_un_rol_no_permitido_recibe_403(client: TestClient, rol: Rol) -> None:
    # 403 y no 401: el usuario SI esta autenticado, lo que falta es permiso.
    # Un 401 invitaria al cliente a reintentar el login, que no arreglaria nada.
    _entrar(client, rol)
    assert client.get("/solo-gerencia").status_code == 403


def test_sin_token_recibe_401(client: TestClient) -> None:
    assert client.get("/solo-gerencia").status_code == 401


def test_un_endpoint_sin_roles_declarados_es_un_error_de_programacion() -> None:
    # Seccion 4.5: ningun endpoint asume un rol por defecto. Falla al construir
    # la dependencia, no en tiempo de peticion, para que se note al arrancar.
    with pytest.raises(RolNoDeclarado):
        requiere_roles()
