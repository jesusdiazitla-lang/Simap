# Fase 5: Dashboard y Cierre — Guía Detallada de Implementación

> Transcripción de `Fase5_Dashboard_y_Cierre_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado). Fuente
> de verdad del **alcance y los criterios de aceptación** de la fase F5 en `docs/PLAN.yaml`. Donde este
> documento contradice a los anteriores, manda este.
>
> El PDF copia íntegro el SQL de la migración y de las sentencias. Aquí no se repite: la migración vive
> en `backend/alembic/versions/20261028_0011_paneles.py` y el cálculo en `backend/app/services/paneles/`.
>
> **Las catorce decisiones de la sección 4 las confirmó el usuario el 2026-10-28**, tal como las propone
> el documento, junto con dos decisiones de implementación: portabilidad «como en F3/F4» (consultas con
> el ORM y cálculo en Python) y web con páginas de cliente más CSP con nonce. Lo que cambió al
> implementarla está en el **anexo**.

## 1. Objetivo de la fase

Hacer visible todo lo construido y dejar el sistema listo para entregarse. Cada rol ve al abrir la
aplicación lo que necesita: el operario, sus reportes recientes y en qué quedaron; el técnico, su cola
de trabajo; el supervisor, las alertas por revisar y las órdenes abiertas; el gerente, la
disponibilidad, el MTBF, el MTTR, el costo de los repuestos y los equipos de mayor riesgo; y el
administrador, además, si el cálculo de riesgo está al día y qué datos le faltan.

La segunda mitad es el cierre: una auditoría automática de que ninguna empresa puede leer ni escribir
datos de otra, una batería de pruebas que corre en cada cambio, la revisión contra el OWASP Top 10, la
documentación técnica y el manual, y la preparación de la demostración y de los capítulos de
resultados de la tesis.

Un número puede parecer correcto sin serlo: una disponibilidad de 99,7 % se ve igual de bien calculada
que mal calculada. Por eso cada indicador se verifica por dos caminos independientes, se somete a
mutaciones deliberadas y se mide en PostgreSQL real.

## 2. Alcance

Construye RF-27 (panel por rol) y RF-28 (disponibilidad, MTBF y costos). Verifica RNF-01, RNF-02 y
RNF-04. El resto de los RNF se cierra en la matriz de trazabilidad
(`anexos/matriz-trazabilidad.md`).

Incluye: cinco paneles armados con widgets independientes; indicadores del gerente (disponibilidad con
y sin paradas planificadas, utilización, MTBF con intervalo de confianza, MTTR, costos separados entre
falla y planificado, repuestos que más costaron, equipos de mayor riesgo y su cobertura); la migración
(«0005» en el PDF); tres endpoints de lectura; la corrección del cierre de órdenes predictivas; la web
con gráficos accesibles y CSP con nonce; la auditoría de aislamiento en tres capas; pruebas, CI,
checklist OWASP Top 10:2025 y fronteras de módulos; documentación, manual y datos de demostración.

No incluye: exportar a PDF o Excel, paneles configurables, comparación entre plantas o periodos,
pronóstico de disponibilidad, notificaciones; calendarios de turnos (la disponibilidad es sobre 24 h,
decisión 2); la planta como frontera de seguridad (decisión 1); inicio de sesión (fase 1, ver 15.2);
caché de paneles; pruebas de carga con miles de usuarios.

## 3. Puerta de entrada

- La Definición de Hecho de la fase 4 está cumplida, incluidos sus tests de concurrencia.
- Existen datos de uso. Una semilla sintética sirve para probar y demostrar, pero el criterio de
  aceptación pide datos reales; si no los hay, la tesis declara que el panel se evaluó con simulados.
- La migración corre con un rol que puede rellenar todas las empresas. Después:
  `SELECT count(*) FROM lecturas_horometro WHERE <válida> AND horas_acumuladas IS NULL` da 0 y ningún
  equipo tiene `creado_en` posterior a su primera lectura.
- Quien aplica la migración puede hacer `ALTER ROLE app_user SET jit = off` (o se apaga por base o en el
  panel del proveedor); conectado como `app_user`, `SHOW jit` responde `off`.
- Hay copia de seguridad reciente y probada; las versiones de la web están fijadas con el lockfile.

> **Comprobado el 2026-10-28** en la base local: 0 lecturas válidas sin horas, 0 equipos observados
> después de su primer dato, `jit=off` en `app_user` y `job_user`, ningún permiso de escritura sobre
> las vistas.

## 4. Decisiones confirmadas

| # | Decisión | Propuesta (confirmada) | Por qué |
|---|---|---|---|
| 1 | Qué es una «planta» | La ubicación (texto) del equipo. El filtro ordena la vista; no restringe lo que un usuario puede ver. | No hay tabla de plantas ni usuarios asignados. La pantalla lo dice para que nadie lo tome por control de acceso. |
| 2 | Horas de la disponibilidad | 24 h de calendario, desde que se observa el equipo hasta hoy o su baja. | No hay calendario de turnos. Se muestra también la utilización. |
| 3 | Cuándo empieza una parada | Una falla, en su fecha de falla. Una predictiva, cuando entra al taller. Las canceladas no cuentan. Hasta el cierre; si sigue abierta, hasta ahora. | Una predictiva puede esperar días su ventana con el equipo produciendo. |
| 4 | Paradas solapadas | El equipo estuvo parado una vez; el solape falla-planificada se atribuye a la falla. | Sumar daría más horas de parada que de calendario. |
| 5 | MTBF | Horas operadas (horómetro) ÷ fallas no planificadas. Sin fallas, una cota inferior. Siempre con IC 90 %. | El calendario sobreestimaría el MTBF; el intervalo evita leer como exacto un número de 3 fallas. |
| 6 | MTTR | Duración media (falla → cierre) de las fallas cerradas del periodo. | Las abiertas no tienen duración final. |
| 7 | Costos | Del libro, al precio del momento, separando fallas de trabajo planificado. | Un cambio de precio no reescribe el pasado. |
| 8 | Desde cuándo se observa | `activos.creado_en`; para los existentes, su primer dato. El administrador puede adelantarla. | Sin esto un equipo nuevo tendría 100 % de disponibilidad por construcción. |
| 9 | Horas por lectura | Columna `horas_acumuladas` mantenida por un trigger; nula si la lectura es dudosa. | Horas operadas de cualquier periodo con dos búsquedas por equipo. |
| 10 | Corrección a la fase 3 | El tiempo fuera de servicio de una predictiva se mide desde que entra al taller. | Incongruencia con la decisión 3. |
| 11 | Zona horaria | Meses y días se cortan en America/Santo_Domingo. | Un servidor en UTC movería a diciembre la noche del 31 de enero. |
| 12 | Paneles de técnico y administrador | Se incluyen. | Completan «ningún rol sin panel». |
| 13 | JIT de PostgreSQL | Apagado para `app_user` y `job_user`. | Agrega ~1,3 s por petición de indicadores sin ganancia. |
| 14 | Vistas sin escritura | `app_user` pierde INSERT, UPDATE y DELETE sobre las vistas. | El `ALTER DEFAULT PRIVILEGES` de la fase 1 se los daba. |

## 5. Cómo se calcula cada indicador

### 5.1 Qué es una parada

Una falla para al equipo desde que ocurre; una intervención predictiva, desde que entra al taller. Si
dos órdenes del mismo equipo coinciden, el equipo estuvo parado una vez, y el solape entre una falla y
una planificada se atribuye a la falla. Ejemplo de la Figura 1 (mes de 30 días): fallas de los días 4
a 6,5 y 20 a 23,5; predictiva que espera del 9 al 12 (no es parada) y para del 12 al 14; otra que
entra el 22 y sale el 25,5. Parada total 10 días: 6 por falla y 4 planificados.

### 5.2 Disponibilidad y utilización

    Disponibilidad = 1 − Σ horas de parada / Σ horas de calendario observadas
    Utilización    = Σ horas operadas / Σ horas de calendario observadas

Las horas de calendario de un equipo van desde su `creado_en` (o el inicio del periodo) hasta el fin
del periodo, su baja o ahora, lo que ocurra primero. **Nunca se cuentan horas futuras.** Se muestran la
disponibilidad completa, la que no cuenta las paradas planificadas y la utilización.

### 5.3 MTBF y su intervalo de confianza

    MTBF = Σ horas operadas por la flota / número de fallas no planificadas

Horas del horómetro: las acumuladas en la última lectura válida **antes** de cada límite de mes (o, si
no había, las de la primera lectura). Las lecturas dudosas no aportan horas. Con T horas y n fallas, el
intervalo bilateral 1 − α (α = 0,10) es `[2T / χ²(1−α/2; 2n+2), 2T / χ²(α/2; 2n)]`. Ejemplo: 19 fallas
en 72 960 h dan 3 840 h, IC de 2 617 a 5 864 h. Sin fallas no hay cota superior: con 1 000 h, «al menos
334 h» (95 % unilateral).

Advertencia para la tesis: el modelo de la fase 4 supone desgaste (β > 1) y este intervalo supone tasa
constante. Para una flota es razonable como orden de magnitud; no para un solo equipo ni para fallas
agrupadas, donde el intervalo real es más ancho. La pantalla lo rotula «IC 90 %» y dice el supuesto.

### 5.4 MTTR y costos

    MTTR = Σ duración de las fallas cerradas del periodo / número de fallas cerradas

La duración va de la fecha de falla a la salida del taller. Una falla pertenece al mes de su falla;
una orden cerrada, al mes de su salida. Las canceladas no cuentan; las de horómetro dudoso sí (la
falla ocurrió) y se informan aparte. El costo suma unidades × costo del libro por mes del consumo,
separado entre fallas y predictivas; el porcentaje planificado se lee con las reservas de 12.5.

### 5.5 Se suman horas, no se promedian porcentajes

Por mes solo se calculan cantidades sumables; las razones se arman sobre los totales del periodo.
Promediar disponibilidades mensuales pondría igual un mes con un equipo que uno con cien. Lo fija la
prueba `test_la_razon_se_arma_sobre_totales_no_como_promedio_de_razones_mensuales`.

### 5.6 Lo que los indicadores no dicen

No miden calidad del mantenimiento (pocas fallas pueden ser pocos datos: por eso la cobertura del
riesgo va junto a la lista); el riesgo es una probabilidad del modelo con su confianza; alta
disponibilidad con baja utilización puede ser un equipo poco usado; con menos de dos o tres fallas el
MTBF y el MTTR son anécdotas, y la pantalla siempre dice cuántas los respaldan.

## 6. Cambios al modelo de datos

Migración `0011` (el PDF la llama `0005`):

- **6.1** `activos.creado_en` (ya existía desde la fase 2; se rellena con el primer dato conocido) y
  `lecturas_horometro.horas_acumuladas` con su trigger `lectura_horas_acumuladas` y el relleno. Una
  lectura dudosa queda sin horas; al confirmarla, el trigger la incorpora. El trigger no consulta
  ninguna tabla del cálculo de riesgo (RNF-02).
- **6.2** Seis índices (última lectura válida por equipo, órdenes cerradas por salida, fallas reales
  por fecha, consumos por fecha, lecturas y alertas por usuario), la vista `v_paradas`
  (`security_invoker`), el `REVOKE` de escritura sobre `v_paradas`, `v_vidas` y `v_riesgo_activo`, y el
  JIT apagado para `app_user` y `job_user`.

## 7. Consultas de indicadores y paneles

Ninguna consulta filtra por empresa: la impone RLS con el tenant de la transacción. Los indicadores
parten de un «cubo» por mes del periodo con su inicio y fin efectivos (el mes en curso, hasta ahora) y
devuelven una fila por mes aunque no haya datos.

- **Paradas y horas de calendario:** horas observadas de cada equipo recortadas al cubo; cada parada
  recortada al cubo y a la vida observada del equipo; unión de intervalos para el total y para las
  fallas; la diferencia son las planificadas.
- **Fallas y duración:** fallas reales por fecha de falla, cuántas en revisión, fallas cerradas y su
  duración por fecha de salida, predictivas cerradas.
- **Horas operadas:** horas acumuladas al inicio y al fin de cada mes por equipo (comparación estricta).
- **Costos:** por mes del consumo, separados por tipo de orden; los repuestos que más costaron.
- **Riesgo:** los equipos activos de mayor riesgo (de `v_riesgo_activo`) y la cobertura: cuántos
  equipos activos tienen riesgo y cuántos no, por falta de edad o de modelo.
- **Paneles operativos** (listas con límite y orden): lecturas y alertas del operario (20); cola del
  taller (50, fallas primero, la más antigua arriba) y trabajos del técnico (10); alertas de campo
  pendientes (50), alertas del sistema por atender (50), órdenes abiertas (100) y cuatro contadores del
  supervisor; estado de la plataforma del administrador; plantas para el filtro (100). El operario y
  el técnico filtran por el usuario **de la sesión**; ese filtro es de presentación (RLS aísla
  empresas, no personas: 15.4).
- **7.8 Corrección del cierre:** en una predictiva, el tiempo fuera de servicio se mide desde
  `en_taller_en` (o la fecha de la orden si no se registró). Los cierres anteriores conservan su valor;
  los indicadores no usan esa columna sino `v_paradas`.

## 8. API y ensamblado de los paneles

### 8.1 Piezas

El cálculo de indicadores no conoce HTTP ni base de datos; el ensamblador arma widgets genéricos y no
sabe qué consulta cada uno; la capa de API los une. Cada widget es una transacción propia con su límite
de tiempo: si uno falla o tarda, devuelve un estado degradado sin el texto del error y el resto del
panel responde.

### 8.2 Indicadores

`resumir` arma toda razón sobre las sumas del periodo, y toda razón sin denominador es `None` («sin
datos»), ni cero ni infinito. `mtbf_intervalo` usa los cuantiles de `scipy.stats.chi2`.

### 8.3 Un widget que falla no tumba el panel (RNF-02)

PostgreSQL aborta la transacción entera ante el primer error, así que cada widget abre la suya. Límite
de 3 s para los indicadores y 2 s para el resto; si falla o se pasa, estado `degradado` con motivo
`error` o `tiempo_agotado`; el detalle va al registro. A lo más tres widgets a la vez por panel.
`CancelledError` no se captura: debe propagarse para liberar la conexión.

### 8.4 Rutas, roles y widgets

| Ruta | Quién | Qué |
|---|---|---|
| GET `/api/v1/panel` | Cualquier rol con panel | Widgets del rol, rol y lista de degradados. `planta` (máx. 80), `desde`, `hasta` |
| GET `/api/v1/indicadores` | Gerente, administrador | Solo el widget de indicadores |
| GET `/api/v1/plantas` | Supervisor, gerente, administrador | Ubicaciones para el filtro |

| Rol | Widgets |
|---|---|
| operario | mis_lecturas, mis_alertas |
| tecnico_taller | cola_taller, mis_trabajos |
| supervisor | contadores, alertas_campo, alertas_sistema, ordenes_abiertas |
| gerente | indicadores, repuestos_costo, riesgo_top, riesgo_cobertura |
| administrador | los del supervisor y los del gerente, más salud (9) |

El periodo por defecto son los últimos 12 meses (incluido el actual hasta ahora); `hasta` es inclusivo
para el usuario y exclusivo en la base; nunca pasa de ahora; más de 24 meses es 422.

### 8.5 Caché

No hay. Si se agrega, la clave lleva **siempre** la empresa (`clave_cache` se niega a construirse sin
ella) y un TTL corto (60 s); el mes en curso nunca más que eso.

### 8.6 Conexión con la fase 1

La transacción de cada widget es de solo lectura, `REPEATABLE READ` (las consultas del indicador ven la
misma foto) y fija el tenant con `set_config(..., true)` y parámetro.

### 8.7 Cabeceras de seguridad de la API

`default-src 'none'; frame-ancestors 'none'`, `nosniff`, `no-referrer`, HSTS, `Permissions-Policy`
cerrada, `Cross-Origin-Resource-Policy` y `no-store`, también en los 404 y 500. El middleware es ASGI
puro y envuelve la pila completa (un 500 no controlado lo genera `ServerErrorMiddleware`, por fuera de
todo lo registrado con `add_middleware`).

## 9. Rendimiento medido (RNF-04 y RNF-07)

Mediana de cinco corridas en PostgreSQL 16.15, como `app_user` con RLS, empresa sintética creciente:

| Consulta (ms) | 200 equipos | 1 000 | 4 000 |
|---|---|---|---|
| Órdenes en la base | 3 000 | 15 000 | 60 000 |
| Riesgo de UN equipo (RNF-04) | 3,4 | 4,7 | 8,9 |
| Los cuatro indicadores juntos | 58 | 212 | 974 |
| Recálculo nocturno de toda la empresa | 33 | 148 | 579 |
| Registrar una lectura (con el trigger) | 0,20 | 0,38 | 0,30 |

**Hallazgo 1:** el JIT de PostgreSQL agregaba ~1,3 s fijos a los cuatro indicadores (1 348 ms frente a
58 ms con 200 equipos); se apaga por rol (decisión 13). **Hallazgo 2:** sin estadísticas, tras una
carga masiva el recálculo nocturno pasó de 0,15 s a 23 s; se ejecuta `ANALYZE` después de cada
migración y de cada carga grande. El trigger de horas cuesta menos que el ruido de la medición.

## 10. Aplicación web

### 10.1 Qué ve cada rol

Una sola ruta, `/panel`, con la vista del rol de la sesión. Operario: sus lecturas (con su estado) y
sus alertas (en qué quedaron). Técnico: cola del taller y trabajos recientes. Supervisor: cuatro
contadores, alertas de campo, alertas del sistema y órdenes abiertas, con filtro de planta. Gerente:
disponibilidad, MTBF con intervalo, MTTR y costo; gráficas de disponibilidad y de costo por mes; equipos
de mayor riesgo con su cobertura; repuestos que más costaron; filtros de planta y periodo.
Administrador: lo del gerente y el supervisor, más el estado de la plataforma.

### 10.2 Seguridad del frontend

El navegador nunca ve la cookie de sesión (`httpOnly`). CSP con un **nonce nuevo en cada petición**: un
script en el marcado sin el nonce no se ejecuta; `strict-dynamic`; `object-src`, `base-uri`,
`form-action` y `frame-ancestors` cerrados; todas las páginas se renderizan por petición. Cabeceras
estáticas: `nosniff`, `X-Frame-Options`, HSTS, `Referrer-Policy`, `Permissions-Policy`,
`Cross-Origin-Opener-Policy`; `poweredByHeader` apagado.

### 10.3 Mostrar números sin engañar

Formato siempre en America/Santo_Domingo; un dato ausente es «—»; una razón sin denominador, «sin
datos». El MTBF nunca aparece desnudo («19 fallas · IC 90 %: 2,617 h a 5,864 h»; sin fallas, «al
menos»). El riesgo se dice con palabras además del color, con su horizonte y su base. Debajo de los
equipos de mayor riesgo, la cobertura: «Un equipo sin riesgo calculado no es un equipo sin riesgo».
El filtro de planta avisa que ordena la vista y no limita lo que se ve.

### 10.4 Gráficos accesibles

SVG propio, sin biblioteca. Título y descripción para lectores de pantalla; una zona por mes que
responde al cursor y al foco del teclado; leyenda con más de una serie; «Ver como tabla». La línea de
disponibilidad no parte de cero pero nunca pasa de 100 %; las columnas parten de cero. Colores
validados con un validador de paletas en los dos temas.

### 10.5 Lo que no hace

No tiene acceso propio (usa el de la fase 1); los paneles necesitan conexión (un panel sin conexión
mostraría datos viejos sin avisarlo); no exporta ni envía el panel por correo.

## 11. Auditoría de aislamiento (RNF-01)

Una prueba que solo confirma que A no ve lo de B pasa también con RLS apagada y la tabla de B vacía. La
auditoría está diseñada para fallar de la manera correcta: cada control se ejecutó contra una versión
saboteada del sistema.

- **11.1 Cómo puede romperse:** tabla sin RLS o sin FORCE; política permisiva; FK simple que cruza
  empresas; vista, función o rol que saltan RLS; privilegios de más; tenant que se arrastra en una
  conexión reutilizada; ruta sin sesión o que revela existencia (403 en vez de 404).
- **11.2 Catálogo** (C1–C13): `empresa_id` no nulo en toda tabla de negocio; RLS activa y forzada; toda
  política filtra con `app_empresa_id()`; toda FK entre tablas de empresa incluye `empresa_id`; vistas
  `security_invoker`; funciones SECURITY DEFINER autorizadas con `search_path` fijo y sin EXECUTE para
  PUBLIC; roles de aplicación sin SUPERUSER, BYPASSRLS, CREATEROLE ni CREATEDB y dueños de nada; tablas
  de solo agregar sin UPDATE ni DELETE; vistas de solo lectura; nada para PUBLIC; `app_empresa_id()`
  STABLE. Informativo I1: los únicos globales (correo de usuarios, código QR) permiten enumeración.
- **Caja negra** (CN0–CN5): cobertura en todas las tablas, lectura propia completa y ajena vacía, sin
  tenant cero filas, escrituras cruzadas sin efecto, cambio de empresa rechazado por la política,
  funciones privilegiadas solo para quien debe.
- **11.3 Recorrido de rutas:** sin credenciales, 401; con un usuario de A y recursos de B, 404 y ninguna
  marca de datos de B; una ruta con parámetros sin recurso con el que probarla es un hallazgo.
- **11.4 Conexiones reutilizadas y simultáneas:** un tenant fijado en la sesión (y no en la
  transacción) se filtraría a la siguiente petición que use esa conexión.
- **11.5 Veinte sabotajes** que la auditoría debe detectar (RLS desactivada o sin FORCE, políticas
  permisivas, tabla nueva sin `empresa_id` o sin RLS, FK simple, vista sin `security_invoker`, función
  privilegiada no autorizada, BYPASSRLS, dueño de una tabla, escritura sobre el libro o una vista,
  `PUBLIC`, `empresa_id` nulo, `app_empresa_id()` nula, WITH CHECK abierto, `search_path` libre).

## 12. Pruebas

El PDF verificó su paquete con suites de SQL en PGlite y PostgreSQL 16.15, validación cruzada contra una
implementación independiente sobre 80 flotas al azar, 31 mutaciones del SQL (todas detectadas), pruebas
de Python sin base, pruebas con asyncpg, 24 mutaciones de la API, una prueba de punta a punta con 73
comprobaciones y ocho sabotajes, axe sobre 20 combinaciones y actionlint.

- **12.5 Lo que no demuestran:** los datos son sintéticos; los tests de concurrencia de fases 3 y 4 no
  se escribieron allí; el CI no se ejecutó en GitHub; no hay prueba de carga ni de penetración; la
  accesibilidad se revisó con una herramienta automática y no con lector de pantalla; el porcentaje
  planificado depende de cómo se clasifican las órdenes; el IC supone tasa constante.
- **12.6 Lo que hay que escribir en el repositorio:** el recorrido de rutas sobre la aplicación
  completa, los tres flujos críticos de punta a punta con el inicio de sesión real, los tests de
  concurrencia de fases 3 y 4, una prueba de zona horaria y la comprobación de que el rol de la
  aplicación no es dueño ni superusuario.

## 13. CI y fronteras de módulos

CI en cada push y pull request, con permisos mínimos y cancelando ejecuciones viejas: backend
(PostgreSQL 16, migraciones, pruebas, auditoría de aislamiento, `pip-audit`), frontend (`npm ci`,
tipos, pruebas, compilación, `npm audit`) y secretos (gitleaks sobre todo el historial), más
Dependabot semanal. Las fronteras entre módulos (RNF-08) se verifican automáticamente; una dependencia
nueva obliga a editar las reglas en el mismo cambio.

## 14. Matriz de trazabilidad

En `anexos/matriz-trazabilidad.md`, con la evidencia de este repositorio por requerimiento.

## 15. Seguridad

- **15.1 Checklist OWASP Top 10:2025:** en `anexos/owasp-top10-2025.md`, punto por punto, con su
  evidencia y lo pendiente.
- **15.2 Fase 1 antes de producción:** límite de intentos en login, refresco y registro (proxies de
  confianza para la IP real); mensajes y tiempos iguales exista o no el correo; el correo único revela
  si existe (mitigación escrita); JWT con algoritmo fijado, 30 min de acceso, 7 días de refresco con
  rotación y revocación, y relectura del usuario al renovar; cookie `httpOnly`, `Secure`, `SameSite`;
  tenant con `set_config` y parámetro; rol de aplicación sin privilegios; contraseñas de 12 o más
  caracteres, sin las comunes, Argon2id de 100 a 500 ms.
- **15.3 Operación:** un secreto por ambiente; copia restaurada al menos una vez; `ANALYZE` tras cada
  migración y carga grande, reinicio del pool tras la migración; la auditoría solo en pruebas o
  staging; los usuarios de demostración nunca en un ambiente expuesto.
- **15.4 Trabajo futuro:** planta como frontera real (RLS adicional); aislar personas de una misma
  empresa; caché solo si una medición lo pide; límite de peticiones por empresa; pentest externo,
  prueba de carga y lector de pantalla; calendarios de turnos, exportación y notificaciones.

## 16. Documentación técnica y manual

Arquitectura, modelo de datos, API (exportada como archivo, no `/docs` en producción), seguridad,
operación, pruebas y decisiones. El manual, un capítulo por rol con los pasos del trabajo diario, «qué
hacer si algo sale mal» y un glosario («sin edad», «sin modelo», «confianza baja», «IC 90 %», «horas
de calendario»). Cómo leer el panel del gerente: disponibilidad y utilización juntas; el MTBF con su
rango; el MTTR solo cuenta fallas cerradas; el porcentaje planificado sube cuando el mantenimiento se
adelanta, si la planta clasifica sus órdenes de forma estable; el riesgo es una probabilidad del
modelo; el filtro de planta ordena la vista.

## 17. Datos de demostración

Datos sintéticos marcados como tales, deterministas y con fechas relativas a la ejecución. Guion de
siete minutos: operario en el teléfono (lectura y alerta), supervisor (reconoce y crea orden
predictiva, filtra por planta), técnico (cambio de pieza y repuestos), supervisor y gerente (cierre;
costo planificado, riesgo casi cero, disponibilidad), aislamiento (otra empresa no ve nada; la
auditoría da cero filas), resiliencia (sin permiso sobre las vistas de riesgo solo esa sección se
degrada, y se recupera al devolverlo).

## 18. Material para la tesis

Capítulo II: disponibilidad, MTBF, MTTR, IC con χ², aislamiento multiempresa, OWASP, mutación,
accesibilidad. Capítulo III: validación cruzada, mutaciones, auditoría con sabotajes, medición con
mediana, definiciones antes que consultas. Capítulo IV: rendimiento, matriz, sabotajes, pruebas,
capturas y hallazgos (JIT, estadísticas, la espera de la predictiva contada como parada, la escritura
sobre vistas, el contraste del botón en oscuro). Limitaciones: datos simulados, un solo desarrollador,
sin pentest ni carga, supuestos del IC. Fuentes: OWASP Top 10:2025, documentación de RLS de PostgreSQL,
WCAG 2.2, Meeker y Escobar, Rausand y Høyland, ISO 14224 y EN 15341 (confirmar edición).

## 19. Orden de implementación (semanas 13 a 16)

Puerta de entrada y decisiones; migración y comprobaciones; sentencias y corrección del cierre; API;
auditoría de aislamiento y recorrido de rutas; web; uso real y mediciones; CI y pruebas de punta a
punta; OWASP, documentación, manual, capítulo IV y ensayo. Se recorta, en este orden: paneles de
técnico y administrador; selector de periodo y modo oscuro; mutaciones propias; pruebas de punta a
punta salvo los tres flujos críticos. **No se recorta nunca:** auditoría de aislamiento y recorrido de
rutas, aislamiento de widgets, corte de meses en la zona de la plataforma, IC y aviso de cobertura,
revisión de A01 y A07, y las limitaciones escritas.

## 20. Definición de «hecho» para la Fase 5

- Los paneles de operario, supervisor y gerente muestran datos reales con semanas de uso, o la tesis
  declara que se evaluó con simulados.
- Cada indicador coincide con un cálculo a mano (un mes, tres equipos: disponibilidad, horas, costo).
- La auditoría da cero violaciones y cero sin cobertura en staging; el recorrido de rutas pasa; los
  sabotajes siguen detectándose.
- La suite corre en CI en cada pull request, `main` está protegida y el flujo corrió en GitHub.
- RNF-02: con el riesgo caído se registra una lectura y una alerta y los paneles responden con solo esa
  sección degradada.
- RNF-04: menos de 2 s en staging con el volumen real, medido y escrito.
- Los tests de concurrencia de fases 3 y 4 corren en CI contra PostgreSQL 16.
- El checklist OWASP está revisado con evidencia y los pendientes son limitaciones escritas.
- Los paneles se recorren con teclado y axe no da violaciones.
- Documentación técnica y manual por rol reflejan la migración y las decisiones; el manual explica el
  panel del gerente.
- El capítulo IV declara qué es simulado, qué no se probó y los límites de cada indicador.
- La demostración se ensayó de principio a fin.

## 21. Siguiente paso

No hay fase 6: queda la entrega. Etiqueta en git, copia de la base y, junto a ella, el resultado de la
auditoría y de la suite. Con el uso real acumulado, la validación retrospectiva de la fase 4 y una
nueva medición de los indicadores.

## 22. Documentos que esta fase deja desactualizados

Fase 1 (tenant con `set_config` y parámetro, no `SET LOCAL`); propuesta inicial (sin sensores ni
TimescaleDB); arquitectura técnica (versiones, Redis); requerimientos (RF-13 con Cancelada, RNF-02 y
RNF-04 se diseñan en F4 y se verifican aquí); especificación (definiciones de la sección 5 y
diccionario con `creado_en`, `horas_acumuladas` y `v_paradas`); fase 3 (tiempo fuera de servicio de una
predictiva desde el taller). Hecho en este repositorio con la marca *[Actualizado en F5]*.

---

## Anexo: cómo quedó implementada en este repositorio (2026-10-28)

### Desviaciones respecto del PDF

| Tema | PDF | Aquí | Por qué |
|---|---|---|---|
| Número de migración | `0005` | `0011` (`20261028_0011_paneles.py`) | Las fases anteriores ya usaron 0001–0010 |
| `activos.creado_en` | La migración la crea | Ya existía (fase 2); solo se rellena | — |
| Qué lectura es válida | `NOT requiere_revision` | `NOT requiere_revision OR resolucion IN ('confirmada','reinicio')`, con `COALESCE` para la lógica de tres valores | Aquí una lectura marcada y confirmada conserva la marca. La prueba `test_horas_acumuladas_las_mantiene_el_trigger` encontró que sin `COALESCE` una lectura marcada recibía horas |
| Lectura confirmada después de un reinicio | Queda sin horas | Se ubica con el offset vigente en su `capturado_en` | Desde la revisión 0008 cada reinicio guarda el offset que deja |
| JIT | En la migración | En `backend/db/roles.sql` (la migración lo intenta y solo avisa si no hay permiso) | `simap_owner` no puede alterar roles |
| Consultas de indicadores | 18 sentencias SQL cargadas por nombre (`generate_series`, ventanas, `LATERAL`) | El ORM trae filas acotadas al periodo y el cálculo (cubos, unión de intervalos, horas, costos) se hace en Python (`app/services/paneles/indicadores.py`) | Decisión de portabilidad del proyecto. Contrastado con casos a mano y con una implementación de referencia independiente (80 flotas) |
| Corte de meses | `SET LOCAL TimeZone` en la transacción | `zoneinfo` en Python | El cálculo ya no depende de la zona de la sesión |
| Transacción del widget | Fábrica con asyncpg | `sesion_de_lectura` (SQLAlchemy) con `EstrategiaTenant.lectura_consistente` (REPEATABLE READ, READ ONLY) | Misma garantía, detrás de la costura del motor |
| Cabeceras de la API | `app = envolver(crear_app())` | `SimapAPI.build_middleware_stack` envuelve la pila completa | Las pruebas necesitan que `app` siga siendo `FastAPI` (`dependency_overrides`) |
| `/docs` en producción | Apagarlo | `EXPONER_DOCS=false` | — |
| Web | Componentes de servidor que llaman a la API desde Next | Páginas de cliente con el proxy `/api` (patrón del resto de la app) y CSP con nonce en `src/proxy.ts`; layout raíz con `connection()` | Decisión de implementación confirmada |
| CSP | `script-src` con `strict-dynamic` | Además `worker-src 'self'` y `upgrade-insecure-requests` solo por HTTPS | Con `strict-dynamic` el navegador ignora `'self'` y no se instalaría el service worker; por http en la red de la planta se rompería la carga |
| Colores de las gráficas | Azul y naranja | Violeta (`--serie-planificado`) y naranja (`--serie-falla`), validados | En SIMAP el azul significa «se puede pulsar» |
| Auditoría de aislamiento | Funciones SQL instaladas en un esquema `auditoria` y sabotajes en un script | Pruebas de pytest que leen el catálogo (C1–C13) y recorren todas las rutas; RLS y caja negra ya cubiertas por las guardias de fases 1 a 4 | Se comprobó a mano con el sabotaje S01 (RLS desactivada en `activos`): fallan C2 y el recorrido de rutas |
| Recorrido de rutas | 404 con recursos de B | La respuesta con recursos de B debe ser indistinguible de la de un id inexistente, para cada rol de A | Distingue un 403 de rol (igual para los dos) de uno que revela existencia |
| Dependencias | — | `python-jose` sustituido por **PyJWT 2.15.0** y `python-dotenv` 1.2.2; `npm audit fix` (zod, fast-uri) | `pip-audit` y `npm audit` encontraron avisos; `python-jose` tenía avisos sin versión corregida |
| Fronteras de módulos | `fronteras.py` con `ast` | `import-linter` (capas) en el backend y `dependency-cruiser` en el frontend, ya en CI desde la fase 1 | Misma garantía, ya existente |

### Correcciones de la revisión del 2026-10-29 (revisión 0012, versión 0.10.1)

| Hallazgo | Corrección | Prueba |
|---|---|---|
| Un reinicio resuelto después de confirmar una lectura posterior dejaba esa lectura con las horas de la escala vieja | Trigger AFTER `lectura_reinicio_propaga`: recalcula las lecturas válidas hasta el reinicio siguiente; el trigger de horas recalcula en todo UPDATE | `test_reinicio_resuelto_despues_recalcula_las_lecturas_posteriores` |
| `activos.creado_en` podía quedar después de lecturas o fallas capturadas hasta 14 días atrás (224 y 97 equipos en la base de desarrollo) | Trigger `activo_observado_desde` en lecturas y órdenes; relleno en la migración (0 y 0 después) | `test_dato_anterior_al_alta_adelanta_desde_cuando_se_observa` |
| La 404 de Next trae estilos en línea que la CSP bloquea (10.2) | `src/app/not-found.tsx` solo con clases | `test_10_2_pagina_404_propia_sin_violaciones_de_csp` |
| El recorrido de rutas mandaba `{}`: 422 con los dos ids sin intentar la escritura (11.3) | `CUERPOS` con un cuerpo válido por ruta y prueba guardiana; un 422 con el id inexistente es hallazgo | Sabotaje: sin RLS en `ordenes_trabajo`, el recorrido falla |
| `fechaHora` usaba la zona del navegador (10.3) | `ZONA` en `src/lib/formato.ts`, también en el reloj del marco y la bitácora del operador | Revisión de código |
| El downgrade de la 0011 no restablecía el JIT de `job_user` | `ALTER ROLE job_user RESET jit` si el rol existe | Migraciones bajadas y subidas |

### Dónde está cada cosa

- Migración: `backend/alembic/versions/20261028_0011_paneles.py` y `20261029_0012_horas_y_observacion_coherentes.py`; JIT: `backend/db/roles.sql`.
- Cálculo: `app/services/paneles/indicadores.py`; ensamblador: `ensamblador.py`; consultas:
  `consultas.py`; widgets por rol: `widgets.py`; rutas: `app/api/v1/routes/paneles.py`.
- Cabeceras: `app/core/seguridad_http.py`; corrección del cierre: `ordenes_estados.inicio_de_parada`.
- Web: `src/app/panel/page.tsx`, `src/components/graficas.tsx`, `src/lib/paneles.ts`; CSP en
  `src/proxy.ts`; cabeceras estáticas en `next.config.ts`.
- Pruebas: `tests/test_indicadores.py` (casos a mano y validación cruzada), `test_ensamblador.py`,
  `test_paneles.py` (API, migración, RNF-02), `test_auditoria_aislamiento.py` (catálogo y rutas);
  `frontend/e2e/fase5.spec.ts` (paneles por rol, CSP y XSS, cookie, periodo, 390 px).
- Checklist y matriz: `anexos/owasp-top10-2025.md` y `anexos/matriz-trazabilidad.md`.
