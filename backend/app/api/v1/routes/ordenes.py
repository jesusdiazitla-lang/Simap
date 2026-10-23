"""Órdenes de trabajo (RF-11 a RF-16; 06-fase3-ordenes-de-trabajo.md, sección 8).

Cada transición tiene su propia ruta: así el rol exigido y el estado de origen son parte de la
definición del endpoint y no un parámetro que el cliente pueda manipular. Los roles son los de la
tabla 11.1 del documento, y `tests/test_ordenes.py` la recorre entera.

El operario no tiene acceso a las órdenes (403). Lo que sí ve —si un equipo está en falla y con qué
orden— le llega con la ficha del equipo (`/activos/{id}`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.api.v1.comun import (
    CursorDePagina,
    LimiteDePagina,
    con_etag,
    http_de_captura,
    limite_por_usuario,
)
from app.core.config import get_settings
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import Pagina
from app.schemas.orden_trabajo import (
    Cancelar,
    Correccion,
    Evento,
    FallaCrear,
    FiltroEstado,
    NotaLibre,
    NotaObligatoria,
    NotaOpcional,
    OrdenCreada,
    OrdenDetalle,
    OrdenEditar,
    OrdenResumen,
    Persona,
    Reparada,
)
from app.schemas.prediccion import ConvertirEnFalla
from app.services import activos, ordenes, ordenes_estados
from app.services.capturas import CapturaInvalida
from app.services.prediccion import tareas

router = APIRouter(tags=["ordenes"])

S, T, A, G = Rol.SUPERVISOR, Rol.TECNICO_TALLER, Rol.ADMINISTRADOR, Rol.GERENTE

#: Tabla 11.1 del documento, fila por fila.
Reporta = Annotated[Claims, Depends(requiere_roles(S, A))]
Consulta = Annotated[Claims, Depends(requiere_roles(T, S, G, A))]
Edita = Annotated[Claims, Depends(requiere_roles(S, A))]
LlevaAlTaller = Annotated[Claims, Depends(requiere_roles(T, S, A))]
Repara = Annotated[Claims, Depends(requiere_roles(T))]
Autoriza = Annotated[Claims, Depends(requiere_roles(S, A))]
Cancela = Annotated[Claims, Depends(requiere_roles(S, A))]
Anota = Annotated[Claims, Depends(requiere_roles(T, S, A))]
Corrige = Annotated[Claims, Depends(requiere_roles(A))]

LimiteFalla = Annotated[
    None, Depends(limite_por_usuario("falla", lambda: get_settings().falla_max_por_minuto))
]
LimiteTransicion = Annotated[
    None,
    Depends(limite_por_usuario("transicion", lambda: get_settings().transicion_max_por_minuto)),
]

R = TypeVar("R")


def actor(claims: Claims) -> ordenes.Actor:
    return ordenes.Actor(
        empresa_id=claims.empresa_id, usuario_id=claims.usuario_id, rol=claims.rol.value
    )


def http_de_orden(exc: Exception) -> HTTPException:
    """Errores del servicio a HTTP, con los códigos estables de la sección 8.1."""
    if isinstance(exc, ordenes.OrdenNoEncontrada):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Orden no encontrada.")
    if isinstance(exc, ordenes.Conflicto):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "codigo": exc.codigo,
                "mensaje": str(exc),
                "orden_id": str(exc.orden_id) if exc.orden_id else None,
                "numero": exc.numero,
                # Lo propio de cada conflicto: los repuestos que faltan (F4, 8.1).
                **exc.extra,
            },
        )
    if isinstance(exc, ordenes.ReferenciaInvalida):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, ordenes.UsuarioInactivo):
        return HTTPException(
            status.HTTP_403_FORBIDDEN, "Tu usuario está dado de baja y ya no puede actuar."
        )
    if isinstance(exc, ordenes.SinPermiso):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, CapturaInvalida):
        return http_de_captura(exc)
    raise exc


async def _o_http(llamada: Awaitable[R]) -> R:
    try:
        return await llamada
    except (
        ordenes.OrdenNoEncontrada,
        ordenes.Conflicto,
        ordenes.ReferenciaInvalida,
        ordenes.UsuarioInactivo,
        ordenes.SinPermiso,
        CapturaInvalida,
    ) as exc:
        raise http_de_orden(exc) from exc


def _persona(personas: dict[UUID, tuple[str, bool]], uid: UUID | None) -> Persona | None:
    if uid is None:
        return None
    nombre, activo = personas.get(uid, ("(desconocido)", False))
    return Persona(id=uid, nombre=nombre, activo=activo)


def resumen(orden: Any, activo_nombre: str, activo_codigo: str, componente: str) -> OrdenResumen:
    return OrdenResumen.model_validate(
        {
            **{c: getattr(orden, c) for c in OrdenResumen.model_fields if hasattr(orden, c)},
            "activo_nombre": activo_nombre,
            "activo_codigo": activo_codigo,
            "componente_nombre": componente,
        }
    )


def salida_detalle(d: ordenes.Detalle) -> OrdenDetalle:
    o = d.orden
    base = resumen(o, d.activo_nombre, d.activo_codigo, d.componente_nombre).model_dump()
    reportado = _persona(d.personas, o.reportado_por)
    assert reportado is not None
    return OrdenDetalle.model_validate(
        {
            **base,
            **{
                c: getattr(o, c)
                for c in (
                    "cliente_id",
                    "alerta_origen_id",
                    "lectura_id",
                    "horas_acumuladas_en_falla",
                    "temperatura",
                    "codigo_error",
                    "descripcion",
                    "trabajo_realizado",
                    "motivo_cancelacion",
                    "motivo_revision",
                    "en_taller_en",
                    "reparada_en",
                    "fecha_salida_taller",
                )
            },
            "reportado_por": reportado,
            "reparado_por": _persona(d.personas, o.reparado_por),
            "autorizado_por": _persona(d.personas, o.autorizado_por),
            "eventos": [
                Evento(
                    id=e.id,
                    tipo=e.tipo,
                    estado_anterior=e.estado_anterior,
                    estado_nuevo=e.estado_nuevo,
                    usuario=_persona(d.personas, e.usuario_id),
                    rol_al_momento=e.rol_al_momento,
                    nota=e.nota,
                    datos=e.datos,
                    creado_en=e.creado_en,
                )
                for e in d.eventos
            ],
        }
    )


async def _detalle(session: SesionDB, orden_id: UUID) -> OrdenDetalle:
    return salida_detalle(await _o_http(ordenes.detalle(session, orden_id)))


# --- Reporte de falla ---------------------------------------------------------------


@router.post("/activos/{activo_id}/fallas", response_model=OrdenCreada)
async def reportar_falla(
    activo_id: UUID,
    datos: FallaCrear,
    claims: Reporta,
    __: LimiteFalla,
    session: SesionDB,
    response: Response,
    tareas_fondo: BackgroundTasks,
) -> OrdenCreada:
    """201 si nació la orden; 200 si es un reenvío del mismo `cliente_id` (sección 6.2).

    La falla registra una lectura de horómetro: el riesgo del equipo se recalcula después del
    commit (F4, 9.2).
    """
    estado, orden = await _o_http(
        ordenes.reportar_falla(
            session,
            actor(claims),
            activo_id=activo_id,
            componente_id=datos.componente_id,
            horometro=datos.horometro,
            descripcion=datos.descripcion,
            capturado_en=datos.capturado_en,
            cliente_id=datos.cliente_id,
            temperatura=datos.temperatura,
            codigo_error=datos.codigo_error,
            alerta_id=datos.alerta_id,
        )
    )
    response.status_code = status.HTTP_201_CREATED if estado == "creado" else status.HTTP_200_OK
    tareas_fondo.add_task(tareas.tras_lectura, claims.empresa_id, activo_id)
    return OrdenCreada(estado=estado, orden=await _detalle(session, orden.id))


# --- Consulta -------------------------------------------------------------------------


async def _pagina(
    session: SesionDB,
    *,
    filtro: str | None,
    activo_id: UUID | None,
    componente_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: CursorDePagina,
    limite: int,
) -> Pagina[OrdenResumen]:
    filas, siguiente = await ordenes.listar(
        session,
        filtro=filtro,
        activo_id=activo_id,
        componente_id=componente_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return Pagina[OrdenResumen](
        items=[resumen(o, n, c, comp) for o, n, c, comp in filas],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@router.get("/ordenes", response_model=Pagina[OrdenResumen])
async def listar(
    _: Consulta,
    session: SesionDB,
    request: Request,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
    estado: FiltroEstado | None = None,
    activo_id: UUID | None = None,
    componente_id: UUID | None = None,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
) -> Response:
    """Bandeja con filtros. Con `If-None-Match`, 304 si nada cambió (sección 9.4): la pantalla
    consulta cada 30 segundos y la mayoría de las veces no hay nada nuevo."""
    pagina = await _pagina(
        session,
        filtro=estado,
        activo_id=activo_id,
        componente_id=componente_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return con_etag(request, pagina)


@router.get("/activos/{activo_id}/ordenes", response_model=Pagina[OrdenResumen])
async def historial_del_equipo(
    activo_id: UUID,
    _: Consulta,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
) -> Pagina[OrdenResumen]:
    try:
        await activos.obtener(session, activo_id)
    except activos.ActivoNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipo no encontrado.") from exc
    return await _pagina(
        session,
        filtro=None,
        activo_id=activo_id,
        componente_id=None,
        desde=None,
        hasta=None,
        cursor=cursor,
        limite=limite,
    )


@router.get("/ordenes/{orden_id}", response_model=OrdenDetalle)
async def obtener(orden_id: UUID, _: Consulta, session: SesionDB, request: Request) -> Response:
    """Detalle con responsables e historial. 404 si es de otra empresa, nunca 403."""
    return con_etag(request, await _detalle(session, orden_id))


# --- Edición, notas y correcciones ------------------------------------------------------


@router.patch("/ordenes/{orden_id}", response_model=OrdenDetalle)
async def editar(
    orden_id: UUID, datos: OrdenEditar, claims: Edita, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    await _o_http(
        ordenes.editar(session, actor(claims), orden_id, datos.model_dump(exclude_unset=True))
    )
    return await _detalle(session, orden_id)


@router.post("/ordenes/{orden_id}/notas", response_model=OrdenDetalle)
async def agregar_nota(
    orden_id: UUID, datos: NotaLibre, claims: Anota, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    await _o_http(ordenes.agregar_nota(session, actor(claims), orden_id, datos.nota))
    return await _detalle(session, orden_id)


@router.post("/ordenes/{orden_id}/confirmar-horometro", response_model=OrdenDetalle)
async def confirmar_horometro(
    orden_id: UUID,
    claims: Edita,
    __: LimiteTransicion,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
) -> OrdenDetalle:
    """Con la orden abierta, supervisor o administrador; cerrada, solo el administrador."""
    orden = await _o_http(ordenes.confirmar_horometro(session, actor(claims), orden_id))
    tareas_fondo.add_task(
        tareas.tras_cierre, claims.empresa_id, orden.componente_id, orden.activo_id
    )
    return await _detalle(session, orden_id)


@router.post("/ordenes/{orden_id}/correccion", response_model=OrdenDetalle)
async def corregir(
    orden_id: UUID, datos: Correccion, claims: Corrige, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    """Único camino para cambiar una orden cerrada (sección 6.5). Deja un evento permanente."""
    cambios = datos.model_dump(exclude_unset=True, exclude={"nota"})
    await _o_http(ordenes.corregir(session, actor(claims), orden_id, cambios, datos.nota))
    return await _detalle(session, orden_id)


# --- Transiciones (sección 6.1) ------------------------------------------------------------


def _transicion(
    accion: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[OrdenDetalle]]:
    async def ejecutar(
        session: SesionDB, claims: Claims, orden_id: UUID, **datos: Any
    ) -> OrdenDetalle:
        await _o_http(accion(session, actor(claims), orden_id, **datos))
        return await _detalle(session, orden_id)

    return ejecutar


@router.post("/ordenes/{orden_id}/en-taller", response_model=OrdenDetalle)
async def a_taller(
    orden_id: UUID, claims: LlevaAlTaller, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    return await _transicion(ordenes_estados.a_taller)(session, claims, orden_id)


@router.post("/ordenes/{orden_id}/reparada", response_model=OrdenDetalle)
async def marcar_reparada(
    orden_id: UUID, datos: Reparada, claims: Repara, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    return await _transicion(ordenes_estados.marcar_reparada)(
        session,
        claims,
        orden_id,
        trabajo_realizado=datos.trabajo_realizado,
        tipo_intervencion=datos.tipo_intervencion,
    )


@router.post("/ordenes/{orden_id}/cerrar", response_model=OrdenDetalle)
async def cerrar(
    orden_id: UUID,
    claims: Autoriza,
    __: LimiteTransicion,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
    datos: NotaOpcional | None = None,
) -> OrdenDetalle:
    """Autoriza la salida del taller y calcula el tiempo fuera de servicio (RF-15).

    Fase 4: descuenta los repuestos (409 `stock_insuficiente` con los faltantes si no alcanzan; la
    orden sigue Reparada) y, después del commit, reajusta el modelo del componente y recalcula el
    riesgo del equipo, sin que la respuesta espere por ello.
    """
    orden = await _o_http(
        ordenes_estados.cerrar(session, actor(claims), orden_id, nota=datos.nota if datos else None)
    )
    tareas_fondo.add_task(
        tareas.tras_cierre, claims.empresa_id, orden.componente_id, orden.activo_id
    )
    return await _detalle(session, orden_id)


@router.post("/ordenes/{orden_id}/rechazar-cierre", response_model=OrdenDetalle)
async def rechazar_cierre(
    orden_id: UUID,
    datos: NotaObligatoria,
    claims: Autoriza,
    __: LimiteTransicion,
    session: SesionDB,
) -> OrdenDetalle:
    return await _transicion(ordenes_estados.rechazar_cierre)(
        session, claims, orden_id, nota=datos.nota
    )


@router.post("/ordenes/{orden_id}/convertir-en-falla", response_model=OrdenDetalle)
async def convertir_en_falla(
    orden_id: UUID,
    datos: ConvertirEnFalla,
    claims: Autoriza,
    __: LimiteTransicion,
    session: SesionDB,
) -> OrdenDetalle:
    """La orden predictiva pasa a ser una falla real, con el horómetro y la fecha de la falla
    (F4, 6.4). Supervisor o administrador; solo con la orden abierta."""
    return await _transicion(ordenes_estados.convertir_en_falla)(
        session, claims, orden_id, horometro=datos.horometro, fecha_falla=datos.fecha_falla
    )


@router.post("/ordenes/{orden_id}/cancelar", response_model=OrdenDetalle)
async def cancelar(
    orden_id: UUID, datos: Cancelar, claims: Cancela, __: LimiteTransicion, session: SesionDB
) -> OrdenDetalle:
    return await _transicion(ordenes_estados.cancelar)(
        session, claims, orden_id, motivo=datos.motivo
    )
