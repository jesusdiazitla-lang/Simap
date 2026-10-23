"""Predicción de fallas (F4; docs/contexto/07-fase4-prediccion-e-inventario.md).

- `weibull`: la matemática del modelo, sin base de datos.
- `configuracion`: los parámetros de cada empresa.
- `componentes_equipo`: qué componentes tiene cada equipo y su edad.
- `ajuste`: marcas de reajuste, ajuste y guardado del modelo con su historial.
- `riesgo`: cálculo del riesgo y alertas de riesgo con histéresis y silencio.
- `alertas`: bandeja de alertas del sistema y orden predictiva.
- `tareas`: lo que corre en segundo plano después del commit.
"""
