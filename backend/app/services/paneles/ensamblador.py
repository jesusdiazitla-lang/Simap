"""Ensamblador de paneles (08-fase5, 8.3 y 8.5; RF-27, RNF-02): genérico, no sabe qué consulta nada.

Cada widget es una función asíncrona que abre **su propia transacción**: PostgreSQL aborta la
transacción entera ante el primer error, así que dos widgets que la compartieran caerían juntos.
Cada uno tiene su límite de tiempo y, si falla o se pasa, devuelve un estado degradado con un código
corto (`error` o `tiempo_agotado`) y **sin** el texto del error, que va al registro del servidor.

La concurrencia se acota (3 a la vez por defecto): un panel no debe consumir una conexión del pool
por widget y por usuario conectado.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

log = logging.getLogger("simap.paneles")


@dataclass(frozen=True)
class Contexto:
    """Lo que un widget sabe de la petición. Empresa, usuario y rol salen siempre de la sesión."""

    empresa_id: UUID
    usuario_id: UUID
    rol: str
    desde: datetime
    hasta: datetime
    ahora: datetime
    ubicacion: str | None = None


Consulta = Callable[[Contexto], Awaitable[Any]]


@dataclass(frozen=True)
class Widget:
    nombre: str
    consulta: Consulta
    roles: frozenset[str] = field(default_factory=frozenset)
    timeout_s: float = 2.0


def widgets_del_rol(rol: str, widgets: Iterable[Widget]) -> list[Widget]:
    return [w for w in widgets if rol in w.roles]


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


async def correr_widget(w: Widget, ctx: Contexto) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        datos = await asyncio.wait_for(w.consulta(ctx), timeout=w.timeout_s)
        return {"estado": "ok", "datos": datos, "ms": _ms(t0)}
    except TimeoutError:
        log.warning("widget %s excedió %.2f s (empresa %s)", w.nombre, w.timeout_s, ctx.empresa_id)
        return {"estado": "degradado", "motivo": "tiempo_agotado", "datos": None, "ms": _ms(t0)}
    except Exception:  # noqa: BLE001 — un widget no debe tumbar el panel (RNF-02).
        log.exception("widget %s falló (empresa %s)", w.nombre, ctx.empresa_id)
        return {"estado": "degradado", "motivo": "error", "datos": None, "ms": _ms(t0)}
    # `asyncio.CancelledError` (la petición se canceló) NO se captura: hereda de BaseException y
    # debe propagarse para liberar la conexión. Atraparla dejaría trabajo huérfano.


async def armar_panel(
    ctx: Contexto, widgets: Iterable[Widget], max_paralelos: int = 3
) -> dict[str, Any]:
    """Corre los widgets del rol en paralelo, con a lo más `max_paralelos` a la vez."""
    seleccion = widgets_del_rol(ctx.rol, widgets)
    semaforo = asyncio.Semaphore(max_paralelos)

    async def uno(w: Widget) -> dict[str, Any]:
        async with semaforo:
            return await correr_widget(w, ctx)

    t0 = time.perf_counter()
    resultados = await asyncio.gather(*(uno(w) for w in seleccion))
    por_nombre = {w.nombre: r for w, r in zip(seleccion, resultados, strict=True)}
    return {
        "rol": ctx.rol,
        "widgets": por_nombre,
        "degradados": [n for n, r in por_nombre.items() if r["estado"] != "ok"],
        "ms_total": _ms(t0),
    }


def clave_cache(empresa_id: UUID | str | None, widget: str, **parametros: Any) -> str:
    """Clave de caché de un widget (8.5). No hay caché hoy; si se agrega, la empresa va **siempre**
    en la clave: una clave sin ella serviría los números de una empresa a otra, y ninguna prueba de
    RLS lo detectaría porque el error ocurriría fuera de la base. Se rechaza construirla sin empresa
    en vez de confiar en la disciplina."""
    if not empresa_id:
        raise ValueError("clave de caché sin empresa_id")
    carga = json.dumps(parametros, sort_keys=True, default=str, separators=(",", ":"))
    resumen = hashlib.sha256(carga.encode()).hexdigest()[:16]
    return f"simap:v1:{empresa_id}:{widget}:{resumen}"


__all__ = [
    "Contexto",
    "Widget",
    "armar_panel",
    "clave_cache",
    "correr_widget",
    "widgets_del_rol",
]
