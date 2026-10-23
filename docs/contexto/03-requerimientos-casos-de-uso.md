# Requerimientos y Casos de Uso — SIMAP

> Transcripción de `Resquerimiento_CasosdeUso_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado).
> Los IDs `RF-xx` / `RNF-xx` / `CU-xx` se usan en `docs/PLAN.yaml`, en commits y en tests.

## 2. Requerimientos funcionales

### Autenticación y multiempresa (Fase 1)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-01 | Registrar e iniciar sesión de usuarios (correo y contraseña). | Esencial |
| RF-02 | Aislar completamente los datos entre empresas mediante Row-Level Security. | Esencial |
| RF-03 | Asignar a cada usuario un rol que determina sus permisos. | Esencial |

### Gestión de activos (Fase 2)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-04 | Registrar un activo con nombre, tipo, ubicación y criticidad. | Esencial |
| RF-05 | Generar automáticamente un código QR único al crear un activo. | Esencial |
| RF-06 | Editar y dar de baja un activo existente. | Importante |
| RF-07 | Mostrar la ficha técnica e historial de un activo al escanear su QR. | Esencial |

### Registro de campo (Fase 2)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-08 | Registrar una lectura de horómetro asociada a un activo. | Esencial |
| RF-09 | Reportar una alerta (síntoma y nota) sobre un activo. | Esencial |
| RF-10 | Funcionar sin conexión (PWA) y sincronizar automáticamente al recuperarla. | Importante |

### Órdenes de trabajo (Fase 3)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-11 | Reportar una falla con horómetro, temperatura, código de error y componente. | Esencial |
| RF-12 | Generar una orden de trabajo automáticamente al reportar una falla. | Esencial |
| RF-13 | Cambiar el estado de una orden: Reportada, En taller, Reparada, Cerrada, y **Cancelada** con motivo. *[Actualizado en F3, decisión 1 de `06-fase3-ordenes-de-trabajo.md` §4, confirmada el 2026-10-14.]* | Esencial |
| RF-14 | Registrar el responsable de cada estado (reportó, reparó, autorizó). | Esencial |
| RF-15 | Calcular el tiempo fuera de servicio al cerrar una orden. | Importante |
| RF-16 | Vincular una alerta previa a la orden de trabajo que origina. | Deseable |

### Motor de predicción (Fase 4)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-17 | Ajustar un modelo de Weibull por componente con el historial de fallas. | Esencial |
| RF-18 | Calcular el riesgo de falla de cada activo. | Esencial |
| RF-19 | Recalcular el riesgo con cada nueva lectura de horómetro. | Esencial |
| RF-20 | Ajustar el riesgo según las alertas recientes del activo. | Importante |
| RF-21 | Generar una alerta automática cuando el riesgo supera el umbral. | Esencial |
| RF-22 | Reajustar periódicamente los parámetros del modelo de cada componente. | Importante |

### Inventario (Fase 4)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-23 | Registrar repuestos con stock actual y stock mínimo. | Esencial |
| RF-24 | Asociar los repuestos usados a una orden de trabajo. | Esencial |
| RF-25 | Descontar el stock automáticamente al cerrar una orden. | Esencial |
| RF-26 | Alertar cuando el stock de un repuesto cae bajo el mínimo. | Importante |

### Panel de control (Fase 5)
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-27 | Mostrar un panel diferenciado según el rol del usuario. | Esencial |
| RF-28 | Mostrar indicadores de disponibilidad, MTBF y costos al gerente. | Importante |

## 3. Requerimientos no funcionales

| ID | Requerimiento | Categoría |
|---|---|---|
| RNF-01 | Ningún usuario debe poder acceder a datos de otra empresa, verificado en BD y en aplicación. | Seguridad |
| RNF-02 | Registro de reportes y consulta de activos disponibles aunque falle el cálculo de riesgo. *Se diseña y mide en F4 (`07-fase4…` §9.2); la Fase 5 lo verifica.* | Disponibilidad |
| RNF-03 | El flujo de reporte desde el QR hasta el envío no excede tres pasos para el operario. | Usabilidad |
| RNF-04 | El cálculo de riesgo de un activo no tarda más de dos segundos. *Se diseña y mide en F4 (`07-fase4…` §9.4: 123 ms con 60.000 órdenes); la Fase 5 lo verifica.* | Rendimiento |
| RNF-05 | Accesible desde cualquier navegador móvil moderno, sin instalación. | Portabilidad |
| RNF-06 | Toda acción sobre una orden queda registrada con usuario y marca de tiempo. | Auditabilidad |
| RNF-07 | La arquitectura permite aumentar empresas y activos sin rediseño. | Escalabilidad |
| RNF-08 | Código en módulos con fronteras claras, extraíbles como servicios independientes. | Mantenibilidad |

## 4. Casos de uso

### 4.1 Actores
Operario · Supervisor · Técnico de Taller · Gerente/Stakeholder · Administrador (ver roles en `01-especificacion-funcional.md`).

### 4.2 Matriz actor – caso de uso
| Caso de uso | Actor principal |
|---|---|
| CU-01 Reportar Alerta | Operario |
| CU-02 Reportar Falla y Generar Orden de Trabajo | Supervisor |
| CU-03 Actualizar y Cerrar Orden de Trabajo | Técnico de Taller; Supervisor o Administrador *[Actualizado en F3, decisión 2 de `06-fase3-ordenes-de-trabajo.md` §4, confirmada el 2026-10-14.]* |
| CU-04 Calcular Riesgo de Falla de un Activo | Sistema (automático) |
| CU-05 Registrar Nuevo Activo con Código QR | Administrador |
| CU-06 Gestionar Stock de Repuestos | Administrador (altas, conteos); Supervisor (ingresos, líneas); Técnico (líneas de su orden); Gerente (lectura) *[Actualizado en F4, decisión 2 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]* |

### CU-01 Reportar Alerta
- **Pre:** sesión activa; activo registrado. **Post:** alerta en estado `pendiente`, visible para el supervisor.
- **Flujo:** escanear QR → sistema identifica activo y muestra acciones → "Reportar alerta" → formulario con síntomas
  (ruido, vibración, calor, olor, fuga, otro) → seleccionar síntoma + nota opcional → confirmar → guardar asociada a
  activo y usuario → confirmación visual.
- **Alternativo:** sin conexión → se guarda localmente y se sincroniza al recuperar red.

### CU-02 Reportar Falla y Generar Orden de Trabajo
- **Pre:** sesión activa; activo y catálogo de componentes existen. **Post:** orden en `reportada`; el activo queda
  marcado en falla hasta que la orden se cierre.
- **Nota (F3):** «marcado en falla» no es un dato guardado en el activo sino **derivado**: el activo está en falla
  mientras tenga alguna orden abierta. Una columna duplicada acabaría desincronizándose
  (`06-fase3-ordenes-de-trabajo.md`, §6.2). *[Actualizado en F3, sección 16 de la guía.]*
- **Flujo:** escanear QR o buscar → "Reportar falla" → ingresar horómetro, temperatura, código de error, componente,
  descripción → confirmar → crear orden vinculada a activo, componente y supervisor → actualizar `horometro_actual` y
  `fecha_ultima_falla` del activo.
- **Alternativo:** la falla nace de una alerta previa → formulario pre-llenado y alerta vinculada (`alerta_origen_id`).

### CU-03 Actualizar y Cerrar Orden de Trabajo
- **Pre:** orden en `reportada` o `en_taller`. **Post:** orden `cerrada` con trazabilidad; stock actualizado.
- **Flujo:** técnico marca `en_taller` → repara y registra trabajo + repuestos → marca `reparada` → supervisor o
  administrador autoriza cierre → `cerrada`, registra `autorizado_por`, calcula tiempo fuera de servicio y **descuenta el
  inventario en la misma transacción del cierre** (no al marcar `reparada`). *[Actualizado en F4, decisión 1 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]* El gerente consulta las órdenes pero no las mueve. *[Actualizado en F3, decisión 2 de `06-fase3-ordenes-de-trabajo.md` §4, confirmada el 2026-10-14.]*
- **Alternativo:** cierre rechazado por reparación incompleta → vuelve a `en_taller` con nota.
- **Alternativo:** stock insuficiente para alguna línea → el cierre no se hace (409 `stock_insuficiente`), la orden sigue
  en `reparada` y la pantalla dice qué repuesto falta y cuánto. *[Actualizado en F4, decisión 3 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]*
- **Alternativo:** orden reportada por error o duplicada → supervisor o administrador la **cancela** con motivo; no se
  borra, libera el componente y, si venía de una alerta, la devuelve a `revisada`. *[Actualizado en F3, decisión 1 de `06-fase3-ordenes-de-trabajo.md` §4, confirmada el 2026-10-14.]*

### CU-04 Calcular Riesgo de Falla de un Activo (automático)
- **Pre:** el componente tiene **vida nominal** declarada o al menos dos fallas cerradas, y se conoce la edad de la pieza
  instalada. **Post:** riesgo actualizado; alerta del sistema si corresponde.
- **Flujo:** nueva lectura de horómetro, cierre de orden o job nocturno → para cada componente del equipo, su Weibull
  (β, η) y la **edad de la pieza** (horas desde su instalación o último reemplazo) → probabilidad de falla en el
  horizonte, **en horas de operación (50 por defecto)** → ajustar por alertas de campo recientes → si supera el umbral de
  la empresa, alerta automática visible para el supervisor. *[Actualizado en F4, decisión 4 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]*
- **Alternativo:** sin historial suficiente → modelo de partida centrado en la **vida nominal** del componente (no un
  dataset público), marcado «estimado» en la UI (fuente `previo`, confianza baja). Sin vida nominal ni dos fallas, «sin
  modelo»; sin edad conocida, «sin edad»: nunca un 0 %. *[Actualizado en F4, decisión 6 y 7 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]*

### CU-05 Registrar Nuevo Activo con Código QR
- **Pre:** administrador con sesión. **Post:** activo disponible para lecturas, alertas y órdenes.
- **Flujo:** "Nuevo activo" → nombre, tipo, ubicación, criticidad → confirmar → generar id único + QR → mostrar QR
  imprimible con código corto de respaldo.
- **Alternativo:** reimprimir QR de un activo existente.

### CU-06 Gestionar Stock de Repuestos
- **Pre:** permisos sobre inventario. **Post:** inventario actualizado y referenciable por órdenes.
- **Flujo:** módulo Inventario → el administrador registra el repuesto (nombre, código, stock inicial, mínimo, costo); el
  supervisor registra ingresos; el administrador ajusta por conteo físico con nota. Todo movimiento queda en el libro, que
  solo se agrega. *[Actualizado en F4, decisión 2 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]*
- **Alternativo:** stock **estrictamente** bajo el mínimo tras un consumo, ingreso o ajuste → alerta de reorden
  automática, una sola vigente, que se resuelve sola al volver al mínimo. *[Actualizado en F4, decisión 12 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]*

## 5. Plan de desarrollo por fases

| Fase | Semanas | Cubre | Definición de "hecho" |
|---|---|---|---|
| 1. Fundamentos | 1–2 | RF-01..03, RNF-01, 07, 08 | Un usuario se registra e inicia sesión; el sistema deniega datos de otra empresa incluso por API directa. |
| 2. Activos y registro de campo | 3–6 | RF-04..10, RNF-03, 05 | Un operario escanea el QR y registra horómetro o alerta; el reporte llega aunque se hiciera offline. |
| 3. Órdenes de trabajo | 7–8 | RF-11..16, RNF-06 | Una falla sigue su ciclo completo hasta cerrarse, con cada responsable visible en el historial. |
| 4. Predicción e inventario | 9–12 | RF-17..26 | Al cerrar una orden real el modelo se reajusta; un activo con fallas frecuentes muestra riesgo visiblemente mayor. |
| 5. Dashboard y cierre | 13–16 | RF-27, 28, RNF-01, 02, 04 | Los tres paneles muestran datos reales; las pruebas de aislamiento entre tenants pasan sin excepción. |

### Features por fase
**Fase 1:** repo + estructura + CI/CD; tablas Empresa y Usuario; registro/login con Argon2id y JWT+refresh; RLS
desde el primer commit; RBAC en middleware; esqueleto PWA con login y navegación por rol.

**Fase 2:** CRUD de activos; QR + código corto; vista móvil al escanear (acciones según rol); catálogo de
componentes; formulario de horómetro; formulario de alerta; offline de la PWA.

**Fase 3:** formulario de reporte de falla; creación automática de orden; máquina de estados con transiciones
por rol; registro de trabajo realizado; tiempo fuera de servicio; vínculo alerta→orden.

**Fase 4:** carga inicial del modelo con dataset público/simulado; ajuste de Weibull por componente; riesgo
por lectura; multiplicador por alertas; tarea diaria; alerta automática por umbral; CRUD de repuestos;
`orden_repuesto` y descuento al cerrar; alerta de reorden.

**Fase 5:** panel operario; panel supervisor; panel gerente (disponibilidad, MTBF, costo de repuestos,
activos de mayor riesgo); auditoría de aislamiento automatizada; pruebas unitarias y e2e de flujos críticos;
checklist OWASP Top 10; documentación técnica y manual de usuario.
