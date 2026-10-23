# Fase 4: Predicción e Inventario — Guía Detallada de Implementación

> Transcripción de `Fase4_Prediccion_e_Inventario_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado).
> Fuente de verdad del **alcance y los criterios de aceptación** de la fase F4 en `docs/PLAN.yaml`.
> Donde este documento contradice a los anteriores, manda este.
>
> El PDF copia íntegro el SQL de la migración y de los servicios. Aquí no se repite: el SQL vive en
> `backend/alembic/versions/20261018_0009_prediccion_e_inventario.py` y en `backend/app/services/`,
> y cada sección dice dónde. La vista `v_vidas` sí se transcribe, porque es el corazón de la fase.
>
> **Las trece decisiones de la sección 4 las confirmó el usuario el 2026-10-18**, tal como las
> propone el documento, junto con tres decisiones de implementación (portabilidad «como en F3», job
> con comando más APScheduler local, y el commit aparte del trabajo pendiente de F3). Lo que cambió
> al implementarla está en el **anexo** del final.

## 1. Objetivo de la fase

Activar la razón de ser de la tesis: que el sistema aprenda de las fallas cerradas y avise antes de
la siguiente. Hasta la Fase 3, SIMAP registra lo que ya pasó; aquí calcula, para cada componente de
cada equipo, la probabilidad de que falle en las próximas horas de operación, genera una alerta
cuando esa probabilidad supera el umbral de la empresa y permite programar el cambio de la pieza
antes de la falla. La segunda mitad completa el ciclo de los repuestos: inventario con libro de
movimientos, repuestos usados por orden, descuento automático al cerrar y alerta de reorden. Las dos
mitades se encuentran en dos puntos: al cerrar una orden (se descuenta el stock y se marca el
componente para reajustar su modelo) y en la orden predictiva (se cambia la pieza sin que haya
fallado).

Es también la fase donde más fácil es afirmar de más. Un porcentaje de riesgo con dos decimales
parece exacto aunque salga de tres fallas. Por eso la sección 14 mide, con datos simulados de verdad
conocida, cuánto se equivoca el método, y la interfaz (sección 10) muestra siempre cuántas fallas
respaldan cada número.

## 2. Alcance de esta fase

Requerimientos: RF-17 a RF-26. RNF-02 (el reporte y la consulta siguen disponibles aunque falle el
cálculo) y RNF-04 (el cálculo de un equipo tarda menos de 2 s) figuran en la Fase 5 del documento de
requerimientos, pero describen el cálculo que nace aquí: se diseñan y se miden en esta fase
(sección 9) y la Fase 5 los verifica formalmente. RNF-01 y RNF-06, de forma transversal.

Incluye:

- Ajuste de un modelo de Weibull por componente con el historial de órdenes cerradas, incluidos los
  componentes que todavía no han fallado (RF-17, RF-22).
- Riesgo por componente y por equipo, recalculado con cada lectura de horómetro y cada noche (RF-18,
  RF-19), con el ajuste por alertas de campo recientes (RF-20).
- Alertas del sistema cuando el riesgo supera el umbral, sin duplicados y sin parpadeo (RF-21).
- Orden de trabajo predictiva creada desde una alerta, y su tratamiento correcto en el modelo.
- Registro de qué componentes tiene cada equipo y a qué hora del equipo se instaló la unidad actual.
- Repuestos con stock actual y mínimo, libro de movimientos, repuestos por orden, descuento al cerrar
  y alerta de reorden (RF-23 a RF-26).
- Configuración de la predicción por empresa (umbral, horizonte, multiplicador).
- Validación del método con simulaciones de verdad conocida (sección 14): Capítulo IV de la tesis.

No incluye: paneles del gerente (disponibilidad, MTBF, costos: Fase 5; el costo unitario ya queda en
el libro); notificaciones push o por correo; modelos de aprendizaje automático (trabajo futuro);
intervalos de credibilidad para β y η (se muestra el nivel de confianza por número de fallas);
aprendizaje entre empresas (Especificación 5.5); modelo preentrenado con un dataset público (CU-04: se
sustituye por la vida nominal, decisión 6); sugerir qué repuesto corresponde a qué componente, lotes,
ubicaciones, reservas y órdenes de compra.

## 3. Puerta de entrada

Esta fase agrega 10 tablas, dos vistas y un proceso nocturno que recorre todas las empresas. Un error
de aislamiento aquí expone el modelo y el inventario de un cliente a otro. Antes de empezar:

- La Definición de Hecho de la Fase 3 está cumplida, incluidos los tests de concurrencia contra
  PostgreSQL 16 real: esta fase añade más bloqueos (repuestos, filas de orden, candados por empresa).
- Existen órdenes cerradas con datos reales, o la fase se construye con datos simulados declarados
  como tales (sección 11).
- La migración se ejecuta con un rol que ignore RLS. Con `FORCE ROW LEVEL SECURITY` el propietario ve
  cero filas de `ordenes_trabajo` y los rellenos insertarían cero filas sin error. Después, comprobar
  que `configuracion_empresa` tiene una fila por empresa y `reajustes_pendientes` una por componente
  con órdenes cerradas.
- `repuestos`, `orden_repuesto` y `activo_componentes` no existen todavía.
- El pooler sigue en modo sesión (Fase 1, 7.4): el job fija el tenant con `set_config` y toma un
  candado consultivo por transacción.
- Hay copia de seguridad reciente y el cron de Railway está disponible.
- Las decisiones de la sección 4 están confirmadas.

> **Adaptación:** la migración corre como `simap_owner`, que no ignora RLS. Los rellenos desactivan
> `FORCE` en las tablas que leen y lo restauran después (ver anexo).

## 4. Decisiones confirmadas

| # | Decisión | Propuesta (confirmada) | Por qué |
|---|---|---|---|
| 1 | Cuándo se descuenta el stock | Al **cerrar** la orden (RF-25), no al marcarla Reparada. | Si el cierre se rechaza, la orden vuelve a En taller y un descuento ya hecho obligaría a devolverlo. Corrige el paso 4 de CU-03. |
| 2 | Quién maneja el inventario | Administrador: altas, vida nominal, configuración y ajuste por conteo. Supervisor: ingresos y líneas. Técnico: líneas de su orden y existencias (no el libro). Gerente: solo lectura. | CU-06 dice «Administrador o Supervisor» sin separar acciones. El ajuste por conteo cambia el stock sin comprobante. |
| 3 | Cierre sin stock suficiente | 409 `stock_insuficiente` y el mensaje dice qué falta. | Un stock negativo falsea el libro y las alertas de reorden. |
| 4 | Horizonte del riesgo | En **horas de operación** (50 por defecto), no 30 días de calendario. | El modelo mide horas. La pantalla muestra un equivalente informativo en días. |
| 5 | Parámetros por empresa | Umbral 25 %, horizonte 50 h, 2 alertas en 15 días, multiplicador 1,30, silencio de 7 días tras descartar. Los ajusta el administrador. | RF-21 habla de un umbral «configurado por la empresa». |
| 6 | Modelo de partida (CU-04) | Vida nominal por componente, en lugar de un dataset público. | No hay un dataset público que sirva. Se conserva la etiqueta «estimado» (fuente = previo). Sin vida nominal ni 2 fallas, no hay modelo. |
| 7 | Edad de la pieza instalada | El administrador declara a cuántas horas del equipo se instaló la unidad actual. Si no se sabe, no hay riesgo hasta el primer reemplazo. | Inventar una edad produce riesgos falsos. |
| 8 | Reemplazo predictivo | Cuenta como **censura**: la vida termina sin falla. | Contarlo como falla o descartarlo sesga el modelo (sección 14). |
| 9 | Falla antes de la intervención | La orden predictiva abierta se convierte en falla real. | Ese dato es una falla y no puede quedar como censura. |
| 10 | Vista de la Fase 3 | `v_intervalos_entre_fallas` se elimina y la sustituye `v_vidas`. | La anterior no ve los componentes que siguen funcionando. |
| 11 | Cómo se ajusta (Esp. 5.3) | Máxima verosimilitud con censura y prior, no `weibull_min.fit` sobre intervalos. | Error de riesgo de 4 a 10 veces mayor en las simulaciones. Se contrasta con scipy en las pruebas. |
| 12 | Alerta de reorden | Cuando `stock_actual` es **estrictamente** menor que `stock_minimo`. | RF-26 dice «cae bajo el mínimo». |
| 13 | Aprendizaje al cerrar | Marca durable (`reajustes_pendientes`) escrita en la transacción del cierre. | La marca no se pierde si el proceso cae y dice exactamente qué reajustar. |

## 5. Cómo aprende el sistema

Base de los capítulos II y III de la tesis.

### 5.1 La unidad de dato: la vida de un componente

El modelo no mira equipos, sino componentes dentro de equipos. Una **vida** es el periodo entre que
se instala una unidad de un componente en un equipo y el momento en que se reemplaza. Dentro de una
vida puede haber fallas que se reparan o se ajustan: la unidad sigue siendo la misma (decisión 4 de
la Fase 3). La vida termina con un reemplazo, por falla o predictivo. Y existe siempre una **vida
abierta**: la unidad instalada hoy, observada hasta las horas actuales del equipo.

Esa vida abierta es el dato más importante y el que más se olvida: un componente que lleva 700 h sin
fallar dice que la vida característica no puede ser muy corta. Un método que solo mire intervalos
entre fallas ve únicamente los que fallaron y subestima la duración (censura por la derecha). La
vista `v_vidas` entrega una fila por vida con tres números —fallas, Σ ln(edades de falla) y horas
observadas—, los estadísticos suficientes del ajuste. La secuencia de la prueba:

| Vida | Inicio (h del equipo) | Fallas (edad en h) | Cómo termina | Horas observadas |
|---|---|---|---|---|
| 0 | 0 | 400 y 700 | Reemplazo por falla a las 700 h | 700 |
| 1 | 700 | 400 (ajuste a las 1100 h) | Reemplazo predictivo a las 1300 h, sin falla: censura | 600 |
| 2 | 1300 | ninguna | Abierta; el equipo marca 1500 h | 200 |

No cuentan: una orden cancelada, una pendiente de revisión del horómetro ni una intervención
predictiva que no reemplazó la pieza. Si no se sabe a qué hora se instaló la pieza, la primera vida
no tiene horas confiables y queda fuera del ajuste hasta el primer reemplazo.

### 5.2 El modelo: Weibull con reparación mínima

Un componente se desgasta según una intensidad de Weibull; una reparación o un ajuste lo dejan como
estaba (reparación mínima) y solo el reemplazo lo renueva. El número esperado de fallas hasta la
edad *a* es Λ(a) = (a/η)^β. η es la vida característica; β dice cómo se desgasta (β > 1 desgaste
progresivo; β = 1 tasa constante; β < 1 fallas tempranas). Con n fallas en las edades a₁…aₙ y vidas
observadas durante T₁…T_k:

    ln L = n·ln β − n·β·ln η + (β − 1)·Σ ln aⱼ − Σ (T_l / η)^β

Se trabaja con u = ln β y v = ln η y se maximiza con L-BFGS-B de scipy y el gradiente analítico
(≈ 1 ms por ajuste). `weibull_min.fit` no admite censura ni prior; se usa para verificar: sin
censura y sin prior, el resultado coincide.

### 5.3 Conocimiento previo y nivel de confianza

Con dos o tres fallas la máxima verosimilitud pura puede devolver cualquier cosa (β = 10). Por eso
el ajuste es de **máximo a posteriori**: creencia normal en (u, v) con β ≈ 2 (±0,5 en ln β) y η
centrada en la vida nominal (±0,7 en ln η). Sin vida nominal y con al menos dos fallas, creencia
débil (±1,5) centrada en horas observadas ÷ fallas. Sin vida nominal y con menos de dos fallas no hay
modelo («sin modelo»). Límites: β entre 0,3 y 10; edad mínima 0,5 h.

| Fallas del componente | Fuente | Confianza | Qué significa |
|---|---|---|---|
| 0 | previo | baja | Solo la vida nominal. Es el «estimado» de CU-04. |
| 1 a 7 | mixto | baja | Los datos de la empresa ya mueven el modelo, pero poco. |
| 8 a 19 | empresa | media | El modelo depende sobre todo de la historia de la empresa. |
| 20 o más | empresa | alta | «Alta» no es «exacta»: el error sigue siendo de varios puntos (sección 14). |

### 5.4 Del modelo al riesgo

    riesgo = 1 − exp( − m · [ ((a + h)/η)^β − (a/η)^β ] )

*m* es 1 por defecto y 1,30 (configurable) si el equipo tiene al menos dos alertas de campo
pendientes o revisadas en los últimos 15 días (RF-20). Se aplica al riesgo acumulado, no a la
probabilidad: nunca pasa de 1 y equivale a «30 % más de intensidad». Con el ejemplo de la
Especificación 5.3 (350 h, h = 50, β = 3,5, η = 430) el riesgo es **25,2 %** y con el multiplicador
**31,4 %** (comprobado en las pruebas). Esas cifras son ilustrativas: ajustar las fallas que cita la
Especificación (entre 380 y 420 h) daría β ≈ 30.

Límite del modelo: no existe un efecto propio de cada equipo (fragilidad). Un equipo con muchas
fallas reparadas muestra más riesgo porque su componente es viejo; uno que falla más que sus gemelos
por cómo se opera no sube hasta que lo reflejen sus alertas de campo. Trabajo futuro (14.7).

Las alertas del sistema viven en otra tabla: nunca cuentan como alertas de campo ni elevan el
multiplicador que las originó. No hay lazo de realimentación.

### 5.5 El ajuste, en código

`backend/app/services/prediccion/weibull.py`: `Datos.de_vidas`, `Prior.desde`, `_neg_logpost`
(menos el logaritmo de la posterior y su gradiente), `ajustar`, `riesgo`, `nivel` y
`ajustar_componente`. Es el código del PDF, con tipos.

## 6. Reglas de negocio

### 6.1 Componentes de un equipo y edad de la pieza

- `activo_componentes` dice qué componentes tiene cada equipo y a qué hora del equipo (horas
  acumuladas) se instaló la unidad actual. El administrador la declara con
  `PUT /activos/{id}/componentes/{cid}`: 0 si el equipo era nuevo, vacío si no se sabe. Una edad
  mayor que las horas acumuladas es 422.
- Al reportar una falla de un componente que el equipo aún no tiene registrado, se registra con edad
  desconocida; nunca pisa una edad declarada.
- Con edad desconocida el equipo muestra «sin edad» y no tiene riesgo. Al primer reemplazo la edad
  pasa a conocerse.
- El reinicio de horómetro no afecta: las horas acumuladas son continuas.
- La fila de `configuracion_empresa` de las empresas existentes la crea la migración; las nuevas, al
  primer uso.

Implementación: `app/services/prediccion/componentes_equipo.py` y `configuracion.py`.

### 6.2 Cuándo se reajusta el modelo

- En la transacción del cierre (y al cambiar la vida nominal o corregir una orden cerrada) se
  escribe una **marca** en `reajustes_pendientes`. Es durable (decisión 13).
- Después del commit, una tarea en segundo plano lee las vidas, ajusta, guarda y libera la marca.
  Cada marca lleva un contador de **generación**: si llega otro cierre mientras se ajusta, la
  generación sube y liberar no borra nada. Un cierre concurrente nunca se pierde.
- El job nocturno ajusta, además, todo componente con marca, sin modelo o con modelo de más de 7 días
  (la vida abierta suma horas cada día).
- Guardar reemplaza el modelo vigente (la versión sube) y agrega una fila a `modelos_historial` solo
  cuando cambia el número de fallas: la **curva de aprendizaje** del Capítulo IV.

Implementación: `app/services/prediccion/ajuste.py`.

### 6.3 Riesgo y alertas del sistema

- El recálculo, para cada vida abierta de la empresa (o de un equipo), clasifica el resultado (`ok`,
  `sin_edad`, `sin_modelo`), aplica el multiplicador y escribe el riesgo de forma idempotente. Tras
  cada lectura de horómetro se calcula solo ese equipo (RF-19).
- Una alerta de riesgo se crea cuando el riesgo alcanza el umbral. Si ya hay una vigente (activa,
  reconocida o atendida) para ese par, el índice único parcial lo impide: nunca hay dos.
- **Histéresis:** una alerta sin atender se cierra sola cuando el riesgo baja del 80 % del umbral.
- Descartar exige nota y **silencia** el par durante 7 días (configurable).
- Reconocer es «la vi». Quien llega tarde a algo ya gestionado recibe 409.

| Estado | Cómo se llega | Qué sigue |
|---|---|---|
| activa | La crea el cálculo al superar el umbral | Reconocer, descartar, crear la orden o resolverse sola |
| reconocida | Un supervisor la vio | Descartar, crear la orden o resolverse sola |
| atendida | Se creó la orden predictiva | Resuelta al cerrar la orden; vuelve a reconocida si se cancela. No se descarta |
| resuelta | El riesgo bajó de 0,8 × umbral, o se cerró la orden | Terminal. Admite una alerta nueva |
| descartada | Un supervisor la descartó con nota | Terminal. Silencia el par durante el plazo |

Implementación: `app/services/prediccion/riesgo.py` y `alertas.py`.

### 6.4 Orden predictiva

- Desde una alerta activa o reconocida, `POST /alertas-sistema/{id}/orden`, en una transacción: la
  alerta pasa a atendida con un UPDATE condicionado (cero filas = 409), se pide el número y se inserta
  la orden con `es_predictiva`. Equipo, componente y horas salen de la alerta y la ficha, nunca del
  cuerpo.
- Si el componente ya tiene una falla abierta: 409 `orden_abierta_existente` y la alerta queda como
  estaba.
- Sigue la máquina de estados de la Fase 3. Al cerrarla, la alerta pasa a resuelta; si se cancela,
  vuelve a reconocida.
- Para el modelo solo cuenta un **reemplazo** predictivo: cierra la vida sin falla (censura) y abre
  otra de cero horas. Una reparación o ajuste predictivo no aportan nada.
- Si el equipo falla antes, `POST /ordenes/{id}/convertir-en-falla` con horómetro y fecha reales: deja
  de ser predictiva y cuenta como falla. Solo con la orden abierta.

### 6.5 Inventario: libro, líneas y consumo

- El stock vive en `stock_actual` y en el libro `stock_movimientos` (solo se agrega: inicial,
  ingreso, consumo o ajuste, con delta, stock resultante y costo del momento). Deben coincidir. Los
  repuestos no se borran: se desactivan.
- El técnico agrega o corrige las líneas de su orden mientras está abierta; un repuesto una vez por
  orden. Un trigger rechaza cambios en órdenes cerradas o canceladas, salvo la corrección
  administrativa.
- El descuento ocurre al **cerrar**, en la misma transacción: se bloquean los repuestos en orden de id
  y un UPDATE condicionado descuenta cada línea solo si alcanza y la asienta. Bloquear siempre en el
  mismo orden evita interbloqueos.
- Si alguna línea no alcanza, se revierte todo el cierre (la orden sigue Reparada) y 409
  `stock_insuficiente` con la lista de faltantes.
- El índice único `mov_consumo_unico` impide descontar dos veces el mismo repuesto de una orden.

### 6.6 Reorden, ingresos y conteos

- Tras un consumo, ingreso o ajuste se revisan los repuestos tocados: stock < mínimo crea una alerta
  de reorden (una sola vigente por repuesto); al volver a ≥ mínimo se resuelve sola.
- El ingreso suma de forma atómica y se asienta.
- El ajuste por conteo lo hace el administrador con nota obligatoria; si coincide, no asienta nada.
- La **conciliación** compara cada `stock_actual` con la suma de su libro y debe devolver cero filas.

Implementación: `app/services/inventario.py`.

### 6.7 Secuencia del cierre de una orden

1. Validar rol (supervisor, administrador) y que la orden esté Reparada.
2. UPDATE condicionado Reparada → Cerrada (cero filas: 404 o 409).
3. Si tiene líneas: bloqueo y consumo. Si no alcanza: ROLLBACK de todo y 409 con los faltantes.
4. Si nació de una alerta del sistema: la alerta queda resuelta.
5. Marca durable de reajuste del componente.
6. Evento `cerrada` (usuario, rol, hora).
7. Reorden con los repuestos consumidos.
8. COMMIT.
9. Después, en segundo plano: ajustar el modelo, recalcular el equipo y crear o resolver alertas.
   Si falla, la marca sigue ahí y el job de las 02:00 lo repite.

## 7. Cambios al modelo de datos

Migración `0009` (el PDF la numera `0004`). Resumen de lo que crea:

- **7.1** `componentes.vida_nominal_horas` (10 a 1.000.000) y `configuracion_empresa` (umbral 0,05–0,95;
  horizonte 1–2000 h; alertas mínimas 1–20; ventana 1–90 días; multiplicador 1,00–2,00; silencio 1–90
  días), rellenada con una fila por empresa.
- **7.2** `repuestos` (código único por empresa, stock y mínimo ≥ 0, costo ≥ 0, `activo`),
  `stock_movimientos` (signo del delta según el tipo; un consumo siempre con orden y costo; un ajuste
  siempre con nota; índice único de consumo por orden y repuesto) y `orden_repuesto` (llave
  primaria empresa, orden, repuesto). Todas las referencias son compuestas `(empresa_id, x_id)`.
- **7.3** `activo_componentes` (`horas_instalacion_inicial` ≥ 0 o nulo), rellenada con los pares que
  ya tenían órdenes.
- **7.4** `alertas_sistema`: tipo riesgo o reorden con su forma por tipo (CHECK), estados de 6.3, nota
  obligatoria al descartar, índices únicos parciales de riesgo y reorden vigentes y el de la bandeja.
  Guarda el umbral y la confianza del día: dentro de un año debe poder explicarse.
- **7.5** `ordenes_trabajo.es_predictiva` y `alerta_sistema_id` (una orden vigente por alerta, las
  canceladas la liberan) e `idx_ot_cerradas_vida`, parcial, con el orden de la ventana de `v_vidas`.
  Se elimina `v_intervalos_entre_fallas`.
- **7.6** `modelos_componente` (β, η, fallas, vidas, exposición, fuente, confianza, convergió,
  versión), `modelos_historial` (solo se agrega), `reajustes_pendientes` (generación) y `riesgos`
  (derivado: se puede borrar y recalcular; CASCADE desde `activo_componentes`).
- **7.7** Vistas `v_vidas` y `v_riesgo_activo`, ambas `security_invoker`.
- **7.8** Trigger de las líneas de órdenes cerradas, con `FOR SHARE` sobre la orden.
- **7.9** RLS: las ocho tablas ordinarias con la política habitual; las dos de solo agregar
  (`stock_movimientos`, `modelos_historial`) con políticas separadas de SELECT e INSERT y sin UPDATE ni
  DELETE.
- **7.10** `job_user` (miembro de `app_user`, sujeto a RLS) y `empresas_activas()`, `SECURITY
  DEFINER` con `search_path` fijo, ejecutable solo por `job_user`. Permisos explícitos: sin DELETE en
  repuestos, alertas y configuración; sin UPDATE ni DELETE en el libro y el historial.

### 7.7 La vista `v_vidas`

`NOT MATERIALIZED` es parte del diseño: sin él, PostgreSQL calcula todas las órdenes de la empresa y
las recorre por cada componente (cuadrático). En la medición de 9.4 recalcular una empresa de 1.000
equipos pasó de 17 s a 0,27 s. La vista se verificó con casos a mano (5.1) y contra un simulador de
flotas independiente (45 vidas de 14 equipos, coincidencia exacta). El texto completo está en la
migración `0009`; su estructura:

1. `ev`: órdenes cerradas y confirmadas por (empresa, equipo, componente), con las horas acumuladas en
   la falla y el número de vida (reemplazos acumulados antes de cada orden, por ventana).
2. `vidas_cerradas`: por vida, fallas reales (las predictivas no cuentan como evento), Σ ln(edad) y
   horas observadas hasta el reemplazo.
3. Vida abierta de cada par de `activo_componentes`: desde el último reemplazo (o la instalación
   declarada) hasta las horas actuales del equipo. Sin edad conocida, exposición nula.
4. Columnas: `empresa_id`, `activo_id`, `componente_id`, `vida`, `abierta`, `n_eventos`,
   `suma_ln_edades`, `exposicion`.

`v_riesgo_activo`: por equipo, el componente de mayor riesgo con estado `ok` (`DISTINCT ON`).

## 8. API de la fase

Todas bajo `/api/v1`, con sesión y dentro de `get_db`. Cada acción tiene su ruta.

| Método y ruta | Roles | Notas |
|---|---|---|
| GET `/activos/{id}/riesgo` | Supervisor, técnico, gerente, administrador | Riesgo de cada componente con edad, β, η, fallas, fuente, confianza y `calculado_en` |
| GET `/riesgos` | Supervisor, gerente, administrador | Equipos por riesgo descendente. Cursor |
| GET, PUT `/activos/{id}/componentes[/{cid}]` | Lectura: supervisor, gerente, administrador. PUT: administrador | 6.1 |
| GET `/componentes/{id}/modelo` | Supervisor, gerente, administrador | Modelo e historial |
| PATCH `/componentes/{id}` | Administrador | Vida nominal; marca para reajustar |
| GET, PUT `/configuracion/prediccion` | Lectura: supervisor, gerente, administrador. PUT: administrador | Parámetros de la empresa |
| GET `/alertas-sistema` | Supervisor, gerente, administrador | Bandeja con filtros por tipo y estado |
| POST `/alertas-sistema/{id}/reconocer` | Supervisor, administrador | 6.3 |
| POST `/alertas-sistema/{id}/descartar` | Supervisor, administrador | Nota obligatoria |
| POST `/alertas-sistema/{id}/orden` | Supervisor, administrador | Crea la orden predictiva |
| POST `/ordenes/{id}/convertir-en-falla` | Supervisor, administrador | Horómetro y fecha reales |
| GET `/repuestos` | Supervisor, técnico, gerente, administrador | Filtro «bajo el mínimo» |
| POST `/repuestos` | Administrador | El stock inicial entra al libro |
| PATCH `/repuestos/{id}` | Administrador | Nunca el stock |
| POST `/repuestos/{id}/ingresos` | Supervisor, administrador | Cantidad positiva y nota opcional |
| POST `/repuestos/{id}/ajuste` | Administrador | Conteo físico con nota |
| GET `/repuestos/{id}/movimientos` | Supervisor, gerente, administrador | Libro. Cursor |
| GET `/ordenes/{id}/repuestos` | Los de la orden | Líneas |
| PUT, DELETE `/ordenes/{id}/repuestos/{rid}` | Técnico, supervisor, administrador | Solo órdenes abiertas |
| GET `/inventario/conciliacion` | Administrador | Debe devolver lista vacía |
| POST `/ordenes/{id}/cerrar` | Supervisor, administrador | Se amplía: descuenta y marca |
| POST `/activos/{id}/fallas` | Supervisor, administrador | Se amplía: registra el componente si falta |

El operario no tiene acceso a nada de esta fase (403). El técnico ve el riesgo del equipo y el
inventario, pero no la bandeja ni el modelo.

### 8.1 Errores uniformes

| Código | Estado | Cuándo |
|---|---|---|
| `stock_insuficiente` | 409 | El cierre no puede descontar alguna línea; el cuerpo lista los faltantes (código, nombre, disponible, requerido) y la orden sigue Reparada |
| `alerta_no_disponible` | 409 | La alerta ya la gestionó otra persona o no admite la acción |
| `orden_abierta_existente` | 409 | El componente ya tiene una orden abierta; incluye su número |
| `estado_cambiado` | 409 | La orden no es predictiva o ya no está abierta (convertir en falla) |
| `codigo_repuesto_duplicado` | 409 | Ya existe un repuesto con ese código |
| `edad_invalida` | 422 | La edad inicial supera las horas acumuladas |
| `referencia_invalida` | 422 | Una llave compuesta rechazó la referencia, sin decir si existe en otra empresa |

## 9. Cuándo y cómo se calcula

### 9.1 Tres disparadores

Cada lectura de horómetro recalcula ese equipo; cada cierre reajusta el modelo de su componente y
recalcula; el job de las 02:00 repasa todo. Los dos primeros, después del commit y en segundo plano;
el tercero, un proceso aparte. Cada uno basta para dejar el sistema correcto y cubre la falla de los
otros.

### 9.2 Tarea en segundo plano (RNF-02)

Después del commit, una `BackgroundTask` abre su sesión, fija el tenant y ejecuta el ajuste (tras un
cierre), el recálculo y las alertas. Si falla, la registra y termina: la lectura o el cierre ya están
guardados. La pantalla muestra siempre `calculado_en`. Si el proceso cae, la marca sigue y el job lo
recupera: solo se pierde latencia, nunca un dato.

### 9.3 Job nocturno (RF-21, RF-22)

Cron de Railway con el mismo contenedor (`python -m app.jobs.diario`) a las 06:00 UTC (02:00 en Santo
Domingo). Se conecta como `job_user`, pide las empresas con `empresas_activas()` y, por cada una, abre
su transacción, fija el tenant, toma `pg_try_advisory_xact_lock` (si no lo obtiene, la salta), fija
`statement_timeout` y ejecuta: asegurar configuración, reajustar lo pendiente, recalcular, crear y
resolver alertas. Un fallo en una empresa no detiene a las demás; si alguna falló, termina con código
distinto de cero. Los logs llevan identificadores, duraciones y contadores, nunca notas.

### 9.4 Rendimiento medido (RNF-04)

Cinco componentes por equipo y tres fallas cerradas por par, como `app_user` con RLS (PGlite):

| Equipos | Pares | Órdenes | Un equipo | Toda la empresa | Datos de un componente |
|---|---|---|---|---|---|
| 200 | 1.000 | 3.000 | 5,8 ms | 0,08 s | 14 ms |
| 1.000 | 5.000 | 15.000 | 7,5 ms | 0,27 s | 43 ms |
| 4.000 | 20.000 | 60.000 | 13,7 ms | 1,08 s | 163 ms |
| 1.000, versión inicial | 5.000 | 15.000 | 62 a 78 ms | 17,1 a 17,6 s | 3,5 s |

La última fila es la vista sin `NOT MATERIALIZED`: pasaba todas las pruebas funcionales y habría sido
cuadrática. La corrigió una medición. El test `rnf04` la repite en PostgreSQL real (en este
repositorio: **123 ms** con 60.000 órdenes).

## 10. Aplicación web

### 10.1 Pantallas

| Ruta | Roles | Contenido |
|---|---|---|
| `/riesgo` | Supervisor, gerente, administrador | Equipos por riesgo con componente crítico, edad, confianza y hora del cálculo |
| `/a/[codigo]` | Todos | Tarjeta de riesgo del equipo (no para el operario) |
| `/alertas-sistema` | Supervisor, gerente, administrador | Bandeja con pestañas Riesgo y Reorden y las acciones de 6.3 |
| `/componentes/[id]/modelo` | Supervisor, gerente, administrador | β, η, fallas, fuente, confianza, curva de riesgo y de aprendizaje |
| `/activos/[id]/componentes` | Administrador | Componentes del equipo y su edad; resalta los pares sin edad |
| `/configuracion/prediccion` | Administrador | Parámetros con valores y límites |
| `/inventario` | Supervisor, técnico, gerente, administrador | Stock, mínimo y marca «bajo el mínimo» |
| `/inventario/[id]` | Los mismos | Libro y, para el administrador, el ajuste por conteo |
| `/ordenes/[id]` | Los de la orden | Panel de repuestos y aviso de faltantes ante el 409 |

### 10.2 Mostrar el riesgo sin engañar

- Cada porcentaje va con su respaldo («12 fallas registradas, confianza media»); con confianza baja
  se escribe «estimado».
- El color nunca es el único portador: el nivel se escribe (bajo, vigilar, alto) y la escala parte
  del umbral de la empresa.
- Cada riesgo se explica en una línea: «Esta pieza lleva 350 h; a esa edad el modelo estima 25 % de
  falla en las próximas 50 h (12 fallas registradas)», y «+30 % por 2 alertas de campo en 15 días».
- «Sin edad» y «sin modelo» no son un cero: son un aviso con su acción.
- El horizonte se muestra en horas, con un equivalente informativo en días.
- Sin conexión, el riesgo solo como último valor conocido con su hora; las acciones exigen conexión.

### 10.3 Repuestos en la orden y en el almacén

- En la orden En taller el técnico busca el repuesto y fija la cantidad; el stock se muestra como
  orientación y decide el servidor al cerrar.
- El resumen de autorización suma los repuestos y su costo. Ante `stock_insuficiente`, la pantalla
  dice qué falta, quién corrige la línea y quién registra el ingreso.
- Los ajustes por conteo piden confirmación y nota; el libro muestra el stock resultante en cada fila.

## 11. Datos de demostración

`tools/seed_demo.py` crea la empresa «Demo» con una flota simulada (β = 2,5; η = 1000 h): equipos con
piezas de edades distintas, fallas con reparación y con reemplazo, una orden predictiva cerrada, unos
15 repuestos (algunos bajo el mínimo) y alertas de campo recientes. Incluye los dos casos de la
Definición de Hecho: un equipo con tres reparaciones sin reemplazo (componente viejo, riesgo alto) y
otro con la pieza recién cambiada (riesgo bajo). Con 14 equipos y 50 fallas, el PDF obtuvo β = 3,10 y
η = 1085 h: con 50 fallas es normal (el 80 % central de β va de 2,05 a 3,07) y es un buen ejemplo de
por qué «confianza alta» no es «exacta». Los datos son simulados y la tesis debe declararlo.

## 12. Seguridad

### 12.1 Quién puede qué

| Acción | Operario | Supervisor | Técnico | Gerente | Administrador |
|---|---|---|---|---|---|
| Ver riesgo de un equipo | No | Sí | Sí | Sí | Sí |
| Ver bandeja de alertas del sistema | No | Sí | No | Sí | Sí |
| Reconocer o descartar una alerta | No | Sí | No | No | Sí |
| Crear orden predictiva | No | Sí | No | No | Sí |
| Convertir una orden en falla | No | Sí | No | No | Sí |
| Ver el modelo de un componente | No | Sí | No | Sí | Sí |
| Declarar componentes, edad y vida nominal | No | No | No | No | Sí |
| Cambiar la configuración de predicción | No | No | No | No | Sí |
| Ver inventario y movimientos | No | Sí | Sí (sin libro) | Sí | Sí |
| Crear o editar repuestos | No | No | No | No | Sí |
| Registrar un ingreso | No | Sí | No | No | Sí |
| Ajuste por conteo | No | No | No | No | Sí |
| Líneas de repuestos de una orden abierta | No | Sí | Sí | No | Sí |

Vive como un test que recorre todas las combinaciones (`test_roles_matriz_12_1_todas_las_combinaciones`).

### 12.2 Entradas no confiables y datos envenenados

- `empresa_id`, el usuario, los estados, los tiempos y los stocks los fija el servidor. El stock no
  se envía en ningún cuerpo. Los esquemas rechazan campos desconocidos.
- La orden predictiva toma equipo y componente de la alerta. Cantidades entre 1 y 10.000.
- Manipular el riesgo con alertas de campo falsas: el multiplicador está acotado (1,00–2,00), las
  alertas son visibles y descartables, y hay límites de peticiones.
- Envenenar el modelo con fallas falsas solo sesga el de la propia empresa; la defensa es la
  trazabilidad.
- Los cálculos son matemática pura; todas las consultas son parametrizadas.

### 12.3 Defensa en profundidad

| Amenaza | Defensa | Cómo se comprueba |
|---|---|---|
| Datos de una empresa visibles a otra | RLS habilitada y forzada en las 10 tablas; `security_invoker` en las vistas | B ve cero filas; guardias de CI |
| Referencias cruzadas entre empresas | Llaves compuestas con RLS | 23503 en cada caso |
| El job lee o escribe otra empresa | `job_user` sujeto a RLS, tenant por empresa | Sin tenant ve cero filas |
| Un usuario lista las empresas | `empresas_activas()` solo para `job_user` | 42501 para `app_user` |
| Dos alertas u órdenes para lo mismo | Índices únicos parciales | 23505; repetir no duplica |
| Una alerta descartada reaparece cada noche | Silencio configurable | Prueba con el plazo vencido |
| Stock negativo o doble descuento | CHECK ≥ 0, UPDATE condicionado, `mov_consumo_unico` | Concurrencia real en CI |
| Alterar el libro o el historial | REVOKE de UPDATE y DELETE | 42501 |
| Cambiar líneas de una orden cerrada | Trigger con `FOR SHARE` | 23514 |
| Perder un cierre mientras se reajusta | Generación de la marca | Liberar con generación vieja no borra |
| Una falla del cálculo tumba el reporte | Cálculo después del commit | Test `rnf02` |
| Vista de vidas que se degrada | `NOT MATERIALIZED` e `idx_ot_cerradas_vida` | Test `rnf04` |

### 12.4 Auditoría y registros

El libro es la auditoría del inventario; `orden_eventos`, la de la orden; `modelos_historial`, qué
modelo estaba vigente. Límite: `alertas_sistema` guarda solo la última gestión. Los logs no llevan
notas. Las notas del libro y de las alertas no deben contener datos personales (no se borran).
Límites por usuario: 30 cambios de líneas y 20 ingresos por minuto.

## 13. Escalabilidad

- **Cálculo por conjuntos:** el riesgo de una empresa en una pasada y el de un equipo con un filtro
  que baja al índice; el ajuste trabaja con tres números por vida. Todos los índices llevan
  `empresa_id` primero.
- **Más empresas:** una empresa mediana tarda del orden de un segundo; cien, minutos. El candado por
  empresa permite varios procesos del job sin coordinación.
- **Crecimiento:** con 200 equipos y 1.200 órdenes al año, `riesgos` no crece (una fila por par) y el
  libro suma unas 2.400 filas al año. No se particiona.
- **Contención:** los repuestos de mayor rotación son filas calientes bloqueadas milisegundos, en orden
  de id.
- **Observabilidad:** duración del job, componentes reajustados, modelos sin convergencia, antigüedad
  del cálculo más viejo, alertas por día, proporción de órdenes predictivas, 409 de stock, filas de
  conciliación y tareas fallidas. Una alerta de plataforma si el job no corrió.

## 14. Validación del método con simulaciones

**Diseño:** flotas de equipos nuevos con piezas Weibull (β de 1,5, 2,5 o 3,5; η = 1000 h) observadas
1000 h; cada falla termina en reemplazo o reparación con probabilidad ½; de 2 a 30 equipos. El error
es la diferencia absoluta media entre el riesgo estimado y el verdadero (horizonte 120 h) a 0,4, 0,7
y 1,0 η, en puntos ÷ 100. Semillas fijas.

Resultados del PDF (los reproducidos en este repositorio, en `docs/contexto/anexos/experimentos-fase4.md`):

- **Experimento 1 (cómo se estima):** scipy sobre intervalos tiene un error mediano de 20 a 33 puntos,
  de 4 a 7 veces el del MAP de SIMAP (0,058 → 0,028 según las fallas). La censura es lo que más
  mejora; el prior ayuda sobre todo con pocas fallas. Con la vida nominal equivocada por un factor 2,
  el error casi no cambia: el previo cede ante los datos.
- **Experimento 2 (ventana de observación):** con una ventana de 1 η, el método sobre intervalos
  subestima η en un 30 %; con 4 η el sesgo se atenúa. Una empresa nueva está justo en la ventana
  corta.
- **Experimento 3 (reemplazo predictivo, decisión 8):** lazo cerrado de 10 equipos durante 6000 h con
  umbral 25 %. Contarlo como falla estima η en el 1,5–1,9 % de la real (de 53 a más de 3.100
  reemplazos: una espiral); descartarlo, en el 45–56 %; tratarlo como censura, en el 99 % y 98 %.
- **Experimento 4 (umbral):** con el 25 % por defecto las fallas bajan un 54 % (β = 2,5) y un 69 %
  (β = 3,5), a cambio de cerca de un reemplazo predictivo por falla evitada. Que convenga depende del
  costo de cada empresa: es el argumento para que el umbral sea configurable.
- **Calibración:** alrededor del umbral (20–30 %) el estimado es 0,245 y el verdadero 0,257. En los
  valores más altos hay optimismo del extremo (0,62 frente a 0,45). Por confianza, error mediano de
  4,4, 3,3 y 2,7 puntos (baja, media, alta).

**Límites (14.7):** los datos se generan con la misma familia que se ajusta; se supone cumplimiento
perfecto; las flotas son homogéneas (sin fragilidad por equipo); no hay validación con datos reales
(el paso siguiente es la validación retrospectiva con las órdenes reales).

## 15. Pruebas de la fase

El PDF verificó el SQL en PGlite (137 comprobaciones de SQL, 14 del modelo, 18 defensas rotas a
propósito y detectadas), sin concurrencia ni servicio en Python. La tabla de 15.2 es la matriz de
trazabilidad requerimiento-prueba; en este repositorio las 35 existen con su nombre (la del doble
descuento como `test_rf25_doble_descuento_imposible_y_stock_nunca_negativo`) en
`backend/tests/test_weibull.py`, `test_prediccion.py`, `test_prediccion_base.py`,
`test_inventario.py` y `test_concurrencia_fase4.py`, más las dos e2e de `frontend/e2e/fase4.spec.ts`:

- `test_rf21_alerta_a_orden_predictiva_a_cierre_con_repuesto` (tres contextos de Playwright);
- `test_rf25_cierre_con_stock_insuficiente_muestra_el_faltante` (el mensaje nombra el repuesto);
- además, `test_10_2_riesgo_sin_conexion_como_ultimo_valor_conocido`.

## 16. Orden de implementación (semanas 9 a 12)

9: migración, modelo, componentes y edad, tarea tras el cierre. 10: alertas, orden predictiva, job y
pantallas de riesgo. 11: inventario completo y concurrencia. 12: demostración, experimentos, RNF-04,
e2e y documentación.

Si el tiempo aprieta se recorta, en orden: la pantalla del modelo, la del ajuste por conteo, la
conversión en falla desde la interfaz y el detalle de la bandeja de reorden. **Nunca** se recortan la
censura, el aislamiento, el libro con el descuento atómico, la deduplicación e histéresis, el cálculo
después del commit ni los experimentos.

## 17. Definición de «hecho» para la Fase 4

- Al cerrar una orden con datos reales, el modelo se reajusta (nueva versión y fila de historial) sin
  intervención y sin que el cierre espere.
- Un equipo con un componente viejo por reparaciones sin reemplazo muestra un riesgo visiblemente
  más alto que otro con la pieza recién cambiada, y la pantalla lo explica con su respaldo.
- Con dos alertas de campo en 15 días el riesgo sube con el multiplicador; con una, no.
- Al superar el umbral aparece **una** alerta aunque el cálculo corra varias veces o a la vez; se
  cierra sola con la histéresis; un descarte con nota la silencia.
- Desde la alerta se crea una orden predictiva; al cerrarla con reemplazo el riesgo vuelve a casi
  cero y la alerta queda resuelta. Si el equipo falla antes, se convierte en falla.
- Cerrar con repuestos descuenta y asienta; si no alcanza, 409 con lo que falta; el libro concilia.
- Un repuesto bajo el mínimo genera una alerta de reorden que se resuelve con el ingreso.
- Un fallo del cálculo no impide registrar una lectura ni reportar una falla; el job recupera lo
  pendiente.
- El cálculo de un equipo tarda menos de 2 s con 60.000 órdenes (test `rnf04`).
- Los tests de concurrencia, RLS, llaves compuestas y vistas pasan contra PostgreSQL 16.
- Los experimentos de la sección 14 están reproducidos y la tesis declara que son simulados.
- El manual describe el flujo por rol y la documentación técnica refleja la migración y las
  decisiones.

## 18. Material para el manual y la tesis

- **Manual:** supervisor (entender un riesgo, reconocer o descartar, crear una orden predictiva,
  ingresos); técnico (repuestos de la orden); administrador (componentes y edad, vida nominal,
  configuración, repuestos y conteos). Qué significan «sin edad», «sin modelo» y «confianza baja».
- **Capítulo II:** Weibull, procesos de Poisson no homogéneos y reparación mínima (Crow-AMSAA), datos
  censurados, MV y MAP, calibración, inventario y punto de reorden.
- **Capítulo III:** validación Monte Carlo con semillas fijas, comparación de estimadores,
  sensibilidad al prior y pruebas de mutación; los supuestos del modelo.
- **Capítulo IV:** figuras y tablas de 14, curva de aprendizaje, medición de 9.4, tabla de 12.3 y
  matriz de 15.2. Declarar que los datos son simulados.
- **Fuentes:** Rausand y Høyland, *System Reliability Theory*; Meeker y Escobar, *Statistical Methods
  for Reliability Data*; Ascher y Feingold, *Repairable Systems Reliability*; trabajos de L. H. Crow.
  Ley 172-13 si la tesis menciona datos personales en el libro y las alertas.
- **Documentos a actualizar:** CU-03 (descuento al cerrar), CU-04 (horizonte en horas, vida nominal,
  «estimado»), CU-06 (roles por acción), Especificación 5.3 (ajuste con censura; el ejemplo es
  ilustrativo) y su diccionario de datos, y el documento de requerimientos (RNF-02 y RNF-04 se
  diseñan aquí). Hecho en este repositorio con la marca *[Actualizado en F4]*.

## 19. Siguiente paso

La Fase 5 (Dashboard y Cierre) se apoya en `v_riesgo_activo`, las alertas y el libro (con el costo
del momento). Al calcular MTBF y disponibilidad, las órdenes predictivas se separan de las fallas: una
parada planificada no es una falla. La Fase 5 verifica RNF-02 y RNF-04, repite la auditoría de
aislamiento y cierra el checklist OWASP. Antes conviene correr la validación retrospectiva con las
órdenes reales que existan.

---

## Anexo: cómo quedó implementada en este repositorio (2026-10-22)

### Desviaciones respecto del PDF

| Tema | PDF | Aquí | Por qué |
|---|---|---|---|
| Número de migración | `0004` | `0009` (`20261018_0009_prediccion_e_inventario.py`) | Las fases anteriores ya usaron 0001–0008 |
| SQL de servicios | `INSERT ... ON CONFLICT` en cada sentencia | ORM de SQLAlchemy: `UPDATE` y, si no hay fila, `INSERT` dentro de un *savepoint* que absorbe la carrera | Portabilidad de motor (decisión de implementación «como en F3»). Las garantías siguen en la base: los índices únicos parciales deciden |
| Recálculo del riesgo | Una sentencia SQL con `power()`/`exp()` | Se leen las vidas abiertas con el ORM y la fórmula se evalúa en Python (`weibull.riesgo`) | Misma razón; un solo lugar para la fórmula. RNF-04 medido: 123 ms con 60.000 órdenes |
| `riesgos` | Sin conteo de fallas | Columna extra `n_eventos` | La pantalla explica cada número con su respaldo sin otro JOIN |
| Rol de la migración | Superusuario o `BYPASSRLS` | `simap_owner` (sin BYPASSRLS); los rellenos ponen `NO FORCE` temporal en `empresas`, `ordenes_trabajo` y `componentes` | Mismo patrón que la 0008 |
| `empresas_activas()` | SECURITY DEFINER sobre `empresas` | Igual, más la política `empresas_lista_para_el_job` para `simap_owner` | `empresas` tiene `FORCE RLS`: el dueño veía cero filas (el PDF lo advierte en 7.10) |
| `job_user` | Lo crea la migración | Lo crea `backend/db/roles.sql` (superusuario); la migración solo concede `EXECUTE` si existe | `simap_owner` no puede crear roles |
| Job nocturno | Cron de Railway | `python -m app.jobs.diario` (el comando del cron) y, en local, APScheduler dentro del backend (`app.jobs.programador`, `JOB_DIARIO_EN_PROCESO=true`) | Decisión de implementación; el despliegue no se hace todavía |
| Trigger de datos de falla | El de la Fase 3 (`ot_horas_solo_al_confirmar`) | Se reemplaza por `ot_datos_de_falla`: las horas solo cambian al confirmar el horómetro o al convertir en falla; horómetro y fecha, solo al convertir | La conversión en falla (6.4) necesita cambiar esos datos y nada más debe poder |
| Edad en `/activos/[id]/componentes` | «Unidad actual» | El campo es la **pieza inicial**; la edad mostrada es la del último cálculo (cuenta los reemplazos de las órdenes) | Encontrado en la revisión visual: mostrar «horas − instalación» ignoraba los reemplazos |

### Dónde está cada cosa

- Migración: `backend/alembic/versions/20261018_0009_prediccion_e_inventario.py`. Rol del job:
  `backend/db/roles.sql`.
- Modelos: `app/models/prediccion.py` y `app/models/repuesto.py`.
- Servicios: `app/services/prediccion/` (`weibull`, `configuracion`, `componentes_equipo`, `ajuste`,
  `riesgo`, `alertas`, `tareas`) y `app/services/inventario.py`.
- Rutas: `app/api/v1/routes/prediccion.py` y `repuestos.py`; amplían `ordenes.py`, `lecturas.py`,
  `campo.py`, `componentes.py`, `activos.py` y `alertas.py` con el recálculo en segundo plano.
- Job: `app/jobs/recalculo_riesgo.py`, `diario.py` y `programador.py`.
- Frontend: pantallas de 10.1, `src/components/riesgo.tsx`, `repuestos-orden.tsx` y `segmento.tsx`. El
  último riesgo de cada equipo se guarda en IndexedDB junto a su ficha (`src/lib/offline-queue.ts`) y
  sin red se muestra como «Último cálculo conocido», con la hora de cada cálculo (10.2).
- Herramientas: `tools/seed_demo.py` (sección 11), `tools/seed_sectores.py --solo-fase4`,
  `tools/experimentos_fase4.py` (sección 14) y `tools/limpiar_datos_de_prueba.py` (conoce las tablas
  y nombres de prueba de la fase).

### Lo que se midió aquí

- Batería del backend contra PostgreSQL 16 real, incluidas las cinco pruebas de concurrencia.
- RNF-04: 123 ms para el cálculo de un equipo en una empresa de 60.000 órdenes.
- Datos de demostración: con 14 equipos y 51 fallas, el ajuste dio β = 2,44 y η = 1104 h frente a
  2,5 y 1000 h; el caso A (pieza vieja, dos alertas de campo) queda con el riesgo más alto y alerta, y
  el caso B (pieza nueva), con el más bajo.
- Experimentos de la sección 14: `docs/contexto/anexos/experimentos-fase4.md` (versión completa,
  semilla 2026). Reproducen las conclusiones del PDF.
