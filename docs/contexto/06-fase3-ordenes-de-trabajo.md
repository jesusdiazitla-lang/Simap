# Fase 3: Órdenes de Trabajo — Guía Detallada de Implementación

> Transcripción de `Fase3_Ordenes_de_Trabajo_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado). Fuente
> de verdad del **alcance y los criterios de aceptación** de la fase F3 en `docs/PLAN.yaml`. Donde
> este documento contradice a los anteriores, manda este.
>
> **Notas de adaptación a este repositorio** (en citas como esta, al final de cada sección afectada).
> La más importante: el documento numera su migración como `0003` y la escribe como `ALTER TABLE`
> porque supone que `ordenes_trabajo` ya existe vacía. Aquí la tabla nunca se creó (solo está en el
> esquema de referencia `backend/db/schema.sql`), así que la revisión `0007` la **crea** ya con su
> forma final y la comprobación de «tabla vacía» de la sección 3 no aplica.
>
> **Las ocho decisiones de la sección 4 las confirmó el usuario el 2026-10-14**, tal como las propone
> el documento.

## 1. Objetivo de la fase

Cerrar el ciclo completo de una falla real, de principio a fin y con trazabilidad total: un
supervisor reporta la falla, el sistema crea la orden de trabajo, el taller la repara, un responsable
autoriza la salida del equipo y cada paso queda registrado con su autor y su hora. Esta fase produce
el dato que da razón de ser a la tesis: la lista de fallas cerradas con las horas de operación en que
ocurrieron. Con ella, la Fase 4 ajusta la distribución de Weibull de cada componente. Por eso aquí
pesa tanto la calidad del dato (una falla duplicada, mal medida o editada después distorsiona el
modelo) como que el flujo funcione.

## 2. Alcance de esta fase

Requerimientos que cubre: RF-11 a RF-16 y RNF-06; RNF-01 de forma transversal. Además paga tres
deudas heredadas de la Fase 2 (sección 5).

**Incluye:**

- Reporte de falla (horómetro, temperatura, código de error, componente y descripción) que crea la
  orden con un número correlativo por empresa (RF-11, RF-12).
- Máquina de estados Reportada, En taller, Reparada y Cerrada con transiciones restringidas por rol,
  más el estado Cancelada y el rechazo de cierre (RF-13).
- Responsable de cada paso e historial de eventos que solo se agrega, nunca se modifica (RF-14,
  RNF-06).
- Registro del trabajo realizado y del tipo de intervención (reemplazo, reparación o ajuste).
- Tiempo fuera de servicio calculado al cerrar (RF-15) y vínculo entre una alerta y la orden que
  origina (RF-16).
- Reporte de falla sin conexión, sobre la cola de la Fase 2.
- Reinicio del horómetro, baja de usuarios sin perder historial y confirmación de lecturas marcadas.
- La vista `v_intervalos_entre_fallas`, que la Fase 4 consumirá para ajustar el modelo.

**No incluye** (llega en fases posteriores o queda fuera):

- Repuestos usados y descuento de stock al cerrar (Fase 4, tabla `orden_repuesto`). En esta fase la
  orden se cierra sin repuestos.
- Cálculo de riesgo, modelo de Weibull y alertas automáticas (Fase 4); paneles de indicadores
  (Fase 5).
- Asignar un técnico al reportar la falla, como menciona la Especificación (3.2). Aquí el técnico
  queda registrado cuando marca la orden como Reparada; la asignación previa sería una columna
  `tecnico_asignado_id` y es una mejora.
- Filtrar por planta: la Especificación habla de «su planta», pero aún no existe asignación de
  usuarios a plantas. Todas las órdenes son visibles para los roles autorizados de la empresa.
- Transiciones sin conexión (decisión 6) y notificaciones push o por correo.

## 3. Puerta de entrada: qué debe estar verificado antes de empezar

Las órdenes de trabajo son los datos con mayor valor del sistema y los que más tablas relacionan
(activos, componentes, usuarios, alertas, lecturas). Un hueco de aislamiento aquí expone lo más
sensible. Antes de escribir la primera línea se verifica:

- La Definición de Hecho de la Fase 2 está cumplida, en especial el test de guardia (toda tabla con
  `empresa_id` tiene RLS habilitada y forzada) corriendo en CI contra PostgreSQL real, y las
  referencias compuestas de las lecturas y alertas.
- Cookies y dominios resueltos entre frontend y backend (Fase 2, 8.2). Todas las transiciones de esta
  fase son POST o PATCH con sesión por cookie; si la sesión no persiste en producción, el flujo no se
  puede ni probar.
- Existen usuarios de prueba para los cinco roles en el entorno de desarrollo (operario, supervisor,
  técnico de taller, gerente y administrador): sin ellos no se puede verificar quién puede qué.
- La tabla `ordenes_trabajo` está vacía. La migración agrega columnas NOT NULL sin valor por defecto
  (`numero`, `horas_acumuladas_en_falla`) y por eso lo exige. Con `FORCE ROW LEVEL SECURITY`, hasta el
  propietario ve cero filas si no fija un tenant: la comprobación debe correr con un rol que ignore
  RLS.
- Hay una copia de seguridad reciente de la base antes de aplicar la migración.
- Las decisiones de la sección 4 están confirmadas.

> **Adaptación.** La tabla no existía, así que la revisión `0007` la crea (no hay datos que perder).
> La sesión en producción sigue pendiente: aún no hay despliegue (tarea abierta de F2). Los usuarios
> de los cinco roles los crea `tools/seed_demo.py` y las pruebas los crean con `tests/planta.py`.

## 4. Decisiones confirmadas

| Decisión | Propuesta (aceptada) | Por qué |
|---|---|---|
| 1. Estado Cancelada (RF-13 define cuatro estados) | Agregarlo: solo desde estados abiertos y con motivo. | Una falla reportada por error o duplicada no tiene salida: no se puede borrar (RNF-06) y cerrarla inventaría una reparación que no ocurrió. Exige actualizar RF-13 y la Especificación 3.3. |
| 2. Quién autoriza el cierre | Supervisor y administrador; el gerente queda en solo lectura. | CU-03 dice «Supervisor o Gerente», pero la tabla de roles define al gerente como solo lectura. Se corrige CU-03. |
| 3. Separación de funciones | Quien repara no autoriza; quien reportó sí puede. | Lo primero lo garantizan los roles. Prohibir lo segundo haría inutilizable el sistema en una planta con un solo supervisor; ambos nombres quedan registrados. |
| 4. Qué renueva un componente | Solo el tipo `reemplazo` reinicia su vida; reparación y ajuste no. | Weibull mide cuánto vive un componente desde que es nuevo. El técnico elige el tipo al marcar Reparada y el supervisor lo ve antes de autorizar. |
| 5. Tiempo fuera de servicio | Tiempo de calendario, de la falla a la autorización de salida. *[Actualizado en F5, `08-fase5-dashboard-y-cierre.md` §22.]* En una orden predictiva, desde que el equipo entra al taller (decisión 10 de F5): antes de eso la orden espera su ventana con el equipo produciendo. | Es lo medible sin conocer los turnos de cada planta; las fechas crudas permiten recalcularlo después. |
| 6. Operación sin conexión | Solo el reporte de falla; las transiciones exigen conexión. | Crear una falla es idempotente; una transición depende del estado actual, y encolarla produce conflictos que nadie resuelve desde campo. |
| 7. Corrección de órdenes cerradas | Solo el administrador, con nota y evento permanente. | Una orden cerrada no se modifica (6.5), pero los errores de digitación existen: la corrección es un camino aparte que deja huella. |
| 8. Reinicio del horómetro | Resolverlo en esta fase, no en la 4. | Sin esto, las horas entre fallas de todo equipo cuyo horómetro se cambie quedan mal calculadas para siempre. |

## 5. Deudas de la Fase 2 que se pagan aquí

### 5.1 Reinicio o cambio del horómetro

El modelo trabaja con las horas de operación entre fallas. Si el horómetro se reinicia o se
reemplaza, el dial vuelve a un número bajo y las horas entre dos fallas saldrían negativas o
disparatadas. La solución separa dos conceptos: el **valor del dial** (lo que el operario ve y
digita) y las **horas acumuladas** del equipo (lo que usa el modelo), que son el dial más un
desplazamiento (offset) que absorbe los reinicios.

- `activos.horometro_offset` (entero, por defecto 0) y `lecturas_horometro.es_reinicio` (booleano).
  Cada orden guarda `horas_acumuladas_en_falla = offset + dial` al momento de la falla; ese es el
  número que consume la Fase 4.
- `POST /activos/{id}/reinicio-horometro` (solo administrador) recibe el valor nuevo del dial. En una
  transacción recalcula el offset para que las horas acumuladas sigan sin interrupción y registra una
  lectura con `es_reinicio` verdadero.
- La regla «lectura menor que la anterior queda marcada» ignora las lecturas anteriores al último
  reinicio. Una lectura o una falla capturada antes del reinicio que llega después (cola sin
  conexión) queda marcada para revisión, porque usar el offset nuevo la mediría mal.
- La CHECK del offset (no negativo) rechaza un valor nuevo absurdo, por ejemplo un horómetro que
  «reinicia» en un número mayor que las horas ya acumuladas.

```sql
-- Cambio o reinicio del horometro: las horas acumuladas no se interrumpen
-- (offset nuevo + valor nuevo = offset anterior + ultimo valor).
UPDATE activos
   SET horometro_offset = horometro_offset + horometro_actual - :nuevo,
       horometro_actual = :nuevo,
       horometro_actualizado_en = now()
 WHERE id = :activo_id
RETURNING horometro_offset;

INSERT INTO lecturas_horometro
    (empresa_id, activo_id, registrado_por, valor_horometro, capturado_en, cliente_id, es_reinicio)
VALUES (:empresa_id, :activo_id, :usuario_id, :nuevo, now(), :cliente_id, true);
```

> **Adaptación.** La revisión 0006 (F2) ya permitía al administrador resolver una lectura marcada
> como `reinicio`. Las dos entradas —esa resolución y la ruta nueva— pasan por el mismo servicio
> (`app.services.activos.reiniciar_horometro`), que aplica la fórmula del offset; así ninguna de las
> dos deja las horas acumuladas sin corregir.

### 5.2 Baja de usuarios sin perder historial

Las órdenes guardan quién reportó, reparó y autorizó. Los usuarios no se borran: se desactivan
(`usuarios.activo`). Un usuario desactivado no puede iniciar sesión ni renovar su sesión y sigue
apareciendo por nombre en el historial. Su access token vigente (hasta 30 minutos) se corta
verificando `activo` en las transiciones. Cada evento guarda `rol_al_momento`: el historial dice con
qué rol actuó cada persona entonces, no con el que tiene hoy.

> **Adaptación.** `usuarios.activo` existe desde la revisión 0005, y el login y la renovación ya lo
> comprueban (F2). Lo nuevo es la comprobación en cada transición.

### 5.3 Confirmación de lecturas marcadas

Se agrega `POST /lecturas/{id}/confirmar` (supervisor y administrador): quita la marca y, si el valor
es mayor o igual al vigente, lo adopta con el mismo UPDATE condicionado de la Fase 2. Si la lectura
está enlazada a una orden, se confirma desde la orden (6.2).

> **Adaptación.** Ya existe desde F2 como `PATCH /lecturas/{id}` con `resolucion: confirmada`
> (revisión 0006), que además conserva quién y cuándo. No se duplica la ruta. Lo nuevo es la regla:
> una lectura enlazada a una orden responde 409 en esa ruta y se confirma desde la orden.

## 6. Reglas de negocio

### 6.1 Máquina de estados

Cerrada y Cancelada son terminales: ninguna ruta de la aplicación las modifica (6.5).

```
                rechazo de cierre (nota obligatoria)
                 ┌──────────────────────────────┐
                 ▼                              │
Reportada ──► En taller ──► Reparada ──► Cerrada
   │             │             │
   └─────────────┴─────────────┴──► Cancelada  (supervisor / admin, con motivo)
```

| Transición | Quién | Datos obligatorios | Efecto |
|---|---|---|---|
| Nueva a Reportada | Supervisor, administrador | Equipo, componente, horómetro, descripción | Crea la orden y su número, registra la lectura y deja el evento «creada». |
| Reportada a En taller | Técnico, supervisor, administrador | Ninguno | Fija `en_taller_en`. |
| En taller a Reparada | Técnico de taller | Trabajo realizado (10 a 2000 caracteres) y tipo de intervención | Fija `reparado_por` y `reparada_en`. |
| Reparada a Cerrada | Supervisor, administrador | Ninguno (nota opcional) | Fija `autorizado_por`, `fecha_salida_taller` y `tiempo_fuera_servicio_min`; emite `orden_cerrada`. |
| Reparada a En taller (rechazo) | Supervisor, administrador | Nota de 10 a 1000 caracteres | Conserva el trabajo anterior dentro del evento. |
| Abierta a Cancelada | Supervisor, administrador | Motivo de 10 a 1000 caracteres | Libera la unicidad del componente y de la alerta; la alerta vuelve a Revisada. |

Quién aparece en cada paso (RF-14): quien reportó (`reportado_por`, `reportada_en`), quien reparó
(`reparado_por`, `reparada_en`) y quien autorizó (`autorizado_por`, `fecha_salida_taller`). Quién pasó
la orden a En taller, quién rechazó el cierre y quién canceló quedan en el historial de eventos
(6.5), que es la fuente completa.

Las CHECK de la base impiden estados a medias (una orden Cerrada sin quien autorizó), pero no fijan
qué estado puede seguir a cuál: eso lo imponen el servicio y la sentencia condicionada de 6.4.

### 6.2 Reporte de falla

- Datos: horómetro (valor del dial), temperatura (opcional, de -100 a 999), código de error
  (opcional, hasta 50 caracteres), componente del catálogo, descripción (5 a 1000 caracteres), alerta
  de origen (opcional) y `cliente_id`. La empresa y quien reporta salen del token, nunca del cuerpo.
- `fecha_falla` es `capturado_en`, con las reglas de la Fase 2 (no más de 5 minutos en el futuro ni
  más de 14 días atrás); `reportada_en` es la recepción.
- Cada reporte registra además una lectura de horómetro con las reglas de la Fase 2 (CU-02, paso 7)
  y guarda su id en `lectura_id`; el `cliente_id` de esa lectura se deriva del de la falla (uuid5)
  para que un reenvío no cree dos. Si la lectura queda marcada, la orden hereda `requiere_revision` y
  su motivo: sigue su ciclo, pero la vista de la Fase 4 la excluye hasta que un supervisor confirme el
  horómetro (`POST /ordenes/{id}/confirmar-horometro`; si ya está cerrada, es una corrección
  administrativa).
- Una sola orden abierta por equipo y componente. Un segundo reporte responde 409 con el número de la
  existente; si dos supervisores lo envían a la vez, decide el índice único parcial y el servicio
  traduce el error (nunca llega texto de PostgreSQL al cliente). Un equipo con dos componentes
  averiados tiene dos órdenes.
- Alerta de origen (RF-16): del mismo equipo y pendiente o revisada. Pasa a `convertida_en_orden` en
  la misma transacción con un UPDATE condicionado; si cambió en ese instante, 409 y no se crea nada.
  Al cancelar la orden, la alerta vuelve a revisada.
- «El equipo está en falla» (mientras exista una orden abierta) y «fecha de última falla» se derivan
  en la consulta, con índices; no se guardan en columnas.
- Si el supervisor no sabe qué componente falló, usa «Otro (por identificar)», que se agrega a la
  plantilla inicial del catálogo si no está; puede corregirlo con `PATCH /ordenes/{id}` mientras la
  orden esté abierta. La Fase 4 no ajustará modelo con ese componente.

Secuencia del servicio, en una sola transacción:

1. Validar rol y cuerpo (Pydantic estricto, campos desconocidos rechazados).
2. Buscar por `(empresa_id, cliente_id)`: si existe, devolverla con 200 (reenvío).
3. Resolver el equipo bajo RLS (404 si no es de la empresa); componente y alerta se validan igual
   (422 si no existen o no corresponden).
4. Registrar la lectura de horómetro (reglas de la Fase 2) y obtener `lectura_id`.
5. `horas_acumuladas_en_falla = activos.horometro_offset + horómetro del dial`.
6. SAVEPOINT; pedir el número al contador; INSERT de la orden.
7. Reenvío concurrente: ROLLBACK TO SAVEPOINT (devuelve el número) y responder la existente.
   Violación de la única abierta por componente: 409 `orden_abierta_existente`.
8. Si hay alerta: UPDATE condicionado a `convertida_en_orden`; 0 filas = 409 y se revierte todo.
9. INSERT del evento «creada» (usuario, rol, hora).
10. COMMIT; solo después, notificar a quien escucha (12.3).

> **Adaptación.** Como en F2, el INSERT idempotente no usa `ON CONFLICT` (sintaxis de PostgreSQL):
> el ORM inserta dentro de un savepoint y el servicio traduce la violación por el **nombre** de la
> restricción, así que solo el reenvío se trata como reenvío y cualquier otra violación sigue siendo
> un error. Es el mismo resultado que el `ON CONFLICT` con destino que exige el documento.

### 6.3 Numeración correlativa

- El número (OT-0001, OT-0002…) se muestra con ese formato, pero la base guarda el entero, único por
  empresa: cada cliente ve su propia secuencia y nada revela cuántas órdenes tienen las demás.
- Un contador por empresa se incrementa con una sola sentencia dentro de la misma transacción que
  inserta la orden. Si la transacción falla, el número vuelve al contador: no quedan huecos. Una
  secuencia nativa consume el número aunque la transacción se revierta.
- La fila del contador queda bloqueada hasta el commit, así que dos fallas de la misma empresa se
  crean una tras otra. Con decenas de fallas al día es imperceptible y las empresas no se bloquean
  entre sí.

> **Adaptación.** El contador se incrementa con un `UPDATE … SET ultimo = ultimo + 1` del ORM
> (portable); la primera orden de una empresa crea la fila, y si dos la crean a la vez, la que pierde
> reintenta el UPDATE.

### 6.4 Transiciones concurrentes

Cada transición es un UPDATE condicionado al estado de origen, sin SELECT previo ni bloqueos
explícitos. Si devuelve cero filas, el servicio consulta bajo RLS: si la orden no existe para esa
empresa responde 404; si existe, 409 («la orden cambió de estado, recarga»). La transición y su
evento se escriben en la misma transacción. En el rechazo de cierre, el servicio guarda en `datos`
del evento el trabajo realizado y el técnico anteriores.

### 6.5 Inmutabilidad, historial y correcciones

- Una orden Cerrada o Cancelada no se modifica. Lo garantiza un trigger de la base (7.7), no solo el
  código. Una nota posterior al cierre es un evento nuevo.
- El historial vive en `orden_eventos` y solo se agrega: la aplicación no tiene permiso de UPDATE ni
  DELETE sobre esa tabla ni existe política RLS que los permita. Cada evento guarda usuario, rol al
  momento, estado anterior y nuevo, nota y una copia JSON de lo que cambió (RNF-06).
- La corrección administrativa (`POST /ordenes/{id}/correccion`) es el único camino sobre una orden
  cerrada: solo el administrador, con nota de al menos 10 caracteres y sobre una lista cerrada de
  campos (descripción, trabajo realizado, código de error, temperatura, tipo de intervención y marca
  de revisión), nunca estado, número, fechas ni responsables. Fija `app.correccion` dentro de su
  transacción y siempre escribe un evento «correccion» con valores anteriores y nuevos.
- Límite: el trigger y los permisos defienden contra errores y rutas olvidadas, no contra quien ya
  ejecute SQL arbitrario como `app_user`. Sellar los eventos con una cadena de hashes queda como
  mejora.

### 6.6 Vida del componente: el dato que consume la Fase 4

La vista `v_intervalos_entre_fallas` resta a las horas acumuladas de cada falla las de la última
falla anterior que renovó el componente (tipo `reemplazo`). Excluye canceladas y las que requieren
revisión.

| Horas del equipo | Intervención | Estado | Vida (horas) | Cómo se calcula |
|---|---|---|---|---|
| 1000 | Reemplazo | Cerrada | sin dato | No hay renovación previa conocida. |
| 1500 | Ajuste | Cerrada | 500 | 1500 menos 1000. |
| 2200 | Reemplazo | Cerrada | 1200 | 2200 menos 1000 (el ajuste no renovó). |
| 2500 | Reemplazo | Cancelada | excluida | Nunca ocurrió como falla válida. |
| 2600 | Ajuste | Cerrada, en revisión | excluida | Horómetro dudoso hasta confirmarse. |
| 2900 | Reparación | Cerrada | 700 | 2900 menos 2200. |

La primera falla de un componente no tiene referencia previa: la Fase 4 decide si la descarta o la
mide desde la instalación. Los componentes que aún no han fallado (datos censurados) también son
asunto de la Fase 4.

## 7. Cambios al modelo de datos

> **Adaptación.** Revisión `0007_ordenes_de_trabajo`. Crea `ordenes_trabajo` con su forma final en
> lugar de alterarla, y nombra restricciones e índices con la convención del proyecto
> (`uq_<tabla>_…`, `fk_<tabla>_…_mismo_tenant`, `ck_<tabla>_…`); el contenido de cada una es el del
> documento. Las claves candidatas `(empresa_id, id)` de `componentes`, `activos` y `usuarios` ya
> existían desde la 0005; se añaden las de `alertas` y `lecturas_horometro`.

### 7.1 Claves candidatas y deudas heredadas

```sql
ALTER TABLE alertas            ADD CONSTRAINT … UNIQUE (empresa_id, id);
ALTER TABLE lecturas_horometro ADD CONSTRAINT … UNIQUE (empresa_id, id);
ALTER TABLE activos            ADD COLUMN horometro_offset INTEGER NOT NULL DEFAULT 0
                                   CHECK (horometro_offset >= 0);
ALTER TABLE lecturas_horometro ADD COLUMN es_reinicio BOOLEAN NOT NULL DEFAULT false;
```

### 7.2 Columnas de `ordenes_trabajo`

Además de las del esquema de referencia (`activo_id`, `componente_id`, `alerta_origen_id`,
`reportado_por`, `reparado_por`, `autorizado_por`, `horometro_en_falla`, `temperatura`,
`codigo_error`, `descripcion`, `estado`, `trabajo_realizado`, `fecha_falla`,
`fecha_salida_taller`): `numero` (NOT NULL, sin default), `cliente_id`, `lectura_id`,
`horas_acumuladas_en_falla` (NOT NULL, ≥ 0, sin default), `requiere_revision`, `motivo_revision`,
`tipo_intervencion` (`reemplazo`, `reparacion`, `ajuste`), `motivo_cancelacion`, `reportada_en`,
`en_taller_en`, `reparada_en`, `tiempo_fuera_servicio_min` (≥ 0). `fecha_falla` sin valor por
defecto (debe venir de `capturado_en`) y `descripcion` NOT NULL.

### 7.3 Restricciones: la base rechaza estados a medias

- Estado en `('reportada','en_taller','reparada','cerrada','cancelada')`.
- Únicos: `(empresa_id, numero)`, `(empresa_id, cliente_id)`, `(empresa_id, id)`.
- `char_length(descripcion) BETWEEN 5 AND 1000`; `temperatura BETWEEN -100 AND 999`.
- Reparada o Cerrada exigen `reparado_por`, `trabajo_realizado` y `tipo_intervencion`.
- Cerrada exige `autorizado_por`, `fecha_salida_taller` y `tiempo_fuera_servicio_min`.
- Cancelada exige `motivo_cancelacion`; `requiere_revision` exige `motivo_revision`.

### 7.4 Referencias compuestas

Todas las referencias de la orden (activo, componente, alerta, lectura, reportado_por, reparado_por,
autorizado_por) son llaves foráneas compuestas `(empresa_id, x_id) → (empresa_id, id)`: PostgreSQL
comprueba las llaves foráneas ignorando RLS. Las anulables no se comprueban mientras sean NULL.

### 7.5 Índices

```sql
-- Una sola orden abierta por equipo y componente (evita fallas duplicadas)
CREATE UNIQUE INDEX … ON ordenes_trabajo (empresa_id, activo_id, componente_id)
    WHERE estado IN ('reportada','en_taller','reparada');
-- Una alerta origina, como maximo, una orden vigente
CREATE UNIQUE INDEX … ON ordenes_trabajo (empresa_id, alerta_origen_id)
    WHERE alerta_origen_id IS NOT NULL AND estado <> 'cancelada';
CREATE INDEX … ON ordenes_trabajo (empresa_id, activo_id, fecha_falla DESC);
CREATE INDEX … ON ordenes_trabajo (empresa_id, fecha_falla DESC)
    WHERE estado IN ('reportada','en_taller','reparada');
```

### 7.6 Contador y eventos

```sql
CREATE TABLE ordenes_contador (
    empresa_id UUID PRIMARY KEY REFERENCES empresas(id),
    ultimo     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE orden_eventos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresas(id),
    orden_id        UUID NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('creada','transicion','nota','correccion')),
    estado_anterior TEXT,
    estado_nuevo    TEXT,
    usuario_id      UUID NOT NULL,
    rol_al_momento  TEXT NOT NULL,
    nota            TEXT CHECK (char_length(nota) <= 1000),
    datos           JSONB,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, orden_id)   REFERENCES ordenes_trabajo (empresa_id, id),
    FOREIGN KEY (empresa_id, usuario_id) REFERENCES usuarios (empresa_id, id)
);
CREATE INDEX … ON orden_eventos (empresa_id, orden_id, creado_en);
```

### 7.7 Inmutabilidad: trigger

```sql
CREATE OR REPLACE FUNCTION ot_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado IN ('cerrada','cancelada')
       AND COALESCE(current_setting('app.correccion', true), '') <> 'on' THEN
        RAISE EXCEPTION 'La orden % esta % y no se puede modificar',
            OLD.numero, OLD.estado USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ot_inmutable BEFORE UPDATE ON ordenes_trabajo
    FOR EACH ROW EXECUTE FUNCTION ot_inmutable();
```

`set_config(…, true)` limita el valor a la transacción en curso: la corrección no se filtra a la
siguiente petición que reutilice la conexión.

### 7.8 Políticas RLS de la fase

Una sola política de aislamiento sobre `ordenes_trabajo` (una prueba exige que quede exactamente
una: las permisivas se combinan con OR). `ordenes_contador` con ENABLE, FORCE y su política.
`orden_eventos` con políticas separadas solo para SELECT e INSERT: sin política de UPDATE o DELETE,
RLS las deniega aunque algún día se concediera el permiso por error.

### 7.9 Vista para la Fase 4

```sql
CREATE VIEW v_intervalos_entre_fallas WITH (security_invoker = true) AS
SELECT empresa_id, activo_id, componente_id, id AS orden_id, numero,
       fecha_falla, tipo_intervencion, horas_acumuladas_en_falla,
       horas_acumuladas_en_falla
         - MAX(CASE WHEN tipo_intervencion = 'reemplazo' THEN horas_acumuladas_en_falla END)
             OVER (PARTITION BY empresa_id, activo_id, componente_id ORDER BY fecha_falla
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS horas_de_vida
FROM ordenes_trabajo
WHERE estado = 'cerrada' AND NOT requiere_revision;
```

Sin `security_invoker` la vista correría con los permisos de su dueño y saltaría RLS. Guardia de CI:
ninguna vista del esquema público sin `security_invoker=true`.

### 7.10 Permisos

```sql
GRANT SELECT, INSERT, UPDATE ON ordenes_contador TO app_user;
GRANT SELECT, INSERT ON orden_eventos TO app_user;
GRANT SELECT ON v_intervalos_entre_fallas TO app_user;
REVOKE DELETE ON ordenes_trabajo FROM app_user;
REVOKE DELETE ON ordenes_contador FROM app_user;
REVOKE UPDATE, DELETE ON orden_eventos FROM app_user;
```

## 8. API de la fase

Todas bajo `/api/v1`, con sesión y dentro de `get_db`. Cada transición tiene su propia ruta.

| Método y ruta | Roles | Notas |
|---|---|---|
| `POST /activos/{id}/fallas` | Supervisor, administrador | Reporta la falla y crea la orden. Idempotente por `cliente_id`. |
| `GET /ordenes` | Técnico, supervisor, gerente, administrador | Cursor; filtros por estado (abiertas, cerradas, canceladas), equipo, componente y fechas. |
| `GET /ordenes/{id}` | Los mismos | Detalle con nombres de responsables y eventos. 404 si es de otra empresa. |
| `GET /activos/{id}/ordenes` | Los mismos | Historial del equipo. |
| `PATCH /ordenes/{id}` | Supervisor, administrador | Solo abiertas: descripción, código de error, temperatura, componente. Deja evento. |
| `POST /ordenes/{id}/en-taller` | Técnico, supervisor, administrador | Reportada a En taller. |
| `POST /ordenes/{id}/reparada` | Técnico de taller | Trabajo realizado y tipo de intervención obligatorios. |
| `POST /ordenes/{id}/cerrar` | Supervisor, administrador | Autoriza la salida; calcula el tiempo fuera de servicio. |
| `POST /ordenes/{id}/rechazar-cierre` | Supervisor, administrador | Vuelve a En taller; nota obligatoria. |
| `POST /ordenes/{id}/cancelar` | Supervisor, administrador | Desde cualquier estado abierto; motivo obligatorio. |
| `POST /ordenes/{id}/notas` | Técnico, supervisor, administrador | Nota libre; también sobre órdenes cerradas (es un evento). |
| `POST /ordenes/{id}/confirmar-horometro` | Supervisor, administrador | Quita la marca de revisión; en cerradas es corrección y la hace el administrador. |
| `POST /ordenes/{id}/correccion` | Administrador | Campos acotados, nota obligatoria, evento permanente. |
| `POST /activos/{id}/reinicio-horometro` | Administrador | 5.1. |
| `POST /lecturas/{id}/confirmar` | Supervisor, administrador | 5.3 (aquí, `PATCH /lecturas/{id}` de F2). |
| `POST /campo/lotes` | Operario, supervisor | Se agrega el tipo falla; un operario que lo envíe recibe `sin_permiso` por ítem. |

El operario no tiene acceso a las órdenes (403), pero sí ve en la pantalla del equipo si está en
falla y el número de la orden abierta.

### 8.1 Errores uniformes

| Código | Cuándo | Detalle |
|---|---|---|
| 401 | Sin sesión o expirada | El cliente renueva el token y reintenta. |
| 403 | Rol insuficiente | No revela datos de otras empresas. |
| 404 | No existe o es de otra empresa | Idéntico en ambos casos. |
| 409 | Estado cambiado, orden abierta existente o alerta ya convertida | Código estable (`orden_abierta_existente`, `estado_cambiado`, `alerta_no_disponible`) y, cuando aplica, id y número de la orden existente. |
| 422 | Cuerpo inválido o referencia que no corresponde | Una violación de llave compuesta se traduce a «referencia inválida». |
| 429 | Límite de peticiones | Con `Retry-After`. |

## 9. Aplicación web y modo sin conexión

### 9.1 Pantallas

| Ruta | Roles | Contenido |
|---|---|---|
| `/activos/[id]/falla` | Supervisor, administrador | Formulario de reporte de falla. Acepta `?alerta=id`. |
| `/ordenes` | Técnico, supervisor, gerente, administrador | Lista con pestañas Abiertas, Cerradas y Canceladas y filtros. |
| `/ordenes/[id]` | Los mismos | Detalle, línea de tiempo de eventos y panel de acciones según rol y estado. |
| `/a/[codigo]` | Todos | Aviso «En falla (OT-0012)» y botón Reportar falla para supervisor. |
| `/alertas` | Supervisor, administrador, gerente | Botón Convertir en orden en alertas pendientes o revisadas. |
| `/activos/[id]` | Administrador | Reiniciar horómetro, con confirmación explícita. |

### 9.2 Formulario de falla

- Desde el QR o desde la bandeja de alertas, el formulario se abre con el equipo (y la alerta) ya
  cargados. El horómetro muestra la última lectura y pide confirmación si el valor es menor o el
  salto es llamativo, como en la Fase 2.
- El componente es una lista con buscador; los que ya tienen una orden abierta en ese equipo aparecen
  deshabilitados con el número de la orden. El servidor sigue siendo quien decide.
- Objetivos táctiles de al menos 44 px. El `cliente_id` se genera antes del primer intento y se
  reutiliza en cada reintento.

### 9.3 Detalle de la orden y acciones por rol

- Encabezado con número, estado, equipo, componente, horómetro, temperatura, código de error y
  descripción, y una línea de tiempo con cada evento: quién (aunque esté desactivado), con qué rol,
  cuándo y la nota.
- El panel de acciones muestra solo lo que el rol y el estado permiten. Ocultar un botón es
  comodidad; la seguridad la impone el servidor.
- Antes de autorizar se muestra un resumen de lo que se va a firmar (trabajo, técnico, tipo de
  intervención y tiempo fuera de servicio).
- Si una acción responde 409, la pantalla recarga la orden y explica qué cambió.

### 9.4 Lista y actualización

Sin canal en tiempo real: lista y detalle consultan cada 30 segundos mientras la pestaña esté
visible, con `If-None-Match` (304 si nada cambió).

### 9.5 Modo sin conexión

- El formulario de falla funciona sin conexión y encola un ítem de tipo falla con su `cliente_id`. Se
  muestra como «pendiente por enviar» y no tiene número hasta llegar al servidor; el aviso debe ser
  más visible que el de una lectura.
- Caso nuevo por ítem: rechazado con motivo `orden_abierta_existente`, mostrado como «No se creó: ya
  existe OT-0009», con enlace, y sin reintento.
- Los botones de transición se deshabilitan sin conexión con un mensaje claro.

## 10. Datos de demostración

Un script de siembra (`seed_demo.py`) crea una empresa «Demo» con tres equipos, cuatro componentes y
una docena de órdenes cerradas, con horas de vida generadas desde una distribución de Weibull
conocida. Nunca se ejecuta contra una empresa real, se identifica por el nombre y se borra completa,
y la tesis debe declarar que esos datos son simulados.

## 11. Consideraciones de seguridad

### 11.1 Quién puede qué

| Acción | Operario | Supervisor | Técnico | Gerente | Administrador |
|---|---|---|---|---|---|
| Reportar falla | No | Sí | No | No | Sí |
| Ver órdenes | No | Sí | Sí | Sí | Sí |
| Editar datos de orden abierta | No | Sí | No | No | Sí |
| Pasar a En taller | No | Sí | Sí | No | Sí |
| Marcar Reparada | No | No | Sí | No | No |
| Autorizar o rechazar cierre | No | Sí | No | No | Sí |
| Cancelar | No | Sí | No | No | Sí |
| Agregar nota | No | Sí | Sí | No | Sí |
| Corregir orden cerrada | No | No | No | No | Sí |
| Reiniciar horómetro | No | No | No | No | Sí |

El administrador no puede marcar Reparada a propósito: «quién reparó» siempre es alguien con ese rol.
Esta tabla vive como un test que recorre todas las combinaciones de rol y endpoint.

### 11.2 Entradas no confiables

- `empresa_id`, quien reporta, repara y autoriza, el número, el estado y las marcas de tiempo los
  fija el servidor. Un cliente que envíe `estado` o `autorizado_por` recibe 422. Los tiempos son del
  servidor.
- Los identificadores del cuerpo se resuelven bajo RLS y, además, las referencias compuestas impiden
  que apunten a otra empresa.
- Descripciones, trabajos y notas se guardan tal cual y se muestran escapadas.

### 11.3 Defensa en profundidad

| Amenaza | Defensa | Cómo se comprueba |
|---|---|---|
| Orden de una empresa apuntando a datos de otra | Referencias compuestas más RLS con WITH CHECK | 23503 y 42501 |
| Leer órdenes, eventos, contador o vista de otra empresa | RLS habilitada y forzada; `security_invoker` | Tenant B ve cero filas; guardias de CI |
| Conexión reutilizada sin tenant | NULLIF en `app_empresa_id()` | Cero filas y sin error |
| Política vieja que amplía el acceso | Una sola política | Prueba que cuenta las políticas |
| Dos órdenes abiertas para la misma falla | Índice único parcial | 23505; concurrencia real |
| Reenvío de la cola | UNIQUE `(empresa_id, cliente_id)` | Segundo envío no crea nada |
| Estado a medias | CHECK de coherencia | 23514 |
| Modificar una orden cerrada | Trigger y corrección con evento | 23514; la corrección no se filtra |
| Alterar o borrar el historial | REVOKE más ausencia de política | 42501 |
| Dos usuarios cambian el estado a la vez | UPDATE condicionado | Una fila para uno, cero para el otro |
| Borrar órdenes | REVOKE DELETE | 42501 |

### 11.4 Auditoría y registros

- `orden_eventos` es la auditoría de negocio. Los logs técnicos nunca incluyen notas, descripciones
  ni trabajos realizados.
- Los eventos no se pueden borrar: el formulario advierte no escribir datos personales en las notas.
- Límites por usuario: 20 reportes de falla y 60 transiciones por minuto.

## 12. Consideraciones de escalabilidad

- Cada consulta empieza por `empresa_id`. «En falla» con EXISTS sobre el índice único parcial, sin
  N+1. Paginación por cursor sobre `(fecha_falla, id)`, página máxima 100.
- Transacciones cortas: nada lento dentro del commit.
- **Evento de dominio.** Al cerrar, el servicio emite `orden_cerrada (empresa_id, orden_id,
  componente_id)` después del commit y dentro del proceso. Hoy no tiene suscriptores; la Fase 4
  reajustará el modelo y añade una tarea diaria que busca cerradas no procesadas.
- Observabilidad: órdenes creadas por día, abiertas por antigüedad, tiempo medio en cada estado,
  rechazos de cierre, 409 por código e ítems de lote rechazados por `orden_abierta_existente`.

## 13. Pruebas de la fase

Los que tocan la base corren contra PostgreSQL real como `app_user`. Es también la matriz de
trazabilidad requerimiento-prueba:

| Test | Qué demuestra |
|---|---|
| `test_rnf01_orden_con_referencias_de_otra_empresa_es_rechazada` | Llaves compuestas (23503) |
| `test_rnf01_listado_y_detalle_de_ordenes_aislados_por_empresa` | B no ve órdenes de A; detalle 404 |
| `test_rnf01_eventos_y_contador_aislados_por_empresa` | RLS en las tablas auxiliares |
| `test_rnf01_sin_tenant_cero_filas_en_conexion_reutilizada` | NULLIF tras una transacción previa |
| `test_rnf01_guardia_rls_forzada_y_vistas_security_invoker` | Dos consultas de guardia con cero filas |
| `test_rf11_supervisor_reporta_falla_y_nace_orden_reportada` | Camino feliz con número y evento |
| `test_rf11_operario_no_puede_reportar_falla` | 403 |
| `test_rf11_reenvio_con_mismo_cliente_id_crea_una_sola_orden` | Idempotencia |
| `test_rf11_segundo_reporte_mismo_componente_devuelve_409` | Índice único parcial traducido |
| `test_rf11_lectura_inconsistente_marca_la_orden_para_revision` | Herencia de la marca |
| `test_rf12_numeros_correlativos_sin_huecos_tras_rollback` | Contador |
| `test_rf13_flujo_completo_reportada_a_cerrada` | Tres usuarios, tres roles |
| `test_rf13_roles_correctos_en_cada_transicion` | Recorre la tabla 11.1 completa |
| `test_rf13_transicion_desde_estado_incorrecto_devuelve_409` | UPDATE condicionado |
| `test_rf13_rechazo_exige_nota_y_conserva_trabajo_anterior` | Evento con datos |
| `test_rf13_cancelar_libera_componente_y_alerta` | Los dos índices parciales |
| `test_rf14_historial_muestra_quien_reporto_reparo_y_autorizo` | Nombres, también de desactivados |
| `test_rf15_cierre_calcula_tiempo_fuera_de_servicio` | Valor y no negativo |
| `test_rf16_alerta_se_convierte_una_vez_y_vuelve_a_revisada` | Estado de la alerta; de otro equipo: 422 |
| `test_rnf06_toda_transicion_deja_evento_con_usuario_y_rol` | Auditoría |
| `test_rnf06_orden_cerrada_y_eventos_no_se_modifican_ni_se_borran` | Trigger, REVOKE y 42501 |
| `test_rnf06_correccion_solo_administrador_con_nota_y_evento` | Camino de excepción |
| `test_horometro_reinicio_conserva_las_horas_acumuladas` | 5.1, con captura previa al reinicio |
| `test_concurrencia_dos_cierres_simultaneos_uno_gana_otro_409` | `asyncio.gather` con dos sesiones |
| `test_concurrencia_dos_reportes_de_la_misma_falla_uno_201_otro_409` | El índice decide |
| `test_concurrencia_veinte_reportes_numeros_unicos_y_consecutivos` | Contador bajo carga |
| `test_concurrencia_reenvio_simultaneo_crea_una_sola_orden` | Idempotencia bajo carrera |
| e2e: `test_rf11_rf13_ciclo_completo_con_tres_usuarios` | Playwright con tres contextos |
| e2e: `test_rf10_falla_sin_conexion_llega_una_sola_vez` | setOffline, envío, reconexión |

## 14. Orden de implementación (semanas 7 y 8)

- **Semana 7:** migración con las deudas; servicio de órdenes (numeración, idempotencia,
  transiciones con eventos, cancelación); endpoints y permisos; reinicio del horómetro y confirmación
  de lecturas. Verificación: tests de base y de API en verde contra PostgreSQL real, incluidos los de
  concurrencia.
- **Semana 8:** frontend (formulario de falla, lista, detalle con línea de tiempo y panel de
  acciones); conversión desde alertas y aviso «en falla» en el QR; falla sin conexión; corrección
  administrativa; datos de demostración; manual. Verificación: e2e del ciclo con tres usuarios y de
  la falla sin conexión; prueba con un teléfono real.

Si el tiempo aprieta se recorta, en este orden: la conversión desde alertas en la interfaz, la falla
sin conexión, la pantalla de corrección administrativa. El reinicio del horómetro no se recorta.
**Nunca** se recortan la máquina de estados con sus roles, el historial, las llaves compuestas, RLS y
sus tests, y la inmutabilidad de las órdenes cerradas.

## 15. Definición de «hecho» para la Fase 3

- Un supervisor reporta una falla desde el QR de un equipo y se crea la orden con su número, en un
  teléfono real.
- La orden recorre Reportada, En taller, Reparada y Cerrada con tres usuarios de roles distintos, y
  el historial muestra nombre, rol y hora de cada responsable.
- Cada rol solo puede las acciones de la tabla 11.1, verificado por un test que recorre todas las
  combinaciones, y una transición desde un estado equivocado devuelve 409.
- El rechazo de cierre devuelve la orden a En taller sin perder lo que escribió el técnico; cancelar
  libera el componente y la alerta.
- El tiempo fuera de servicio se calcula al cerrar, y la orden Cerrada no se puede modificar salvo
  por la corrección administrativa, que deja evento.
- Una falla enviada sin conexión llega una sola vez al recuperar la red.
- Una orden de la empresa A no puede apuntar a datos de la B ni ser leída por la B (contra PostgreSQL
  real), y los eventos no se pueden modificar ni borrar.
- Dos usuarios que actúan a la vez sobre la misma orden o el mismo componente obtienen un resultado y
  un 409, no un estado corrupto.
- Un reinicio de horómetro conserva las horas acumuladas, y `v_intervalos_entre_fallas` devuelve los
  valores esperados con los datos de demostración.
- Las guardias de CI pasan: toda tabla con `empresa_id` con RLS forzada y toda vista con
  `security_invoker`.
- El manual describe el ciclo para cada rol, y la documentación técnica refleja la migración y las
  decisiones de la sección 4.

## 16. Material para el manual y la tesis

- Manual: un capítulo por rol (supervisor: reportar desde el QR, convertir una alerta, autorizar o
  rechazar un cierre; técnico: tomar una orden y registrar el trabajo; administrador: corregir una
  orden y reiniciar un horómetro).
- Si la tesis menciona que el historial guarda nombres de personas, citar la Ley 172-13 de
  protección de datos personales (confirmar el texto vigente).
- Documentos a actualizar: RF-13 (cinco estados), CU-03 (quién autoriza el cierre), la
  Especificación 3.3 (estado Cancelada) y la nota de CU-02 sobre «marcar el equipo en falla» (es un
  dato derivado).

## 17. Siguiente paso

La Fase 4 se apoya en lo construido aquí: `v_intervalos_entre_fallas` es su entrada, el evento
`orden_cerrada` su disparador y las horas acumuladas su unidad de medida. `orden_repuesto` debe nacer
con `empresa_id` y referencias compuestas, y el descuento de stock se suma a la transacción de cierre.

## Anexo: cómo quedó implementada en este repositorio (2026-10-14)

| Punto del documento | Implementación | Desviación y motivo |
|---|---|---|
| 7 Migración «0003» | Revisión `0007`, que **crea** `ordenes_trabajo`, `ordenes_contador` y `orden_eventos` | `0003`–`0006` ya existían, y la tabla nunca se había creado: no había nada que alterar. |
| 7 Nombres | Convención del proyecto: `uq_ordenes_trabajo_…`, `fk_…_mismo_tenant`, `ck_ordenes_trabajo_…`, `ix_ordenes_trabajo_…` | El contenido de cada restricción es el del documento. |
| 7.10 Permisos | Además de lo pedido, UPDATE **por columna** en `ordenes_trabajo` | Número, empresa, fecha de la falla y quién reportó no se pueden reescribir ni por error. Las horas acumuladas, solo al confirmar el horómetro (revisión `0008`, trigger `ot_horas_solo_al_confirmar`). |
| 6.2 / 6.3 `ON CONFLICT` | ORM en savepoint; el choque se traduce por el nombre de la restricción | Portabilidad de motor, como en F2. Ante cualquier choque se comprueba primero el reenvío. |
| 6.3 Contador | `UPDATE … ultimo = ultimo + 1` del ORM; la primera orden crea la fila | Sin `INSERT … ON CONFLICT DO UPDATE`, por la misma razón. |
| 7.7 `app.correccion` | `EstrategiaTenant.permitir_correccion` en `app.db.tenant` | Lo propio de PostgreSQL vive en la capa `app.db`. |
| 5.1 Reinicio | `activos.reiniciar_horometro`, usado por la ruta nueva **y** por la resolución `reinicio` de F2 | F2 ya tenía una entrada para el reinicio; las dos ajustan ahora el offset. |
| 5.1 Falla anterior a un reinicio (2026-10-15) | Revisión `0008`: cada reinicio guarda el offset que dejó (`lecturas_horometro.offset_resultante`); las horas de la falla usan el offset **vigente en su fecha** (`activos.offset_en`), y `confirmar-horometro` las recalcula | Con el offset de hoy, una falla capturada antes del reinicio y recibida después contaba dos veces lo acumulado antes del cambio, y confirmar no lo corregía. `test_horometro_falla_previa_al_reinicio_usa_el_offset_de_su_momento`. |
| 5.3 `POST /lecturas/{id}/confirmar` | Ya existía como `PATCH /lecturas/{id}` (F2) con `resolucion` `confirmada`, `descartada` o `reinicio`; una lectura de una orden responde 409 allí | No se duplica la ruta, y la de F2 cubre más casos que confirmar. |
| 6.4 Rechazo de cierre | Además de guardar el trabajo anterior en el evento, **vacía** las columnas de reparación | La orden no muestra como hecho un trabajo rechazado. |
| 8 `PATCH /ordenes/{id}` | El evento de la edición es de tipo `nota`, con los cambios en `datos` | La CHECK de `orden_eventos.tipo` no tiene un tipo propio para la edición. |
| 9.4 ETag | `con_etag` en `app.api.v1.comun`; el navegador revalida solo (respuesta `no-cache`) | — |
| 9.5 Falla sin conexión | Solo para el supervisor; al administrador se le pide red | `/campo/lotes` es del personal de campo (tabla de la sección 8). |
| 10 `seed_demo.py` | `tools/seed_demo.py` (superusuario, solo `localhost`) | Doce órdenes: cuatro componentes × tres fallas, todas reemplazos. |
| 12.3 Evento de dominio | `app.core.eventos_dominio`: anotado en la sesión, publicado en `after_commit` | — |

**Lo que este documento cambia de los anteriores.** La sección 16 pide actualizarlos, así que los
cuatro puntos están editados en `01` y `03` con la marca *[Actualizado en F3]* (2026-10-15):

- **RF-13** (03) define cuatro estados: son **cinco**, con **Cancelada** (decisión 1).
- **CU-03** (03) dice que autoriza el cierre «Supervisor o Gerente»: lo autorizan **supervisor o
  administrador**; el gerente es de solo lectura (decisión 2).
- **Especificación 3.3** (01): la orden admite el estado **Cancelada**, con motivo.
- **CU-02** (03), «marcar el equipo en falla»: no es un dato guardado sino **derivado** de tener una
  orden abierta.
