"""Cálculo de los indicadores del gerente (08-fase5, secciones 5 y 12; RF-28), sin base de datos.

Tres tipos de prueba:
- **Casos calculados a mano**: la Figura 1 de la guía, el corte de meses en Santo Domingo, la
  lectura justo en el límite de un mes, el intervalo del MTBF contra los números de la guía.
- **La decisión de 5.5**: la razón se arma sobre los totales, no como promedio de razones mensuales.
- **Validación cruzada** (12.1): `calcular_meses` contra una implementación de referencia escrita
  aparte con otro algoritmo (barrido de eventos en lugar de fusión de intervalos ordenados, y
  recorrido lineal en lugar de búsqueda binaria), sobre flotas generadas al azar con semilla fija.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.paneles.indicadores import (
    TZ_PLATAFORMA,
    Consumo,
    Cubo,
    Equipo,
    Lectura,
    Mes,
    Orden,
    Parada,
    PeriodoInvalido,
    calcular_meses,
    cubos,
    mtbf_intervalo,
    resolver_periodo,
    resumir,
    segundos_de_union,
)

DIA = timedelta(days=1)


def sd(*args: int) -> datetime:
    """Un instante en la zona de la plataforma."""
    return datetime(*args, tzinfo=TZ_PLATAFORMA)


# --- Casos a mano ---------------------------------------------------------------------------------


def test_rf28_figura_1_solape_cuenta_una_vez_y_se_atribuye_a_la_falla() -> None:
    """La Figura 1 de la guía: un mes de 30 días, dos fallas y dos intervenciones planificadas.
    Parada total de 10 días: 6 por falla y 4 planificados; la espera de la predictiva no cuenta
    (la vista ya la da desde la entrada al taller)."""
    inicio = sd(2026, 6, 1)
    equipo = Equipo(uuid4(), sd(2026, 1, 1))
    d = lambda x: inicio + timedelta(days=x)  # noqa: E731
    paradas = [
        Parada(equipo.id, d(4), d(6.5), planificada=False),
        Parada(equipo.id, d(12), d(14), planificada=True),
        Parada(equipo.id, d(20), d(23.5), planificada=False),
        Parada(equipo.id, d(22), d(25.5), planificada=True),
    ]
    [mes] = calcular_meses(
        [Cubo(date(2026, 6, 1), inicio, sd(2026, 7, 1))], [equipo], paradas, [], [], []
    )
    assert mes.horas_calendario == pytest.approx(30 * 24)
    assert mes.paradas_total_h == pytest.approx(10 * 24)
    assert mes.paradas_falla_h == pytest.approx(6 * 24)
    r = resumir([mes])
    assert r.paradas_planificadas_h == pytest.approx(4 * 24)
    assert r.disponibilidad == pytest.approx(1 - 10 / 30)
    assert r.disponibilidad_sin_planificadas == pytest.approx(1 - 6 / 30)


def test_union_de_intervalos_contenido_suma_cero() -> None:
    a = sd(2026, 1, 1)
    assert (
        segundos_de_union([(a, a + DIA), (a + timedelta(hours=2), a + timedelta(hours=3))]) == 86400
    )


def test_rf28_meses_se_cortan_en_santo_domingo() -> None:
    """Decisión 11: la medianoche del 1 de febrero en Santo Domingo son las 04:00 UTC. Una falla a
    las 02:00 UTC del 1 de febrero ocurrió el 31 de enero en la planta y es de enero."""
    periodo = cubos(sd(2026, 1, 1), sd(2026, 3, 1), sd(2026, 6, 1))
    assert [c.mes for c in periodo] == [date(2026, 1, 1), date(2026, 2, 1)]
    falla = Orden(False, False, False, datetime(2026, 2, 1, 2, tzinfo=UTC), None)
    enero, febrero = calcular_meses(periodo, [], [], [falla], [], [])
    assert (enero.fallas, febrero.fallas) == (1, 0)


def test_rf28_el_mes_en_curso_se_corta_en_ahora() -> None:
    """Nunca se cuentan horas de calendario futuras (5.2)."""
    ahora = sd(2026, 3, 10, 12)
    periodo = cubos(sd(2026, 3, 1), sd(2026, 4, 1), ahora)
    [mes] = calcular_meses(periodo, [Equipo(uuid4(), sd(2025, 1, 1))], [], [], [], [])
    assert mes.horas_calendario == pytest.approx(9 * 24 + 12)


def test_rf28_equipo_cuenta_desde_que_se_observa_y_hasta_su_baja() -> None:
    """Decisión 8: un equipo dado de alta a mitad de mes no cuenta las horas anteriores."""
    periodo = cubos(sd(2026, 4, 1), sd(2026, 5, 1), sd(2026, 6, 1))
    nuevo = Equipo(uuid4(), sd(2026, 4, 21))
    de_baja = Equipo(uuid4(), sd(2025, 1, 1), sd(2026, 4, 11))
    [mes] = calcular_meses(periodo, [nuevo, de_baja], [], [], [], [])
    assert mes.horas_calendario == pytest.approx(10 * 24 + 10 * 24)
    assert mes.equipos == 2


def test_rf28_lectura_justo_en_el_limite_es_del_mes_siguiente() -> None:
    """Comparación estricta (mutación M11): las horas de un mes usan la última lectura **antes** del
    límite; una tomada justo en el límite pertenece al mes siguiente."""
    eq = uuid4()
    periodo = cubos(sd(2026, 1, 1), sd(2026, 3, 1), sd(2026, 6, 1))
    lecturas = [
        Lectura(eq, sd(2025, 12, 31), 1000),
        Lectura(eq, sd(2026, 1, 15), 1100),
        Lectura(eq, sd(2026, 2, 1), 1300),
        Lectura(eq, sd(2026, 2, 20), 1400),
    ]
    enero, febrero = calcular_meses(periodo, [Equipo(eq, sd(2025, 1, 1))], [], [], lecturas, [])
    assert (enero.horas_operadas, febrero.horas_operadas) == (100, 300)


def test_rf28_horas_sin_lectura_previa_usan_la_primera_y_los_meses_suman_el_total() -> None:
    eq = uuid4()
    lecturas = [Lectura(eq, sd(2026, 1, 20), 500), Lectura(eq, sd(2026, 3, 5), 800)]
    equipos = [Equipo(eq, sd(2026, 1, 20))]
    meses = calcular_meses(
        cubos(sd(2026, 1, 1), sd(2026, 4, 1), sd(2026, 6, 1)), equipos, [], [], lecturas, []
    )
    [total] = calcular_meses(
        [Cubo(date(2026, 1, 1), sd(2026, 1, 1), sd(2026, 4, 1))], equipos, [], [], lecturas, []
    )
    assert [m.horas_operadas for m in meses] == [0, 0, 300]
    assert sum(m.horas_operadas for m in meses) == total.horas_operadas


def test_rf28_mttr_cuenta_fallas_cerradas_y_canceladas_no_llegan() -> None:
    """Decisión 6: duración de la falla a la salida, en el mes de la salida; las predictivas
    cerradas se cuentan aparte."""
    periodo = cubos(sd(2026, 5, 1), sd(2026, 6, 1), sd(2026, 7, 1))
    ordenes = [
        Orden(False, False, True, sd(2026, 5, 2), sd(2026, 5, 3)),
        Orden(False, True, True, sd(2026, 4, 30), sd(2026, 5, 2)),
        Orden(True, False, True, sd(2026, 5, 10), sd(2026, 5, 11)),
        Orden(False, False, False, sd(2026, 5, 20), None),
    ]
    [mes] = calcular_meses(periodo, [], [], ordenes, [], [])
    assert (mes.fallas, mes.fallas_cerradas, mes.planificadas_cerradas) == (2, 2, 1)
    assert mes.suma_duracion_fallas_h == pytest.approx(24 + 48)
    assert resumir([mes]).mttr_h == pytest.approx(36)


def test_rf28_costos_separados_y_al_precio_del_momento() -> None:
    periodo = cubos(sd(2026, 5, 1), sd(2026, 6, 1), sd(2026, 7, 1))
    consumos = [
        Consumo(sd(2026, 5, 3), 2, Decimal("100.00"), False),
        Consumo(sd(2026, 5, 4), 1, Decimal("50.50"), True),
        Consumo(sd(2026, 6, 1), 9, Decimal("999.00"), False),
    ]
    [mes] = calcular_meses(periodo, [], [], [], [], consumos)
    r = resumir([mes])
    assert (r.costo_fallas, r.costo_planificadas, r.costo_total) == (
        Decimal("200.00"),
        Decimal("50.50"),
        Decimal("250.50"),
    )
    assert r.porcentaje_planificado == pytest.approx(50.5 / 250.5)


def test_la_razon_se_arma_sobre_totales_no_como_promedio_de_razones_mensuales() -> None:
    """Decisión de 5.5: un mes con un equipo no pesa lo mismo que uno con cien."""
    chico = Mes(date(2026, 1, 1), equipos=1, horas_calendario=100, paradas_total_h=50)
    grande = Mes(date(2026, 2, 1), equipos=100, horas_calendario=10_000, paradas_total_h=0)
    promedio = ((1 - 50 / 100) + 1) / 2
    r = resumir([chico, grande])
    assert r.disponibilidad == pytest.approx(1 - 50 / 10_100)
    assert r.disponibilidad != pytest.approx(promedio)


def test_razon_sin_denominador_es_none_no_cero_ni_infinito() -> None:
    r = resumir([Mes(date(2026, 1, 1))])
    assert r.disponibilidad is None and r.utilizacion is None and r.mttr_h is None
    assert r.mtbf_h is None and r.mtbf_ic is None and r.porcentaje_planificado is None


# --- MTBF y su intervalo --------------------------------------------------------------------------


def test_rf28_mtbf_intervalo_con_los_numeros_de_la_guia() -> None:
    """19 fallas en 72 960 h: MTBF 3 840 h, IC 90 % de 2 617 h a 5 864 h (5.3)."""
    inferior, superior = mtbf_intervalo(72_960, 19)
    assert inferior == pytest.approx(2617, abs=1)
    assert superior == pytest.approx(5864, abs=1)


def test_rf28_sin_fallas_el_mtbf_es_una_cota_inferior() -> None:
    """1 000 h sin fallas: «al menos 334 h» con 95 % (unilateral); sin valor puntual."""
    inferior, superior = mtbf_intervalo(1000, 0)
    assert inferior == pytest.approx(334, abs=1)
    assert superior is None
    r = resumir([Mes(date(2026, 1, 1), horas_calendario=1, horas_operadas=1000)])
    assert r.mtbf_h is None and r.mtbf_es_cota_inferior


def test_mtbf_entradas_invalidas() -> None:
    for args in ((100, -1), (-1, 1)):
        with pytest.raises(ValueError):
            mtbf_intervalo(*args)
    with pytest.raises(ValueError):
        mtbf_intervalo(100, 1, nivel=1.0)
    assert mtbf_intervalo(0, 3) == (0.0, None)


def test_mtbf_intervalo_se_estrecha_con_mas_datos() -> None:
    a = mtbf_intervalo(10_000, 5)
    b = mtbf_intervalo(100_000, 50)
    assert a[1] is not None and b[1] is not None
    assert (b[1] - b[0]) / (b[0] + b[1]) < (a[1] - a[0]) / (a[0] + a[1])


# --- Periodo --------------------------------------------------------------------------------------


def test_periodo_por_defecto_son_12_meses_hasta_ahora() -> None:
    ahora = sd(2026, 10, 28, 15)
    d, h, _ = resolver_periodo(None, None, ahora)
    assert d == sd(2025, 11, 1) and h == ahora
    assert len(cubos(d, h, ahora)) == 12


def test_periodo_hasta_es_inclusivo_y_no_pasa_de_ahora() -> None:
    ahora = sd(2026, 10, 28, 15)
    _, h, _ = resolver_periodo(date(2026, 9, 1), date(2026, 9, 30), ahora)
    assert h == sd(2026, 10, 1)
    _, h, _ = resolver_periodo(date(2026, 9, 1), date(2027, 1, 1), ahora)
    assert h == ahora


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (date(2026, 10, 1), date(2026, 9, 1)),
        (date(2024, 1, 1), date(2026, 9, 30)),
        (date(2027, 1, 1), None),
    ],
)
def test_periodo_invalido(desde: date, hasta: date | None) -> None:
    with pytest.raises(PeriodoInvalido):
        resolver_periodo(desde, hasta, sd(2026, 10, 28))


# --- Validación cruzada contra una referencia independiente ---------------------------------------


def _referencia(
    periodo: list[Cubo],
    equipos: list[Equipo],
    paradas: list[Parada],
    ordenes: list[Orden],
    lecturas: list[Lectura],
    consumos: list[Consumo],
) -> list[dict[str, float]]:
    """Otro algoritmo para lo mismo: barrido de eventos con contadores de cobertura (paradas) y
    recorrido lineal de las lecturas (horas). Comparte con el código solo las definiciones."""
    salida = []
    for c in periodo:
        cal = tot = fal = 0.0
        for e in equipos:
            ini = max(c.ini, e.desde)
            fin = c.fin if e.hasta is None else min(c.fin, e.hasta)
            if fin <= ini:
                continue
            cal += (fin - ini).total_seconds()
            eventos: list[tuple[datetime, int, int]] = []
            for p in paradas:
                if p.activo_id != e.id:
                    continue
                a = max(p.inicio, ini)
                b = fin if p.fin is None else min(p.fin, fin)
                if b > a:
                    eventos += [
                        (a, 1, 0 if p.planificada else 1),
                        (b, -1, 0 if p.planificada else -1),
                    ]
            eventos.sort(key=lambda x: (x[0], -x[1]))
            cuenta = cuenta_falla = 0
            previo: datetime | None = None
            for t, d_tot, d_fal in eventos:
                if previo is not None and t > previo:
                    tot += (t - previo).total_seconds() if cuenta > 0 else 0
                    fal += (t - previo).total_seconds() if cuenta_falla > 0 else 0
                cuenta += d_tot
                cuenta_falla += d_fal
                previo = t
        horas = 0
        for e in equipos:
            propias = sorted(
                (x for x in lecturas if x.activo_id == e.id), key=lambda x: x.capturado_en
            )

            def valor(t: datetime, propias: list[Lectura] = propias) -> int | None:
                ultimo = None
                for x in propias:
                    if x.capturado_en < t:
                        ultimo = x.horas
                return ultimo if ultimo is not None else (propias[0].horas if propias else None)

            i, f = valor(c.ini), valor(c.fin)
            if i is not None and f is not None and f > i:
                horas += f - i
        fallas = sum(1 for o in ordenes if not o.es_predictiva and c.ini <= o.fecha_falla < c.fin)
        dur = sum(
            (o.salida - o.fecha_falla).total_seconds()
            for o in ordenes
            if o.cerrada and not o.es_predictiva and o.salida and c.ini <= o.salida < c.fin
        )
        costo = sum(
            (
                float(k.costo_unitario) * k.unidades
                for k in consumos
                if c.ini <= k.creado_en < c.fin
            ),
            0.0,
        )
        salida.append(
            {
                "cal": cal / 3600,
                "tot": tot / 3600,
                "fal": fal / 3600,
                "horas": horas,
                "fallas": fallas,
                "dur": dur / 3600,
                "costo": costo,
            }
        )
    return salida


def _flota(
    azar: random.Random, ahora: datetime
) -> tuple[list[Equipo], list[Parada], list[Orden], list[Lectura], list[Consumo]]:
    base = ahora - timedelta(days=420)
    minuto = lambda: base + timedelta(minutes=azar.randint(0, 420 * 24 * 60))  # noqa: E731
    equipos, paradas, ordenes, lecturas, consumos = [], [], [], [], []
    for _ in range(azar.randint(1, 8)):
        desde = minuto()
        hasta = desde + timedelta(days=azar.uniform(5, 300)) if azar.random() < 0.2 else None
        e = Equipo(uuid4(), desde, hasta)
        equipos.append(e)
        for _ in range(azar.randint(0, 6)):
            ini = minuto()
            fin = None if azar.random() < 0.15 else ini + timedelta(hours=azar.uniform(1, 200))
            planificada = azar.random() < 0.4
            paradas.append(Parada(e.id, ini, fin, planificada))
            ordenes.append(Orden(planificada, azar.random() < 0.1, fin is not None, ini, fin))
        acumulado = azar.randint(0, 5000)
        t = desde
        while t < ahora:
            lecturas.append(Lectura(e.id, t, acumulado))
            t += timedelta(days=azar.uniform(1, 40))
            acumulado += azar.randint(0, 600)
        for _ in range(azar.randint(0, 4)):
            consumos.append(
                Consumo(
                    minuto(),
                    azar.randint(1, 5),
                    Decimal(azar.randint(100, 99999)) / 100,
                    azar.random() < 0.3,
                )
            )
    return equipos, paradas, ordenes, lecturas, consumos


@pytest.mark.parametrize("semilla", range(80))
def test_rf28_validacion_cruzada_contra_implementacion_de_referencia(semilla: int) -> None:
    """80 flotas al azar (12.1): los totales mensuales coinciden con la referencia independiente."""
    azar = random.Random(semilla)
    ahora = sd(2026, 10, 28, 15) - timedelta(minutes=azar.randint(0, 60 * 24 * 30))
    datos = _flota(azar, ahora)
    d, h, ahora = resolver_periodo(None, None, ahora)
    periodo = cubos(d, h, ahora)
    meses = calcular_meses(periodo, *datos)
    esperado = _referencia(periodo, *datos)
    for m, r in zip(meses, esperado, strict=True):
        assert m.horas_calendario == pytest.approx(r["cal"], abs=1e-6)
        assert m.paradas_total_h == pytest.approx(r["tot"], abs=1e-6)
        assert m.paradas_falla_h == pytest.approx(r["fal"], abs=1e-6)
        assert m.horas_operadas == r["horas"]
        assert m.fallas == r["fallas"]
        assert m.suma_duracion_fallas_h == pytest.approx(r["dur"], abs=1e-6)
        assert float(m.costo_fallas + m.costo_planificadas) == pytest.approx(r["costo"], abs=1e-6)
