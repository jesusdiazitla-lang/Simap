"""Modelo de Weibull con reparación mínima: ajuste por máximo a posteriori y riesgo (RF-17, RF-18).

`docs/contexto/07-fase4-prediccion-e-inventario.md`, sección 5. Matemática pura: no toca la base.

EL MODELO (5.2)
---------------
Un componente se desgasta con la edad según una intensidad de Weibull; una reparación o un ajuste lo
dejan como estaba y solo el reemplazo lo renueva. El número esperado de fallas hasta la edad `a` es
Λ(a) = (a/η)^β. Con `n` fallas en las edades a₁…aₙ y vidas observadas durante T₁…Tₖ:

    ln L = n·ln β − n·β·ln η + (β − 1)·Σ ln aⱼ − Σ (Tₗ/η)^β

Tres números por vida bastan (`v_vidas`): cuántas fallas tuvo, la suma de los logaritmos de sus
edades y las horas observadas. La vida **abierta** (la pieza instalada hoy) entra con sus horas y
sin falla: es la censura por la derecha, y es lo que la Especificación 5.3 (`weibull_min.fit` sobre
intervalos) ignoraba (decisión 11).

CONOCIMIENTO PREVIO (5.3)
-------------------------
Con dos o tres fallas la máxima verosimilitud puede devolver cualquier cosa. Se maximiza la densidad
a posteriori con una normal en (u = ln β, v = ln η): β ≈ 2 (±0,5 en ln β) y η centrada en la vida
nominal (±0,7 en ln η). Sin vida nominal pero con dos fallas o más, una creencia débil (±1,5)
centrada en horas observadas / fallas. Sin ninguna de las dos no hay modelo.

`scipy.stats.weibull_min.fit` no admite censura ni prior; se usa solo en las pruebas, para comprobar
que sin censura y sin prior este ajuste da lo mismo.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

#: Límites de β (5.3): fuera de ellos el ajuste está extrapolando ruido.
BETA_MIN = 0.3
BETA_MAX = 10.0
#: Edad mínima de una falla, para no tomar el logaritmo de cero (lo aplica también `v_vidas`).
EDAD_MIN = 0.5
#: Creencia previa sobre β: desgaste moderado. Configurable aquí, en un solo sitio.
BETA_PREVIA = 2.0
SIGMA_LN_BETA = 0.5
SIGMA_LN_ETA = 0.7
#: Creencia débil sobre η cuando el componente no tiene vida nominal declarada.
SIGMA_LN_ETA_DEBIL = 1.5


@dataclass(frozen=True)
class Datos:
    """Estadísticos suficientes: `n` fallas, `s1` = Σ ln(edad) y `t` = horas observadas por vida."""

    n: int
    s1: float
    t: NDArray[np.float64] = field(default_factory=lambda: np.zeros(0))

    @classmethod
    def de_vidas(cls, filas: Iterable[tuple[int, float | None, float | None]]) -> Datos:
        """Desde filas de `v_vidas` (n_eventos, suma_ln_edades, exposicion).

        Una vida sin edad conocida (exposición nula) no entra: sus horas no son confiables (5.1).
        Una vida de cero horas tampoco aporta nada a la verosimilitud, y su logaritmo no existe.
        """
        n, s1, t = 0, 0.0, []
        for eventos, suma, exposicion in filas:
            if exposicion is None:
                continue
            n += int(eventos)
            s1 += float(suma or 0.0)
            if exposicion > 0:
                t.append(float(exposicion))
        return cls(n, s1, np.asarray(t, dtype=np.float64))


@dataclass(frozen=True)
class Prior:
    """Normal en (ln β, ln η) con medias `u0`, `v0` y desviaciones `su`, `sv`."""

    u0: float
    v0: float
    su: float
    sv: float

    @classmethod
    def desde(cls, vida_nominal: float | None, datos: Datos) -> Prior | None:
        if vida_nominal:
            return cls(math.log(BETA_PREVIA), math.log(vida_nominal), SIGMA_LN_BETA, SIGMA_LN_ETA)
        if datos.n >= 2 and datos.t.sum() > 0:
            centro = datos.t.sum() / datos.n
            return cls(math.log(BETA_PREVIA), math.log(centro), SIGMA_LN_BETA, SIGMA_LN_ETA_DEBIL)
        return None


@dataclass(frozen=True)
class Ajuste:
    beta: float
    eta: float
    convergio: bool
    n_eventos: int
    n_vidas: int
    exposicion: float


def _neg_logpost(
    x: NDArray[np.float64], d: Datos, pr: Prior | None
) -> tuple[float, NDArray[np.float64]]:
    """Menos el logaritmo de la densidad a posteriori, y su gradiente analítico en (u, v)."""
    u, v = float(x[0]), float(x[1])
    b = math.exp(u)
    f = 0.0
    gu = 0.0
    gv = 0.0
    if d.n:
        f += d.n * u - d.n * b * v + (b - 1.0) * d.s1
        gu += d.n - d.n * b * v + b * d.s1
        gv += -d.n * b
    if d.t.size:
        z = np.log(d.t) - v
        e = np.exp(b * z)
        f -= float(e.sum())
        gu -= float((e * b * z).sum())
        gv += float((e * b).sum())
    if pr is not None:
        f -= 0.5 * ((u - pr.u0) / pr.su) ** 2 + 0.5 * ((v - pr.v0) / pr.sv) ** 2
        gu -= (u - pr.u0) / pr.su**2
        gv -= (v - pr.v0) / pr.sv**2
    return -f, np.array([-gu, -gv])


def ajustar(datos: Datos, prior: Prior | None) -> Ajuste:
    """Máximo a posteriori (con prior) o máxima verosimilitud (`prior=None`)."""
    ub = (math.log(BETA_MIN), math.log(BETA_MAX))
    if prior is None:
        if datos.n == 0 or datos.t.size == 0:
            raise ValueError("sin datos ni prior: no hay modelo")
        x0 = np.array([math.log(1.5), math.log(datos.t.sum() / datos.n)])
        vb = (float(x0[1]) - 8.0, float(x0[1]) + 8.0)
    else:
        x0 = np.array([prior.u0, prior.v0])
        vb = (prior.v0 - 6.0, prior.v0 + 6.0)
    # Sin eventos la verosimilitud solo empuja η hacia arriba; el máximo existe porque el prior lo
    # acota, y se resuelve igual numéricamente.
    r = minimize(
        _neg_logpost,
        x0,
        args=(datos, prior),
        jac=True,
        method="L-BFGS-B",
        bounds=[ub, vb],
        options={"maxiter": 200, "ftol": 1e-12, "gtol": 1e-8},
    )
    u, v = float(r.x[0]), float(r.x[1])
    return Ajuste(
        math.exp(u), math.exp(v), bool(r.success), datos.n, int(datos.t.size), float(datos.t.sum())
    )


def hazard_acum(edad: float, beta: float, eta: float) -> float:
    """Λ(a) = (a/η)^β: fallas esperadas hasta la edad `a`."""
    return float((max(edad, 0.0) / eta) ** beta)


def riesgo(edad: float, horizonte: float, beta: float, eta: float, m: float = 1.0) -> float:
    """P(al menos una falla en las próximas `horizonte` horas), dada la edad actual (5.4).

    `m` multiplica la intensidad (alertas de campo, RF-20), no la probabilidad: así el resultado
    nunca pasa de 1. Con el ejemplo de la Especificación 5.3 (350 h, 50 h, β = 3,5, η = 430) da
    25,2 %, y con m = 1,30, 31,4 %.
    """
    d = hazard_acum(edad + horizonte, beta, eta) - hazard_acum(edad, beta, eta)
    return -math.expm1(-m * d)


def nivel(n_eventos: int) -> tuple[str, str]:
    """Etiquetas de fuente y de confianza por número de fallas reales (5.3)."""
    fuente = "previo" if n_eventos == 0 else ("mixto" if n_eventos < 8 else "empresa")
    confianza = "baja" if n_eventos < 8 else ("media" if n_eventos < 20 else "alta")
    return fuente, confianza


def ajustar_componente(
    filas: Iterable[tuple[int, float | None, float | None]], vida_nominal: float | None
) -> dict[str, Any] | None:
    """Modelo de un componente con las vidas de todos los equipos de la empresa, o `None`.

    Sin vida nominal hacen falta al menos dos fallas: no se inventa un modelo (decisión 6).
    """
    d = Datos.de_vidas(filas)
    prior = Prior.desde(vida_nominal, d)
    if prior is None:
        return None
    a = ajustar(d, prior)
    fuente, confianza = nivel(d.n)
    return {
        "beta": a.beta,
        "eta": a.eta,
        "n_eventos": d.n,
        "n_vidas": a.n_vidas,
        "exposicion": a.exposicion,
        "fuente": fuente,
        "confianza": confianza,
        "convergio": a.convergio,
    }
