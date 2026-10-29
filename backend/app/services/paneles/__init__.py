"""Paneles por rol e indicadores del gerente (F5; docs/contexto/08-fase5-dashboard-y-cierre.md).

- `indicadores`: el cálculo puro (periodo, cubos por mes, paradas, MTBF y su intervalo). No conoce
  HTTP ni la base de datos.
- `ensamblador`: corre widgets genéricos, cada uno en su transacción y con su límite, y degrada el
  que falla sin tumbar el panel (RNF-02). No sabe qué consulta cada uno.
- `consultas`: las lecturas del ORM que alimentan cada widget.
- `widgets`: une las tres piezas: qué widget ve cada rol y qué consulta hace.
"""
