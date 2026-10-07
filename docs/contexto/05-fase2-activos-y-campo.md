# Fase 2: Activos y Registro de Campo — Guía Detallada de Implementación

> Transcripción de `Fase2_Activos_y_Registro_de_Campo_SIMAP.pdf` (ITLA, TDS — Proyecto Final de
> Grado). Fuente de verdad del **alcance y los criterios de aceptación** de la fase F2 en
> `docs/PLAN.yaml`. Donde este documento contradice a `02-arquitectura.md`, manda este.
>
> **Notas de adaptación a este repositorio** (al final de cada sección afectada, en citas como esta):
> el documento numera su migración como `0002`, pero aquí ya existen `0002`–`0004` de la fase 1, y
> asume que las tablas de negocio ya existen (las altera con `ALTER TABLE`); aquí la fase 1 solo creó
> `empresas`, `usuarios`, `intentos_login` y las del plano de control, así que la migración de esta
> fase **crea** las tablas ya con la forma final.

## 1. Objetivo de la fase

Dar al operario y al supervisor una razón real para usar SIMAP todos los días, incluso antes de que
exista predicción: registrar los equipos, identificarlos con un código QR y capturar desde el teléfono
lecturas de horómetro y alertas de síntomas, también sin conexión. Esta fase produce los datos de los
que depende todo el modelo predictivo (las horas de operación entre fallas), así que la integridad de
lo que se captura pesa tanto como que la captura funcione.

## 2. Alcance

Requerimientos que cubre: **RF-04 a RF-10, RNF-03 y RNF-05**; RNF-01 y RNF-06 de forma transversal.

**Incluye:**
- Catálogo de componentes por empresa, con una plantilla inicial que se carga al crear la empresa.
- CRUD de activos con ficha técnica, baja lógica y código QR único por equipo.
- Etiqueta imprimible (QR más código corto de respaldo) y pantalla del equipo al escanear.
- Registro de lecturas de horómetro y de alertas de síntomas, con validaciones de coherencia.
- Revisión de alertas por el supervisor (revisada o descartada).
- Captura sin conexión con sincronización automática e idempotente.

**No incluye (fases posteriores):**
- Reporte de falla y órdenes de trabajo (Fase 3); el estado `convertida_en_orden` de las alertas se
  habilita ahí.
- Cálculo de riesgo y alertas automáticas del sistema, e inventario de repuestos (Fase 4).
- Paneles de indicadores (Fase 5).

## 3. Puerta de entrada: qué debe estar verificado antes de empezar

Las tablas y endpoints de esta fase son los primeros que guardan datos reales de negocio. Si el
aislamiento entre empresas no está demostrado, cada tabla nueva hereda ese riesgo. Antes de escribir
la primera línea de la Fase 2 se verifica:

- La tarea RNF-01 está cerrada contra PostgreSQL real: dos empresas con un usuario cada una y un test
  que demuestra aislamiento de lectura y de escritura.
- El backend se conecta como `app_user` (sin privilegios de superusuario ni de propietario) y las
  tablas tienen `ENABLE` y `FORCE ROW LEVEL SECURITY`.
- Una consulta sin tenant fijado devuelve cero filas, también en una conexión reutilizada del pool
  (ver 8.5: `current_setting` devuelve cadena vacía, no NULL, cuando la conexión ya fijó el parámetro
  antes).
- Está resuelta la decisión de dominios y cookies entre frontend y backend (ver 8.2): los formularios
  de esta fase son los primeros que llaman al API desde el navegador en producción.

Si algún punto no se cumple, se corrige primero. Es mucho más barato que arreglarlo con diez tablas
encima.

## 4. Cambios al modelo de datos

Todos los cambios son aditivos: columnas nuevas con valor por defecto o nulas, restricciones e índices
nuevos. Ninguna columna existente se elimina ni se renombra. Se escriben como migración de Alembic,
nunca como SQL manual.

### 4.1 Columnas y restricciones nuevas (SQL equivalente)

```sql
-- Claves candidatas para las referencias compuestas (ver 4.2)
ALTER TABLE usuarios ADD CONSTRAINT usuarios_empresa_id_id_unq UNIQUE (empresa_id, id);
ALTER TABLE activos  ADD CONSTRAINT activos_empresa_id_id_unq  UNIQUE (empresa_id, id);

ALTER TABLE activos
  ADD COLUMN marca TEXT,
  ADD COLUMN modelo TEXT,
  ADD COLUMN numero_serie TEXT,
  ADD COLUMN fecha_instalacion DATE,
  ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','baja')),
  ADD COLUMN dado_de_baja_en TIMESTAMPTZ,
  ADD COLUMN horometro_actualizado_en TIMESTAMPTZ;

ALTER TABLE lecturas_horometro
  ADD COLUMN cliente_id UUID NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN capturado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN requiere_revision BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN motivo_revision TEXT,
  ADD CONSTRAINT lectura_valor_valido CHECK (valor_horometro >= 0),
  ADD CONSTRAINT lectura_idempotente UNIQUE (empresa_id, cliente_id);

ALTER TABLE alertas
  ADD COLUMN cliente_id UUID NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN capturado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD CONSTRAINT alerta_sintoma_valido CHECK (sintoma IN
    ('ruido','vibracion','calor','olor','fuga','otro')),
  ADD CONSTRAINT alerta_idempotente UNIQUE (empresa_id, cliente_id);

ALTER TABLE componentes
  ADD COLUMN activo BOOLEAN NOT NULL DEFAULT true,
  ADD CONSTRAINT componente_nombre_unico UNIQUE (empresa_id, nombre);
```

- `cliente_id` es la clave de idempotencia: lo genera el dispositivo y es único solo dentro de la
  empresa. No se usa como llave primaria a propósito: un conflicto de llave primaria delataría la
  existencia de ese UUID en otra empresa.
- `capturado_en` es el momento en que el operario capturó el dato (puede ser horas antes de llegar al
  servidor); `fecha` sigue siendo el momento de recepción. Los cálculos del modelo usan `capturado_en`.
- El código de síntoma se guarda sin tildes (`vibracion`) y se traduce en la interfaz.

> **Adaptación:** migración `0005`, que crea `componentes`, `activos`, `lecturas_horometro` y
> `alertas` directamente con estas columnas y restricciones.

### 4.2 Referencias compuestas: el hueco que RLS no cubre

PostgreSQL comprueba las llaves foráneas ignorando RLS (lo documenta así para preservar la integridad
referencial). Como cada tabla hija lleva su propio `empresa_id`, nada impediría guardar una fila con
`empresa_id = A` que apunte a un `activo_id` de la empresa B: la política de la fila hija se cumple, y
la llave foránea, que no ve RLS, también. La solución es que la llave foránea incluya el
`empresa_id`, de modo que la propia base garantice que hijo y padre pertenecen a la misma empresa:

```sql
ALTER TABLE lecturas_horometro
  DROP CONSTRAINT lecturas_horometro_activo_id_fkey,
  ADD  CONSTRAINT lecturas_activo_mismo_tenant
       FOREIGN KEY (empresa_id, activo_id) REFERENCES activos (empresa_id, id);
-- Igual para alertas.activo_id y para registrado_por / reportado_por (contra usuarios).
```

El mismo patrón se aplica a todas las tablas hijas de las fases 3 y 4 (órdenes de trabajo,
repuestos). `orden_repuesto` no tiene `empresa_id`: conviene añadírselo por esta misma razón.

### 4.3 Índices

```sql
CREATE INDEX idx_lecturas_activo_captura ON lecturas_horometro (empresa_id, activo_id, capturado_en DESC);
CREATE INDEX idx_alertas_activo_fecha    ON alertas (empresa_id, activo_id, fecha DESC);
CREATE INDEX idx_alertas_pendientes      ON alertas (empresa_id, fecha DESC) WHERE estado = 'pendiente';
CREATE INDEX idx_activos_empresa_estado  ON activos (empresa_id, estado);
```

El primero sirve a la consulta más frecuente del sistema (la última lectura de un equipo y su
historial); el índice parcial hace barata la bandeja de pendientes del supervisor aunque la tabla
acumule años de alertas ya revisadas.

### 4.4 Políticas RLS para las tablas de la fase

Cada tabla con `empresa_id` se protege en la misma migración que la crea o la modifica: nunca existe
una tabla multiempresa sin RLS, ni siquiera durante un commit. La lectura del tenant se centraliza en
una función para que la corrección (`NULLIF`, ver 8.5) viva en un solo lugar; envolverla en un
`SELECT` hace que PostgreSQL la evalúe una vez por consulta y no una vez por fila.

```sql
CREATE OR REPLACE FUNCTION app_empresa_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.empresa_id', true), '')::uuid $$;

ALTER TABLE lecturas_horometro ENABLE ROW LEVEL SECURITY;
ALTER TABLE lecturas_horometro FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_lecturas ON lecturas_horometro
  USING      (empresa_id = (SELECT app_empresa_id()))
  WITH CHECK (empresa_id = (SELECT app_empresa_id()));
-- Repetir para: componentes, activos y alertas, y re-crear con esta misma expresión las políticas
-- ya existentes de empresas y usuarios.
```

Además, un **test de guardia** corre en CI y debe devolver cero filas. Convierte «no olvidar RLS» en
una regla que falla sola:

```sql
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND EXISTS (SELECT 1 FROM information_schema.columns col
              WHERE col.table_schema = 'public' AND col.table_name = c.relname
                AND col.column_name = 'empresa_id')
  AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
```

## 5. API de la fase

Todas las rutas viven bajo `/api/v1`, requieren sesión válida y se ejecutan dentro de `get_db`, que
fija el tenant. Cada endpoint declara sus roles de forma explícita.

| Método y ruta | Roles | Notas |
|---|---|---|
| `GET /componentes` | Todos | Solo activos; el administrador puede incluir inactivos. |
| `POST /componentes` | Administrador | Nombre único por empresa. |
| `PATCH /componentes/{id}` | Administrador | Renombrar o desactivar; no se borra (lo referencian las órdenes). |
| `GET /activos` | Todos | Paginación por cursor; filtros por estado, tipo, ubicación y texto. |
| `POST /activos` | Administrador | Genera el código QR único. |
| `GET /activos/{id}` | Todos | 404 si pertenece a otra empresa. |
| `PATCH /activos/{id}` | Administrador | No permite cambiar `qr_code` ni `empresa_id`. |
| `POST /activos/{id}/baja` | Administrador | Baja lógica; el código sigue resolviendo. |
| `POST /activos/{id}/regenerar-codigo` | Administrador | Opcional: etiqueta comprometida; el código anterior deja de resolver. |
| `GET /activos/por-codigo/{codigo}` | Todos | 404 uniforme; con límite de peticiones. |
| `GET /activos/{id}/etiqueta.svg` | Administrador, supervisor | QR con código corto y nombre. |
| `POST /activos/{id}/lecturas` | Operario, supervisor | Idempotente por `cliente_id`. |
| `GET /activos/{id}/lecturas` | Supervisor, administrador, gerente | Paginado por cursor. |
| `POST /activos/{id}/alertas` | Operario, supervisor | Con deduplicación (5.2). |
| `GET /alertas` | Supervisor, administrador, gerente; operario solo las propias | Filtro por estado y activo. |
| `PATCH /alertas/{id}` | Supervisor, administrador | Estado: revisada o descartada. |
| `POST /campo/lotes` | Operario, supervisor | Cola sin conexión; resultado por ítem (5.3). |

### 5.1 Reglas de negocio del horómetro

- El valor es un entero entre 0 y un máximo configurable (`HOROMETRO_MAX`, por ejemplo 1.000.000).
- `capturado_en` lo envía el dispositivo. El servidor lo acepta si no está en el futuro (tolerancia de
  5 minutos) ni tiene más de 14 días; si no, rechaza el ítem con un motivo claro.
- Una lectura se guarda **marcada** (`requiere_revision`, con su motivo) si es menor que la lectura
  anterior según `capturado_en`, si es mayor que una lectura posterior ya existente (llegada fuera de
  orden), o si el incremento supera las horas de calendario transcurridas entre ambas capturas más
  una tolerancia: una máquina no puede acumular más horas de operación que las que han pasado en el
  reloj.
- Solo las lecturas sin marca actualizan `activos.horometro_actual`. Una lectura marcada se conserva
  (el dato del operario nunca se pierde), pero no mueve el valor vigente hasta que un supervisor la
  confirme. Protege contra el error humano más común: un dígito de más.
- Cambio o reinicio de horómetro: en esta fase se trata como lectura marcada; la gestión explícita (un
  evento «horómetro reiniciado» registrado por el administrador) debe resolverse antes de la Fase 4.

La escritura es una sola transacción: se inserta la lectura de forma idempotente y, solo si no está
marcada, se actualiza el valor vigente con una sentencia condicionada y atómica, sin `SELECT` previo
ni bloqueos explícitos:

```sql
INSERT INTO lecturas_horometro (empresa_id, activo_id, registrado_por, valor_horometro,
                                capturado_en, cliente_id, requiere_revision, motivo_revision)
VALUES (:empresa_id, :activo_id, :usuario_id, :valor, :capturado_en, :cliente_id, :marcada, :motivo)
ON CONFLICT (empresa_id, cliente_id) DO NOTHING
RETURNING id;   -- sin fila: era un duplicado, responder con la existente

UPDATE activos SET horometro_actual = :valor, horometro_actualizado_en = :capturado_en
WHERE id = :activo_id AND :valor >= horometro_actual;   -- solo si no está marcada
```

### 5.2 Reglas de negocio de las alertas

- El síntoma pertenece a una lista cerrada (ruido, vibración, calor, olor, fuga, otro); la nota es
  opcional y de hasta 500 caracteres.
- **Deduplicación:** la misma persona, sobre el mismo equipo y con el mismo síntoma dentro de una
  ventana (`ALERTA_DEDUP_MINUTOS`, por ejemplo 10) cuenta como duplicado y no crea una fila nueva.
  Razón: en la Fase 4 las alertas recientes multiplican el riesgo calculado, y un botón atascado o una
  persona insistiendo no debe poder inflar el riesgo de un equipo.
- Estados: `pendiente` pasa a `revisada` o `descartada`, solo por supervisor o administrador. Las
  alertas nunca se borran.
- Un operario solo ve las alertas que él mismo reportó.

### 5.3 Sincronización en lote

Para la cola sin conexión, un solo endpoint recibe hasta 50 ítems y procesa cada uno con su propio
savepoint: un ítem inválido no tumba al resto. La respuesta informa el resultado por ítem (creado,
duplicado o rechazado con su motivo) para que el dispositivo sepa cuáles quitar de su cola.

```http
POST /api/v1/campo/lotes
{ "items": [
  { "tipo": "lectura", "cliente_id": "9f1c...", "activo_id": "c3a9...",
    "valor": 4821, "capturado_en": "2026-10-12T14:03:00Z" },
  { "tipo": "alerta", "cliente_id": "2b7e...", "activo_id": "c3a9...",
    "sintoma": "ruido", "nota": "Golpeteo al arrancar", "capturado_en": "2026-10-12T14:05:00Z" } ] }

200 OK
{ "resultados": [
  { "cliente_id": "9f1c...", "estado": "creado" },
  { "cliente_id": "2b7e...", "estado": "duplicado" } ] }
```

## 6. Código QR: generación, resolución y etiqueta

### 6.1 El código
- Ocho caracteres de un alfabeto de 32 símbolos sin ambiguos (sin I, O, 0 ni 1): 32⁸, más de un millón
  de millones de combinaciones.
- Se genera con un generador criptográfico (`secrets`), nunca con `random` ni con un contador: un
  código secuencial permitiría recorrer los equipos de todas las empresas.
- El QR codifica únicamente la URL `{APP_BASE_URL}/a/{código}`. Nada del equipo, ningún `empresa_id`.
- El código corto impreso bajo el QR es el mismo valor, en grupos (`XK7P-2QH9`). Al teclearlo se
  normaliza: mayúsculas, sin guion ni espacios.
- `qr_code` tiene un índice UNIQUE global. Si el INSERT falla por duplicado se reintenta con otro
  código (hasta 5 veces); el error de base de datos nunca llega al cliente.

```python
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I, O, 0, 1

def generar_codigo(largo: int = 8) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))

def qr_svg(codigo: str, base_url: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4)
    qr.add_data(f"{base_url}/a/{codigo}")
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    ...
```

### 6.2 Resolución del código
- `GET /activos/por-codigo/{codigo}` se ejecuta bajo RLS: un usuario de otra empresa recibe **404**,
  igual que si el código no existiera. Nunca 403, porque confirmaría que el código existe.
- Con límite de peticiones por usuario (por ejemplo 30 por minuto) para frenar el barrido de códigos.
- Un equipo dado de baja sigue resolviendo, con su estado visible.

### 6.3 Etiqueta física
- Salida en SVG con QR, código corto y nombre del equipo.
- Corrección de errores nivel Q (25 %) y margen blanco de al menos 4 módulos.
- Tamaño mínimo recomendado de 3 × 3 cm, material resistente, superficie plana y visible, lejos del
  calor. Antes de imprimir todas, probar el escaneo a unos 50 cm con el teléfono real del personal.
- Reimprimir no cambia el código. Si una etiqueta fue copiada o comprometida, el administrador
  regenera el código y el anterior deja de resolver.

## 7. Aplicación web y modo sin conexión

### 7.1 Pantallas de la fase

| Ruta | Roles | Contenido |
|---|---|---|
| `/a/[codigo]` | Todos | Pantalla de aterrizaje al escanear (7.2). |
| `/activos` | Supervisor, administrador, gerente | Lista paginada con filtros. |
| `/activos/nuevo` y `/activos/[id]/editar` | Administrador | Alta y edición con ficha técnica. |
| `/activos/[id]/etiqueta` | Administrador, supervisor | Vista de impresión del QR. |
| `/componentes` | Administrador | Catálogo editable. |
| `/alertas` | Supervisor, administrador, gerente | Bandeja con filtros por estado. |

### 7.2 Pantalla de aterrizaje del QR
- Muestra primero nombre, ubicación y última lectura con su fecha: quien escanea confirma que la
  etiqueta corresponde a la máquina que tiene delante.
- Sin sesión, redirige a `/login?next=/a/CODIGO`. El destino `next` se valida: solo rutas relativas
  internas (una sola barra inicial), nunca URLs completas, para evitar open redirect.
- Botones según el rol: el operario ve Registrar horómetro y Reportar alerta; el supervisor, además, el
  historial (y desde la Fase 3, Reportar falla); el gerente solo consulta.
- RNF-03: del escaneo al envío, tres pasos como máximo.

### 7.3 Formularios de campo
- Horómetro: un campo numérico (`inputMode="numeric"`) con la última lectura al lado. Si el valor es
  menor que la última lectura o el salto es llamativo, la app pide confirmar antes de enviar.
- Alerta: los síntomas son botones grandes de un toque, no listas desplegables; la nota es opcional.
- Objetivos táctiles de al menos 44 px, alto contraste y legibles con guantes y bajo luz solar.
- Cada envío genera en el dispositivo un `cliente_id` (`crypto.randomUUID()`) antes del primer
  intento, y ese mismo identificador se reutiliza en cualquier reintento.

### 7.4 Escaneo
- Cámara nativa: el QR abre la URL directamente.
- Escáner dentro de la app (html5-qrcode) como alternativa: el contenido leído se valida con una
  expresión estricta (origen propio, ruta `/a/` y código de 8 caracteres del alfabeto) antes de
  navegar.
- `getUserMedia` exige contexto seguro (HTTPS): para probar en un teléfono por la red local hace falta
  HTTPS (servidor de desarrollo con HTTPS o un túnel como cloudflared).

### 7.5 Modo sin conexión
Recorrido: (1) el operario escanea el QR → (2) la app muestra el equipo → (3) el operario envía su
reporte y el dispositivo genera un `cliente_id` → (4) sin conexión: cola local en IndexedDB ligada al
usuario que capturó → (5) vuelve la conexión: envío en lote a `POST /campo/lotes` (máx. 50) → (6) el
servidor valida e ignora duplicados (RLS + `ON CONFLICT (empresa_id, cliente_id)`).

- Alcance: la aplicación abre sin conexión (cascarón estático precargado), los formularios de
  horómetro y alerta funcionan y encolan, y se muestra el último dato guardado del equipo escaneado,
  marcado como no actualizado.
- La cola vive en IndexedDB (Dexie o idb). Cada ítem guarda `cliente_id`, tipo, datos, `capturado_en`,
  `usuario_id`, `empresa_id`, número de intentos y estado.
- Disparadores de sincronización: evento `online`, regreso a primer plano (`visibilitychange`),
  arranque de la app y un temporizador con retroceso exponencial mientras queden ítems. No se depende
  de la Background Sync API (no está en iOS ni en Safari).
- Antes de reenviar se renueva el access token si expiró. Si el refresh token también expiró, la cola
  se conserva y se envía después de volver a iniciar sesión.
- La cola pertenece a un usuario: en un teléfono compartido solo se envían los ítems del usuario con
  sesión activa; los de otras personas esperan y se descartan, con aviso, pasados 7 días.
- Al cerrar sesión se borran las cachés de datos de equipos, no la cola de pendientes.
- El service worker precarga solo recursos estáticos versionados. Las respuestas autenticadas del API
  nunca se guardan en su caché compartida.
- iOS puede purgar el almacenamiento de un sitio usado solo en pestañas de Safari: instalar la PWA y
  solicitar `navigator.storage.persist()`.
- Indicadores siempre visibles: «Sin conexión», «3 pendientes por enviar», «Enviado».

### 7.6 Herramientas a revisar al inicio de la fase
`next-pwa` lleva tiempo sin mantenimiento y no está pensado para el App Router; Serwist
(`@serwist/next`) es su sucesor. Verificar el estado de ambos y decidir. Dependencias nuevas del
frontend: Dexie (o idb), html5-qrcode y el paquete de service worker elegido. En el backend no se
necesita nada fuera de lo ya listado (`qrcode` ya está).

## 8. Consideraciones de seguridad

### 8.1 Autorización de las acciones de campo
- El rol se verifica en cada endpoint. Lecturas y alertas son de solo adición para el operario.
- Defensa en profundidad opcional: que la base haga de solo adición la tabla de lecturas:
  `REVOKE UPDATE, DELETE ON lecturas_horometro FROM app_user;`
  `GRANT UPDATE (requiere_revision, motivo_revision) ON lecturas_horometro TO app_user;`

### 8.2 Cookies, dominios y CSRF
En desarrollo, `localhost:3000` y `localhost:8000` son del mismo sitio. En producción, el frontend en
Vercel y el backend en Railway están en dominios distintos: con `SameSite=Strict` o `Lax` la cookie no
se envía en los fetch del frontend hacia el API, y con `SameSite=None` queda expuesta a CSRF y al
bloqueo de cookies de terceros. Resultado típico: el login responde bien pero la sesión no persiste.

- **Opción recomendada:** que el navegador hable solo con el origen del frontend, y que Next.js
  reenvíe `/api/*` al backend mediante *rewrites*. Elimina CORS, mantiene la cookie en el mismo sitio
  y permite `SameSite=Strict` o `Lax`.
- Con dominio propio: subdominios (`app.dominio.com`, `api.dominio.com`) y cookie con
  `Domain=.dominio.com`.
- En ambos casos, los métodos que modifican datos verifican que la cabecera `Origin` sea la esperada.

### 8.3 Entradas no confiables
- Todo lo que llega del dispositivo es no confiable. `empresa_id` y `usuario_id` nunca vienen en el
  cuerpo: salen del token.
- Pydantic estricto: listas cerradas, longitudes máximas, rangos y rechazo de campos desconocidos.
  Límite de tamaño del cuerpo y de ítems por lote.
- Notas y descripciones se guardan tal cual y se muestran escapadas; prohibido
  `dangerouslySetInnerHTML` con datos de usuarios.

### 8.4 Límites de peticiones detrás de un proxy
- Límite por usuario en lecturas, alertas y lotes (por ejemplo 60 por minuto).
- Detrás de Railway o de los rewrites de Next.js, el servidor ve la IP del proxy. El límite por IP debe
  leer `X-Forwarded-For` solo de proxies de confianza (`uvicorn --proxy-headers` con
  `--forwarded-allow-ips` acotado).

### 8.5 RLS en las tablas nuevas
- `current_setting('app.empresa_id', true)` devuelve NULL solo mientras la conexión nunca fijó el
  parámetro; después devuelve cadena vacía, y convertirla a uuid lanza un error (500). Con
  `NULLIF(..., '')` el resultado es NULL y la consulta devuelve cero filas. El test debe ejecutarse
  sobre una conexión reutilizada.
- `WITH CHECK` explícito en cada política.
- Referencias compuestas (4.2) y test de guardia (4.4).
- `app_user` sin privilegios de propietario y `FORCE ROW LEVEL SECURITY`; ningún test de la fase debe
  conectarse como superusuario.

## 9. Consideraciones de escalabilidad

- **9.1 Paginación por cursor** desde el primer listado (`capturado_en` o `fecha` más `id`,
  codificado), nunca `OFFSET`. Tamaño máximo de página (por ejemplo 100); respuesta con `items` y
  `next_cursor`.
- **9.2 Consultas e índices:** la última lectura sale del índice con `LIMIT 1`; el valor vigente está
  desnormalizado en `activos.horometro_actual`, sin JOIN ni N+1. `horometro_actualizado_en` permite
  detectar equipos sin lecturas recientes. `EXPLAIN ANALYZE` antes de añadir índices; nada de
  `SELECT *` en listados.
- **9.3 Crecimiento:** `lecturas_horometro` es de solo adición (~146.000 filas/año/empresa con 200
  equipos). No se particiona ahora.
- **9.4 Escritura concurrente** sin bloqueos largos: el `UPDATE` condicionado es atómico.
- **9.5 Etiquetas y QR** generados al vuelo, con ETag y `Cache-Control` privado.
- **9.6 Migraciones sin tiempo de inactividad:** patrón expandir y contraer.
- **9.7 Observabilidad:** logs estructurados con `request_id`, `empresa_id` y `usuario_id` (nunca
  contraseñas, tokens ni notas) y métricas: lotes, ítems creados, duplicados, rechazados y lecturas
  marcadas.

## 10. Pruebas de la fase

| Test | Qué demuestra |
|---|---|
| `test_rnf01_listado_de_activos_aislado_por_empresa` | Un usuario de B no ve activos de A. |
| `test_rnf01_codigo_qr_de_otra_empresa_devuelve_404` | Resolución uniforme, sin filtrar existencia. |
| `test_rnf01_no_puede_crear_lectura_sobre_activo_ajeno` | La FK compuesta y RLS rechazan la escritura cruzada. |
| `test_rnf01_sin_tenant_cero_filas_en_conexion_reutilizada` | `NULLIF` funciona tras una transacción previa. |
| `test_rnf01_tablas_con_empresa_id_tienen_rls_forzada` | Consulta de guardia con cero filas. |
| `test_rf05_codigo_qr_unico_aleatorio_sin_ambiguos` | Alfabeto, longitud y reintento por colisión. |
| `test_rf06_activo_dado_de_baja_sigue_resolviendo` | Baja lógica; el QR sigue respondiendo. |
| `test_rf08_lectura_con_mismo_cliente_id_crea_una_sola_fila` | Idempotencia. |
| `test_rf08_lectura_menor_queda_marcada_y_no_mueve_el_valor` | Protección contra errores de digitación. |
| `test_rf08_llegada_fuera_de_orden_no_retrocede_el_horometro` | UPDATE condicionado. |
| `test_rf09_alerta_duplicada_en_ventana_no_se_crea` | Deduplicación. |
| `test_rf09_operario_no_ve_alertas_ajenas` | Autorización por propietario. |
| `test_rf10_lote_con_item_invalido_no_afecta_a_los_demas` | Savepoint por ítem. |
| e2e: `test_rf10_envio_sin_conexion_llega_una_sola_vez` | Playwright con `setOffline(true)`, envío, reconexión. |
| e2e: `test_rnf03_escaneo_a_envio_en_tres_pasos` | Flujo completo desde `/a/[codigo]`. |
| unit (frontend): parser de QR y destino `next` | Rechazan URLs ajenas, absolutas y códigos mal formados. |

## 11. Orden de implementación sugerido (semanas 3 a 6)

| Semana | Entregable | Verificación |
|---|---|---|
| 3 | Puerta de entrada cerrada; migración, función y políticas RLS, test de guardia; componentes con plantilla inicial; CRUD de activos y baja lógica. | Tests de aislamiento contra PostgreSQL real en verde. |
| 4 | Generación y resolución de QR y etiqueta SVG; lecturas y alertas con validaciones, idempotencia y deduplicación; revisión de alertas. | Tests rf05, rf06, rf08 y rf09. |
| 5 | Frontend: lista y ficha de activos, etiqueta, aterrizaje del QR, formularios de campo y bandeja de alertas. | E2E del camino feliz con red. |
| 6 | Modo sin conexión (cola, lote, indicadores); pruebas en teléfonos reales (iOS y Android); pulido y manual de usuario. | E2E sin conexión y prueba de campo con etiqueta impresa. |

## 12. Definición de «hecho» para la Fase 2

- [ ] Un operario escanea el QR de un equipo con la cámara nativa y llega a la pantalla del equipo en
      un teléfono real.
- [ ] Registra una lectura de horómetro y una alerta en no más de tres pasos.
- [ ] El mismo envío hecho sin conexión llega una sola vez al recuperar la red, aunque se reintente.
- [ ] Un usuario de otra empresa recibe 404 con ese código y no puede referenciar ese equipo desde sus
      propias filas (verificado contra PostgreSQL real).
- [ ] Una lectura inconsistente se guarda marcada para revisión y no altera `horometro_actual`.
- [ ] Las alertas repetidas no se multiplican, y solo supervisor o administrador las revisan.
- [ ] Una etiqueta impresa se escanea correctamente a unos 50 cm con el teléfono más modesto.
- [ ] Todas las tablas con `empresa_id` pasan el test de guardia en CI.
- [ ] La sesión persiste en producción entre frontend y backend (dominios y cookies resueltos).
- [ ] El manual de usuario describe las pantallas de campo, y la documentación técnica refleja la
      migración.

## 13. Siguiente paso

La Fase 3 (Órdenes de Trabajo) reutiliza lo construido aquí: `capturado_en`, el patrón de referencias
compuestas y el vínculo `alerta_origen_id`. La bandeja de alertas del supervisor es el punto de
partida natural del reporte de falla.

---

## Anexo: cómo quedó implementada en este repositorio (2026-10-07)

| Punto del documento | Implementación | Desviación y motivo |
|---|---|---|
| 4 Migración «0002» | Revisiones `0005` (tablas, RLS, FK compuestas, solo adición) y `0006` (revisión de lecturas) | Numeración: `0002`–`0004` ya eran de la fase 1. Las tablas se **crean** con su forma final porque la fase 1 no las había creado. |
| 4.4 `app_empresa_id()` | Creada; las políticas de `empresas` y `usuarios` se recrearon con ella y `WITH CHECK` | — |
| 5.1 `INSERT … ON CONFLICT` | ORM dentro de un savepoint; la restricción UNIQUE decide igual | `ON CONFLICT` es sintaxis de PostgreSQL y el proyecto exige poder cambiar de motor. |
| 5.1 «hasta que un supervisor la confirme» | `PATCH /lecturas/{id}` con `confirmada`, `descartada` o `reinicio`; bandeja en `/alertas` | El reinicio del horómetro (pedido «antes de F4») se registra así, solo por el administrador. |
| 5 `alertas` | Añadidas `revisada_por` y `revisada_en` | Quién descartó una alerta tiene consecuencias en el riesgo de F4. |
| 6.3 Etiqueta | `GET /activos/{id}/etiqueta.svg` con ETag, `Cache-Control: private` y CSP propia | — |
| 7.1 `/a/[codigo]` | Página estática `/equipo` servida en `/a/:codigo` por reescritura | Así el service worker guarda **un** cascarón que sirve para todas las etiquetas sin conexión. |
| 7.4 html5-qrcode | `BarcodeDetector` del navegador, con jsQR donde no existe | html5-qrcode no publica versiones desde 2023. |
| 7.6 next-pwa / Serwist | Service worker propio (`public/sw.js`) y cola con `idb` | next-pwa no publica desde 2022; lo necesario es acotado y así no hay caché de API por accidente. |
| 8.2 Cookies | Next reenvía `/api/*` al backend; el navegador solo habla con un origen. `Origin` comprobado en métodos que escriben | — |
| 8.4 Límites | Por usuario (campo 60/min, resolución de códigos 30/min) | — |
| Plantilla de componentes | Ocho componentes genéricos, en la misma transacción que el alta de empresa; `POST /componentes/plantilla` para empresas anteriores | — |
| RF-03 | Gestión de personal por el administrador (`/panel/usuarios`) | Estaba asignado a F1 sin tarea que lo construyera. |

Pendiente, fuera del alcance de lo automatizable: prueba con teléfonos reales y etiqueta impresa a 50 cm, y verificación en producción (Vercel + Railway) de que la sesión persiste.
