"""Consultas de los paneles (08-fase5, sección 7) con el ORM.

Ninguna filtra por empresa: la impone RLS con el tenant que fijó la transacción del widget, y una
consulta a la que le faltara un filtro seguiría sin poder ver otra empresa. Todas las listas tienen
límite y orden, para que un panel nunca crezca sin tope. El usuario del operario y del técnico sale
de la sesión, nunca de la petición; ese filtro es de presentación (RLS aísla empresas, no
personas de una misma empresa: 15.4).

Los indicadores traen filas crudas acotadas al periodo y `indicadores` hace el cálculo: así no hay
`generate_series`, `LATERAL` ni funciones propias del motor (decisión de portabilidad del proyecto).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activo import Activo
from app.models.alerta import Alerta
from app.models.componente import Componente
from app.models.lectura_horometro import LecturaHorometro
from app.models.orden_trabajo import ABIERTOS, OrdenTrabajo
from app.models.prediccion import (
    AlertaSistema,
    ConfiguracionEmpresa,
    ModeloComponente,
    Riesgo,
    v_paradas,
    v_riesgo_activo,
)
from app.models.repuesto import Repuesto, StockMovimiento
from app.models.usuario import Usuario
from app.services.paneles.indicadores import (
    Consumo,
    Equipo,
    Lectura,
    Orden,
    Parada,
)

#: Estados de una alerta del sistema que todavía piden atención (los del contador del supervisor).
SISTEMA_POR_ATENDER = ("activa", "reconocida")


def _en_planta(ubicacion: str | None) -> ColumnElement[bool]:
    """El filtro de planta (decisión 1): ordena la vista, no limita lo que el usuario puede ver."""
    return true() if ubicacion is None else Activo.ubicacion == ubicacion


def _iso(valor: datetime | None) -> str | None:
    return None if valor is None else valor.isoformat()


def _dinero(valor: Decimal | None) -> str:
    return f"{(valor or Decimal(0)):.2f}"


# --- Datos crudos para los indicadores ------------------------------------------------------------


async def equipos(session: AsyncSession, ubicacion: str | None) -> list[Equipo]:
    filas = await session.execute(
        select(Activo.id, Activo.creado_en, Activo.estado, Activo.dado_de_baja_en).where(
            _en_planta(ubicacion)
        )
    )
    return [
        Equipo(
            id=f.id,
            desde=f.creado_en,
            # Un equipo de baja deja de observarse en su baja (o, sin fecha, nunca se observó).
            hasta=(f.dado_de_baja_en or f.creado_en) if f.estado == "baja" else None,
        )
        for f in filas
    ]


async def paradas(
    session: AsyncSession, ubicacion: str | None, desde: datetime, hasta: datetime
) -> list[Parada]:
    p = v_paradas.c
    filas = await session.execute(
        select(p.activo_id, p.inicio, p.fin, p.planificada)
        .join(Activo, and_(Activo.empresa_id == p.empresa_id, Activo.id == p.activo_id))
        .where(
            _en_planta(ubicacion),
            p.inicio < hasta,
            or_(p.fin.is_(None), p.fin > desde),
        )
    )
    return [Parada(f.activo_id, f.inicio, f.fin, bool(f.planificada)) for f in filas]


async def ordenes(
    session: AsyncSession, ubicacion: str | None, desde: datetime, hasta: datetime
) -> list[Orden]:
    o = OrdenTrabajo
    filas = await session.execute(
        select(o.es_predictiva, o.requiere_revision, o.estado, o.fecha_falla, o.fecha_salida_taller)
        .join(Activo, and_(Activo.empresa_id == o.empresa_id, Activo.id == o.activo_id))
        .where(
            _en_planta(ubicacion),
            o.estado != "cancelada",
            or_(
                and_(o.fecha_falla >= desde, o.fecha_falla < hasta),
                and_(
                    o.estado == "cerrada",
                    o.fecha_salida_taller >= desde,
                    o.fecha_salida_taller < hasta,
                ),
            ),
        )
    )
    return [
        Orden(
            es_predictiva=f.es_predictiva,
            requiere_revision=f.requiere_revision,
            cerrada=f.estado == "cerrada",
            fecha_falla=f.fecha_falla,
            salida=f.fecha_salida_taller,
        )
        for f in filas
    ]


async def lecturas(
    session: AsyncSession, ubicacion: str | None, desde: datetime, hasta: datetime
) -> list[Lectura]:
    """Las lecturas válidas del periodo, más la última anterior a `desde` de cada equipo: con eso
    se conocen las horas acumuladas en cualquier límite de mes del periodo (5.3)."""
    lec = LecturaHorometro
    base = (
        select(lec.activo_id, lec.capturado_en, lec.horas_acumuladas)
        .join(Activo, and_(Activo.empresa_id == lec.empresa_id, Activo.id == lec.activo_id))
        .where(_en_planta(ubicacion), lec.horas_acumuladas.is_not(None))
    )
    del_periodo = base.where(lec.capturado_en >= desde, lec.capturado_en < hasta)
    numeradas = (
        base.add_columns(
            func.row_number()
            .over(
                partition_by=lec.activo_id,
                order_by=(lec.capturado_en.desc(), lec.id.desc()),
            )
            .label("n")
        )
        .where(lec.capturado_en < desde)
        .subquery()
    )
    anteriores: Select[Any] = select(
        numeradas.c.activo_id, numeradas.c.capturado_en, numeradas.c.horas_acumuladas
    ).where(numeradas.c.n == 1)
    resultado = []
    for consulta in (del_periodo, anteriores):
        for f in await session.execute(consulta):
            resultado.append(Lectura(f.activo_id, f.capturado_en, int(f.horas_acumuladas)))
    return resultado


async def consumos(
    session: AsyncSession, ubicacion: str | None, desde: datetime, hasta: datetime
) -> list[Consumo]:
    m, o = StockMovimiento, OrdenTrabajo
    filas = await session.execute(
        select(m.creado_en, m.delta, m.costo_unitario, o.es_predictiva)
        .join(o, and_(o.empresa_id == m.empresa_id, o.id == m.orden_id))
        .join(Activo, and_(Activo.empresa_id == o.empresa_id, Activo.id == o.activo_id))
        .where(
            _en_planta(ubicacion),
            m.tipo == "consumo",
            m.creado_en >= desde,
            m.creado_en < hasta,
        )
    )
    return [
        Consumo(f.creado_en, -f.delta, Decimal(f.costo_unitario), f.es_predictiva) for f in filas
    ]


# --- Gerente: repuestos y riesgo ------------------------------------------------------------------


async def repuestos_costo(
    session: AsyncSession, ubicacion: str | None, desde: datetime, hasta: datetime, n: int = 5
) -> list[dict[str, Any]]:
    """Los repuestos que más costaron en el periodo, a precio del momento del consumo."""
    m, o, r = StockMovimiento, OrdenTrabajo, Repuesto
    unidades = func.sum(-m.delta)
    costo = func.sum(-m.delta * m.costo_unitario)
    filas = await session.execute(
        select(r.codigo, r.nombre, unidades.label("unidades"), costo.label("costo"))
        .join(r, and_(r.empresa_id == m.empresa_id, r.id == m.repuesto_id))
        .join(o, and_(o.empresa_id == m.empresa_id, o.id == m.orden_id))
        .join(Activo, and_(Activo.empresa_id == o.empresa_id, Activo.id == o.activo_id))
        .where(
            _en_planta(ubicacion),
            m.tipo == "consumo",
            m.creado_en >= desde,
            m.creado_en < hasta,
        )
        .group_by(r.id, r.codigo, r.nombre)
        .order_by(costo.desc(), r.codigo)
        .limit(n)
    )
    return [
        {
            "codigo": f.codigo,
            "nombre": f.nombre,
            "unidades": int(f.unidades),
            "costo": _dinero(f.costo),
        }
        for f in filas
    ]


async def riesgo_top(
    session: AsyncSession, ubicacion: str | None, n: int = 5
) -> list[dict[str, Any]]:
    """Los equipos activos de mayor riesgo, con su componente crítico, la base del número y el
    umbral de la empresa (el nivel bajo/vigilar/alto se lee contra él, no contra números fijos)."""
    umbral = await session.scalar(select(ConfiguracionEmpresa.umbral_riesgo))
    v = v_riesgo_activo.c
    filas = await session.execute(
        select(
            Activo.id,
            Activo.nombre,
            Activo.qr_code,
            Activo.ubicacion,
            Activo.criticidad,
            Componente.nombre.label("componente"),
            v.riesgo,
            v.confianza,
            v.fuente,
            v.calculado_en,
            Riesgo.n_eventos,
            Riesgo.horizonte_horas,
        )
        .join(Activo, and_(Activo.empresa_id == v.empresa_id, Activo.id == v.activo_id))
        .join(
            Componente,
            and_(Componente.empresa_id == v.empresa_id, Componente.id == v.componente_critico),
        )
        .join(
            Riesgo,
            and_(
                Riesgo.empresa_id == v.empresa_id,
                Riesgo.activo_id == v.activo_id,
                Riesgo.componente_id == v.componente_critico,
            ),
        )
        .where(Activo.estado == "activo", _en_planta(ubicacion))
        .order_by(v.riesgo.desc(), Activo.nombre)
        .limit(n)
    )
    return [
        {
            "activo_id": str(f.id),
            "equipo": f.nombre,
            "codigo": f.qr_code,
            "planta": f.ubicacion,
            "criticidad": f.criticidad,
            "componente": f.componente,
            "riesgo": float(f.riesgo),
            "confianza": f.confianza,
            "fuente": f.fuente,
            "n_eventos": f.n_eventos,
            "horizonte_horas": f.horizonte_horas,
            "umbral": None if umbral is None else float(umbral),
            "calculado_en": _iso(f.calculado_en),
        }
        for f in filas
    ]


async def riesgo_cobertura(session: AsyncSession, ubicacion: str | None) -> dict[str, int]:
    """Cuántos equipos activos tienen riesgo y cuántos no, y por qué (7.6): un panel con pocos
    equipos calculados no debe parecer que dice «todo está bien»."""
    con_riesgo = select(v_riesgo_activo.c.activo_id)
    sin_edad = select(Riesgo.activo_id).where(Riesgo.estado_calculo == "sin_edad")
    filas = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(Activo.id.in_(con_riesgo)),
                func.count().filter(Activo.id.not_in(con_riesgo), Activo.id.in_(sin_edad)),
            ).where(Activo.estado == "activo", _en_planta(ubicacion))
        )
    ).one()
    activos, calculados, sin_edad_n = (int(x) for x in filas)
    return {
        "equipos_activos": activos,
        "con_riesgo": calculados,
        "sin_edad": sin_edad_n,
        "sin_modelo_o_sin_componentes": activos - calculados - sin_edad_n,
    }


# --- Operario y técnico ---------------------------------------------------------------------------


async def mis_lecturas(
    session: AsyncSession, usuario_id: UUID, n: int = 20
) -> list[dict[str, Any]]:
    lec = LecturaHorometro
    filas = await session.execute(
        select(
            lec.id,
            Activo.nombre,
            Activo.qr_code,
            lec.valor_horometro,
            lec.capturado_en,
            lec.requiere_revision,
            lec.resolucion,
            lec.es_reinicio,
        )
        .join(Activo, and_(Activo.empresa_id == lec.empresa_id, Activo.id == lec.activo_id))
        .where(lec.registrado_por == usuario_id)
        .order_by(lec.capturado_en.desc(), lec.id.desc())
        .limit(n)
    )

    def estado(f: Any) -> str:
        if f.es_reinicio or f.resolucion == "reinicio":
            return "reinicio"
        if f.requiere_revision and f.resolucion is None:
            return "en_revision"
        if f.resolucion == "descartada":
            return "descartada"
        return "registrada"

    return [
        {
            "id": str(f.id),
            "equipo": f.nombre,
            "codigo": f.qr_code,
            "valor": f.valor_horometro,
            "capturado_en": _iso(f.capturado_en),
            "estado": estado(f),
        }
        for f in filas
    ]


async def mis_alertas(session: AsyncSession, usuario_id: UUID, n: int = 20) -> list[dict[str, Any]]:
    filas = await session.execute(
        select(
            Alerta.id,
            Activo.nombre,
            Activo.qr_code,
            Alerta.sintoma,
            Alerta.capturado_en,
            Alerta.estado,
        )
        .join(Activo, and_(Activo.empresa_id == Alerta.empresa_id, Activo.id == Alerta.activo_id))
        .where(Alerta.reportado_por == usuario_id)
        .order_by(Alerta.capturado_en.desc(), Alerta.id.desc())
        .limit(n)
    )
    return [
        {
            "id": str(f.id),
            "equipo": f.nombre,
            "codigo": f.qr_code,
            "sintoma": f.sintoma,
            "capturado_en": _iso(f.capturado_en),
            "estado": f.estado,
        }
        for f in filas
    ]


def _orden_fila(f: Any, ahora: datetime | None = None) -> dict[str, Any]:
    fila = {
        "id": str(f.id),
        "numero": f.numero,
        "estado": f.estado,
        "es_predictiva": f.es_predictiva,
        "equipo": f.equipo,
        "codigo": f.qr_code,
        "planta": f.ubicacion,
        "componente": f.componente,
        "fecha_falla": _iso(f.fecha_falla),
    }
    if ahora is not None:
        fila["horas_abierta"] = round((ahora - f.fecha_falla).total_seconds() / 3600, 1)
    return fila


def _select_ordenes() -> Select[Any]:
    o = OrdenTrabajo
    return (
        select(
            o.id,
            o.numero,
            o.estado,
            o.es_predictiva,
            o.fecha_falla,
            o.reparada_en,
            o.tipo_intervencion,
            Activo.nombre.label("equipo"),
            Activo.qr_code,
            Activo.ubicacion,
            Componente.nombre.label("componente"),
        )
        .join(Activo, and_(Activo.empresa_id == o.empresa_id, Activo.id == o.activo_id))
        .join(
            Componente,
            and_(Componente.empresa_id == o.empresa_id, Componente.id == o.componente_id),
        )
    )


async def cola_taller(session: AsyncSession, n: int = 50) -> list[dict[str, Any]]:
    """Órdenes reportadas o en taller: primero las fallas, la más antigua arriba; luego lo
    planificado."""
    o = OrdenTrabajo
    filas = await session.execute(
        _select_ordenes()
        .where(o.estado.in_(("reportada", "en_taller")))
        .order_by(o.es_predictiva, o.fecha_falla, o.numero)
        .limit(n)
    )
    return [_orden_fila(f) for f in filas]


async def mis_trabajos(
    session: AsyncSession, usuario_id: UUID, n: int = 10
) -> list[dict[str, Any]]:
    o = OrdenTrabajo
    filas = await session.execute(
        _select_ordenes()
        .where(o.reparado_por == usuario_id, o.reparada_en.is_not(None))
        .order_by(o.reparada_en.desc(), o.numero.desc())
        .limit(n)
    )
    return [
        {
            **_orden_fila(f),
            "reparada_en": _iso(f.reparada_en),
            "tipo_intervencion": f.tipo_intervencion,
        }
        for f in filas
    ]


# --- Supervisor -----------------------------------------------------------------------------------


async def alertas_campo(
    session: AsyncSession, ubicacion: str | None, n: int = 50
) -> list[dict[str, Any]]:
    """Alertas de campo pendientes de revisión (RF-27), la más reciente arriba."""
    filas = await session.execute(
        select(
            Alerta.id,
            Activo.nombre,
            Activo.qr_code,
            Activo.ubicacion,
            Alerta.sintoma,
            Alerta.capturado_en,
            Usuario.nombre.label("reporto"),
        )
        .join(Activo, and_(Activo.empresa_id == Alerta.empresa_id, Activo.id == Alerta.activo_id))
        .join(
            Usuario,
            and_(Usuario.empresa_id == Alerta.empresa_id, Usuario.id == Alerta.reportado_por),
        )
        .where(Alerta.estado == "pendiente", _en_planta(ubicacion))
        .order_by(Alerta.capturado_en.desc(), Alerta.id.desc())
        .limit(n)
    )
    return [
        {
            "id": str(f.id),
            "equipo": f.nombre,
            "codigo": f.qr_code,
            "planta": f.ubicacion,
            "sintoma": f.sintoma,
            "capturado_en": _iso(f.capturado_en),
            "reporto": f.reporto,
        }
        for f in filas
    ]


async def alertas_sistema(
    session: AsyncSession, ubicacion: str | None, n: int = 50
) -> list[dict[str, Any]]:
    """Alertas del sistema por atender: las de riesgo, de mayor a menor; después las de reorden.

    Las de reorden no tienen equipo, así que el filtro de planta solo se aplica a las de riesgo."""
    a = AlertaSistema
    filas = await session.execute(
        select(
            a.id,
            a.tipo,
            a.estado,
            a.riesgo,
            a.creada_en,
            a.stock_al_alertar,
            a.stock_minimo_al_alertar,
            Activo.nombre.label("equipo"),
            Componente.nombre.label("componente"),
            Repuesto.nombre.label("repuesto"),
            Repuesto.codigo.label("repuesto_codigo"),
        )
        .outerjoin(Activo, and_(Activo.empresa_id == a.empresa_id, Activo.id == a.activo_id))
        .outerjoin(
            Componente,
            and_(Componente.empresa_id == a.empresa_id, Componente.id == a.componente_id),
        )
        .outerjoin(
            Repuesto, and_(Repuesto.empresa_id == a.empresa_id, Repuesto.id == a.repuesto_id)
        )
        .where(
            a.estado.in_(SISTEMA_POR_ATENDER),
            or_(a.tipo == "reorden", _en_planta(ubicacion)),
        )
        .order_by((a.tipo == "reorden"), a.riesgo.desc().nulls_last(), a.creada_en.desc())
        .limit(n)
    )
    return [
        {
            "id": str(f.id),
            "tipo": f.tipo,
            "estado": f.estado,
            "riesgo": None if f.riesgo is None else float(f.riesgo),
            "creada_en": _iso(f.creada_en),
            "equipo": f.equipo,
            "componente": f.componente,
            "repuesto": f.repuesto,
            "repuesto_codigo": f.repuesto_codigo,
            "stock": f.stock_al_alertar,
            "stock_minimo": f.stock_minimo_al_alertar,
        }
        for f in filas
    ]


async def ordenes_abiertas(
    session: AsyncSession, ubicacion: str | None, ahora: datetime, n: int = 100
) -> list[dict[str, Any]]:
    """Órdenes abiertas (reportada, en taller, reparada) y cuánto llevan abiertas; la más antigua
    arriba."""
    o = OrdenTrabajo
    filas = await session.execute(
        _select_ordenes()
        .where(o.estado.in_(ABIERTOS), _en_planta(ubicacion))
        .order_by(o.fecha_falla, o.numero)
        .limit(n)
    )
    return [_orden_fila(f, ahora) for f in filas]


async def contadores(session: AsyncSession, ubicacion: str | None) -> dict[str, int]:
    """Los cuatro contadores del supervisor: alertas de campo por revisar, alertas del sistema por
    atender, órdenes abiertas y lecturas por confirmar."""
    en_planta = select(Activo.id).where(_en_planta(ubicacion))
    campo = await session.scalar(
        select(func.count())
        .select_from(Alerta)
        .where(Alerta.estado == "pendiente", Alerta.activo_id.in_(en_planta))
    )
    sistema = await session.scalar(
        select(func.count())
        .select_from(AlertaSistema)
        .where(
            AlertaSistema.estado.in_(SISTEMA_POR_ATENDER),
            or_(AlertaSistema.tipo == "reorden", AlertaSistema.activo_id.in_(en_planta)),
        )
    )
    abiertas = await session.scalar(
        select(func.count())
        .select_from(OrdenTrabajo)
        .where(OrdenTrabajo.estado.in_(ABIERTOS), OrdenTrabajo.activo_id.in_(en_planta))
    )
    por_confirmar = await session.scalar(
        select(func.count())
        .select_from(LecturaHorometro)
        .where(
            LecturaHorometro.requiere_revision.is_(True),
            LecturaHorometro.resolucion.is_(None),
            LecturaHorometro.activo_id.in_(en_planta),
        )
    )
    return {
        "alertas_campo": int(campo or 0),
        "alertas_sistema": int(sistema or 0),
        "ordenes_abiertas": int(abiertas or 0),
        "lecturas_por_confirmar": int(por_confirmar or 0),
    }


# --- Administrador y filtro de planta -------------------------------------------------------------


async def salud(session: AsyncSession) -> dict[str, Any]:
    """Estado de la plataforma: si el cálculo está al día y qué datos faltan (decisión 12)."""
    ultimo = await session.scalar(select(func.max(Riesgo.calculado_en)))
    filas = await session.execute(
        select(Riesgo.estado_calculo, func.count()).group_by(Riesgo.estado_calculo)
    )
    estados = {estado: int(n) for estado, n in filas}
    confianza_baja = await session.scalar(
        select(func.count())
        .select_from(ModeloComponente)
        .where(ModeloComponente.confianza == "baja")
    )
    bajo_minimo = await session.scalar(
        select(func.count())
        .select_from(Repuesto)
        .where(Repuesto.activo.is_(True), Repuesto.stock_actual < Repuesto.stock_minimo)
    )
    por_confirmar = await session.scalar(
        select(func.count())
        .select_from(LecturaHorometro)
        .where(LecturaHorometro.requiere_revision.is_(True), LecturaHorometro.resolucion.is_(None))
    )
    usuarios = await session.scalar(
        select(func.count()).select_from(Usuario).where(Usuario.activo.is_(True))
    )
    configurada = await session.scalar(select(func.count()).select_from(ConfiguracionEmpresa))
    return {
        "ultimo_calculo": _iso(ultimo),
        "pares_sin_edad": int(estados.get("sin_edad", 0)),
        "pares_sin_modelo": int(estados.get("sin_modelo", 0)),
        "modelos_confianza_baja": int(confianza_baja or 0),
        "repuestos_bajo_minimo": int(bajo_minimo or 0),
        "lecturas_por_confirmar": int(por_confirmar or 0),
        "usuarios_activos": int(usuarios or 0),
        "prediccion_configurada": bool(configurada),
    }


async def plantas(session: AsyncSession, n: int = 100) -> list[str]:
    """Ubicaciones con equipos activos, para el filtro. No es una frontera de seguridad."""
    filas = await session.scalars(
        select(Activo.ubicacion)
        .where(Activo.estado == "activo", Activo.ubicacion.is_not(None), Activo.ubicacion != "")
        .distinct()
        .order_by(Activo.ubicacion)
        .limit(n)
    )
    return [p for p in filas if p]
