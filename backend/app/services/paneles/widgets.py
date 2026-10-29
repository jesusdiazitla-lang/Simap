"""Los widgets de cada rol (08-fase5, 8.4; RF-27): qué consulta cada uno y quién lo ve.

| Rol            | Widgets                                                         |
|----------------|-----------------------------------------------------------------|
| operario       | mis_lecturas, mis_alertas                                       |
| tecnico_taller | cola_taller, mis_trabajos                                       |
| supervisor     | contadores, alertas_campo, alertas_sistema, ordenes_abiertas    |
| gerente        | indicadores, repuestos_costo, riesgo_top, riesgo_cobertura      |
| administrador  | los del supervisor y los del gerente, más salud (9)             |

Cada consulta abre su propia transacción de solo lectura con el tenant de la sesión
(`sesion_de_lectura`). Los datos que devuelven son JSON sin `Decimal` ni fechas crudas: dinero como
texto con dos decimales, instantes en ISO 8601.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

from app.db.deps import sesion_de_lectura
from app.services.paneles import consultas
from app.services.paneles.ensamblador import Contexto, Widget
from app.services.paneles.indicadores import Mes, Resumen, calcular_meses, cubos, resumir

OPERARIO, TECNICO, SUPERVISOR, GERENTE, ADMIN = (
    "operario",
    "tecnico_taller",
    "supervisor",
    "gerente",
    "administrador",
)

#: Límites de tiempo (8.3): 3 s los indicadores, 2 s los demás (RNF-04 pide < 2 s para el riesgo).
TIMEOUT_INDICADORES = 3.0
TIMEOUT_WIDGET = 2.0


def _json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if isinstance(valor, float):
        return round(valor, 6)
    if isinstance(valor, tuple):
        return [_json(v) for v in valor]
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def serializar_mes(m: Mes) -> dict[str, Any]:
    return {k: _json(v) for k, v in dataclasses.asdict(m).items()}


def serializar_resumen(r: Resumen) -> dict[str, Any]:
    return {k: _json(v) for k, v in dataclasses.asdict(r).items()}


async def calcular_indicadores(ctx: Contexto) -> dict[str, Any]:
    """Los cuatro conjuntos de datos en una transacción con una foto fija (8.6), y el cálculo."""
    async with sesion_de_lectura(ctx.empresa_id) as s:
        equipos = await consultas.equipos(s, ctx.ubicacion)
        paradas = await consultas.paradas(s, ctx.ubicacion, ctx.desde, ctx.hasta)
        ordenes = await consultas.ordenes(s, ctx.ubicacion, ctx.desde, ctx.hasta)
        lecturas = await consultas.lecturas(s, ctx.ubicacion, ctx.desde, ctx.hasta)
        consumos = await consultas.consumos(s, ctx.ubicacion, ctx.desde, ctx.hasta)
    meses = calcular_meses(
        cubos(ctx.desde, ctx.hasta, ctx.ahora), equipos, paradas, ordenes, lecturas, consumos
    )
    return {
        "desde": ctx.desde.isoformat(),
        "hasta": ctx.hasta.isoformat(),
        "resumen": serializar_resumen(resumir(meses)),
        "meses": [serializar_mes(m) for m in meses],
    }


async def _repuestos_costo(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.repuestos_costo(s, ctx.ubicacion, ctx.desde, ctx.hasta)


async def _riesgo_top(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.riesgo_top(s, ctx.ubicacion)


async def _riesgo_cobertura(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.riesgo_cobertura(s, ctx.ubicacion)


async def _mis_lecturas(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.mis_lecturas(s, ctx.usuario_id)


async def _mis_alertas(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.mis_alertas(s, ctx.usuario_id)


async def _cola_taller(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.cola_taller(s)


async def _mis_trabajos(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.mis_trabajos(s, ctx.usuario_id)


async def _contadores(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.contadores(s, ctx.ubicacion)


async def _alertas_campo(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.alertas_campo(s, ctx.ubicacion)


async def _alertas_sistema(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.alertas_sistema(s, ctx.ubicacion)


async def _ordenes_abiertas(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.ordenes_abiertas(s, ctx.ubicacion, ctx.ahora)


async def _salud(ctx: Contexto) -> Any:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.salud(s)


def _w(nombre: str, consulta: Any, *roles: str, timeout: float = TIMEOUT_WIDGET) -> Widget:
    return Widget(nombre, consulta, frozenset(roles), timeout)


WIDGETS: tuple[Widget, ...] = (
    _w("mis_lecturas", _mis_lecturas, OPERARIO),
    _w("mis_alertas", _mis_alertas, OPERARIO),
    _w("cola_taller", _cola_taller, TECNICO),
    _w("mis_trabajos", _mis_trabajos, TECNICO),
    _w("contadores", _contadores, SUPERVISOR, ADMIN),
    _w("alertas_campo", _alertas_campo, SUPERVISOR, ADMIN),
    _w("alertas_sistema", _alertas_sistema, SUPERVISOR, ADMIN),
    _w("ordenes_abiertas", _ordenes_abiertas, SUPERVISOR, ADMIN),
    _w("indicadores", calcular_indicadores, GERENTE, ADMIN, timeout=TIMEOUT_INDICADORES),
    _w("repuestos_costo", _repuestos_costo, GERENTE, ADMIN),
    _w("riesgo_top", _riesgo_top, GERENTE, ADMIN),
    _w("riesgo_cobertura", _riesgo_cobertura, GERENTE, ADMIN),
    _w("salud", _salud, ADMIN),
)

#: Roles que ven el filtro de planta y el de periodo (10.1).
CON_FILTRO_DE_PLANTA = frozenset({SUPERVISOR, GERENTE, ADMIN})


async def lista_plantas(ctx: Contexto) -> list[str]:
    async with sesion_de_lectura(ctx.empresa_id) as s:
        return await consultas.plantas(s)
