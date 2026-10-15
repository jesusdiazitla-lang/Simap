"""Siembra directa en la base para las pruebas de la fase 3 que no pasan por HTTP.

Las defensas de la base (llaves compuestas, trigger, permisos, RLS, la vista) se prueban contra la
base misma: por HTTP, el servicio las taparía y no se sabría cuál de las dos capas frenó el ataque.

Como en `test_aislamiento_fase2`, ninguna prueba se conecta como superusuario. Se siembra con
`simap_owner`, al que `FORCE ROW LEVEL SECURITY` también alcanza, fijando el tenant como lo haría la
aplicación; y se ataca como `app_user`, el rol del backend. Los UUID se generan en Python porque un
`INSERT ... RETURNING` sin tenant fijado fallaría.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import URL_APP, URL_DUENO

T = TypeVar("T")


def correr(corutina: Awaitable[T]) -> T:
    return asyncio.run(corutina)  # type: ignore[arg-type]


async def fijar(conn: AsyncConnection, empresa_id: UUID | None) -> None:
    await conn.execute(
        text("SELECT set_config('app.empresa_id', :v, true)"),
        {"v": str(empresa_id) if empresa_id else ""},
    )


@dataclass(frozen=True)
class Empresa:
    empresa_id: UUID
    usuario_id: UUID
    activo_id: UUID
    componente_id: UUID


async def _sembrar_empresa(conn: AsyncConnection, nombre: str) -> Empresa:
    e = Empresa(uuid4(), uuid4(), uuid4(), uuid4())
    await conn.execute(
        text("INSERT INTO empresas (id, nombre) VALUES (:i, :n)"),
        {"i": e.empresa_id, "n": f"{nombre} {uuid4().hex[:8]}"},
    )
    await fijar(conn, e.empresa_id)
    await conn.execute(
        text(
            "INSERT INTO usuarios (id, empresa_id, nombre, correo, password_hash, rol)"
            " VALUES (:i, :e, 'Supervisora', :c, 'x', 'supervisor')"
        ),
        {"i": e.usuario_id, "e": e.empresa_id, "c": f"{uuid4().hex}@example.com"},
    )
    await conn.execute(
        text("INSERT INTO activos (id, empresa_id, nombre, qr_code) VALUES (:i, :e, 'Prensa', :q)"),
        {"i": e.activo_id, "e": e.empresa_id, "q": uuid4().hex[:8].upper()},
    )
    await conn.execute(
        text("INSERT INTO componentes (id, empresa_id, nombre) VALUES (:i, :e, 'Motor')"),
        {"i": e.componente_id, "e": e.empresa_id},
    )
    return e


async def sembrar(*nombres: str) -> list[Empresa]:
    motor = create_async_engine(URL_DUENO)
    try:
        empresas = []
        for nombre in nombres:
            async with motor.begin() as conn:
                empresas.append(await _sembrar_empresa(conn, nombre))
        return empresas
    finally:
        await motor.dispose()


def fila_orden(
    e: Empresa,
    *,
    numero: int,
    horas: int,
    estado: str = "cerrada",
    tipo: str | None = "reemplazo",
    requiere_revision: bool = False,
    fecha: datetime | None = None,
    activo_id: UUID | None = None,
    componente_id: UUID | None = None,
) -> dict[str, Any]:
    """Los valores de una orden coherente con su estado, para insertarla directamente."""
    cerrada = estado == "cerrada"
    reparada = estado in ("reparada", "cerrada")
    momento = fecha or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=numero)
    return {
        "id": uuid4(),
        "e": e.empresa_id,
        "numero": numero,
        "activo": activo_id or e.activo_id,
        "componente": componente_id or e.componente_id,
        "autor": e.usuario_id,
        "dial": horas,
        "horas": horas,
        "fecha": momento,
        "estado": estado,
        "reparado_por": e.usuario_id if reparada else None,
        "trabajo": "Cambio del componente completo." if reparada else None,
        "tipo": tipo if reparada else None,
        "autorizado_por": e.usuario_id if cerrada else None,
        "salida": momento + timedelta(hours=4) if cerrada else None,
        "minutos": 240 if cerrada else None,
        "cancelacion": "Reportada por error, duplicada." if estado == "cancelada" else None,
        "revision": requiere_revision,
        "motivo_revision": "Horómetro dudoso." if requiere_revision else None,
    }


INSERT_ORDEN = text(
    "INSERT INTO ordenes_trabajo (id, empresa_id, numero, activo_id, componente_id,"
    " reportado_por, horometro_en_falla, horas_acumuladas_en_falla, descripcion, fecha_falla,"
    " estado, reparado_por, trabajo_realizado, tipo_intervencion, autorizado_por,"
    " fecha_salida_taller, tiempo_fuera_servicio_min, motivo_cancelacion, requiere_revision,"
    " motivo_revision)"
    " VALUES (:id, :e, :numero, :activo, :componente, :autor, :dial, :horas,"
    " 'Falla de prueba en el equipo', :fecha, :estado, :reparado_por, :trabajo, :tipo,"
    " :autorizado_por, :salida, :minutos, :cancelacion, :revision, :motivo_revision)"
)


async def insertar_ordenes(e: Empresa, filas: list[dict[str, Any]]) -> None:
    motor = create_async_engine(URL_DUENO)
    try:
        async with motor.begin() as conn:
            await fijar(conn, e.empresa_id)
            for fila in filas:
                await conn.execute(INSERT_ORDEN, fila)
    finally:
        await motor.dispose()


def motor_app() -> Any:
    return create_async_engine(URL_APP)
