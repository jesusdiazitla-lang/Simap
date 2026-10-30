# Matriz de trazabilidad final

> Cada requerimiento de `03-requerimientos-casos-de-uso.md`, la fase que lo construyó y dónde queda la
> evidencia **en este repositorio** (08-fase5, sección 14). Base del capítulo IV. Una celda que dice
> «no se verificó» no es un error: es lo que todavía hay que cerrar. Estado al 2026-10-28.

| Requerimiento | Fase | Evidencia |
|---|---|---|
| RF-01 a RF-03 (acceso, empresas, usuarios) | 1 | `tests/test_auth.py`, `test_aislamiento_tenant.py`, `test_operador.py`; auditoría de catálogo y recorrido de rutas de F5 (`test_auditoria_aislamiento.py`). |
| RF-04 a RF-07 (equipos, QR) | 2 | `tests/test_activos.py` y afines; F5 rellena `activos.creado_en` (decisión 8) y usa la ubicación como filtro de planta (decisión 1). |
| RF-08 a RF-10 (horómetro, alertas, sin conexión) | 2 | `tests/test_lecturas.py`, `test_campo.py`; e2e `campo.spec.ts`. F5 agrega `horas_acumuladas` con su trigger (`test_horas_acumuladas_las_mantiene_el_trigger`, `test_reinicio_resuelto_despues_recalcula_las_lecturas_posteriores`) y la observación empieza con el primer dato (`test_dato_anterior_al_alta_adelanta_desde_cuando_se_observa`). El modo sin conexión se volvió a probar con la CSP de F5 (suite e2e completa). |
| RF-11 a RF-16 (órdenes de trabajo) | 3 | `tests/test_ordenes*.py`, `test_orden_trabajo.py`, `test_concurrencia_ordenes.py`; e2e `ordenes.spec.ts`. F5 corrige el cierre de las predictivas (`test_cierre_de_predictiva_mide_desde_la_entrada_al_taller`). |
| RF-17 a RF-22 (modelo, riesgo, alertas del sistema) | 4 | `tests/test_weibull.py`, `test_prediccion*.py`, `test_concurrencia_fase4.py`; experimentos de `anexos/experimentos-fase4.md`; e2e `fase4.spec.ts`. Los paneles leen `v_riesgo_activo`. |
| RF-23 a RF-26 (inventario) | 4 | `tests/test_inventario.py`, `test_concurrencia_fase4.py`; el costo del panel sale del libro y la validación cruzada lo recalcula por otro camino (`test_indicadores.py`). |
| RF-27 (panel por rol) | 5 | Cinco paneles (`/panel`); `test_rf27_*` en `test_paneles.py` y `test_ensamblador.py`; e2e `test_rf27_cada_rol_ve_su_panel_y_no_el_de_otro`. |
| RF-28 (disponibilidad, MTBF, costos) | 5 | Fórmulas de 08-fase5 §5; casos a mano y 80 flotas al azar contra una implementación independiente (`test_indicadores.py`); indicador calculado a mano sobre datos sembrados en PostgreSQL (`test_rf28_indicadores_coinciden_con_el_calculo_a_mano`); mutaciones M04 y M11 detectadas. |
| RNF-01 (aislamiento) | 1 y 5 | Guardias de RLS de cada fase; catálogo C1–C13 y recorrido de todas las rutas con un cuerpo válido por escritura (`test_auditoria_aislamiento.py`); sabotajes S01 (RLS de `activos`) y de RLS en `ordenes_trabajo` detectados. **Falta:** correrlo contra staging; las pruebas con pool de conexiones reutilizadas (11.4) no se escribieron. |
| RNF-02 (registro aunque falle el riesgo) | 4 y 5 | Cálculo después del commit (`test_rnf02_falla_del_calculo_no_afecta_lectura_ni_reporte`); widgets aislados (`test_si_el_calculo_de_riesgo_falla_el_resto_del_panel_responde`, `test_rnf02_*` en `test_ensamblador.py`); el trigger de lecturas no consulta el riesgo. |
| RNF-03 (tres pasos para reportar) | 2 | Flujo de campo de la fase 2. **No se verificó** con un conteo automático en F5. |
| RNF-04 (riesgo de un equipo < 2 s) | 4 y 5 | 123 ms con 60 000 órdenes en PostgreSQL local (`test_rnf04_*`); el panel del gerente responde en ~30 ms con los datos sectoriales. **Falta:** medirlo en staging, con la latencia real. |
| RNF-05 (móvil) | 2 | Pantallas revisadas a 390 px en cada fase; e2e `test_rnf05_panel_del_gerente_en_390_px_sin_desplazamiento_horizontal`. **No se probó** en dispositivos físicos ni fuera de Chromium. |
| RNF-06 (trazabilidad de órdenes) | 3 | `orden_eventos` de solo agregar (control C10). F5 no crea acciones sobre órdenes. |
| RNF-07 (escalabilidad) | 1 y 5 | Mediciones de 08-fase5 §9 (guía) y RNF-04 con 60 000 órdenes. Sin caché ni cola. |
| RNF-08 (módulos con fronteras) | 1 y 5 | `import-linter` (capas del backend) y `dependency-cruiser` (frontend) en CI; el grafo del proyecto (`tools/graph`). |
