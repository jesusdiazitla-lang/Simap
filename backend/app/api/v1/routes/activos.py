"""Equipos: alta con QR, ficha, baja lógica, resolución del código y etiqueta (RF-04..07).

Todas las rutas pasan por `get_db` (RLS) y declaran sus roles. La resolución del código lleva además
un límite por usuario: es la que permitiría barrer códigos ajenos a base de probar (sección 6.2).
"""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.v1.comun import TODOS, CursorDePagina, LimiteCodigo, LimiteDePagina
from app.core.config import get_settings
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.models.activo import Activo
from app.schemas.activo import ActivoCrear, ActivoEditar, ActivoOut, Pagina
from app.services import activos as servicio
from app.services import qr

router = APIRouter(prefix="/activos", tags=["activos"])

Cualquiera = Annotated[Claims, Depends(requiere_roles(*TODOS))]
Administrador = Annotated[Claims, Depends(requiere_roles(Rol.ADMINISTRADOR))]
ImprimeEtiquetas = Annotated[Claims, Depends(requiere_roles(Rol.ADMINISTRADOR, Rol.SUPERVISOR))]

NO_ENCONTRADO = "Equipo no encontrado."


def salida(activo: Activo) -> ActivoOut:
    return ActivoOut.model_validate(
        {
            **{c: getattr(activo, c) for c in ActivoOut.model_fields if hasattr(activo, c)},
            "codigo": activo.qr_code,
            "codigo_corto": qr.presentar(activo.qr_code),
            "url_qr": qr.url_de(activo.qr_code, get_settings().app_base_url),
        }
    )


def _no_encontrado(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NO_ENCONTRADO)


@router.get("", response_model=Pagina[ActivoOut])
async def listar(
    _: Cualquiera,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
    estado: Literal["activo", "baja"] | None = None,
    tipo: Annotated[str | None, Query(max_length=120)] = None,
    ubicacion: Annotated[str | None, Query(max_length=120)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Pagina[ActivoOut]:
    filas, siguiente = await servicio.listar(
        session,
        estado=estado,
        tipo=tipo,
        ubicacion=ubicacion,
        texto=q,
        cursor=cursor,
        limite=limite,
    )
    return Pagina[ActivoOut](
        items=[salida(a) for a in filas],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@router.post("", response_model=ActivoOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: ActivoCrear, claims: Administrador, session: SesionDB) -> ActivoOut:
    """Alta con código QR único generado por el servidor (RF-05)."""
    try:
        activo = await servicio.crear(
            session,
            empresa_id=claims.empresa_id,
            autor_id=claims.usuario_id,
            datos=datos.model_dump(exclude={"horometro_inicial"}),
            horometro_inicial=datos.horometro_inicial,
        )
    except servicio.SinCodigoLibre as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No se pudo generar el código. Vuelve a intentarlo.",
        ) from exc
    return salida(activo)


# Antes que `/{activo_id}`: si no, «por-codigo» se intentaría leer como un UUID.
@router.get("/por-codigo/{codigo}", response_model=ActivoOut)
async def por_codigo(
    codigo: str,
    _: Cualquiera,
    __: LimiteCodigo,
    session: SesionDB,
) -> ActivoOut:
    """Lo que se consulta al escanear o teclear una etiqueta.

    Inexistente, mal formado o de otra empresa: siempre el mismo 404, nunca un 403 (sección 6.2).
    Ni siquiera un 422 por longitud: también distinguiría «formato» de «existencia».
    """
    if len(codigo) > 20:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_ENCONTRADO)
    try:
        return salida(await servicio.por_codigo(session, codigo))
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc


@router.get("/{activo_id}", response_model=ActivoOut)
async def obtener(activo_id: UUID, _: Cualquiera, session: SesionDB) -> ActivoOut:
    try:
        return salida(await servicio.obtener(session, activo_id))
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc


@router.patch("/{activo_id}", response_model=ActivoOut)
async def editar(
    activo_id: UUID, datos: ActivoEditar, _: Administrador, session: SesionDB
) -> ActivoOut:
    """Ficha técnica. El esquema no admite `qr_code` ni `empresa_id`: intentarlo es un 422."""
    try:
        activo = await servicio.editar(session, activo_id, datos.model_dump(exclude_unset=True))
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc
    return salida(activo)


@router.post("/{activo_id}/baja", response_model=ActivoOut)
async def dar_de_baja(activo_id: UUID, _: Administrador, session: SesionDB) -> ActivoOut:
    """Baja lógica (RF-06). El código sigue resolviendo, con el estado visible."""
    try:
        return salida(await servicio.dar_de_baja(session, activo_id))
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc


@router.post("/{activo_id}/regenerar-codigo", response_model=ActivoOut)
async def regenerar_codigo(activo_id: UUID, _: Administrador, session: SesionDB) -> ActivoOut:
    """Etiqueta copiada o comprometida: código nuevo, y el anterior deja de resolver."""
    try:
        return salida(await servicio.regenerar_codigo(session, activo_id))
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc
    except servicio.SinCodigoLibre as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No se pudo generar el código. Vuelve a intentarlo.",
        ) from exc


@router.get("/{activo_id}/etiqueta.svg")
async def etiqueta(
    activo_id: UUID, _: ImprimeEtiquetas, session: SesionDB, request: Request
) -> Response:
    """Etiqueta imprimible en SVG (sección 6.3), generada al vuelo (sección 9.5).

    - `ETag` y `Cache-Control: private`: el navegador de quien la pidió puede reutilizarla, ningún
      proxy intermedio puede guardarla.
    - `Content-Security-Policy` propia: un SVG abierto en el navegador es un documento que podría
      ejecutar código. El nombre del equipo ya va escapado, pero si algún día se colara algo, esta
      cabecera impide que corra.
    """
    try:
        activo = await servicio.obtener(session, activo_id)
    except servicio.ActivoNoEncontrado as exc:
        raise _no_encontrado(exc) from exc
    base_url = get_settings().app_base_url
    huella = hashlib.sha256(f"{activo.qr_code}|{activo.nombre}|{base_url}".encode()).hexdigest()
    etag = f'"{huella[:32]}"'
    cabeceras = {
        "ETag": etag,
        "Cache-Control": "private, max-age=0, must-revalidate",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "Content-Disposition": f'inline; filename="etiqueta-{activo.qr_code}.svg"',
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cabeceras)
    svg = qr.etiqueta_svg(codigo=activo.qr_code, nombre=activo.nombre, base_url=base_url)
    return Response(content=svg, media_type="image/svg+xml", headers=cabeceras)
