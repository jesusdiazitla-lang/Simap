"""Piezas compartidas por las rutas de la fase 2: roles, límites por usuario, cursores y errores.

Son cuestiones de transporte —cómo se traduce algo a HTTP—, no de negocio, y por eso viven en la
capa de API y no en `services/`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from app.core.almacen import AlmacenEfimero, get_almacen
from app.core.auth import ClaimsActuales
from app.core.config import get_settings
from app.core.cursor import Cursor, CursorInvalido
from app.core.security import Claims, Rol
from app.services import limites
from app.services.capturas import ActivoNoDisponible, CapturaInvalida

#: Todos los roles de una empresa. Se escribe la lista entera en vez de «cualquiera autenticado»
#: porque `requiere_roles` exige declarar siempre a quién se deja pasar
#: (04-fase1-fundamentos.md, sección 4.5): un rol nuevo no hereda acceso a nada sin que alguien lo
#: añada a mano.
TODOS = tuple(Rol)

Almacen = Annotated[AlmacenEfimero, Depends(get_almacen)]


def demasiadas_peticiones(exc: limites.DemasiadosIntentos) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiadas peticiones seguidas. Espera un momento antes de volver a probar.",
        headers={"Retry-After": str(exc.espera_segundos)},
    )


def limite_por_usuario(
    prefijo: str, maximo: Callable[[], int]
) -> Callable[[ClaimsActuales, Almacen], Awaitable[None]]:
    """Dependencia que limita las peticiones de cada usuario (secciones 6.2 y 8.4).

    Por usuario y no por IP: detrás del reenvío de Next.js o del proxy del hosting, todas las
    peticiones llegan desde la misma IP, y un límite por IP haría que los operarios de una planta se
    bloquearan entre sí.
    """

    async def dependencia(claims: ClaimsActuales, almacen: Almacen) -> None:
        try:
            await limites.comprobar(
                almacen,
                [f"{prefijo}:usuario:{claims.usuario_id}"],
                maximo=maximo(),
                ventana_segundos=60,
            )
        except limites.DemasiadosIntentos as exc:
            raise demasiadas_peticiones(exc) from exc

    return dependencia


LimiteCampo = Annotated[
    None,
    Depends(limite_por_usuario("campo", lambda: get_settings().campo_max_peticiones_por_minuto)),
]
LimiteCodigo = Annotated[
    None,
    Depends(limite_por_usuario("codigo", lambda: get_settings().codigo_max_peticiones_por_minuto)),
]


def leer_cursor(cursor: Annotated[str | None, Query(max_length=500)] = None) -> Cursor | None:
    if cursor is None:
        return None
    try:
        return Cursor.decodificar(cursor)
    except CursorInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cursor no válido.") from exc


def leer_limite(limite: Annotated[int, Query(ge=1)] = 50) -> int:
    """Tamaño de página, recortado al máximo del servidor (sección 9.1) en vez de rechazado."""
    return min(limite, get_settings().pagina_max)


def con_etag(request: Request, modelo: BaseModel) -> Response:
    """Respuesta JSON con `ETag`, y 304 si el cliente ya tiene esa versión (06-fase3, 9.4).

    La lista y el detalle de órdenes se consultan cada 30 segundos mientras la pestaña está visible.
    El ETag se calcula sobre el cuerpo, así que ahorra red pero no la consulta, que con los índices
    de la fase es barata. `private`: ningún proxy intermedio guarda datos de una empresa.
    """
    cuerpo = modelo.model_dump_json().encode()
    etag = '"' + hashlib.sha256(cuerpo).hexdigest()[:32] + '"'
    cabeceras = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cabeceras)
    return Response(content=cuerpo, media_type="application/json", headers=cabeceras)


CursorDePagina = Annotated[Cursor | None, Depends(leer_cursor)]
LimiteDePagina = Annotated[int, Depends(leer_limite)]


def http_de_captura(exc: CapturaInvalida) -> HTTPException:
    """Rechazo de captura a HTTP. El mensaje va tal cual: está escrito para el operario."""
    if isinstance(exc, ActivoNoDisponible):
        codigo = status.HTTP_409_CONFLICT if exc.existe else status.HTTP_404_NOT_FOUND
        return HTTPException(status_code=codigo, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


__all__ = [
    "TODOS",
    "Almacen",
    "Claims",
    "CursorDePagina",
    "LimiteCampo",
    "LimiteCodigo",
    "LimiteDePagina",
    "demasiadas_peticiones",
    "http_de_captura",
]
