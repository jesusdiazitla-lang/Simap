"""Módulo del modelo (07-fase4, sección 5.5): matemática pura, sin base de datos (RF-17, RF-18)."""

import math

import numpy as np
import pytest
from scipy.stats import weibull_min

from app.services.prediccion import weibull as w


def test_rf18_ejemplo_especificacion_5_3_da_25_por_ciento() -> None:
    """350 h de edad, horizonte 50 h, β = 3,5, η = 430: 25,2 %, y 31,4 % con el multiplicador."""
    d = w.hazard_acum(400, 3.5, 430) - w.hazard_acum(350, 3.5, 430)
    assert d == pytest.approx(0.290, abs=5e-4)
    assert w.riesgo(350, 50, 3.5, 430) == pytest.approx(0.252, abs=5e-4)
    assert w.riesgo(350, 50, 3.5, 430, m=1.30) == pytest.approx(0.314, abs=5e-4)


def test_rf20_el_multiplicador_actua_sobre_la_intensidad_y_nunca_pasa_de_uno() -> None:
    base = w.riesgo(450, 100, 3.5, 430)
    con_alertas = w.riesgo(450, 100, 3.5, 430, m=2.0)
    assert base < con_alertas < 1.0
    assert w.riesgo(5000, 500, 3.5, 430, m=2.0) <= 1.0
    assert w.riesgo(350, 50, 3.5, 430, m=1.0) == pytest.approx(w.riesgo(350, 50, 3.5, 430))


def test_el_riesgo_crece_con_la_edad_si_hay_desgaste() -> None:
    edades = [0, 100, 200, 300, 400]
    riesgos = [w.riesgo(a, 50, 2.5, 1000) for a in edades]
    assert riesgos == sorted(riesgos)
    assert w.riesgo(0, 50, 2.5, 1000) > 0


def test_sin_censura_ni_prior_coincide_con_scipy() -> None:
    """Contraste de la implementación (15.1): con vidas completas, el mismo resultado que scipy."""
    vidas = weibull_min.rvs(2.5, scale=1000, size=60, random_state=np.random.default_rng(7))
    datos = w.Datos(n=len(vidas), s1=float(np.log(vidas).sum()), t=np.asarray(vidas))
    a = w.ajustar(datos, None)
    beta, _, eta = weibull_min.fit(vidas, floc=0)
    assert a.beta == pytest.approx(beta, rel=1e-3)
    assert a.eta == pytest.approx(eta, rel=1e-3)
    assert a.convergio


def test_el_gradiente_analitico_coincide_con_diferencias_finitas() -> None:
    datos = w.Datos(n=5, s1=30.0, t=np.array([700.0, 600.0, 200.0]))
    prior = w.Prior.desde(900, datos)
    x = np.array([math.log(2.2), math.log(800.0)])
    _, g = w._neg_logpost(x, datos, prior)
    h = 1e-6
    for i in range(2):
        mas, menos = x.copy(), x.copy()
        mas[i] += h
        menos[i] -= h
        numerico = (
            w._neg_logpost(mas, datos, prior)[0] - w._neg_logpost(menos, datos, prior)[0]
        ) / (2 * h)
        assert g[i] == pytest.approx(numerico, rel=1e-5, abs=1e-6)


def test_la_censura_alarga_la_vida_estimada() -> None:
    """Las piezas que siguen funcionando dicen que η no puede ser corta (5.1)."""
    fallas = w.Datos(n=3, s1=3 * math.log(400.0), t=np.array([400.0, 400.0, 400.0]))
    con_abiertas = w.Datos(n=3, s1=fallas.s1, t=np.array([400.0, 400.0, 400.0, 900.0, 900.0]))
    prior = w.Prior.desde(500, fallas)
    assert w.ajustar(con_abiertas, prior).eta > w.ajustar(fallas, prior).eta


def test_sin_fallas_el_modelo_es_el_previo() -> None:
    """Cero fallas y vida nominal: el «estimado» de CU-04, centrado cerca de la vida nominal."""
    modelo = w.ajustar_componente([(0, 0.0, 100.0)], 1000)
    assert modelo is not None
    assert modelo["fuente"] == "previo"
    assert modelo["confianza"] == "baja"
    assert 700 < modelo["eta"] < 1600


def test_rf17_sin_vida_nominal_ni_dos_fallas_no_hay_modelo() -> None:
    assert w.ajustar_componente([(1, math.log(500), 500.0)], None) is None
    assert w.ajustar_componente([], None) is None
    con_dos = w.ajustar_componente([(2, 2 * math.log(500), 800.0)], None)
    assert con_dos is not None


def test_las_vidas_sin_edad_no_entran_al_ajuste() -> None:
    d = w.Datos.de_vidas([(2, 12.0, None), (1, 6.0, 500.0), (0, 0.0, 0.0)])
    assert d.n == 1
    assert d.s1 == pytest.approx(6.0)
    assert list(d.t) == [500.0]


def test_maxima_verosimilitud_sin_datos_es_un_error() -> None:
    with pytest.raises(ValueError, match="no hay modelo"):
        w.ajustar(w.Datos(n=0, s1=0.0), None)


def test_beta_queda_dentro_de_sus_limites() -> None:
    """Fallas casi idénticas empujan β al infinito; el límite lo contiene (7: β ≈ 30 sin él)."""
    edades = np.array([380.0, 400.0, 420.0])
    datos = w.Datos(n=3, s1=float(np.log(edades).sum()), t=edades)
    a = w.ajustar(datos, None)
    assert w.BETA_MIN <= a.beta <= w.BETA_MAX + 1e-9


@pytest.mark.parametrize(
    ("eventos", "esperado"),
    [
        (0, ("previo", "baja")),
        (1, ("mixto", "baja")),
        (7, ("mixto", "baja")),
        (8, ("empresa", "media")),
        (19, ("empresa", "media")),
        (20, ("empresa", "alta")),
    ],
)
def test_nivel_de_confianza_por_numero_de_fallas(eventos: int, esperado: tuple[str, str]) -> None:
    assert w.nivel(eventos) == esperado


def test_rf17_ajuste_recupera_parametros_con_muchas_vidas() -> None:
    """Con 400 vidas completas de una Weibull conocida, el MAP cae cerca de la verdad."""
    vidas = weibull_min.rvs(2.5, scale=1000, size=400, random_state=np.random.default_rng(3))
    filas = [(1, math.log(v), v) for v in vidas]
    modelo = w.ajustar_componente(filas, 1000)
    assert modelo is not None
    assert modelo["beta"] == pytest.approx(2.5, rel=0.12)
    assert modelo["eta"] == pytest.approx(1000, rel=0.08)
    assert modelo["confianza"] == "alta"


def test_el_prior_cede_ante_los_datos() -> None:
    """Con la vida nominal equivocada por un factor 2, muchos datos la corrigen (14.2)."""
    vidas = weibull_min.rvs(2.5, scale=1000, size=300, random_state=np.random.default_rng(11))
    filas = [(1, math.log(v), v) for v in vidas]
    modelo = w.ajustar_componente(filas, 2000)
    assert modelo is not None
    assert modelo["eta"] == pytest.approx(1000, rel=0.1)
