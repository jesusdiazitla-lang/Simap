"""Indicadores del gerente (08-fase5, secciones 5 y 8.2; RF-28): cálculo puro, sin base ni HTTP.

Recibe datos crudos ya filtrados por empresa (RLS) y por planta (`consultas`), y devuelve cantidades
por mes que se pueden sumar —horas, conteos, dinero— y un resumen del periodo cuyas razones se arman
**sobre los totales** (5.5): promediar las disponibilidades mensuales pondría igual un mes con un
equipo que uno con cien.

DÓNDE SE CORTAN LOS MESES
-------------------------
Siempre en America/Santo_Domingo (decisión 11), aquí y no en la base: los cubos se calculan en
Python con `zoneinfo`, así que no dependen de la zona horaria de la sesión ni del servidor. El mes
en curso solo cuenta hasta ahora: nunca se cuentan horas de calendario futuras (5.2).

POR QUÉ EN PYTHON Y NO EN SQL
-----------------------------
El PDF escribe la unión de intervalos y las horas operadas en SQL de PostgreSQL (`generate_series`,
funciones de ventana, `LATERAL`). Con la decisión de portabilidad del proyecto, las consultas traen
filas acotadas al periodo con el ORM y el cálculo se hace aquí, igual que el riesgo de la fase 4.
Las pruebas lo contrastan con casos a mano y con una implementación de referencia independiente.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from scipy.stats import chi2

TZ_PLATAFORMA = ZoneInfo("America/Santo_Domingo")
#: Periodo máximo de una consulta (8.4): por encima, 422 con un mensaje claro.
MESES_MAXIMOS = 24
#: Nivel del intervalo de confianza del MTBF (decisión 5).
NIVEL_IC = 0.90
CERO = Decimal("0")


class PeriodoInvalido(ValueError):
    """`desde`/`hasta` incoherentes o un periodo de más de `MESES_MAXIMOS` meses."""


# --- Periodo y cubos ------------------------------------------------------------------------------


def resolver_periodo(
    desde: date | None, hasta: date | None, ahora: datetime
) -> tuple[datetime, datetime, datetime]:
    """`(desde, hasta, ahora)` como instantes con zona; `hasta` es exclusivo y nunca pasa de ahora.

    Por defecto, los últimos 12 meses calendario, incluido el mes en curso hasta ahora. `hasta` es
    inclusivo para quien lo escribe (el día completo) y exclusivo aquí.
    """
    ahora = ahora.astimezone(TZ_PLATAFORMA)
    if desde is None:
        anio, mes = ahora.year, ahora.month - 11
        while mes < 1:
            anio, mes = anio - 1, mes + 12
        desde = date(anio, mes, 1)
    d = datetime.combine(desde, time(0), TZ_PLATAFORMA)
    h = ahora
    if hasta is not None:
        h = min(datetime.combine(hasta + timedelta(days=1), time(0), TZ_PLATAFORMA), ahora)
    if d >= h:
        raise PeriodoInvalido(
            "La fecha de inicio debe ser anterior a la de fin, y no estar en el futuro."
        )
    if (h.year - d.year) * 12 + h.month - d.month > MESES_MAXIMOS:
        raise PeriodoInvalido(f"El periodo no puede superar {MESES_MAXIMOS} meses.")
    return d, h, ahora


@dataclass(frozen=True)
class Cubo:
    """Un mes del periodo con su inicio y fin efectivos (recortados al periodo y a ahora)."""

    mes: date
    ini: datetime
    fin: datetime


def _siguiente_mes(inicio: datetime) -> datetime:
    anio, mes = (inicio.year + 1, 1) if inicio.month == 12 else (inicio.year, inicio.month + 1)
    return datetime(anio, mes, 1, tzinfo=TZ_PLATAFORMA)


def cubos(desde: datetime, hasta: datetime, ahora: datetime) -> list[Cubo]:
    """Una entrada por mes del periodo, aunque no haya datos: las series siempre tienen los mismos
    meses. Los meses se cortan en la zona de la plataforma (decisión 11)."""
    desde = desde.astimezone(TZ_PLATAFORMA)
    tope = min(hasta, ahora)
    inicio = datetime(desde.year, desde.month, 1, tzinfo=TZ_PLATAFORMA)
    resultado = []
    while inicio < tope:
        siguiente = _siguiente_mes(inicio)
        ini, fin = max(inicio, desde), min(siguiente, tope)
        if fin > ini:
            resultado.append(Cubo(inicio.date(), ini, fin))
        inicio = siguiente
    return resultado


# --- Datos de entrada (los entrega `consultas`) ---------------------------------------------------


@dataclass(frozen=True)
class Equipo:
    """Un equipo observado: desde `creado_en` (decisión 8) hasta su baja, o sin fin."""

    id: UUID
    desde: datetime
    hasta: datetime | None = None


@dataclass(frozen=True)
class Parada:
    """Fila de `v_paradas`: una falla desde la falla; una predictiva desde la entrada al taller."""

    activo_id: UUID
    inicio: datetime
    fin: datetime | None
    planificada: bool


@dataclass(frozen=True)
class Orden:
    """Una orden no cancelada, para contar fallas y su duración (decisión 6)."""

    es_predictiva: bool
    requiere_revision: bool
    cerrada: bool
    fecha_falla: datetime
    salida: datetime | None


@dataclass(frozen=True)
class Lectura:
    """Una lectura válida con sus horas acumuladas (columna de la revisión 0011)."""

    activo_id: UUID
    capturado_en: datetime
    horas: int


@dataclass(frozen=True)
class Consumo:
    """Un consumo del libro de movimientos, a precio del momento (decisión 7)."""

    creado_en: datetime
    unidades: int
    costo_unitario: Decimal
    es_predictiva: bool


# --- Por mes --------------------------------------------------------------------------------------


@dataclass
class Mes:
    """Lo que se puede sumar de un mes. Las razones se arman después, sobre los totales."""

    mes: date
    equipos: int = 0
    horas_calendario: float = 0.0
    paradas_total_h: float = 0.0
    paradas_falla_h: float = 0.0
    fallas: int = 0
    fallas_en_revision: int = 0
    fallas_cerradas: int = 0
    suma_duracion_fallas_h: float = 0.0
    planificadas_cerradas: int = 0
    horas_operadas: int = 0
    equipos_con_horas: int = 0
    costo_fallas: Decimal = field(default_factory=lambda: CERO)
    costo_planificadas: Decimal = field(default_factory=lambda: CERO)
    unidades: int = 0


def _horas(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


def segundos_de_union(intervalos: Iterable[tuple[datetime, datetime]]) -> float:
    """Segundos cubiertos por la unión de los intervalos: dos paradas que se solapan cuentan una vez
    (decisión 4). Un intervalo contenido en otro suma cero."""
    total = 0.0
    alcance: datetime | None = None
    for ini, fin in sorted(intervalos):
        if alcance is None or ini >= alcance:
            total += (fin - ini).total_seconds()
            alcance = fin
        elif fin > alcance:
            total += (fin - alcance).total_seconds()
            alcance = fin
    return total


def _recortar(
    ini: datetime, fin: datetime | None, *limites: tuple[datetime, datetime | None]
) -> tuple[datetime, datetime] | None:
    a = ini
    b = fin if fin is not None else datetime.max.replace(tzinfo=UTC)
    for li, lf in limites:
        a = max(a, li)
        if lf is not None:
            b = min(b, lf)
    return (a, b) if b > a else None


class _Horometros:
    """Horas acumuladas de cada equipo en un instante: las de su última lectura válida **antes**
    del instante (comparación estricta: una lectura justo en el límite es del mes siguiente) o, si
    aún no tenía, las de la primera que tenga: lo anterior no se observó (5.3)."""

    def __init__(self, lecturas: Iterable[Lectura]) -> None:
        por_equipo: dict[UUID, list[tuple[datetime, int]]] = defaultdict(list)
        for lectura in lecturas:
            por_equipo[lectura.activo_id].append((lectura.capturado_en, lectura.horas))
        self._series = {k: sorted(v) for k, v in por_equipo.items()}
        self._instantes = {k: [t for t, _ in v] for k, v in self._series.items()}

    def en(self, activo_id: UUID, instante: datetime) -> int | None:
        serie = self._series.get(activo_id)
        if not serie:
            return None
        i = bisect.bisect_left(self._instantes[activo_id], instante)
        return serie[i - 1][1] if i > 0 else serie[0][1]


def calcular_meses(
    periodo: Sequence[Cubo],
    equipos: Iterable[Equipo],
    paradas: Iterable[Parada],
    ordenes: Iterable[Orden],
    lecturas: Iterable[Lectura],
    consumos: Iterable[Consumo],
) -> list[Mes]:
    """Las cantidades de cada mes del periodo. Los datos ya vienen filtrados por planta."""
    observados = {e.id: e for e in equipos}
    paradas_por_equipo: dict[UUID, list[Parada]] = defaultdict(list)
    for p in paradas:
        if p.activo_id in observados:
            paradas_por_equipo[p.activo_id].append(p)
    ordenes = list(ordenes)
    consumos = list(consumos)
    horometros = _Horometros(lecturas)
    meses = []
    for c in periodo:
        m = Mes(c.mes)
        for equipo in observados.values():
            vida = _recortar(c.ini, c.fin, (equipo.desde, equipo.hasta))
            if vida is None:
                continue
            m.equipos += 1
            m.horas_calendario += _horas(vida[1] - vida[0])
            todas, fallas = [], []
            for p in paradas_por_equipo.get(equipo.id, ()):
                tramo = _recortar(p.inicio, p.fin, vida)
                if tramo is not None:
                    todas.append(tramo)
                    if not p.planificada:
                        fallas.append(tramo)
            # El solape entre una planificada y una falla queda atribuido a la falla (decisión 4):
            # la unión de todas menos la de las fallas es lo que solo pararon las planificadas.
            m.paradas_total_h += segundos_de_union(todas) / 3600.0
            m.paradas_falla_h += segundos_de_union(fallas) / 3600.0
        for o in ordenes:
            if not o.es_predictiva and c.ini <= o.fecha_falla < c.fin:
                m.fallas += 1
                m.fallas_en_revision += int(o.requiere_revision)
            if o.cerrada and o.salida is not None and c.ini <= o.salida < c.fin:
                if o.es_predictiva:
                    m.planificadas_cerradas += 1
                else:
                    m.fallas_cerradas += 1
                    m.suma_duracion_fallas_h += _horas(o.salida - o.fecha_falla)
        for activo_id in observados:
            inicio, fin = horometros.en(activo_id, c.ini), horometros.en(activo_id, c.fin)
            if inicio is None or fin is None:
                continue
            if fin > inicio:
                m.horas_operadas += fin - inicio
                m.equipos_con_horas += 1
        for k in consumos:
            if c.ini <= k.creado_en < c.fin:
                costo = k.costo_unitario * k.unidades
                if k.es_predictiva:
                    m.costo_planificadas += costo
                else:
                    m.costo_fallas += costo
                m.unidades += k.unidades
        meses.append(m)
    return meses


# --- Resumen del periodo --------------------------------------------------------------------------


def mtbf_intervalo(
    horas: float, fallas: int, nivel: float = NIVEL_IC
) -> tuple[float, float | None]:
    """Intervalo de confianza bilateral del MTBF con fallas a tasa constante y observación truncada
    por tiempo (5.3): `[2T/χ²(1−α/2; 2n+2), 2T/χ²(α/2; 2n)]`. Sin fallas no hay cota superior
    (`None`) y la inferior es la unilateral con 2 grados de libertad."""
    if not 0 < nivel < 1:
        raise ValueError("nivel debe estar entre 0 y 1")
    if horas < 0 or fallas < 0:
        raise ValueError("horas y fallas no pueden ser negativas")
    if horas == 0:
        return (0.0, None)
    a = 1 - nivel
    inferior = 2 * horas / float(chi2.ppf(1 - a / 2, 2 * fallas + 2))
    superior = None if fallas == 0 else 2 * horas / float(chi2.ppf(a / 2, 2 * fallas))
    return (inferior, superior)


@dataclass(frozen=True)
class Resumen:
    horas_calendario: float
    paradas_total_h: float
    paradas_falla_h: float
    paradas_planificadas_h: float
    #: `None` = sin datos (sin horas de calendario): la pantalla escribe «sin datos», nunca 100 %.
    disponibilidad: float | None
    disponibilidad_sin_planificadas: float | None
    utilizacion: float | None
    horas_operadas: int
    fallas: int
    fallas_en_revision: int
    #: Sin fallas no hay MTBF: `None` y `mtbf_es_cota_inferior` (se muestra «al menos»).
    mtbf_h: float | None
    mtbf_es_cota_inferior: bool
    mtbf_ic: tuple[float, float | None] | None
    fallas_cerradas: int
    mttr_h: float | None
    planificadas_cerradas: int
    costo_fallas: Decimal
    costo_planificadas: Decimal
    costo_total: Decimal
    porcentaje_planificado: float | None


def _razon(numerador: float, denominador: float) -> float | None:
    return None if denominador <= 0 else numerador / denominador


def resumir(meses: Iterable[Mes], nivel: float = NIVEL_IC) -> Resumen:
    """El resumen que ve el gerente. Toda razón sale de las sumas del periodo (5.5) y toda razón sin
    denominador es `None`: ni cero ni infinito."""
    meses = list(meses)
    cal = sum(m.horas_calendario for m in meses)
    tot = sum(m.paradas_total_h for m in meses)
    fal = sum(m.paradas_falla_h for m in meses)
    ops = sum(m.horas_operadas for m in meses)
    n = sum(m.fallas for m in meses)
    cerradas = sum(m.fallas_cerradas for m in meses)
    duracion = sum(m.suma_duracion_fallas_h for m in meses)
    cf = sum((m.costo_fallas for m in meses), CERO)
    cp = sum((m.costo_planificadas for m in meses), CERO)
    return Resumen(
        horas_calendario=cal,
        paradas_total_h=tot,
        paradas_falla_h=fal,
        paradas_planificadas_h=tot - fal,
        disponibilidad=None if cal <= 0 else 1 - tot / cal,
        disponibilidad_sin_planificadas=None if cal <= 0 else 1 - fal / cal,
        utilizacion=_razon(ops, cal),
        horas_operadas=ops,
        fallas=n,
        fallas_en_revision=sum(m.fallas_en_revision for m in meses),
        mtbf_h=None if n == 0 or ops <= 0 else ops / n,
        mtbf_es_cota_inferior=(n == 0 and ops > 0),
        mtbf_ic=None if ops <= 0 else mtbf_intervalo(ops, n, nivel),
        fallas_cerradas=cerradas,
        mttr_h=_razon(duracion, cerradas),
        planificadas_cerradas=sum(m.planificadas_cerradas for m in meses),
        costo_fallas=cf,
        costo_planificadas=cp,
        costo_total=cf + cp,
        porcentaje_planificado=None if cf + cp == 0 else float(cp / (cf + cp)),
    )
