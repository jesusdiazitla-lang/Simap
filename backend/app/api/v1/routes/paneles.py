"""Paneles por rol e indicadores (08-fase5, sección 8.4; RF-27, RF-28).

Tres rutas de solo lectura. Empresa, usuario y rol salen **de la sesión**: ninguna acepta
`empresa_id` ni `usuario_id` de la petición (una prueba los envía y comprueba que no cambian nada).
La ruta no usa `get_db`: cada widget abre su propia transacción de solo lectura con el tenant de la
sesión, para que uno que falle no arrastre a los demás (RNF-02).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.services.paneles.ensamblador import Contexto, armar_panel
from app.services.paneles.indicadores import PeriodoInvalido, resolver_periodo
from app.services.paneles.widgets import CON_FILTRO_DE_PLANTA, WIDGETS, lista_plantas

router = APIRouter(tags=["paneles"])

OP, S, T, G, A = Rol.OPERARIO, Rol.SUPERVISOR, Rol.TECNICO_TALLER, Rol.GERENTE, Rol.ADMINISTRADOR
ConPanel = Annotated[Claims, Depends(requiere_roles(OP, S, T, G, A))]
VeIndicadores = Annotated[Claims, Depends(requiere_roles(G, A))]
VePlantas = Annotated[Claims, Depends(requiere_roles(S, G, A))]

#: La planta es texto libre de la columna de ubicación: comparación exacta y longitud acotada.
Planta = Annotated[str | None, Query(max_length=80)]
Fecha = Annotated[date | None, Query()]


def _contexto(
    claims: Claims, planta: str | None, desde: date | None, hasta: date | None
) -> Contexto:
    try:
        d, h, ahora = resolver_periodo(desde, hasta, datetime.now(UTC))
    except PeriodoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    con_filtro = str(claims.rol) in CON_FILTRO_DE_PLANTA
    return Contexto(
        empresa_id=claims.empresa_id,
        usuario_id=claims.usuario_id,
        rol=str(claims.rol),
        desde=d,
        hasta=h,
        ahora=ahora,
        ubicacion=(planta or None) if con_filtro else None,
    )


@router.get("/panel")
async def panel(
    claims: ConPanel, planta: Planta = None, desde: Fecha = None, hasta: Fecha = None
) -> dict[str, Any]:
    """Los widgets del rol de la sesión, con la lista de los que vienen degradados."""
    ctx = _contexto(claims, planta, desde, hasta)
    resultado = await armar_panel(ctx, WIDGETS)
    if not resultado["widgets"]:
        # Ningún rol tiene panel por defecto (fase 1): un rol sin widgets no ve nada.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene panel.")
    return {
        **resultado,
        "desde": ctx.desde.isoformat(),
        "hasta": ctx.hasta.isoformat(),
        "planta": ctx.ubicacion,
    }


@router.get("/indicadores")
async def indicadores(
    claims: VeIndicadores, planta: Planta = None, desde: Fecha = None, hasta: Fecha = None
) -> dict[str, Any]:
    """Solo el widget de indicadores, con el mismo formato (para exportar y para pruebas)."""
    ctx = _contexto(claims, planta, desde, hasta)
    solo = [w for w in WIDGETS if w.nombre == "indicadores"]
    resultado = await armar_panel(ctx, solo)
    return {
        **resultado,
        "desde": ctx.desde.isoformat(),
        "hasta": ctx.hasta.isoformat(),
        "planta": ctx.ubicacion,
    }


@router.get("/plantas")
async def plantas(claims: VePlantas) -> list[str]:
    """Ubicaciones con equipos activos, para el filtro. Ordena la vista; no es control de acceso."""
    ctx = _contexto(claims, None, None, None)
    return await lista_plantas(ctx)
