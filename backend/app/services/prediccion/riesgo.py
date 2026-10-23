"""Riesgo de cada componente de cada equipo y alertas de riesgo (RF-18 a RF-21; 07-fase4, 6.3).

EL CÁLCULO
----------
Para cada vida abierta (la pieza instalada hoy) de la empresa, o de un solo equipo:

    riesgo = 1 − exp(−m · [((a + h)/η)^β − (a/η)^β])

con `a` la edad de la pieza, `h` el horizonte de la empresa y `m` el multiplicador de las alertas
de campo (1,30 con dos o más pendientes o revisadas en la ventana; RF-20). El resultado se clasifica
en `ok`, `sin_edad` o `sin_modelo`: los dos últimos **nunca** son un 0 % (10.2).

La guía lo escribe como una sola sentencia SQL con `INSERT … ON CONFLICT`. Aquí se lee lo mismo con
el ORM (las filas abiertas de `v_vidas`, los modelos y la configuración) y la fórmula se aplica en
Python con `weibull.riesgo`, la función que prueba el ejemplo de la Especificación (25,2 % y
31,4 %).
El cálculo de un equipo sigue costando milisegundos (RNF-04).

LAS ALERTAS
-----------
- Se crea una cuando el riesgo alcanza el umbral. Si ya hay una vigente para ese componente de ese
  equipo, el índice único parcial lo impide: dos cálculos a la vez nunca crean dos (savepoint).
- **Histéresis**: una alerta sin atender se resuelve sola cuando el riesgo baja del 80 % del umbral,
  no del umbral. Sin esa banda, un riesgo que oscila alrededor del 25 % abriría y cerraría alertas
  cada noche.
- **Silencio**: un descarte silencia ese componente de ese equipo los días configurados.

Las alertas del sistema viven en su propia tabla: nunca cuentan como alertas de campo ni elevan el
multiplicador que las originó.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activo import Activo
from app.models.alerta import Alerta
from app.models.componente import Componente
from app.models.lectura_horometro import LecturaHorometro
from app.models.prediccion import (
    VIGENTES_RIESGO,
    ActivoComponente,
    AlertaSistema,
    ConfiguracionEmpresa,
    ModeloComponente,
    Riesgo,
    v_riesgo_activo,
    v_vidas,
)
from app.services.prediccion import configuracion, weibull

#: Estados de una alerta de campo que cuentan para el multiplicador (RF-20). Las descartadas y las
#: convertidas en orden no: la primera era un error y la segunda ya se está atendiendo.
ESTADOS_CAMPO = ("pendiente", "revisada")
#: Banda de histéresis: una alerta se resuelve sola por debajo de esta fracción del umbral.
HISTERESIS = Decimal("0.8")
CINCO_DECIMALES = Decimal("0.00001")


@dataclass(frozen=True)
class Calculo:
    activo_id: UUID
    componente_id: UUID
    estado_calculo: str
    edad_horas: float | None
    horizonte_horas: int
    beta: float | None
    eta: float | None
    riesgo_base: Decimal | None
    multiplicador: Decimal
    riesgo: Decimal | None
    n_eventos: int | None
    fuente: str | None
    confianza: str | None


def _redondear(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(CINCO_DECIMALES, rounding=ROUND_HALF_UP)


async def alertas_de_campo(
    session: AsyncSession, config: ConfiguracionEmpresa, activo_id: UUID | None
) -> dict[UUID, int]:
    """Alertas de campo pendientes o revisadas de la ventana, por equipo (RF-20)."""
    desde = datetime.now(UTC) - timedelta(days=config.ventana_alertas_dias)
    consulta = (
        select(Alerta.activo_id, func.count())
        .where(Alerta.estado.in_(ESTADOS_CAMPO), Alerta.fecha >= desde)
        .group_by(Alerta.activo_id)
    )
    if activo_id is not None:
        consulta = consulta.where(Alerta.activo_id == activo_id)
    return {fila[0]: int(fila[1]) for fila in await session.execute(consulta)}


async def calcular(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID | None = None
) -> list[Calculo]:
    """El riesgo de cada vida abierta, sin escribir nada."""
    config = await configuracion.asegurar(session, empresa_id)
    campo = await alertas_de_campo(session, config, activo_id)
    consulta = (
        select(
            v_vidas.c.activo_id,
            v_vidas.c.componente_id,
            v_vidas.c.exposicion,
            ModeloComponente.beta,
            ModeloComponente.eta,
            ModeloComponente.n_eventos,
            ModeloComponente.fuente,
            ModeloComponente.confianza,
        )
        .outerjoin(
            ModeloComponente,
            and_(
                ModeloComponente.empresa_id == v_vidas.c.empresa_id,
                ModeloComponente.componente_id == v_vidas.c.componente_id,
            ),
        )
        .where(v_vidas.c.abierta.is_(True))
    )
    if activo_id is not None:
        consulta = consulta.where(v_vidas.c.activo_id == activo_id)
    h = config.horizonte_horas
    calculos: list[Calculo] = []
    for fila in await session.execute(consulta):
        n_campo = campo.get(fila.activo_id, 0)
        m = config.multiplicador_alertas if n_campo >= config.alertas_minimas else Decimal("1.00")
        edad = fila.exposicion
        if edad is None:
            estado = "sin_edad"
        elif fila.beta is None:
            estado = "sin_modelo"
        else:
            estado = "ok"
        base = riesgo = None
        if estado == "ok":
            base = _redondear(weibull.riesgo(edad, h, fila.beta, fila.eta))
            riesgo = _redondear(weibull.riesgo(edad, h, fila.beta, fila.eta, float(m)))
        calculos.append(
            Calculo(
                activo_id=fila.activo_id,
                componente_id=fila.componente_id,
                estado_calculo=estado,
                edad_horas=edad,
                horizonte_horas=h,
                beta=fila.beta,
                eta=fila.eta,
                riesgo_base=base,
                multiplicador=m,
                riesgo=riesgo,
                n_eventos=fila.n_eventos,
                fuente=fila.fuente,
                confianza=fila.confianza,
            )
        )
    return calculos


async def _escribir(session: AsyncSession, empresa_id: UUID, c: Calculo, ahora: datetime) -> None:
    """Reemplaza el riesgo del par. Repetirlo no duplica filas (UPDATE y, si no existía, INSERT)."""
    valores = {
        "estado_calculo": c.estado_calculo,
        "edad_horas": c.edad_horas,
        "horizonte_horas": c.horizonte_horas,
        "beta": c.beta,
        "eta": c.eta,
        "riesgo_base": c.riesgo_base,
        "multiplicador": c.multiplicador,
        "riesgo": c.riesgo,
        "n_eventos": c.n_eventos,
        "fuente": c.fuente,
        "confianza": c.confianza,
        "calculado_en": ahora,
    }
    actualizar = (
        update(Riesgo)
        .where(Riesgo.activo_id == c.activo_id, Riesgo.componente_id == c.componente_id)
        .values(**valores)
        .execution_options(synchronize_session=False)
    )
    if (await session.execute(actualizar)).rowcount:
        return
    try:
        async with session.begin_nested():
            session.add(
                Riesgo(
                    empresa_id=empresa_id,
                    activo_id=c.activo_id,
                    componente_id=c.componente_id,
                    **valores,
                )
            )
            await session.flush()
    except IntegrityError:
        await session.execute(actualizar)


async def recalcular(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID | None = None
) -> list[Calculo]:
    """Calcula y guarda el riesgo de la empresa, o de un equipo (tras cada lectura, RF-19)."""
    calculos = await calcular(session, empresa_id, activo_id)
    ahora = datetime.now(UTC)
    for c in calculos:
        await _escribir(session, empresa_id, c, ahora)
    return calculos


async def crear_alertas(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID | None = None
) -> int:
    """Una alerta por cada componente sobre el umbral sin otra vigente ni silencio (RF-21)."""
    config = await configuracion.asegurar(session, empresa_id)
    silencio = datetime.now(UTC) - timedelta(days=config.descarte_silencio_dias)
    descartada = exists().where(
        AlertaSistema.tipo == "riesgo",
        AlertaSistema.estado == "descartada",
        AlertaSistema.activo_id == Riesgo.activo_id,
        AlertaSistema.componente_id == Riesgo.componente_id,
        AlertaSistema.gestionada_en > silencio,
    )
    vigente = exists().where(
        AlertaSistema.tipo == "riesgo",
        AlertaSistema.estado.in_(VIGENTES_RIESGO),
        AlertaSistema.activo_id == Riesgo.activo_id,
        AlertaSistema.componente_id == Riesgo.componente_id,
    )
    consulta = select(Riesgo).where(
        Riesgo.estado_calculo == "ok",
        Riesgo.riesgo >= config.umbral_riesgo,
        ~descartada,
        ~vigente,
    )
    if activo_id is not None:
        consulta = consulta.where(Riesgo.activo_id == activo_id)
    creadas = 0
    for r in (await session.scalars(consulta)).all():
        try:
            async with session.begin_nested():
                session.add(
                    AlertaSistema(
                        empresa_id=empresa_id,
                        tipo="riesgo",
                        activo_id=r.activo_id,
                        componente_id=r.componente_id,
                        riesgo=r.riesgo,
                        umbral=config.umbral_riesgo,
                        confianza=r.confianza,
                        fuente=r.fuente,
                    )
                )
                await session.flush()
            creadas += 1
        except IntegrityError:
            # Otro cálculo la creó en este instante: el índice decidió, y hay una sola.
            continue
    return creadas


async def resolver_alertas(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID | None = None
) -> int:
    """Histéresis: resuelve las alertas sin atender cuyo riesgo bajó del 80 % del umbral."""
    config = await configuracion.asegurar(session, empresa_id)
    bajo = exists().where(
        Riesgo.activo_id == AlertaSistema.activo_id,
        Riesgo.componente_id == AlertaSistema.componente_id,
        or_(
            Riesgo.estado_calculo != "ok",
            Riesgo.riesgo < config.umbral_riesgo * HISTERESIS,
        ),
    )
    sentencia = (
        update(AlertaSistema)
        .where(
            AlertaSistema.tipo == "riesgo",
            AlertaSistema.estado.in_(("activa", "reconocida")),
            bajo,
        )
        .values(estado="resuelta", gestionada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if activo_id is not None:
        sentencia = sentencia.where(AlertaSistema.activo_id == activo_id)
    return int((await session.execute(sentencia)).rowcount)


async def recalcular_y_alertar(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID | None = None
) -> dict[str, int]:
    """Recálculo, alertas nuevas e histéresis, en ese orden (9.2)."""
    calculos = await recalcular(session, empresa_id, activo_id)
    creadas = await crear_alertas(session, empresa_id, activo_id)
    resueltas = await resolver_alertas(session, empresa_id, activo_id)
    return {"calculados": len(calculos), "alertas_creadas": creadas, "alertas_resueltas": resueltas}


# --- Consultas para la interfaz (07-fase4, secciones 8 y 10) ---------------------------------


@dataclass(frozen=True)
class ComponenteConRiesgo:
    componente_id: UUID
    componente: str
    riesgo: Riesgo | None


@dataclass(frozen=True)
class RiesgoDelEquipo:
    activo_id: UUID
    config: ConfiguracionEmpresa
    horas_por_dia: float | None
    alertas_de_campo: int
    componentes: list[ComponenteConRiesgo]


async def horas_por_dia(session: AsyncSession, activo_id: UUID) -> float | None:
    """Horas diarias recientes del equipo, para el equivalente informativo en días (decisión 4).

    Primera y última lectura válida de los últimos 60 días, sin reinicios entre medias. `None` si no
    hay base para estimarlo: la pantalla muestra entonces solo las horas.
    """
    desde = datetime.now(UTC) - timedelta(days=60)
    filas = (
        await session.execute(
            select(
                LecturaHorometro.valor_horometro,
                LecturaHorometro.capturado_en,
                LecturaHorometro.es_reinicio,
                LecturaHorometro.resolucion,
            )
            .where(
                LecturaHorometro.activo_id == activo_id,
                LecturaHorometro.capturado_en >= desde,
                or_(
                    LecturaHorometro.requiere_revision.is_(False),
                    LecturaHorometro.resolucion.in_(("confirmada", "reinicio")),
                ),
            )
            .order_by(LecturaHorometro.capturado_en)
        )
    ).all()
    # Solo la serie posterior al último reinicio: antes de él el dial no es comparable.
    serie: list[tuple[int, datetime]] = []
    for valor, cuando, reinicio, resolucion in filas:
        if reinicio or resolucion == "reinicio":
            serie = []
        serie.append((valor, cuando))
    if len(serie) < 2:
        return None
    (v0, t0), (v1, t1) = serie[0], serie[-1]
    dias = (t1 - t0).total_seconds() / 86400
    if dias < 2 or v1 <= v0:
        return None
    return round((v1 - v0) / dias, 1)


async def riesgo_del_equipo(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID
) -> RiesgoDelEquipo:
    """El riesgo de cada componente del equipo. Si algún par aún no tiene cálculo, se calcula ya:
    cuesta milisegundos y evita mostrar un hueco como si fuera un dato."""
    config = await configuracion.asegurar(session, empresa_id)

    async def leer() -> list[ComponenteConRiesgo]:
        filas = await session.execute(
            select(ActivoComponente.componente_id, Componente.nombre, Riesgo)
            .join(
                Componente,
                and_(
                    Componente.empresa_id == ActivoComponente.empresa_id,
                    Componente.id == ActivoComponente.componente_id,
                ),
            )
            .outerjoin(
                Riesgo,
                and_(
                    Riesgo.empresa_id == ActivoComponente.empresa_id,
                    Riesgo.activo_id == ActivoComponente.activo_id,
                    Riesgo.componente_id == ActivoComponente.componente_id,
                ),
            )
            .where(ActivoComponente.activo_id == activo_id)
            .order_by(Componente.nombre)
            .execution_options(populate_existing=True)
        )
        return [ComponenteConRiesgo(f[0], f[1], f[2]) for f in filas]

    componentes = await leer()
    if any(c.riesgo is None for c in componentes):
        await recalcular_y_alertar(session, empresa_id, activo_id)
        componentes = await leer()
    campo = await alertas_de_campo(session, config, activo_id)
    return RiesgoDelEquipo(
        activo_id=activo_id,
        config=config,
        horas_por_dia=await horas_por_dia(session, activo_id),
        alertas_de_campo=campo.get(activo_id, 0),
        componentes=componentes,
    )


@dataclass(frozen=True)
class FilaRanking:
    activo_id: UUID
    activo: str
    codigo: str
    componente_id: UUID
    componente: str
    riesgo: Decimal
    confianza: str | None
    fuente: str | None
    n_eventos: int | None
    edad_horas: float | None
    calculado_en: datetime


async def ranking(
    session: AsyncSession, *, cursor_riesgo: Decimal | None, cursor_id: UUID | None, limite: int
) -> tuple[list[FilaRanking], tuple[Decimal, UUID] | None]:
    """Equipos por riesgo descendente: cada uno por su componente más riesgoso (v_riesgo_activo)."""
    vista = v_riesgo_activo.c
    consulta = (
        select(
            vista.activo_id,
            Activo.nombre,
            Activo.qr_code,
            vista.componente_critico,
            Componente.nombre,
            vista.riesgo,
            vista.confianza,
            vista.fuente,
            Riesgo.n_eventos,
            Riesgo.edad_horas,
            vista.calculado_en,
        )
        .join(Activo, and_(Activo.empresa_id == vista.empresa_id, Activo.id == vista.activo_id))
        .join(
            Componente,
            and_(
                Componente.empresa_id == vista.empresa_id,
                Componente.id == vista.componente_critico,
            ),
        )
        .join(
            Riesgo,
            and_(
                Riesgo.empresa_id == vista.empresa_id,
                Riesgo.activo_id == vista.activo_id,
                Riesgo.componente_id == vista.componente_critico,
            ),
        )
        .where(Activo.estado == "activo")
    )
    if cursor_riesgo is not None and cursor_id is not None:
        consulta = consulta.where(
            or_(
                vista.riesgo < cursor_riesgo,
                and_(vista.riesgo == cursor_riesgo, vista.activo_id > cursor_id),
            )
        )
    consulta = consulta.order_by(vista.riesgo.desc(), vista.activo_id).limit(limite + 1)
    filas = [FilaRanking(*f) for f in await session.execute(consulta)]
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], (ultima.riesgo, ultima.activo_id)
