"""Ayudantes de las pruebas de la fase 2: una planta con su personal, por los caminos reales.

Cada planta se crea igual que en producción: la empresa con su administrador por el comando de
consola, y el resto del personal con `POST /usuarios` (RF-03), entrando después cada uno con la
contraseña temporal que devolvió el alta. Si algo de eso se rompe, se enteran todas las pruebas que
lo usan.

Para actuar como distintas personas en una misma prueba no se usan varios `TestClient` —asyncpg no
soporta que compartan conexiones entre bucles de eventos distintos—, sino uno solo y el token de
cada persona en la cabecera `Authorization`. Las cookies se vacían después de cada login para que
no se mezclen: si llegan las dos, la cookie manda (`app.core.auth`).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.almacen import AlmacenMemoria, get_almacen
from app.core.auth import COOKIE_ACCESO
from app.core.config import get_settings
from app.db.session import get_engine, get_estrategia_tenant, get_sessionmaker
from app.main import app
from tests.conftest import dar_de_alta

PASSWORD_ADMIN = "contrasena-larga-de-prueba"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()
    _limpiar()
    almacen = AlmacenMemoria()
    app.dependency_overrides[get_almacen] = lambda: almacen
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpiar()
    get_settings.cache_clear()


def _limpiar() -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_estrategia_tenant.cache_clear()


def ahora() -> datetime:
    return datetime.now(UTC)


def hace(**delta: float) -> str:
    return (ahora() - timedelta(**delta)).isoformat()


@dataclass
class Persona:
    correo: str
    token: str
    id: UUID

    @property
    def cabeceras(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class Planta:
    """Una empresa con su personal: los cinco roles (06-fase3, sección 3)."""

    client: TestClient
    admin: Persona
    personas: dict[str, Persona] = field(default_factory=dict)

    @property
    def supervisor(self) -> Persona:
        return self.personas["supervisor"]

    @property
    def operario(self) -> Persona:
        return self.personas["operario"]

    @property
    def gerente(self) -> Persona:
        return self.personas["gerente"]

    @property
    def tecnico(self) -> Persona:
        return self.personas["tecnico_taller"]

    def componente(self, nombre: str = "Motor") -> str:
        """Id de un componente de la plantilla inicial, que toda empresa nueva recibe."""
        resp = self.pedir(self.admin, "GET", "/componentes")
        assert resp.status_code == 200, resp.text
        for c in resp.json()["items"] if isinstance(resp.json(), dict) else resp.json():
            if c["nombre"] == nombre:
                return str(c["id"])
        raise AssertionError(f"La plantilla no tiene el componente {nombre!r}")

    def falla(
        self,
        activo_id: str,
        *,
        componente_id: str | None = None,
        horometro: int = 4801,
        quien: Persona | None = None,
        **extra: Any,
    ) -> httpx.Response:
        """Reporta una falla (F3, 6.2). Por defecto el supervisor, sobre el motor del equipo."""
        cuerpo: dict[str, Any] = {
            "cliente_id": str(uuid4()),
            "capturado_en": ahora().isoformat(),
            "componente_id": componente_id or self.componente(),
            "horometro": horometro,
            "descripcion": "Se detuvo por sobrecalentamiento al arrancar",
        }
        cuerpo.update(extra)
        return self.pedir(
            quien or self.supervisor, "POST", f"/activos/{activo_id}/fallas", json=cuerpo
        )

    def orden(self, activo_id: str, **extra: Any) -> dict[str, Any]:
        """Una orden recién reportada, para las pruebas que parten de ella."""
        resp = self.falla(activo_id, **extra)
        assert resp.status_code == 201, resp.text
        return dict(resp.json()["orden"])

    def mover(self, quien: Persona, orden_id: str, accion: str, **cuerpo: Any) -> httpx.Response:
        """Una transición: `en-taller`, `reparada`, `cerrar`, `rechazar-cierre`, `cancelar`."""
        return self.pedir(
            quien, "POST", f"/ordenes/{orden_id}/{accion}", json=cuerpo if cuerpo else None
        )

    def reparar(self, orden_id: str, tipo: str = "reemplazo") -> httpx.Response:
        return self.mover(
            self.tecnico,
            orden_id,
            "reparada",
            trabajo_realizado="Se cambió el rodamiento del lado acople y se alineó el eje.",
            tipo_intervencion=tipo,
        )

    def llevar_a_reparada(self, orden_id: str, tipo: str = "reemplazo") -> None:
        assert self.mover(self.tecnico, orden_id, "en-taller").status_code == 200
        resp = self.reparar(orden_id, tipo)
        assert resp.status_code == 200, resp.text

    def pedir(self, quien: Persona, metodo: str, ruta: str, **kwargs: Any) -> httpx.Response:
        self.client.cookies.clear()
        cabeceras = {**quien.cabeceras, **kwargs.pop("headers", {})}
        return self.client.request(metodo, f"/api/v1{ruta}", headers=cabeceras, **kwargs)

    def nuevo_activo(self, nombre: str = "Compresor 1", **datos: Any) -> dict[str, Any]:
        resp = self.pedir(self.admin, "POST", "/activos", json={"nombre": nombre, **datos})
        assert resp.status_code == 201, resp.text
        return dict(resp.json())

    def lectura(
        self, activo_id: str, valor: int, *, quien: Persona | None = None, **extra: Any
    ) -> httpx.Response:
        cuerpo = {"cliente_id": str(uuid4()), "capturado_en": ahora().isoformat(), "valor": valor}
        cuerpo.update(extra)
        return self.pedir(
            quien or self.operario, "POST", f"/activos/{activo_id}/lecturas", json=cuerpo
        )

    def alerta(
        self, activo_id: str, sintoma: str = "ruido", *, quien: Persona | None = None, **extra: Any
    ) -> httpx.Response:
        cuerpo = {
            "cliente_id": str(uuid4()),
            "capturado_en": ahora().isoformat(),
            "sintoma": sintoma,
        }
        cuerpo.update(extra)
        return self.pedir(
            quien or self.operario, "POST", f"/activos/{activo_id}/alertas", json=cuerpo
        )


def entrar(client: TestClient, correo: str, password: str) -> Persona:
    client.cookies.clear()
    resp = client.post("/api/v1/auth/login", json={"correo": correo, "password": password})
    assert resp.status_code == 200, resp.text
    token = client.cookies.get(COOKIE_ACCESO)
    assert token
    client.cookies.clear()
    return Persona(correo=correo, token=token, id=UUID(resp.json()["usuario"]["id"]))


def montar_planta(client: TestClient, monkeypatch: pytest.MonkeyPatch, nombre: str) -> Planta:
    correo_admin = f"{uuid4().hex}@example.com"
    salida = dar_de_alta(
        monkeypatch,
        correo=correo_admin,
        password=PASSWORD_ADMIN,
        empresa=f"{nombre} {uuid4().hex[:6]}",
    )
    assert salida == 0
    # dar_de_alta cambia sys.stdin; se restaura para no afectar a otros pasos de la prueba.
    monkeypatch.setattr(sys, "stdin", sys.__stdin__)
    planta = Planta(client=client, admin=entrar(client, correo_admin, PASSWORD_ADMIN))
    for rol in ("supervisor", "operario", "gerente", "tecnico_taller"):
        correo = f"{rol}-{uuid4().hex}@example.com"
        alta = planta.pedir(
            planta.admin,
            "POST",
            "/usuarios",
            json={"nombre": rol.title(), "correo": correo, "rol": rol},
        )
        assert alta.status_code == 201, alta.text
        planta.personas[rol] = entrar(client, correo, alta.json()["password_temporal"])
    return planta
