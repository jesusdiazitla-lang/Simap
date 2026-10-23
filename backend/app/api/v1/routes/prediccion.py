"""Predicción de fallas (RF-17 a RF-22; 07-fase4-prediccion-e-inventario.md, sección 8).

Roles de la tabla 12.1: el operario no tiene acceso a nada de esta fase (403); el técnico ve el
riesgo de un equipo, pero no la bandeja de alertas ni el modelo; el gerente solo lee; declarar
componentes, edades y la configuración es del administrador. `tests/test_prediccion.py` recorre
las combinaciones.

Lo que cambia el riesgo (declarar una edad, la configuración) lo recalcula **después del commit**,
en segundo plano (RNF-02): la respuesta no espera al cálculo.
"""

from __future__ import annotations

from collections.abc import Awaitable
from decimal import Decimal, InvalidOperation
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.v1.comun import CursorDePagina, LimiteDePagina
from app.api.v1.routes.ordenes import actor, http_de_orden, salida_detalle
from app.core.cursor import Cursor
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import Pagina
from app.schemas.orden_trabajo import OrdenDetalle
from app.schemas.prediccion import (
    AlertaSistemaOut,
    ComponenteEquipoOut,
    ComponentesEquipo,
    ConfiguracionEditar,
    ConfiguracionOut,
    CrearOrdenPredictiva,
    DeclararEdad,
    Descartar,
    FiltroAlerta,
    HistorialModelo,
    ModeloOut,
    RiesgoActivo,
    RiesgoComponente,
    RiesgoEquipo,
    TipoAlerta,
)
from app.services import activos, ordenes
from app.services.prediccion import (
    ajuste,
    alertas,
    componentes_equipo,
    configuracion,
    riesgo,
    tareas,
)

router = APIRouter(tags=["prediccion"])

S, T, A, G = Rol.SUPERVISOR, Rol.TECNICO_TALLER, Rol.ADMINISTRADOR, Rol.GERENTE

#: Tabla 12.1 del documento.
VeRiesgo = Annotated[Claims, Depends(requiere_roles(S, T, G, A))]
VeBandeja = Annotated[Claims, Depends(requiere_roles(S, G, A))]
GestionaAlerta = Annotated[Claims, Depends(requiere_roles(S, A))]
VeModelo = Annotated[Claims, Depends(requiere_roles(S, G, A))]
Administrador = Annotated[Claims, Depends(requiere_roles(A))]

#: La bandeja se abre en las vigentes; «historial» son las terminales.
FILTROS: dict[str, tuple[str, ...]] = {
    "vigentes": ("activa", "reconocida", "atendida"),
    "historial": ("resuelta", "descartada"),
}

R = TypeVar("R")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, alertas.AlertaNoEncontrada):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada.")
    if isinstance(exc, componentes_equipo.EquipoNoEncontrado | activos.ActivoNoEncontrado):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Activo no encontrado.")
    if isinstance(exc, ajuste.ComponenteNoEncontrado):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Componente no encontrado.")
    if isinstance(exc, componentes_equipo.EdadInvalida):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, {"codigo": "edad_invalida", "mensaje": str(exc)}
        )
    if isinstance(exc, componentes_equipo.ComponenteNoValido):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"codigo": "referencia_invalida", "mensaje": str(exc)},
        )
    return http_de_orden(exc)


async def _o_http(llamada: Awaitable[R]) -> R:
    try:
        return await llamada
    except (
        alertas.AlertaNoEncontrada,
        componentes_equipo.EquipoNoEncontrado,
        componentes_equipo.EdadInvalida,
        componentes_equipo.ComponenteNoValido,
        activos.ActivoNoEncontrado,
        ajuste.ComponenteNoEncontrado,
        ordenes.Conflicto,
        ordenes.OrdenNoEncontrada,
        ordenes.ReferenciaInvalida,
        ordenes.UsuarioInactivo,
    ) as exc:
        raise _error(exc) from exc


# --- Riesgo ---------------------------------------------------------------------------------


def _riesgo_componente(c: riesgo.ComponenteConRiesgo) -> RiesgoComponente:
    r = c.riesgo
    return RiesgoComponente(
        componente_id=c.componente_id,
        componente=c.componente,
        estado_calculo=r.estado_calculo if r else "sin_edad",
        edad_horas=r.edad_horas if r else None,
        horizonte_horas=r.horizonte_horas if r else None,
        beta=r.beta if r else None,
        eta=r.eta if r else None,
        riesgo_base=r.riesgo_base if r else None,
        multiplicador=r.multiplicador if r else None,
        riesgo=r.riesgo if r else None,
        n_eventos=r.n_eventos if r else None,
        fuente=r.fuente if r else None,
        confianza=r.confianza if r else None,
        calculado_en=r.calculado_en if r else None,
    )


@router.get("/activos/{activo_id}/riesgo", response_model=RiesgoEquipo)
async def riesgo_del_equipo(activo_id: UUID, claims: VeRiesgo, session: SesionDB) -> RiesgoEquipo:
    """Riesgo de cada componente: edad, β, η, fallas, fuente, confianza y hora del cálculo.

    «Sin edad» y «sin modelo» llegan como estado, nunca como un 0 %.
    """
    await _o_http(activos.obtener(session, activo_id))
    datos = await riesgo.riesgo_del_equipo(session, claims.empresa_id, activo_id)
    return RiesgoEquipo(
        activo_id=activo_id,
        umbral=datos.config.umbral_riesgo,
        horizonte_horas=datos.config.horizonte_horas,
        horas_por_dia=datos.horas_por_dia,
        alertas_de_campo=datos.alertas_de_campo,
        alertas_minimas=datos.config.alertas_minimas,
        componentes=[_riesgo_componente(c) for c in datos.componentes],
    )


@router.get("/riesgos", response_model=Pagina[RiesgoActivo])
async def ranking(
    _: VeBandeja, session: SesionDB, cursor: CursorDePagina, limite: LimiteDePagina
) -> Pagina[RiesgoActivo]:
    """Equipos por riesgo descendente, cada uno por su componente más riesgoso (v_riesgo_activo)."""
    cursor_riesgo = None
    if cursor is not None:
        try:
            cursor_riesgo = Decimal(cursor.valor)
        except InvalidOperation as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cursor ilegible.") from exc
    filas, siguiente = await riesgo.ranking(
        session,
        cursor_riesgo=cursor_riesgo,
        cursor_id=cursor.id if cursor else None,
        limite=limite,
    )
    return Pagina[RiesgoActivo](
        items=[
            RiesgoActivo(
                activo_id=f.activo_id,
                activo=f.activo,
                codigo=f.codigo,
                componente_critico_id=f.componente_id,
                componente_critico=f.componente,
                riesgo=f.riesgo,
                confianza=f.confianza,
                fuente=f.fuente,
                n_eventos=f.n_eventos,
                edad_horas=f.edad_horas,
                calculado_en=f.calculado_en,
            )
            for f in filas
        ],
        next_cursor=Cursor(str(siguiente[0]), siguiente[1]).codificar() if siguiente else None,
    )


# --- Componentes de un equipo (6.1) ------------------------------------------------------------


async def _componentes(session: SesionDB, activo_id: UUID) -> ComponentesEquipo:
    activo = await _o_http(activos.obtener(session, activo_id))
    lista = await componentes_equipo.listar(session, activo_id)
    return ComponentesEquipo(
        activo_id=activo_id,
        horas_acumuladas=activo.horometro_offset + activo.horometro_actual,
        componentes=[
            ComponenteEquipoOut(
                componente_id=c.componente_id,
                nombre=c.nombre,
                horas_instalacion_inicial=c.horas_instalacion_inicial,
                estado_calculo=c.estado_calculo,
                riesgo=c.riesgo,
                edad_horas=c.edad_horas,
            )
            for c in lista
        ],
    )


@router.get("/activos/{activo_id}/componentes", response_model=ComponentesEquipo)
async def componentes_del_equipo(
    activo_id: UUID, _: VeBandeja, session: SesionDB
) -> ComponentesEquipo:
    return await _componentes(session, activo_id)


@router.put("/activos/{activo_id}/componentes/{componente_id}", response_model=ComponentesEquipo)
async def declarar_componente(
    activo_id: UUID,
    componente_id: UUID,
    datos: DeclararEdad,
    claims: Administrador,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
) -> ComponentesEquipo:
    """Registra el componente en el equipo y a qué horas del equipo se instaló la unidad actual."""
    await _o_http(
        componentes_equipo.declarar(
            session, claims.empresa_id, activo_id, componente_id, datos.horas_instalacion_inicial
        )
    )
    tareas_fondo.add_task(tareas.tras_ajuste_de_componente, claims.empresa_id, componente_id)
    return await _componentes(session, activo_id)


# --- Modelo de un componente --------------------------------------------------------------------


@router.get("/componentes/{componente_id}/modelo", response_model=ModeloOut)
async def modelo(componente_id: UUID, _: VeModelo, session: SesionDB) -> ModeloOut:
    """Modelo vigente e historial: la curva de aprendizaje."""
    datos = await _o_http(ajuste.modelo_de(session, componente_id))
    m = datos.modelo
    return ModeloOut(
        componente_id=componente_id,
        componente=datos.componente.nombre,
        vida_nominal_horas=datos.componente.vida_nominal_horas,
        beta=m.beta if m else None,
        eta=m.eta if m else None,
        n_eventos=m.n_eventos if m else None,
        n_vidas=m.n_vidas if m else None,
        exposicion_horas=m.exposicion_horas if m else None,
        fuente=m.fuente if m else None,
        confianza=m.confianza if m else None,
        convergio=m.convergio if m else None,
        version=m.version if m else None,
        ajustado_en=m.ajustado_en if m else None,
        historial=[HistorialModelo.model_validate(h) for h in datos.historial],
    )


# --- Configuración --------------------------------------------------------------------------------


@router.get("/configuracion/prediccion", response_model=ConfiguracionOut)
async def leer_configuracion(claims: VeBandeja, session: SesionDB) -> ConfiguracionOut:
    return ConfiguracionOut.model_validate(await configuracion.asegurar(session, claims.empresa_id))


@router.put("/configuracion/prediccion", response_model=ConfiguracionOut)
async def cambiar_configuracion(
    datos: ConfiguracionEditar,
    claims: Administrador,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
) -> ConfiguracionOut:
    """Umbral, horizonte, alertas mínimas, ventana, multiplicador y silencio. Recalcula todo."""
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    config = await configuracion.actualizar(session, claims.empresa_id, cambios)
    tareas_fondo.add_task(tareas.recalcular_empresa, claims.empresa_id)
    return ConfiguracionOut.model_validate(config)


# --- Alertas del sistema (6.3 y 6.4) --------------------------------------------------------------


def _alerta(f: alertas.FilaAlerta) -> AlertaSistemaOut:
    a = f.alerta
    return AlertaSistemaOut(
        id=a.id,
        tipo=a.tipo,
        estado=a.estado,
        activo_id=a.activo_id,
        activo=f.activo_nombre,
        componente_id=a.componente_id,
        componente=f.componente_nombre,
        repuesto_id=a.repuesto_id,
        repuesto=f.repuesto_nombre,
        repuesto_codigo=f.repuesto_codigo,
        riesgo=a.riesgo,
        umbral=a.umbral,
        confianza=a.confianza,
        fuente=a.fuente,
        stock_al_alertar=a.stock_al_alertar,
        stock_minimo_al_alertar=a.stock_minimo_al_alertar,
        creada_en=a.creada_en,
        gestionada_en=a.gestionada_en,
        nota=a.nota,
        orden_id=f.orden_id,
        orden_numero=f.orden_numero,
    )


@router.get("/alertas-sistema", response_model=Pagina[AlertaSistemaOut])
async def bandeja(
    _: VeBandeja,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
    tipo: TipoAlerta | None = None,
    estado: FiltroAlerta = "vigentes",
    activo_id: Annotated[UUID | None, Query()] = None,
) -> Pagina[AlertaSistemaOut]:
    estados = FILTROS.get(estado, (estado,))
    filas, siguiente = await alertas.listar(
        session, tipo=tipo, estados=estados, activo_id=activo_id, cursor=cursor, limite=limite
    )
    return Pagina[AlertaSistemaOut](
        items=[_alerta(f) for f in filas],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@router.post("/alertas-sistema/{alerta_id}/reconocer", response_model=AlertaSistemaOut)
async def reconocer(alerta_id: UUID, claims: GestionaAlerta, session: SesionDB) -> AlertaSistemaOut:
    await _o_http(alertas.reconocer(session, actor(claims), alerta_id))
    return _alerta(await alertas.fila(session, alerta_id))


@router.post("/alertas-sistema/{alerta_id}/descartar", response_model=AlertaSistemaOut)
async def descartar(
    alerta_id: UUID, datos: Descartar, claims: GestionaAlerta, session: SesionDB
) -> AlertaSistemaOut:
    await _o_http(alertas.descartar(session, actor(claims), alerta_id, datos.nota))
    return _alerta(await alertas.fila(session, alerta_id))


@router.post(
    "/alertas-sistema/{alerta_id}/orden",
    response_model=OrdenDetalle,
    status_code=status.HTTP_201_CREATED,
)
async def crear_orden(
    alerta_id: UUID,
    claims: GestionaAlerta,
    session: SesionDB,
    datos: CrearOrdenPredictiva | None = None,
) -> OrdenDetalle:
    """Orden predictiva: equipo y componente salen de la alerta, nunca del cuerpo (6.4)."""
    orden = await _o_http(
        alertas.crear_orden_predictiva(
            session, actor(claims), alerta_id, datos.descripcion if datos else None
        )
    )
    return salida_detalle(await ordenes.detalle(session, orden.id))


__all__ = ["router"]
