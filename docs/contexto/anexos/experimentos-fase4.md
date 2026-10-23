# Validación del método con simulaciones (fase 4)

Versión completa, semilla 2026. Datos SIMULADOS con la misma familia de modelos que se ajusta (ver 07-fase4, 14.7). Generado por `tools/experimentos_fase4.py` en 156 s.

## Experimento 1: cómo se estima

3,374 flotas ajustadas (β ∈ {1,5; 2,5; 3,5}, η = 1000 h, ventana 1000 h, reparación o reemplazo con probabilidad ½). Error mediano del riesgo:

| Fallas | Ajustes | scipy sobre intervalos | MV con censura | MAP (SIMAP) | MAP, p90 |
|---|---|---|---|---|---|
| 2 a 3 | 749 | 0,335 | 0,087 | 0,057 | 0,130 |
| 4 a 7 | 878 | 0,264 | 0,067 | 0,057 | 0,153 |
| 8 a 19 | 1200 | 0,213 | 0,044 | 0,039 | 0,092 |
| 20 o más | 547 | 0,200 | 0,028 | 0,027 | 0,065 |

Sensibilidad del MAP a la vida nominal declarada (error mediano):

| Fallas | Vida nominal correcta | × 2 | ÷ 2 |
|---|---|---|---|
| 2 a 3 | 0,057 | 0,066 | 0,061 |
| 4 a 7 | 0,057 | 0,056 | 0,060 |
| 8 a 19 | 0,039 | 0,039 | 0,041 |
| 20 o más | 0,027 | 0,027 | 0,027 |

## Calibración (14.6)

Riesgo estimado por el MAP frente al verdadero, agrupado por el estimado:

| Riesgo estimado | Pares | Estimado medio | Verdadero medio |
|---|---|---|---|
| menos de 5 % | 273 | 0,040 | 0,070 |
| 5 a 10 % | 1887 | 0,078 | 0,092 |
| 10 a 20 % | 4242 | 0,148 | 0,159 |
| 20 a 30 % | 2125 | 0,242 | 0,223 |
| 30 a 50 % | 1300 | 0,375 | 0,292 |
| 50 % o más | 295 | 0,630 | 0,319 |

Error por nivel de confianza:

| Confianza | Ajustes | Error mediano | Percentil 90 |
|---|---|---|---|
| baja | 1627 | 0,057 | 0,142 |
| media | 1200 | 0,039 | 0,092 |
| alta | 547 | 0,027 | 0,065 |

## Experimento 2: cuánto pesa la ventana de observación

8 equipos, solo reemplazos, β = 2,5.

| Ventana (× η) | Fallas medias | Error scipy | Error MAP | η est./η real, scipy | η est./η real, MAP |
|---|---|---|---|---|---|
| 1 | 5,7 | 0,321 | 0,051 | 71,3 % | 99,1 % |
| 2 | 14,6 | 0,049 | 0,034 | 91,0 % | 100,7 % |
| 4 | 32,8 | 0,027 | 0,022 | 95,7 % | 100,0 % |

## Experimento 3: qué hacer con un reemplazo predictivo

Lazo cerrado: 10 equipos, 6000 h, umbral 25 % a 120 h, 100 corridas por celda.

| Tratamiento | η est./η real (β = 2,5) | Predictivos (β = 2,5) | η est./η real (β = 3,5) | Predictivos (β = 3,5) |
|---|---|---|---|---|
| Censura: la vida termina sin falla (SIMAP) | 98,1 % | 51,0 | 99,3 % | 57,0 |
| Descartarlo, como si no hubiera existido | 55,3 % | 190,9 | 65,5 % | 117,7 |
| Contarlo como una falla | 1,9 % | 2377,3 | 7,2 % | 1171,7 |

## Experimento 4: qué umbral conviene

Mismo lazo, tratamiento por censura, 100 corridas por celda.

| Umbral | Fallas (β = 2,5) | Predictivos (β = 2,5) | Fallas (β = 3,5) | Predictivos (β = 3,5) |
|---|---|---|---|---|
| Sin intervenir | 95,1 | 0,0 | 100,0 | 0,0 |
| 40 % | 71,3 | 19,3 | 53,4 | 34,6 |
| 25 % | 44,9 | 52,1 | 34,7 | 56,0 |
| 10 % | 16,3 | 146,2 | 13,7 | 104,8 |
