"""Validación del método de predicción con simulaciones (07-fase4, sección 14).

Reproduce los cuatro experimentos de la guía y la calibración, con el MISMO código de ajuste que usa
el backend (`app.services.prediccion.weibull`): lo que aquí se mide es lo que corre en producción.

QUÉ SIMULA
----------
Flotas de equipos nuevos cuyas piezas fallan según una Weibull con **reparación mínima**: una
reparación deja la pieza con la edad que tenía, un reemplazo la deja en cero. La próxima falla de
una pieza de edad `a` se sortea invirtiendo la intensidad acumulada Λ(a) = (a/η)^β:

    a' = η · ((a/η)^β + E)^(1/β),   E ~ Exponencial(1)

Cada vida de pieza se resume como la vista `v_vidas`: fallas, Σ ln(edad en cada falla) y horas
observadas. Una vida que sigue abierta al final de la ventana entra **censurada**.

EXPERIMENTOS
------------
1. Cómo se estima: scipy sobre intervalos entre fallas (lo que proponía la Especificación 5.3) frente
   a máxima verosimilitud con censura y frente al MAP de SIMAP, por número de fallas; y la
   sensibilidad del MAP a una vida nominal equivocada por un factor 2.
2. Cuánto pesa la ventana de observación (8 equipos, solo reemplazos, ventanas de 1, 2 y 4 η).
3. Qué hacer con un reemplazo predictivo en lazo cerrado: censura (SIMAP), descartarlo o contarlo
   como falla.
4. Qué umbral conviene (sin intervenir, 40 %, 25 %, 10 %).
5. Calibración del riesgo estimado frente al verdadero, y error por nivel de confianza.

El error es la diferencia absoluta media entre el riesgo estimado y el verdadero (horizonte 120 h)
a las edades 0,4, 0,7 y 1,0 η, en puntos porcentuales divididos por 100 (0,05 son cinco puntos).

Los datos son SIMULADOS y el modelo está bien especificado por construcción: esto muestra que el
método es correcto en su propio mundo, no que prediga bien en una planta (14.7).

Uso (desde la raíz del repositorio; no necesita la base de datos):

    python tools/experimentos_fase4.py                  # versión rápida (≈ 1 min)
    python tools/experimentos_fase4.py --completo       # tamaños de la guía (varios minutos)
    python tools/experimentos_fase4.py --salida docs/contexto/anexos/experimentos-fase4.md
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import warnings
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.stats import weibull_min

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from app.services.prediccion.weibull import Datos, Prior, ajustar, nivel, riesgo  # noqa: E402

ETA = 1000.0
HORIZONTE = 120.0
EDADES = (0.4, 0.7, 1.0)
SEMILLA = 2026


# --------------------------------------------------------------------------------------------------
# Simulación
# --------------------------------------------------------------------------------------------------


@dataclass
class Vida:
    """Una pieza instalada: sus fallas (edades) y las horas que lleva observada."""

    edades_falla: list[float] = field(default_factory=list)
    exposicion: float = 0.0
    #: Cómo terminó: None (sigue abierta), "falla" o "predictivo".
    fin: str | None = None


def proxima_falla(rng: np.random.Generator, edad: float, beta: float, eta: float) -> float:
    return eta * ((edad / eta) ** beta + rng.exponential()) ** (1.0 / beta)


def simular_equipo(
    rng: np.random.Generator, beta: float, eta: float, ventana: float, p_reemplazo: float
) -> tuple[list[Vida], list[float]]:
    """Un equipo observado `ventana` horas. Devuelve sus vidas y las horas del equipo en cada falla."""
    vidas = [Vida()]
    fallas_equipo: list[float] = []
    reloj, edad = 0.0, 0.0
    while True:
        siguiente = proxima_falla(rng, edad, beta, eta)
        if reloj + (siguiente - edad) > ventana:
            vidas[-1].exposicion = edad + (ventana - reloj)
            return vidas, fallas_equipo
        reloj += siguiente - edad
        edad = siguiente
        vidas[-1].edades_falla.append(edad)
        fallas_equipo.append(reloj)
        if rng.random() < p_reemplazo:
            vidas[-1].exposicion = edad
            vidas[-1].fin = "falla"
            vidas.append(Vida())
            edad = 0.0


def filas(vidas: Iterable[Vida]) -> list[tuple[int, float, float]]:
    """Como `v_vidas`: (n_eventos, suma_ln_edades, exposicion)."""
    return [(len(v.edades_falla), sum(math.log(a) for a in v.edades_falla), v.exposicion) for v in vidas]


def riesgo_seguro(edad: float, beta: float, eta: float) -> float:
    """El riesgo del backend, sin desbordar con los β absurdos que a veces devuelve scipy sobre
    intervalos (en producción β está acotado a 10 y no puede pasar): un Λ enorme es riesgo 1."""
    try:
        return riesgo(edad, HORIZONTE, beta, eta)
    except OverflowError:
        return 1.0


def error_riesgo(beta: float, eta: float, beta_real: float, eta_real: float) -> float:
    return float(
        np.mean(
            [abs(riesgo_seguro(k * eta_real, beta, eta) - riesgo_seguro(k * eta_real, beta_real, eta_real)) for k in EDADES]
        )
    )


def ajuste_scipy(fallas_por_equipo: list[list[float]]) -> tuple[float, float] | None:
    """El método de la Especificación 5.3: Weibull sobre los intervalos entre fallas consecutivas."""
    intervalos = []
    for fallas in fallas_por_equipo:
        anterior = 0.0
        for t in fallas:
            intervalos.append(t - anterior)
            anterior = t
    if len(intervalos) < 2:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c, _, escala = weibull_min.fit(intervalos, floc=0)
    return float(c), float(escala)


def tramo(n: int) -> str:
    return "2 a 3" if n <= 3 else "4 a 7" if n <= 7 else "8 a 19" if n <= 19 else "20 o más"


TRAMOS = ("2 a 3", "4 a 7", "8 a 19", "20 o más")


def pct(xs: list[float], q: float) -> float:
    return float(np.percentile(xs, q)) if xs else float("nan")


def tabla(encabezado: list[str], filas_: list[list[str]]) -> str:
    lineas = ["| " + " | ".join(encabezado) + " |", "|" + "|".join("---" for _ in encabezado) + "|"]
    lineas += ["| " + " | ".join(f) + " |" for f in filas_]
    return "\n".join(lineas)


def coma(x: float, d: int = 3) -> str:
    return f"{x:.{d}f}".replace(".", ",")


# --------------------------------------------------------------------------------------------------
# Experimento 1 (y la calibración, que usa los mismos ajustes)
# --------------------------------------------------------------------------------------------------


def experimento_1(rng: np.random.Generator, repeticiones: int) -> str:
    errores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    calibracion: list[tuple[float, float]] = []
    por_confianza: dict[str, list[float]] = defaultdict(list)
    ajustes = 0
    for beta in (1.5, 2.5, 3.5):
        for flota in (2, 3, 5, 8, 12, 18, 30):
            for _ in range(repeticiones):
                vidas, por_equipo = [], []
                for _ in range(flota):
                    v, f = simular_equipo(rng, beta, ETA, ETA, 0.5)
                    vidas += v
                    por_equipo.append(f)
                d = Datos.de_vidas(filas(vidas))
                if d.n < 2:
                    continue
                t = tramo(d.n)
                ajustes += 1
                s = ajuste_scipy(por_equipo)
                if s is not None:
                    errores["scipy"][t].append(error_riesgo(*s, beta, ETA))
                mv = ajustar(d, None)
                errores["mv"][t].append(error_riesgo(mv.beta, mv.eta, beta, ETA))
                for nombre, nominal in (("map", ETA), ("map_x2", ETA * 2), ("map_d2", ETA / 2)):
                    m = ajustar(d, Prior.desde(nominal, d))
                    e = error_riesgo(m.beta, m.eta, beta, ETA)
                    errores[nombre][t].append(e)
                    if nombre == "map":
                        por_confianza[nivel(d.n)[1]].append(e)
                        for k in EDADES:
                            calibracion.append(
                                (riesgo(k * ETA, HORIZONTE, m.beta, m.eta), riesgo(k * ETA, HORIZONTE, beta, ETA))
                            )
    filas1 = [
        [
            t,
            str(len(errores["map"][t])),
            coma(pct(errores["scipy"][t], 50)),
            coma(pct(errores["mv"][t], 50)),
            coma(pct(errores["map"][t], 50)),
            coma(pct(errores["map"][t], 90)),
        ]
        for t in TRAMOS
    ]
    sens = [
        [t, coma(pct(errores["map"][t], 50)), coma(pct(errores["map_x2"][t], 50)), coma(pct(errores["map_d2"][t], 50))]
        for t in TRAMOS
    ]
    bandas = [(0, 0.05, "menos de 5 %"), (0.05, 0.10, "5 a 10 %"), (0.10, 0.20, "10 a 20 %"),
              (0.20, 0.30, "20 a 30 %"), (0.30, 0.50, "30 a 50 %"), (0.50, 1.01, "50 % o más")]
    filas_cal = []
    for lo, hi, nombre in bandas:
        sel = [(e, v) for e, v in calibracion if lo <= e < hi]
        if sel:
            filas_cal.append([nombre, str(len(sel)), coma(np.mean([e for e, _ in sel])), coma(np.mean([v for _, v in sel]))])
    filas_conf = [
        [c, str(len(por_confianza[c])), coma(pct(por_confianza[c], 50)), coma(pct(por_confianza[c], 90))]
        for c in ("baja", "media", "alta")
    ]
    return "\n\n".join(
        [
            f"## Experimento 1: cómo se estima\n\n{ajustes:,} flotas ajustadas (β ∈ {{1,5; 2,5; 3,5}}, η = 1000 h, "
            "ventana 1000 h, reparación o reemplazo con probabilidad ½). Error mediano del riesgo:",
            tabla(["Fallas", "Ajustes", "scipy sobre intervalos", "MV con censura", "MAP (SIMAP)", "MAP, p90"], filas1),
            "Sensibilidad del MAP a la vida nominal declarada (error mediano):",
            tabla(["Fallas", "Vida nominal correcta", "× 2", "÷ 2"], sens),
            "## Calibración (14.6)\n\nRiesgo estimado por el MAP frente al verdadero, agrupado por el estimado:",
            tabla(["Riesgo estimado", "Pares", "Estimado medio", "Verdadero medio"], filas_cal),
            "Error por nivel de confianza:",
            tabla(["Confianza", "Ajustes", "Error mediano", "Percentil 90"], filas_conf),
        ]
    )


# --------------------------------------------------------------------------------------------------
# Experimento 2
# --------------------------------------------------------------------------------------------------


def experimento_2(rng: np.random.Generator, repeticiones: int) -> str:
    filas2 = []
    beta = 2.5
    for k in (1, 2, 4):
        n_fallas, e_s, e_m, r_s, r_m = [], [], [], [], []
        for _ in range(repeticiones):
            vidas, por_equipo = [], []
            for _ in range(8):
                v, f = simular_equipo(rng, beta, ETA, k * ETA, 1.0)
                vidas += v
                por_equipo.append(f)
            d = Datos.de_vidas(filas(vidas))
            s = ajuste_scipy(por_equipo)
            if s is None:
                continue
            m = ajustar(d, Prior.desde(ETA, d))
            n_fallas.append(d.n)
            e_s.append(error_riesgo(*s, beta, ETA))
            e_m.append(error_riesgo(m.beta, m.eta, beta, ETA))
            r_s.append(s[1] / ETA)
            r_m.append(m.eta / ETA)
        filas2.append([
            str(k), coma(np.mean(n_fallas), 1), coma(np.median(e_s)), coma(np.median(e_m)),
            f"{coma(np.median(r_s) * 100, 1)} %", f"{coma(np.median(r_m) * 100, 1)} %",
        ])
    return "## Experimento 2: cuánto pesa la ventana de observación\n\n8 equipos, solo reemplazos, β = 2,5.\n\n" + tabla(
        ["Ventana (× η)", "Fallas medias", "Error scipy", "Error MAP", "η est./η real, scipy", "η est./η real, MAP"], filas2
    )


# --------------------------------------------------------------------------------------------------
# Experimentos 3 y 4: lazo cerrado
# --------------------------------------------------------------------------------------------------


@dataclass
class Resultado:
    fallas: int
    predictivos: int
    beta: float
    eta: float


def lazo(
    rng: np.random.Generator,
    beta: float,
    umbral: float | None,
    tratamiento: str,
    equipos: int = 10,
    duracion: float = 6000.0,
    paso: float = 10.0,
    reajuste_cada: float = 100.0,
) -> Resultado:
    """10 equipos durante 6000 h; el modelo decide el reemplazo cuando su riesgo a 120 h llega al umbral.

    `tratamiento`: "censura" (SIMAP), "descartar" o "falla": cómo entra un reemplazo predictivo al
    reajustar. El modelo parte de la vida nominal correcta y se reajusta cada `reajuste_cada` horas.
    """
    cerradas: list[Vida] = []
    abiertas = [Vida() for _ in range(equipos)]
    proximas = [proxima_falla(rng, 0.0, beta, ETA) for _ in range(equipos)]
    edad = [0.0] * equipos
    b_est, e_est = 2.0, ETA
    fallas = predictivos = 0
    reloj = 0.0
    while reloj < duracion:
        for i in range(equipos):
            fin = edad[i] + paso
            while proximas[i] <= fin:
                a = proximas[i]
                abiertas[i].edades_falla.append(a)
                fallas += 1
                if rng.random() < 0.5:
                    abiertas[i].exposicion, abiertas[i].fin = a, "falla"
                    cerradas.append(abiertas[i])
                    abiertas[i] = Vida()
                    fin -= a
                    proximas[i] = proxima_falla(rng, 0.0, beta, ETA)
                else:
                    proximas[i] = proxima_falla(rng, a, beta, ETA)
            edad[i] = fin
            if umbral is not None and riesgo(edad[i], HORIZONTE, b_est, e_est) >= umbral:
                predictivos += 1
                v = abiertas[i]
                v.exposicion, v.fin = edad[i], "predictivo"
                if tratamiento == "falla":
                    v.edades_falla.append(edad[i])
                if tratamiento != "descartar":
                    cerradas.append(v)
                abiertas[i] = Vida()
                edad[i] = 0.0
                proximas[i] = proxima_falla(rng, 0.0, beta, ETA)
        reloj += paso
        if reloj % reajuste_cada < paso:
            vivas = [Vida(list(v.edades_falla), edad[i]) for i, v in enumerate(abiertas)]
            d = Datos.de_vidas(filas(cerradas + vivas))
            m = ajustar(d, Prior.desde(ETA, d))
            b_est, e_est = m.beta, m.eta
    return Resultado(fallas, predictivos, b_est, e_est)


def experimento_3(rng: np.random.Generator, corridas: int) -> str:
    filas3 = []
    nombres = {"censura": "Censura: la vida termina sin falla (SIMAP)",
               "descartar": "Descartarlo, como si no hubiera existido", "falla": "Contarlo como una falla"}
    for t in ("censura", "descartar", "falla"):
        celdas = [nombres[t]]
        for beta in (2.5, 3.5):
            rs = [lazo(rng, beta, 0.25, t) for _ in range(corridas)]
            celdas.append(f"{coma(np.median([r.eta for r in rs]) / ETA * 100, 1)} %")
            celdas.append(coma(np.mean([r.predictivos for r in rs]), 1))
        filas3.append(celdas)
    return (
        f"## Experimento 3: qué hacer con un reemplazo predictivo\n\nLazo cerrado: 10 equipos, 6000 h, umbral 25 % a 120 h, "
        f"{corridas} corridas por celda.\n\n"
        + tabla(["Tratamiento", "η est./η real (β = 2,5)", "Predictivos (β = 2,5)", "η est./η real (β = 3,5)", "Predictivos (β = 3,5)"], filas3)
    )


def experimento_4(rng: np.random.Generator, corridas: int) -> str:
    filas4 = []
    for umbral, nombre in ((None, "Sin intervenir"), (0.40, "40 %"), (0.25, "25 %"), (0.10, "10 %")):
        celdas = [nombre]
        for beta in (2.5, 3.5):
            rs = [lazo(rng, beta, umbral, "censura") for _ in range(corridas)]
            celdas += [coma(np.mean([r.fallas for r in rs]), 1), coma(np.mean([r.predictivos for r in rs]), 1)]
        filas4.append(celdas)
    return (
        f"## Experimento 4: qué umbral conviene\n\nMismo lazo, tratamiento por censura, {corridas} corridas por celda.\n\n"
        + tabla(["Umbral", "Fallas (β = 2,5)", "Predictivos (β = 2,5)", "Fallas (β = 3,5)", "Predictivos (β = 3,5)"], filas4)
    )


# --------------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--completo", action="store_true", help="Tamaños de la guía (tarda varios minutos).")
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--salida", type=Path, help="Además de imprimirlo, escribe el informe en este archivo.")
    args = parser.parse_args()
    rep1, rep2, corridas = (180, 300, 100) if args.completo else (25, 60, 12)
    secciones: list[str] = []
    pasos: list[tuple[str, Callable[[np.random.Generator, int], str], int]] = [
        ("1", experimento_1, rep1), ("2", experimento_2, rep2), ("3", experimento_3, corridas), ("4", experimento_4, corridas),
    ]
    inicio = time.perf_counter()
    for nombre, fn, n in pasos:
        # Una semilla por experimento: cada uno se puede reproducir por separado.
        rng = np.random.default_rng(args.semilla + int(nombre))
        t0 = time.perf_counter()
        secciones.append(fn(rng, n))
        print(f"[experimento {nombre}: {time.perf_counter() - t0:.0f} s]", file=sys.stderr)
    modo = "completa" if args.completo else "rápida"
    informe = (
        f"# Validación del método con simulaciones (fase 4)\n\nVersión {modo}, semilla {args.semilla}. "
        "Datos SIMULADOS con la misma familia de modelos que se ajusta (ver 07-fase4, 14.7). "
        f"Generado por `tools/experimentos_fase4.py` en {time.perf_counter() - inicio:.0f} s.\n\n"
        + "\n\n".join(secciones)
        + "\n"
    )
    print(informe)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(informe, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
