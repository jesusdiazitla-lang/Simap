"""Inventario de repuestos (RF-23 a RF-26; 07-fase4-prediccion-e-inventario.md, sección 8).

Roles por acción (decisión 2, tabla 12.1): el administrador da de alta y edita repuestos y hace el
ajuste por conteo; el supervisor registra ingresos; el técnico agrega los repuestos de su orden y
consulta existencias, pero no el libro ni los costos; el gerente solo lee. El operario no entra.

El stock no se puede enviar en ningún cuerpo: solo lo mueve el libro.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.v1.comun import CursorDePagina, LimiteDePagina, limite_por_usuario
from app.api.v1.routes.ordenes import actor, http_de_orden
from app.core.config import get_settings
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import Pagina
from app.schemas.inventario import (
    Ajuste,
    Descuadre,
    Ingreso,
    LineaGuardar,
    LineaOut,
    MovimientoOut,
    RepuestoCrear,
    RepuestoEditar,
    RepuestoOut,
    RepuestoTecnico,
)
from app.services import inventario, ordenes

router = APIRouter(tags=["inventario"])

S, T, A, G = Rol.SUPERVISOR, Rol.TECNICO_TALLER, Rol.ADMINISTRADOR, Rol.GERENTE

VeInventario = Annotated[Claims, Depends(requiere_roles(S, T, G, A))]
VeLibro = Annotated[Claims, Depends(requiere_roles(S, G, A))]
RegistraIngreso = Annotated[Claims, Depends(requiere_roles(S, A))]
Administrador = Annotated[Claims, Depends(requiere_roles(A))]
VeLineas = Annotated[Claims, Depends(requiere_roles(S, T, G, A))]
EditaLineas = Annotated[Claims, Depends(requiere_roles(S, T, A))]

LimiteLinea = Annotated[
    None,
    Depends(limite_por_usuario("linea", lambda: get_settings().linea_repuesto_max_por_minuto)),
]
LimiteIngreso = Annotated[
    None, Depends(limite_por_usuario("ingreso", lambda: get_settings().ingreso_max_por_minuto))
]

R = TypeVar("R")


async def _o_http(llamada: Awaitable[R]) -> R:
    try:
        return await llamada
    except inventario.RepuestoNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repuesto no encontrado.") from exc
    except (
        ordenes.Conflicto,
        ordenes.OrdenNoEncontrada,
        ordenes.UsuarioInactivo,
        ordenes.ReferenciaInvalida,
    ) as exc:
        raise http_de_orden(exc) from exc


def _repuesto(r: object) -> RepuestoOut:
    salida = RepuestoOut.model_validate(r)
    salida.bajo_minimo = salida.stock_actual < salida.stock_minimo
    return salida


# --- Catálogo ---------------------------------------------------------------------------------


@router.get("/repuestos", response_model=Pagina[RepuestoOut] | Pagina[RepuestoTecnico])
async def listar(
    claims: VeInventario,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
    buscar: Annotated[str | None, Query(max_length=60)] = None,
    bajo_minimo: bool = False,
    incluir_inactivos: bool = False,
) -> Pagina[RepuestoOut] | Pagina[RepuestoTecnico]:
    """Con stock y mínimo; filtro «bajo el mínimo». El técnico no ve costos."""
    filas, siguiente = await inventario.listar(
        session,
        buscar=buscar,
        bajo_minimo=bajo_minimo,
        incluir_inactivos=incluir_inactivos and claims.rol is A,
        cursor=cursor,
        limite=limite,
    )
    proximo = siguiente.codificar() if siguiente else None
    if claims.rol is T:
        return Pagina[RepuestoTecnico](
            items=[
                RepuestoTecnico(
                    id=r.id,
                    nombre=r.nombre,
                    codigo=r.codigo,
                    stock_actual=r.stock_actual,
                    stock_minimo=r.stock_minimo,
                    bajo_minimo=r.stock_actual < r.stock_minimo,
                )
                for r in filas
            ],
            next_cursor=proximo,
        )
    return Pagina[RepuestoOut](items=[_repuesto(r) for r in filas], next_cursor=proximo)


@router.get("/repuestos/{repuesto_id}", response_model=RepuestoOut)
async def obtener(repuesto_id: UUID, _: VeLibro, session: SesionDB) -> RepuestoOut:
    return _repuesto(await _o_http(inventario.obtener(session, repuesto_id)))


@router.post("/repuestos", response_model=RepuestoOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: RepuestoCrear, claims: Administrador, session: SesionDB) -> RepuestoOut:
    """Alta; el stock inicial entra al libro como movimiento `inicial`."""
    repuesto = await _o_http(
        inventario.crear(
            session,
            actor(claims),
            nombre=datos.nombre,
            codigo=datos.codigo,
            stock_inicial=datos.stock_inicial,
            stock_minimo=datos.stock_minimo,
            costo_unitario=datos.costo_unitario,
        )
    )
    return _repuesto(repuesto)


@router.patch("/repuestos/{repuesto_id}", response_model=RepuestoOut)
async def editar(
    repuesto_id: UUID, datos: RepuestoEditar, claims: Administrador, session: SesionDB
) -> RepuestoOut:
    """Nombre, mínimo, costo y activo. Nunca el stock."""
    repuesto = await _o_http(
        inventario.editar(session, actor(claims), repuesto_id, datos.model_dump(exclude_unset=True))
    )
    return _repuesto(repuesto)


@router.post("/repuestos/{repuesto_id}/ingresos", response_model=RepuestoOut)
async def ingreso(
    repuesto_id: UUID,
    datos: Ingreso,
    claims: RegistraIngreso,
    __: LimiteIngreso,
    session: SesionDB,
) -> RepuestoOut:
    return _repuesto(
        await _o_http(
            inventario.ingreso(session, actor(claims), repuesto_id, datos.cantidad, datos.nota)
        )
    )


@router.post("/repuestos/{repuesto_id}/ajuste", response_model=RepuestoOut)
async def ajuste(
    repuesto_id: UUID, datos: Ajuste, claims: Administrador, session: SesionDB
) -> RepuestoOut:
    """Conteo físico con nota obligatoria. Si coincide con el sistema, no asienta nada."""
    return _repuesto(
        await _o_http(
            inventario.ajustar(session, actor(claims), repuesto_id, datos.conteo, datos.nota)
        )
    )


@router.get("/repuestos/{repuesto_id}/movimientos", response_model=Pagina[MovimientoOut])
async def movimientos(
    repuesto_id: UUID,
    _: VeLibro,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
) -> Pagina[MovimientoOut]:
    """El libro del repuesto, del más reciente al más antiguo, con el stock resultante."""
    filas, siguiente = await _o_http(
        inventario.movimientos(session, repuesto_id, cursor=cursor, limite=limite)
    )
    return Pagina[MovimientoOut](
        items=[MovimientoOut.model_validate(m) for m in filas],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@router.get("/inventario/conciliacion", response_model=list[Descuadre])
async def conciliacion(_: Administrador, session: SesionDB) -> list[Descuadre]:
    """Repuestos cuyo stock no es la suma de su libro. Debe devolver una lista vacía."""
    return [Descuadre(**d) for d in await inventario.conciliacion(session)]


# --- Líneas de repuestos de una orden (RF-24) -----------------------------------------------------


async def _lineas(session: SesionDB, orden_id: UUID, ver_costos: bool) -> list[LineaOut]:
    return [
        LineaOut(
            repuesto_id=linea.repuesto_id,
            codigo=linea.codigo,
            nombre=linea.nombre,
            cantidad=linea.cantidad,
            stock_actual=linea.stock_actual,
            costo_unitario=linea.costo_unitario if ver_costos else None,
        )
        for linea in await _o_http(inventario.lineas(session, orden_id))
    ]


@router.get("/ordenes/{orden_id}/repuestos", response_model=list[LineaOut])
async def lineas(orden_id: UUID, claims: VeLineas, session: SesionDB) -> list[LineaOut]:
    return await _lineas(session, orden_id, ver_costos=claims.rol is not T)


@router.put("/ordenes/{orden_id}/repuestos/{repuesto_id}", response_model=list[LineaOut])
async def guardar_linea(
    orden_id: UUID,
    repuesto_id: UUID,
    datos: LineaGuardar,
    claims: EditaLineas,
    __: LimiteLinea,
    session: SesionDB,
) -> list[LineaOut]:
    """Agrega o corrige la cantidad. Solo con la orden abierta; el stock se descuenta al cerrar."""
    await _o_http(
        inventario.guardar_linea(session, actor(claims), orden_id, repuesto_id, datos.cantidad)
    )
    return await _lineas(session, orden_id, ver_costos=claims.rol is not T)


@router.delete(
    "/ordenes/{orden_id}/repuestos/{repuesto_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def quitar_linea(
    orden_id: UUID, repuesto_id: UUID, claims: EditaLineas, __: LimiteLinea, session: SesionDB
) -> Response:
    await _o_http(inventario.quitar_linea(session, actor(claims), orden_id, repuesto_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
