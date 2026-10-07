# SIMAP — Sistema Inteligente de Mantenimiento Predictivo

Proyecto Final de Grado (ITLA, asignatura TDS). Documentación **técnica** del proyecto. Para la guía
de usuario final ver [README_USER.md](README_USER.md) y [MANUAL_USUARIO.md](MANUAL_USUARIO.md).

SIMAP predice el riesgo de falla de equipos industriales a partir de dos fuentes que cualquier empresa
puede capturar sin depender del fabricante: las **horas de operación (horómetro)** y los **reportes del
personal de planta** vía código QR. Sobre eso gestiona alertas, órdenes de trabajo con trazabilidad e
inventario de repuestos, en una arquitectura **multi-tenant** con aislamiento por Row-Level Security.

## Documentos de contexto (fuente de verdad)

| Documento | Contenido |
|---|---|
| [docs/contexto/01-especificacion-funcional.md](docs/contexto/01-especificacion-funcional.md) | Módulos, roles, modelo de Weibull, modelo de datos conceptual |
| [docs/contexto/02-arquitectura.md](docs/contexto/02-arquitectura.md) | Stack completo, seguridad (RLS, JWT, RBAC), empaquetado y despliegue |
| [docs/contexto/03-requerimientos-casos-de-uso.md](docs/contexto/03-requerimientos-casos-de-uso.md) | RF-01..28, RNF-01..08, CU-01..06 y plan por fases |
| [docs/contexto/04-fase1-fundamentos.md](docs/contexto/04-fase1-fundamentos.md) | Alcance de F1: auth, multi-tenant, RLS y su definición de «hecho» |
| [docs/contexto/05-fase2-activos-y-campo.md](docs/contexto/05-fase2-activos-y-campo.md) | Alcance de F2: activos, QR, horómetro, alertas, sin conexión. Anexo con cómo quedó implementada |
| [backend/db/schema.sql](backend/db/schema.sql) · [rls_policies.sql](backend/db/rls_policies.sql) | DDL de PostgreSQL y políticas de aislamiento por empresa |
| [docs/PLAN.yaml](docs/PLAN.yaml) | Las 5 fases como tareas rastreables por `graph.py status` |

> **Regla del equipo:** cada push a `main` debe dejar actualizados este README,
> `README_USER.md` y `MANUAL_USUARIO.md`. El hook `pre-push` y la GitHub Action
> `docs.yml` lo verifican (ver [Flujo de documentación](#flujo-de-documentación)).

## Stack

| Capa | Tecnología | Carpeta |
|---|---|---|
| Backend | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 async + asyncpg · Alembic · python-jose (JWT) · argon2-cffi · qrcode · scipy (Weibull) · APScheduler · redis | `backend/` |
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 · TanStack Query · react-hook-form + zod · html5-qrcode · Serwist (PWA) · Playwright | `frontend/` |
| Datos | PostgreSQL 16 con Row-Level Security · Redis 7 | `docker-compose.yml` |
| Despliegue | Docker (backend) · Railway · Vercel · Supabase · Upstash · GitHub Actions | `backend/Dockerfile`, `.github/` |
| Tooling | grimp · import-linter · dependency-cruiser · madge | `tools/graph/` |

Desviaciones respecto a `02-arquitectura.md`, decididas al montar el repo: Python 3.11 local (doc: 3.12; el
Dockerfile sí usa 3.12) · React 19 / Next 16 (doc: React 18; Next 16 exige React 19) · **Serwist** en lugar
de `next-pwa` (sin mantenimiento y sin soporte para App Router; Serwist es su sucesor).

### Dominio en dos líneas

Entidades: `empresas → usuarios | componentes | activos → lecturas_horometro | alertas | ordenes_trabajo → orden_repuesto → repuestos`.
Roles: `operario`, `supervisor`, `tecnico_taller`, `gerente`, `administrador`. Estados de orden:
`reportada → en_taller → reparada → cerrada`.

## Estructura del repositorio

```text
SIMAP/
├── backend/
│   ├── app/
│   │   ├── main.py            # create_app(): instancia FastAPI, CORS, routers
│   │   ├── api/v1/            # router.py agrega las rutas de routes/
│   │   ├── core/config.py     # Settings (pydantic-settings, lee .env)
│   │   ├── core/security.py   # Argon2id + emisión/verificación de JWT
│   │   ├── core/auth.py       # extrae y valida el token (cookie o Bearer)
│   │   ├── core/rbac.py       # requiere_roles(): permisos por endpoint
│   │   ├── core/almacen.py    # rate limiting y revocación (Redis o memoria)
│   │   ├── schemas/           # modelos Pydantic de entrada/salida
│   │   ├── services/          # lógica de negocio (sin FastAPI)
│   │   ├── db/session.py      # motor async y fábrica de sesiones (pool)
│   │   ├── db/deps.py         # get_db: valida el JWT y fija app.empresa_id
│   │   ├── db/tenant.py       # estrategia de aislamiento por motor (portabilidad)
│   │   ├── models/            # entidades SQLAlchemy (espejo de db/schema.sql)
│   │   └── jobs/              # tareas APScheduler (recalculo diario de riesgo)
│   ├── alembic/versions/      # migraciones: la ÚNICA forma de crear tablas
│   ├── db/roles.sql           # arranque: roles y pgcrypto (se ejecuta)
│   ├── db/schema.sql          # DDL de referencia + rls_policies.sql (NO se ejecutan)
│   ├── tests/                 # pytest + httpx TestClient
│   ├── Dockerfile
│   ├── pyproject.toml         # ruff, mypy, pytest, import-linter (capas)
│   └── requirements*.txt
├── frontend/
│   ├── src/app/               # App Router de Next.js
│   ├── .dependency-cruiser.cjs
│   └── package.json           # scripts graph:* / lint / build
├── tools/graph/graph.py       # CLI del grafo unificado (ver abajo)
├── docs/
│   ├── contexto/              # transcripción de los documentos del proyecto
│   ├── PLAN.yaml              # fases y tareas; alimenta `graph.py status`
│   └── diagramas/             # Mermaid auto-generado
├── docker-compose.yml         # postgres:16 + redis:7 (+ api) para desarrollo
├── .githooks/pre-push         # validación local antes de subir a main
├── .github/workflows/docs.yml # grafo + docs en cada push a main (los tests, en ci.yml)
├── README.md                  # este archivo (técnico)
├── README_USER.md             # introducción para usuarios
└── MANUAL_USUARIO.md          # manual de usuario completo
```

## Puesta en marcha

Requisitos: Python 3.11+, Node 22+, git.

```powershell
# 1) Clonar y preparar todo (venv, pip, npm, hooks)
git clone <url> SIMAP; cd SIMAP
.\tools\setup.ps1          # en Linux/macOS: ./tools/setup.sh

# 2) Infraestructura local (PostgreSQL + Redis)
#    Al inicializar solo se ejecuta backend/db/roles.sql: crea los roles y pgcrypto.
#    Las tablas NO las crea este paso.
docker compose up -d db redis

# 3) Backend
.\.venv\Scripts\Activate.ps1
cd backend; Copy-Item .env.example .env         # ajustar JWT_SECRET
alembic upgrade head                            # crea las tablas y sus politicas RLS

# 4) Sembrar el operador de SIMAP. Es el UNICO comando que hace falta, y solo esta vez:
#    a partir de aqui los clientes se dan de alta desde /operador en el navegador.
#    Pide la contrasena por teclado y no la hace eco.
python -m app.cli crear-operador --nombre "Tu Nombre" --correo tu@correo.com

# 5) Arrancar la API. COOKIE_SECURE=false en local: sin HTTPS el navegador
#    descartaria la cookie de sesion y el login no funcionaria.
$env:COOKIE_SECURE = "false"; uvicorn app.main:app --reload   # http://localhost:8000/docs

# 6) Frontend (otra terminal). El navegador habla SOLO con el frontend: Next reenvia /api/* a
#    API_ORIGEN (http://localhost:8000 por defecto). Ver «Cookies y dominios».
cd frontend; Copy-Item .env.local.example .env.local; npm run dev   # http://localhost:3000
```

Luego, en el navegador: entra en **http://localhost:3000** con el operador que acabas de sembrar
(el acceso es el mismo para todos y te lleva a la consola), da de alta una empresa cliente, y usa
la contraseña temporal que te muestra para entrar como su administrador por el mismo acceso.

## Dos planos: control y datos

SIMAP tiene dos superficies que **no se tocan**, y la separación es de arquitectura, no de interfaz.

**Una sola pantalla de acceso, `/login`, para los dos.** Con un correo y una contraseña, el
frontend prueba primero la entrada de las plantas y, si no abre, la del operador
(`src/lib/acceso.ts`); cada cuenta cae en su sitio. Por debajo nada se mezcla: son dos endpoints,
dos roles de base de datos, dos juegos de cookies y dos límites de intentos, y ningún endpoint toca
los dos planos. Si el mismo correo y la misma contraseña valen en los dos, gana la planta; con
contraseñas distintas cada una abre la suya. Un fallo cuesta dos comprobaciones de Argon2, y las dos
ramas lo pagan igual, así que el tiempo de respuesta no delata en qué plano existe un correo.
`/operador/login` redirige a `/login`.

| | Plano de control | Plano de datos |
|---|---|---|
| Quién | El operador de SIMAP (tú) | Los cinco roles dentro de una empresa |
| Tabla | `operadores` (sin `empresa_id`) | `usuarios` (con `empresa_id`) |
| Ruta | `/operador`, API `/api/v1/operador/*` (acceso por `/login`) | `/`, API `/api/v1/auth/*` |
| Cookies | `simap_op_*`, limitadas a `/api/v1/operador` | `simap_*`, en `/` |
| Rol de BD | `operador_user` | `app_user` |
| Puede leer | Empresas, sus administradores, conteo de equipos | Solo su propia empresa, vía RLS |
| **No** puede leer | **Ningún dato de negocio de ningún cliente** | Nada de otra empresa, ni el plano de control |

### Por qué no basta con una bandera en el código

Lo obvio habría sido un `es_superadmin` en `usuarios` y saltarse el Row-Level Security cuando
estuviera activo. Eso pone en internet, detrás de una contraseña, una cuenta capaz de leer los
datos de **todos** los clientes: una credencial filtrada deja de ser «una empresa comprometida» y
pasa a ser «todas». Además haría inservible la prueba que comprueba que ningún rol que atiende HTTP
puede saltarse el aislamiento.

La frontera la impone PostgreSQL con un **cuarto rol de base de datos**:

```
simap           superusuario. Ignora RLS SIEMPRE. Solo administrar.
simap_owner     dueño de las tablas. Migraciones y siembra inicial.
app_user        atiende a los clientes. Ni dueño ni superusuario.
operador_user   atiende la consola. Permisos tabla por tabla.
```

**La regla que hace que esto siga siendo cierto mañana:** a `operador_user` se le conceden permisos
**tabla por tabla**, en la migración que crea cada tabla que deba ver, y **nunca** con un
`ALTER DEFAULT PRIVILEGES` como el de `app_user`. Por eso las tablas de negocio de F2 en adelante
—activos, lecturas, alertas, órdenes, repuestos— quedan fuera de su alcance **por omisión**:
hacerlas visibles exigiría un `GRANT` explícito que se ve en la revisión del código.

Encima de los permisos, las políticas lo estrechan más: sobre `usuarios`, el operador solo alcanza
las filas con rol `administrador`. El personal de planta le es invisible.

Lo comprueba `tests/test_operador.py`, con cuatro pruebas dedicadas a la frontera: que el operador
no ve al personal de planta, que `app_user` no ve la tabla de operadores ni la bitácora, que el
operador no puede leer una tabla a la que nadie le dio permiso, y que los tokens de los dos planos
no son intercambiables en ninguna dirección.

### El alta de empresas es por invitación

SIMAP se cobra **por equipo monitoreado**, así que una empresa no puede darse de alta a sí misma:
lo haría gratis. No existe `POST /auth/register`. Esconder la ruta no habría bastado —FastAPI la
anunciaría en el esquema OpenAPI de `/docs`—, así que se retiró *y* la revisión `0002` de Alembic
estrechó la política RLS de `empresas` para que solo el rol dueño pueda insertar.

El alta se hace desde la consola, y el primer operador desde la terminal:

```powershell
# Solo la primera vez: sembrar al operador. Pide la contrasena por teclado.
python -m app.cli crear-operador --nombre "Tu Nombre" --correo tu@correo.com

# A partir de ahi, todo desde /operador en el navegador.
```

Queda además `python -m app.cli crear-empresa` para dar de alta un cliente sin pasar por la web
(automatización, recuperación, pruebas). Usa la misma función de servicio que la consola y valida
con el mismo esquema Pydantic, de modo que las reglas no pueden divergir entre los dos caminos.

### Endpoints del plano de control

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/v1/operador/login` | Abre sesión de operador. Cookies propias, limitadas a este prefijo. 429 al superar el límite |
| POST | `/api/v1/operador/cambiar-clave` | El operador cambia su propia clave. Exige la actual; queda en la bitácora |
| POST | `/api/v1/operador/logout` | Cierra sesión. No exige estar autenticado |
| GET | `/api/v1/operador/yo` | El operador de la sesión actual |
| GET | `/api/v1/operador/empresas` | Empresas con su administrador, estado y conteo de equipos |
| POST | `/api/v1/operador/empresas` | Alta de empresa + administrador. Devuelve la clave temporal |
| PATCH | `/api/v1/operador/empresas/{id}` | Renombrar |
| POST | `/api/v1/operador/empresas/{id}/suspender` | Suspender: sus usuarios reciben 403 al entrar |
| POST | `/api/v1/operador/empresas/{id}/reactivar` | Reactivar |
| POST | `/api/v1/operador/empresas/{id}/restablecer-clave` | Clave temporal nueva para el administrador |
| GET | `/api/v1/operador/bitacora` | Historial de acciones, con quién y cuándo |

**La contraseña la genera el servidor, nunca el operador.** Si quien opera SIMAP eligiera la
contraseña de su cliente, tendría acceso permanente a esa cuenta. Se muestra una sola vez y no se
guarda en claro en ningún sitio; si se pierde, se genera otra.

Toda acción del plano de control queda en `operador_bitacora`, escrita **en la misma transacción**
que la acción: o quedan las dos cosas o ninguna.

### Endpoints de autenticación (plano de datos)

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/v1/auth/login` | Valida credenciales. 429 con `Retry-After` al superar el límite |
| POST | `/api/v1/auth/refresh` | Rota el refresh token y revoca el anterior |
| POST | `/api/v1/auth/logout` | Borra cookies y revoca. No exige estar autenticado |
| POST | `/api/v1/auth/cambiar-clave` | Cambia la clave propia. Exige la actual (400 si no coincide, 429 al superar el límite) y cierra las demás sesiones |
| GET | `/api/v1/auth/yo` | Usuario de la sesión actual, leído a través de RLS |

No hay endpoint de registro: ver «Alta de empresas» más arriba.

Los tokens **nunca** viajan en el cuerpo: van en cookies `httpOnly` (`simap_access` en `/`,
`simap_refresh` restringida a `/api/v1/auth`). En desarrollo hay que poner `COOKIE_SECURE=false` o
el navegador las descartará al no haber HTTPS.

Hay una tercera cookie, `simap_sesion` (y `simap_op_sesion` en la consola), que **no es una
credencial**: vale siempre `1` y ninguna ruta de la API la lee. Es la pista que usa el `proxy.ts`
del frontend para decidir si mandar a alguien a `/login` (ver «Frontend → Desvío por sesión»).

### Esquema de base de datos

`alembic upgrade head` es la **única** forma de crear o modificar tablas; `backend/db/schema.sql` y
`backend/db/rls_policies.sql` son documentos de referencia del modelo completo y no se ejecutan.
Las migraciones corren como `simap_owner` (`DATABASE_URL_MIGRACIONES`), nunca como el superusuario:
una tabla creada por un superusuario escapa a `FORCE ROW LEVEL SECURITY`.

```powershell
alembic upgrade head            # aplicar
alembic downgrade -1            # revertir la ultima
alembic revision --autogenerate -m "descripcion"   # tras cambiar un modelo
```

`tests/test_migraciones.py` falla si los modelos y la base divergen, que es el error silencioso más
fácil de cometer: cambiar un modelo y olvidar la migración.

> **Cuidado con `INSERT ... RETURNING` bajo RLS.** Al devolver la fila, PostgreSQL le aplica además
> la política de **lectura**, no solo la de escritura. Un `INSERT INTO empresas (...) RETURNING id`
> sin tenant fijado inserta y aun así falla, porque `tenant_isolation_empresas` oculta la fila
> recién creada. El ORM no se topa con esto porque genera el UUID en Python; el SQL escrito a mano
> sí. Si necesitas el id, genéralo antes y pásalo en el `INSERT`.

> En Windows con Next.js: si `npm run dev` falla con *"Turbopack is not supported on this platform"*,
> el binario nativo de SWC no carga (Avast suele bloquearlo). Alternativa: `npx next dev --webpack`.

## Fase 2: activos y registro de campo

Fuente: [05-fase2-activos-y-campo.md](docs/contexto/05-fase2-activos-y-campo.md); su anexo final
resume dónde se apartó la implementación del documento y por qué.

### Endpoints

Todos pasan por `get_db` (RLS) y declaran sus roles con `requiere_roles`.

| Método | Ruta | Roles | Qué hace |
|---|---|---|---|
| GET | `/usuarios` | Administrador | Personal de la empresa (RF-03) |
| POST | `/usuarios` | Administrador | Alta con rol; la clave la genera el servidor y se ve una vez |
| PATCH | `/usuarios/{id}` | Administrador | Nombre, rol o baja. Nadie se degrada a sí mismo; nunca queda la empresa sin administrador |
| POST | `/usuarios/{id}/restablecer-clave` | Administrador | Clave temporal nueva; cierra sus sesiones |
| GET | `/componentes` | Todos | Catálogo; `?incluir_inactivos=true` solo para el administrador |
| POST | `/componentes` | Administrador | Nombre único por empresa (409 si se repite) |
| POST | `/componentes/plantilla` | Administrador | Añade lo que falte del catálogo inicial |
| PATCH | `/componentes/{id}` | Administrador | Renombrar o desactivar. No hay DELETE |
| GET | `/activos` | Todos | Paginado por cursor; filtros `estado`, `tipo`, `ubicacion`, `q` |
| POST | `/activos` | Administrador | Alta con código QR; `horometro_inicial` queda como primera lectura |
| GET | `/activos/por-codigo/{codigo}` | Todos | Lo que se consulta al escanear. 404 uniforme; 30/min por usuario |
| GET | `/activos/{id}` | Todos | 404 si es de otra empresa |
| PATCH | `/activos/{id}` | Administrador | Ficha técnica; rechaza `qr_code` y `empresa_id` (422) |
| POST | `/activos/{id}/baja` | Administrador | Baja lógica; el código sigue resolviendo |
| POST | `/activos/{id}/regenerar-codigo` | Administrador | El código anterior deja de resolver |
| GET | `/activos/{id}/etiqueta.svg` | Administrador, supervisor | Etiqueta imprimible con ETag |
| POST | `/activos/{id}/lecturas` | Operario, supervisor | Idempotente por `cliente_id`: 201 creada, 200 duplicada |
| GET | `/activos/{id}/lecturas` | Supervisor, administrador, gerente | Historial por cursor |
| GET | `/lecturas/por-revisar` | Supervisor, administrador | Lecturas marcadas sin resolver |
| PATCH | `/lecturas/{id}` | Supervisor, administrador | `confirmada` o `descartada`; `reinicio` solo el administrador |
| POST | `/activos/{id}/alertas` | Operario, supervisor | Con deduplicación |
| GET | `/alertas` | Operario (solo las suyas), supervisor, administrador, gerente | Bandeja por cursor |
| PATCH | `/alertas/{id}` | Supervisor, administrador | `revisada` o `descartada`, una sola vez |
| POST | `/campo/lotes` | Operario, supervisor | Cola sin conexión: hasta 50 ítems, resultado por ítem |

### Reglas del horómetro

Una lectura se guarda siempre —el dato del operario nunca se pierde—, pero queda **marcada** si es
menor que la anterior, mayor que una posterior ya registrada, o sube más horas de las que han pasado
en el reloj (más una holgura). Una lectura marcada no mueve `activos.horometro_actual` hasta que un
supervisor la resuelve (revisión 0006):

| Resolución | Quién | Efecto |
|---|---|---|
| `confirmada` | Supervisor o administrador | Cuenta como válida y, si es la más reciente, mueve el horómetro |
| `descartada` | Supervisor o administrador | Se conserva y no cuenta para nada |
| `reinicio` | Solo administrador | El horómetro se cambió o se puso a cero: empieza una serie nueva |

El horómetro vigente se mueve con un **UPDATE condicionado**, sin leer antes ni bloquear: solo
avanza, en valor y en tiempo, así que una lectura vieja que llega tarde nunca lo hace retroceder. El
reinicio es el único caso en que puede bajar. **Para F4:** las horas desde la última falla tienen que
sumar las horas de cada serie, no restar el valor actual del de la falla.

### Idempotencia y cola sin conexión

Cada captura lleva un `cliente_id` que genera el teléfono **antes** del primer intento y repite en
cada reintento; la restricción `UNIQUE (empresa_id, cliente_id)` hace que entre una sola vez. No es
la llave primaria a propósito: un choque de llave primaria delataría que ese UUID existe en otra
empresa. Se usa el ORM dentro de un savepoint y no `ON CONFLICT`, que ataría el código a PostgreSQL.

En el teléfono (`src/lib/offline-queue.ts`, IndexedDB con `idb`): la cola es de una persona —en un
aparato compartido solo se envía lo de quien tiene la sesión, y lo de otros se descarta a los 7
días—; cerrar sesión no la borra; se sincroniza al volver la red, al volver a primer plano, al
arrancar y con retroceso exponencial, sin depender de Background Sync, que no existe en iOS.
`POST /campo/lotes` procesa cada ítem en su propio savepoint y valida cada uno por separado: un ítem
malo vuelve como `rechazado` con su motivo y los demás entran.

### Lo que la base impone además de RLS

- **Referencias compuestas.** PostgreSQL comprueba las llaves foráneas ignorando RLS, así que una
  lectura de la empresa A podría colgar de un equipo de B. Las FK incluyen `empresa_id`:
  `(empresa_id, activo_id) → activos (empresa_id, id)`, y lo mismo para autor y revisor.
- **`app_empresa_id()`** lee el tenant con `NULLIF(..., '')`: una conexión del pool que ya fijó el
  parámetro devuelve cadena vacía, no NULL, y convertirla a uuid daba un 500 en vez de cero filas.
- **Solo adición.** `app_user` no puede borrar en ninguna tabla de negocio; de una lectura solo puede
  cambiar su resolución, y de una alerta solo su estado.
- **El operador cuenta sin leer.** `operador_user` tiene SELECT sobre `activos.empresa_id` y
  `activos.estado` y nada más: factura por equipos en servicio, y pedir el nombre de un equipo le da
  un error de permisos.
- **Test de guardia** (`test_rnf01_tablas_con_empresa_id_tienen_rls_forzada`): cualquier tabla con
  `empresa_id` sin RLS habilitada y forzada hace fallar la batería.

> **Nombres de restricciones en las migraciones.** Alembic aplica la convención de nombres de
> `app.models.base` también en `op.create_table` y `op.create_check_constraint`: un CHECK se nombra
> solo con su sufijo (`estado_valido`) y la convención le antepone `ck_<tabla>_`. Escribir el nombre
> completo lo duplicaba. `test_ninguna_restriccion_tiene_el_prefijo_duplicado` lo vigila.

### Código QR y etiqueta

Ocho caracteres de un alfabeto sin I, O, 0 ni 1, generados con `secrets` (nunca un contador, que
permitiría recorrer los equipos de todas las empresas). Único en todo el sistema, con reintento si
choca. El QR codifica solo `{APP_BASE_URL}/a/{código}`. La etiqueta es un SVG con corrección de
errores nivel Q y margen de 4 módulos, el código corto en dos grupos (`XK7P-2QH9`) y el nombre
escapado.

### Cookies y dominios

El navegador habla **solo con el origen del frontend**: `next.config.ts` reenvía `/api/*` a
`API_ORIGEN`. Así la cookie de sesión es siempre del mismo sitio, también en producción, donde
frontend y backend viven en dominios distintos y una cookie de otro sitio no viajaría (sección 8.2).
Como defensa adicional contra CSRF, la API rechaza con 403 cualquier método que escriba si trae un
`Origin` que no es el del frontend.

Detrás de ese reenvío la API ve la IP del servidor de Next. Para que el límite de login por IP vea la
real, uvicorn debe arrancar con `--proxy-headers` y `FORWARDED_ALLOW_IPS` acotado a la IP del proxy.

### Nota sobre TLS en máquinas con Avast

Avast Web Shield intercepta TLS. Node ya confía en su CA vía `NODE_EXTRA_CA_CERTS`;
para pip, `tools/setup.ps1` genera un bundle combinado (certifi + CA de Avast) en
`~/.certs/ca-bundle-avast.pem` y lo registra en `.venv/pip.ini`. **No** se desactiva
la verificación de certificados.

## Grafo de dependencias

`tools/graph/graph.py` fusiona el grafo de imports de Python (grimp) y de
TypeScript (dependency-cruiser) en `.graph/graph.json` y permite consultarlo:

| Comando | Qué hace |
|---|---|
| `python tools/graph/graph.py build` | Regenera el snapshot y los diagramas Mermaid en `docs/diagramas/` |
| `... deps <mod>` | Qué importa `<mod>` (directo y transitivo) |
| `... rdeps <mod>` | Quién depende de `<mod>` — análisis de impacto antes de cambiarlo |
| `... cycles` | Ciclos de importación (Tarjan) |
| `... orphans` | Módulos que nadie importa |
| `... status` | Métricas del código + avance de `docs/PLAN.yaml` |
| `... check` | import-linter + dependency-cruiser + ciclos (usado por hook y CI) |
| `... docs` | Reescribe la sección auto-generada de este README |
| `... view` | Genera `.graph/graph.html` (visor interactivo: colores por capa, buscar, clic para ver deps/rdeps) y lo abre en el navegador. `--no-open` solo genera |

`<mod>` acepta ids completos (`app.services.foo`, `src/lib/api.ts`) o un
fragmento único (`services.foo`, `lib/api`).

### Ver el grafo visualmente

- **Interactivo:** `python tools/graph/graph.py view` (plantilla en `tools/graph/viewer.html`; vis-network desde CDN).
- **Mermaid:** `docs/diagramas/*.md`, renderizado por GitHub y por VS Code con la extensión *Markdown Preview Mermaid Support*.
- **SVG del frontend:** `cd frontend && npm run graph:svg` (requiere Graphviz en el PATH).

### Reglas de arquitectura

**Backend** (`pyproject.toml` → `[tool.importlinter]`): capas de arriba hacia abajo
`main → (api | jobs) → services → db → models → schemas → core`. Una capa solo importa
de las inferiores; `api` y `jobs` son hermanas (ninguna importa de la otra). Los routers no contienen
lógica de negocio ni transiciones de estado: eso vive en `services/` (RBAC y máquina de estados de órdenes
se verifican ahí, como exige el documento de arquitectura §5.2).

**Frontend** (`.dependency-cruiser.cjs`): sin ciclos; `src/components` no importa
de `src/app`; se avisan huérfanos (salvo convenciones de Next.js).

## Seguridad multi-tenant (no negociable)

1. Toda tabla de empresa lleva `empresa_id` y tiene RLS con **`ENABLE` y `FORCE`**
   (`backend/db/rls_policies.sql`).
2. **Tres roles de base de datos, no dos.** `simap` (superusuario, solo administración),
   `simap_owner` (dueño de las tablas, sin superusuario, corre las migraciones) y `app_user` (el que
   usa el backend, sin `BYPASSRLS` y dueño de nada). `FORCE` hace que las políticas alcancen también
   al propietario — **pero solo si el propietario no es superusuario**, porque a un superusuario
   PostgreSQL le deja pasar siempre. Como la imagen de Docker crea `POSTGRES_USER` como superusuario
   y dueño, `rls_policies.sql` transfiere la propiedad a `simap_owner`; sin ese paso el `FORCE` es
   decorativo. Verificado en `tests/test_aislamiento_tenant.py`.
3. `app.db.deps.get_db` ejecuta `set_config('app.empresa_id', <empresa_id del JWT>, true)` dentro de
   la transacción del request — equivale a `SET LOCAL`, pero admite parámetro enlazado, así que el
   contenido del token nunca se concatena en el SQL. El valor sale **del token firmado**, jamás de un
   parámetro, cabecera o cuerpo del cliente.
4. Las políticas comparan contra `current_setting('app.empresa_id', true)`, que devuelve NULL si nadie
   lo fijó. Una transacción que olvide el `set_config` **no ve ninguna fila**: falla cerrado.
5. El token de acceso viaja en cookie `httpOnly`/`Secure`/`SameSite` (`simap_access`), nunca en
   `localStorage`. Se acepta `Authorization: Bearer` solo para clientes que no son navegador; si
   llegan los dos, manda la cookie.
6. Contraseñas con Argon2id (`app.core.security`), nunca bcrypt ni SHA. Los tokens de refresco no
   sirven como tokens de acceso: la reclamación `typ` los distingue.
7. RBAC se verifica en cada endpoint con `requiere_roles(...)` (`app.core.rbac`), no solo en la UI.
   Llamarla sin roles lanza `RolNoDeclarado` al arrancar: ningún endpoint queda abierto por descuido.
8. **La política `login_lookup` es la excepción deliberada al aislamiento.** El login tiene un
   problema de huevo y gallina: para saber a qué empresa pertenece alguien hay que leer su fila,
   pero leer exige conocer la empresa. La política deja ver únicamente la fila cuyo correo coincide
   **exactamente** con el que se acaba de teclear, y solo mientras dure esa transacción. No permite
   listar, buscar por patrón ni enumerar correos.
9. Cada token lleva un `jti` único. Sin él, dos tokens emitidos en el mismo segundo serían la misma
   cadena, la rotación del refresh token no rotaría nada y revocar el viejo revocaría también el nuevo.
10. **Crear una empresa no es una operación HTTP.** Ningún rol que atienda tráfico web puede insertar
   en `empresas`: la política `empresa_alta_administrativa` (revisión 0002) solo alcanza a
   `simap_owner`, que es con quien corre `python -m app.cli crear-empresa`. Retirar la ruta pública
   no habría bastado por sí solo, porque una ruta se puede reintroducir sin querer; la política es
   lo que hace que el cierre no dependa de que nadie se despiste.
11. **El frontend no guarda ningún token.** No hay nada en `localStorage` ni cabecera `Authorization`
   que construir: el cliente (`src/lib/api.ts`) solo envía `credentials: "include"` y el navegador
   adjunta las cookies `httpOnly`. Un XSS en la página no puede leer la sesión porque el JavaScript
   no tiene acceso a ella. El rol tampoco se cachea en el cliente: se pregunta a `/auth/yo` en cada
   carga, para que nadie pueda cambiarlo desde las herramientas del navegador y ver un menú que no
   le corresponde.
12. **El plano de control no puede leer datos de negocio, y lo impone PostgreSQL.** La consola del
   operador se atiende con el rol `operador_user`, que recibe permisos **tabla por tabla** y nunca
   por defecto. Al crear una tabla de negocio en F2 y siguientes, **no concederle permisos**: así
   queda fuera de su alcance sin que nadie tenga que acordarse. Sobre `usuarios` solo alcanza las
   filas con rol `administrador`.
13. **Los tokens de los dos planos no son intercambiables.** Cada uno lleva la reclamación `suj`
   que dice a qué plano pertenece, y las dos funciones de decodificación la comprueban en su
   dirección. Un token de operador no lleva `empresa_id` y ya fallaría por eso, pero rechazarlo por
   lo que **dice ser** es lo que seguirá funcionando el día que alguien añada un `empresa_id`
   opcional sin acordarse de esta frontera.
14. **La contraseña de un cliente la genera el servidor, nunca el operador.** Con `secrets`, no con
   `random`. Si quien opera SIMAP pudiera elegirla, tendría acceso permanente a la cuenta de ese
   cliente. Se muestra una vez y solo se guarda su hash.
15. **Toda acción del plano de control queda en la bitácora**, escrita en la misma transacción que
   la acción. La clave foránea a `operadores` es `RESTRICT`: nadie puede borrar su propia cuenta
   para hacer desaparecer lo que hizo.
16. **Toda puerta que compara una contraseña tiene límite de intentos**, no solo `/auth/login`: también
   el login de la consola y el cambio de clave en los dos planos (`app.services.limites`). Cada
   puerta lleva su propio contador; si compartieran uno, bastaría golpear la consola con el correo
   de un administrador de planta para dejarlo fuera de su propia empresa.
17. **Cambiar o restablecer una clave cierra las demás sesiones.** `usuarios.version_clave`
   (revisión 0004) sube en cada cambio, el refresh token lleva la versión con la que se emitió
   (reclamación `ver`) y `/auth/refresh` rechaza los que no coinciden. Es un contador y no una fecha
   porque `iat` tiene resolución de un segundo y un token emitido en el mismo segundo que el cambio
   caería a un lado u otro por azar. El token de acceso de los otros aparatos no se comprueba contra
   la base —sería una consulta por petición—: les queda como mucho lo que falte de sus 30 minutos.
18. **Cambiar la clave exige la actual**, aunque haya sesión: una sesión olvidada en un aparato
   compartido no debe bastar para quedarse con la cuenta. Responde 400, no 401, para que el cliente
   no confunda el error con una sesión caducada y lo tape con un reintento.
19. **Las tablas de negocio son de solo adición y sus FK incluyen `empresa_id`.** Ver «Lo que la
   base impone además de RLS» en la sección de la fase 2.
20. **Lo que llega del teléfono es no confiable**: `empresa_id` y el autor salen del token, nunca del
   cuerpo; `capturado_en` se acepta solo con zona horaria, hasta 5 minutos en el futuro y 14 días
   atrás; las notas se guardan tal cual y React las escapa (`dangerouslySetInnerHTML` prohibido con
   datos de usuarios).
21. Antes de cada entrega: test automatizado de aislamiento entre tenants, OWASP Top 10 sobre lo nuevo,
   sin secretos en repo ni logs (`pip-audit` / `npm audit` en CI).

> Si más adelante se añade PgBouncer, debe ir en **session pooling**. En transaction pooling la
> conexión puede reiniciarse entre sentencias y perder el `app.empresa_id` a mitad de una operación.

## Frontend

### El sistema visual: sobrio, como una herramienta de mantenimiento

El listón es el software de mantenimiento industrial (CMMS) que un jefe de planta ya reconoce:
gris neutro, superficies planas, controles con caja visible, densidad alta y un único color de
acción. Es una decisión del usuario, registrada en `PRODUCT.md` como compromiso de marca, y el
sistema completo está documentado en `DESIGN.md`.

Hubo antes una versión con mundo visual propio —la interfaz imitaba una bitácora de mantenimiento
en papel, con fondo rayado, margen perforado y sello de fecha— y el usuario la rechazó por poco
sobria para una herramienta industrial. Queda dicho aquí porque explica una regla: **nada de
texturas, papel ni metáforas de objetos físicos.** La estructura se comunica con espaciado,
alineación y bordes de 1 px. Cuando una decisión pueda ir hacia lo expresivo o hacia el estándar
de la categoría bien ejecutado, va hacia el estándar.

Tres reglas del sistema que conviene no romper:

- **Hay dos vocabularios de color que nunca se mezclan.** El azul (`--accion`) significa «aquí se
  puede hacer algo» y solo aparece en controles activos; un control deshabilitado lo pierde por
  completo. Verde, ámbar y rojo (`--estado-*`) quedan reservados para el **estado de una máquina**
  (alerta, orden, riesgo). No es estética: el par verde/rojo es justo el que no distingue alguien
  con deuteranopía, así que si además significara «pulsable» no quedaría ninguna señal libre para
  el estado real del equipo.
- **Ocupado no es lo mismo que deshabilitado.** Mientras una petición está en vuelo el control
  conserva el color y solo cambia el texto; el gris sin color queda para lo genuinamente
  deshabilitado.
- **Un error nunca mueve el botón.** El aviso va debajo de la acción, no encima, y las pantallas de
  una sola pieza se anclan con un desplazamiento fijo en lugar de centrarse: un bloque centrado
  sube la mitad de lo que crece, y el botón se movería bajo el cursor justo cuando el usuario va a
  volver a pulsarlo.

Los campos y los botones miden 48 px: esto se usa de pie, con guantes y a menudo con una sola mano.
El tema claro y el oscuro son **los dos de primera clase**, porque la luz ambiente de una planta
cambia dentro del mismo turno; se auditan por separado y todos los pares texto/fondo cumplen 4.5:1,
los bordes de control 3:1.

### Rutas

| Ruta | Para quién |
|---|---|
| `/` | Desvía: al panel si hay sesión, al acceso si no |
| `/login` | Acceso único: usuarios de una empresa y operador de SIMAP |
| `/panel` | Panel del turno, distinto según el rol |
| `/panel/clave` | Cambiar la contraseña propia |
| `/operador/login` | Redirige a `/login` (el acceso se unificó) |
| `/operador` | Consola: alta de clientes, suspensión, claves y bitácora |
| `/operador/clave` | El operador cambia su propia contraseña |
| `/a/{código}` | Pantalla del equipo al escanear su QR (página `/equipo` por reescritura) |
| `/escanear` | Escáner dentro de la app y código tecleado a mano |
| `/activos`, `/activos/nuevo`, `/activos/{id}/editar` | Lista, alta y edición de equipos |
| `/activos/{id}/etiqueta` | Vista de impresión de la etiqueta |
| `/alertas` | Bandeja de alertas y de lecturas por revisar |
| `/componentes` | Catálogo de componentes |
| `/panel/usuarios` | Personal de la empresa |

### Desvío por sesión (`src/proxy.ts`)

El documento de F1 pide un `middleware.ts`; desde Next.js 16 esa convención se llama `proxy.ts`.
Antes de pintar nada, manda a `/login` a quien no tiene sesión, también desde la consola. **No es control de acceso**: es una comprobación optimista para no enseñar el esqueleto
de una pantalla que no se puede usar. El permiso lo decide la API en cada petición.

Tres decisiones que no son obvias:

- **No mira el token, mira una pista.** El token de acceso caduca a los 30 minutos mientras la
  sesión vive siete días gracias al refresh token, que el navegador no manda a las páginas. Mirar
  el de acceso echaría a quien todavía puede renovar en silencio. La API pone y quita
  `simap_sesion` junto con el refresh token.
- **Nunca desvía `/login`.** Si mandara al panel a quien llega al acceso con pista, una pista
  caducada daría un bucle infinito.
- **Se aparta si no puede ver la pista.** Las cookies son del host que las pone; si la API vive en
  otro host, su ausencia no significa nada. El proxy compara el host de `NEXT_PUBLIC_API_URL` con el
  de la petición, y si no coinciden deja que cada página compruebe la sesión por su cuenta, como
  antes.

Protege **todo por defecto** y enumera lo público, igual que en el backend un endpoint sin roles se
rechaza: una pantalla nueva nace protegida.

### Service worker (`public/sw.js`)

Hace que la aplicación **abra sin cobertura**. Precarga el cascarón de la pantalla del equipo
(`/equipo`, que se sirve en todas las `/a/{código}`) con sus recursos; los recursos de
`/_next/static` van primero a la caché (llevan la huella de su contenido en el nombre); las
pantallas, primero a la red y, sin ella, a la última copia guardada o a `offline.html`. **Nunca
guarda respuestas de la API**: son datos de una persona y una empresa, y en un teléfono compartido
una caché del navegador se los serviría a quien venga después. Los datos para consultar sin red los
guarda la aplicación, por persona, en IndexedDB, y los borra al cerrar sesión. Se escribió a mano en
lugar de usar next-pwa (sin versiones desde 2022) o Serwist porque lo necesario es acotado.

El escáner dentro de la app usa `BarcodeDetector` donde existe y jsQR donde no (Safari). Valida que
lo leído sea exactamente `{este origen}/a/{código válido}` (`src/lib/qr.ts`): un QR ajeno pegado
encima de una etiqueta no lleva a ninguna parte. La cámara exige HTTPS fuera de `localhost`: para
probar en un teléfono por la red local hace falta un túnel (cloudflared) o HTTPS de desarrollo.

`src/lib/operador.ts` está deliberadamente separado de `src/lib/auth.ts`. Comparten el cliente HTTP
y nada más: mezclarlos sería la forma más fácil de que un día una pantalla de cliente acabe llamando
a un endpoint de operador porque «ya estaba importado».

### Sesión en el cliente

`src/lib/api.ts` no contiene ningún token, y eso es lo importante: la sesión va en cookies
`httpOnly` que el JavaScript de la página no puede leer. Toda la gestión se reduce a
`credentials: "include"`. Ante un 401 el cliente refresca la sesión una vez y reintenta, con un
**cerrojo compartido**: sin él, tres peticiones simultáneas dispararían tres refrescos, y como el
backend rota el refresh token y revoca el anterior en el mismo paso, el segundo llegaría con un
token ya revocado y cerraría la sesión de alguien que no hizo nada mal.

### Revisión de interfaz automatizada

`frontend/e2e/` (Playwright) comprueba lo que se rompe sin que nadie lo note: desplazamiento
horizontal en **tres anchos** (390, 768 y 1280) y los dos temas, que los controles alcancen el
tamaño táctil mínimo, que el foco se distinga sin el anillo del navegador, y que un error no
desplace el botón.

Los 768 px no estaban al principio, y una versión anterior desbordó justo ahí: entre el móvil y el
escritorio hay un tramo donde nada encaja por defecto y que nadie mira.

`campo.spec.ts` cubre la fase 2 de punta a punta, con un equipo y un operario nuevos en cada
ejecución: escanear y registrar en tres pasos en un móvil, la confirmación de una lectura que no
cuadra, **el envío sin conexión que llega una sola vez** al recuperar la red (con
`context.setOffline`), la etiqueta de otra empresa, la bandeja de lecturas por revisar y que ninguna
pantalla nueva desborde en móvil ni en escritorio. `unidad-qr.spec.ts` prueba el analizador de QR y
el destino `next` del login contra URLs ajenas, absolutas y códigos mal formados.

`sesion-y-cuenta.spec.ts` cubre el cierre de F1: el proxy (pidiendo la página con
`maxRedirects: 0` y mirando el 307, porque la URL final no distinguiría el proxy del desvío que cada
página ya hacía en el navegador), el cambio de clave en los dos planos —usa las cuentas de
demostración y **les devuelve la clave original** al terminar, pase lo que pase— y la página sin
conexión con la red cortada.

Corren con **un solo trabajador**: comparten backend y cuentas, y en paralelo una prueba intentaba
entrar con la clave de Ana justo mientras otra la tenía cambiada.

`consola-operador.spec.ts` cubre además la consola, y deja fijada por escrito la frontera del plano
de control: comprueba que las columnas de la tabla son exactamente empresa, administrador, equipos,
estado y acciones. Si algún día aparece ahí una columna con datos de negocio, esa prueba falla.

```powershell
cd frontend
npm run build; npx next start --port 3000   # se ejecutan contra la COMPILACION
npm run test:e2e
```

Contra `next dev` fallaban dos o tres pruebas distintas en cada ejecución —el servidor de desarrollo
compila cada ruta al pedirla y llegó a devolver 500 con un manifiesto truncado—, y una prueba que
unas veces pasa y otras no enseña a ignorar los fallos. Necesitan la API levantada, una empresa dada
de alta y un operador sembrado. Las credenciales salen **solo** de variables de entorno
(`E2E_CORREO`, `E2E_PASSWORD`, `E2E_OPERADOR_CORREO`, `E2E_OPERADOR_PASSWORD`), que
`playwright.config.ts` carga de `frontend/.env.e2e` si existe. Ese archivo no se versiona: son
contraseñas reales de la base de desarrollo, incluida la del operador. Si falta una variable, la
prueba que la necesita falla diciendo cuál.

Todavía no están en CI: entran en F5, cuando el `docker compose` completo corra allí.

## Integración continua

Dos workflows con responsabilidades distintas:

| Workflow | Cuándo | Qué hace |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | Cada push **y** cada pull request | Puerta de calidad. Puede bloquear un PR |
| [`docs.yml`](.github/workflows/docs.yml) | Solo push a `main` | Regenera el grafo y commitea la documentación |

`ci.yml` tiene tres jobs: **backend** (levanta `postgres:16` como servicio, aplica `roles.sql`,
migra, comprueba que la migración es reversible, y pasa ruff · `mypy --strict` · import-linter ·
pytest · pip-audit), **frontend** (lint · dependency-cruiser · build · npm audit) y **grafo**.

> **`CI=true` convierte en error la ausencia de base de datos.** En local, las ~30 pruebas que
> necesitan PostgreSQL se saltan con un motivo explícito si no está levantado. En CI eso sería un
> agujero: un test saltado no prueba nada pero deja el pipeline en verde, y la cobertura de RNF-01
> desaparecería sin que nadie lo note. `tests/conftest.py` aborta la ejecución entera en ese caso.

**Sin protección de rama sobre `main`, por decisión.** El documento de F1 (sección 4.2) pide
prohibir el push directo y exigir pull requests, pero SIMAP lo desarrolla y publica una sola
persona: la regla no protegería de nadie y solo añadiría pasos. La puerta de calidad está en el
hook `pre-push` local, que corre las pruebas antes de publicar, y en `ci.yml` después.

## Flujo de documentación

1. **Local (`.githooks/pre-push`)** — al hacer push a `main`:
   - regenera grafo y diagramas, ejecuta `check` y los tests;
   - refresca la sección auto-generada del README (`graph.py docs`);
   - si los commits tocan `backend/` o `frontend/` pero ninguno toca
     `README.md`, `README_USER.md` o `MANUAL_USUARIO.md`, **bloquea el push**.
2. **Remoto (`.github/workflows/docs.yml`)** — en cada push a `main`:
   - repite `build`, `check` y `docs`. Las pruebas no: las corre `ci.yml`, que es el único con
     PostgreSQL, y el `conftest` se niega a correr en CI sin base de datos;
   - si el README auto-generado cambió, lo commitea como `docs: actualizar grafo y estado [skip ci]`.

Para saltar el hook en una emergencia: `git push --no-verify` (queda registrado en el historial que no se validó).

### Limpiar los datos que dejan las pruebas

La batería de integración corre contra un PostgreSQL real —es lo que hace que las pruebas de
aislamiento valgan algo— y cada ejecución deja empresas, usuarios y operadores con nombres
generados al azar. Tras unas cuantas, la consola del operador muestra cientos de empresas basura.

```powershell
python tools/limpiar_datos_de_prueba.py              # muestra lo que haria
python tools/limpiar_datos_de_prueba.py --ejecutar   # lo hace
```

Borra solo lo que coincide con patrones **declarados explícitamente** en el propio script, y se
niega a correr si la URL no apunta a `localhost`. Si añades un nombre de empresa nuevo en una
prueba, añádelo también allí.

Está en `tools/` y no en `app.cli` a propósito: `app.cli` es una herramienta de producción y un
comando que borra filas por patrón de nombre no debe estar a un tecleo de una base con clientes
reales.

## Calidad

```powershell
cd backend
ruff check . ; ruff format . ; mypy app ; pytest
cd ../frontend
npm run lint ; npm run graph:check
```

<!-- graph:auto:start -->
_Sección generada por `python tools/graph/graph.py docs`. No editar a mano; se sobrescribe en cada push a `main`._

Última actualización: 2026-10-07 14:04 UTC

### Estado del proyecto

```text
=== ESTADO DEL CÓDIGO ===

[backend]  módulos: 47   LOC: 4782   TODO/FIXME: 0
  con test: 37/47   stubs/vacíos: 0
  por capa: api=11, cli=1, core=6, db=3, main=1, models=8, schemas=6, services=11

[frontend]  módulos: 45   LOC: 6222   TODO/FIXME: 0
  con test: 0/45   stubs/vacíos: 0
  por capa: app=17, components=15, lib=12, src=1

ciclos de importación: 0

=== PLAN (docs/PLAN.yaml) ===

  F0 - Infraestructura del repositorio  (5/5, 100%)
    [x] Repositorio, .gitignore, estructura backend/frontend  <done>
    [x] Herramienta de grafo de dependencias (tools/graph)  <done>
    [x] Hook pre-push + GitHub Action de documentación  <done>
    [x] Documentación inicial (README, README_USER, MANUAL_USUARIO)  <done>
    [x] Documentos de contexto transcritos en docs/contexto y DDL en backend/db  <done>

  F1 - Fundamentos: auth, multi-tenant y RLS (semanas 1-2)  (13/13, 100%)
    cubre: RF-01, RF-02, RF-03, RNF-01, RNF-07, RNF-08
    hecho cuando: Un usuario se registra e inicia sesión; el sistema deniega datos de otra empresa incluso por API directa.
    [x] Dependencias del stack (SQLAlchemy async, asyncpg, Alembic, python-jose, argon2, redis, scipy, APScheduler, qrcode)  <done>
    [x] docker-compose con postgres:16 y redis:7; Dockerfile del backend  <done>
    [x] Sesión async de SQLAlchemy y dependencia get_db que fija app.empresa_id desde el JWT  <done (auto)>
    [x] Modelos Empresa y Usuario + migración inicial Alembic (schema.sql + rls_policies.sql)  <done (auto)>
    [x] Registro e inicio de sesión: Argon2id, JWT 30 min + refresh token  <done (auto)>
    [x] RBAC: dependencia require_roles verificada en cada endpoint  <done (auto)>
    [x] Test automatizado de aislamiento entre tenants (RNF-01)  <done>
    [x] Frontend: login, cliente API con JWT, navegación básica por rol, base PWA  <done>
    [x] Alta de empresas por invitación: comando de consola en vez de ruta pública  <done>
    [x] Plano de control: consola del operador de SIMAP (alta de clientes, suspensión, claves, bitácora)  <done>
    [x] Cierre de F1: proxy de sesión, service worker mínimo y cambio de la clave propia  <done>
    [x] Protección de main en GitHub (4.2): descartada por decisión del usuario  <done>
    [x] CI: pytest + lint + pip-audit/npm audit en cada push  <done>

  F2 - Activos y registro de campo (semanas 3-6)  (12/14, 85%)
    cubre: RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RNF-03, RNF-05
    hecho cuando: Un operario escanea el QR y registra horómetro o alerta; el reporte llega aunque se hiciera offline.
    [x] Puerta de entrada (05, sección 3) y migración 0005 con RLS, referencias compuestas y solo adición  <done>
    [x] Cookies y dominios (05, 8.2): el navegador habla solo con el frontend, Next reenvía /api  <done>
    [x] Gestión de usuarios de la empresa: alta, rol y baja, por el administrador (RF-03)  <done (auto)>
    [x] CRUD de activos con ficha técnica, ubicación y criticidad; baja lógica  <done (auto)>
    [x] Generación de QR único + código corto de respaldo al crear el activo; etiqueta SVG  <done (auto)>
    [x] Catálogo de componentes editable por el administrador, con plantilla inicial  <done (auto)>
    [x] Lecturas de horómetro  <done (auto)>
    [x] Alertas de campo (síntoma + nota) con estados  <done (auto)>
    [x] Frontend: escáner QR y vista móvil del activo con acciones por rol  <done (auto)>
    [x] Frontend: formularios de horómetro y alerta, máx. 3 pasos  <done (auto)>
    [x] Frontend: PWA offline con cola local y sincronización automática  <done (auto)>
    [ ] Prueba en teléfonos reales (iOS y Android) y de una etiqueta impresa a 50 cm  <pending>
    [ ] Verificar en producción que la sesión persiste entre frontend y backend (8.2)  <pending>
    [x] Confirmar una lectura marcada para revisión, y el evento «horómetro reiniciado»  <done>

  F3 - Órdenes de trabajo (semanas 7-8)  (0/5, 0%)
    cubre: RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RNF-06
    hecho cuando: Una falla sigue su ciclo completo hasta cerrarse, con cada responsable visible en el historial.
    [ ] Reporte de falla del supervisor → crea orden en 'reportada' y actualiza el activo  <pending>
    [ ] Máquina de estados reportada→en_taller→reparada→cerrada con transiciones por rol  <pending>
    [ ] Trazabilidad reportado_por / reparado_por / autorizado_por y tiempo fuera de servicio  <pending>
    [ ] Vincular alerta previa a la orden (alerta_origen_id) y pre-llenar el formulario  <pending>
    [ ] Frontend: formulario de falla, detalle de orden y cambio de estado  <pending>

  F4 - Predicción e inventario (semanas 9-12)  (0/8, 0%)
    cubre: RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25, RF-26
    hecho cuando: Al cerrar una orden real el modelo se reajusta; un activo con fallas frecuentes muestra riesgo visiblemente mayor.
    [ ] Ajuste de Weibull por componente (scipy.stats.weibull_min.fit) sobre órdenes cerradas  <pending>
    [ ] Riesgo condicional por activo 1 − R(T+Δt)/R(T), disparado por cada lectura de horómetro  <pending>
    [ ] Multiplicador por alertas recientes (≥2 en 15 días → ×1.30)  <pending>
    [ ] Alerta automática del sistema al superar RISK_THRESHOLD  <pending>
    [ ] Tarea diaria APScheduler: recalcular riesgo y reajustar β, η  <pending>
    [ ] Carga inicial con dataset público/simulado marcado como 'estimado'  <pending>
    [ ] CRUD de repuestos y detalle orden_repuesto; descuento de stock al cerrar; alerta de reorden  <pending>
    [ ] Frontend: inventario y riesgo visible en la ficha del activo  <pending>

  F5 - Dashboard y cierre (semanas 13-16)  (0/5, 0%)
    cubre: RF-27, RF-28, RNF-01, RNF-02, RNF-04
    hecho cuando: Los tres paneles muestran datos reales; las pruebas de aislamiento entre tenants pasan sin excepción.
    [ ] Endpoints de indicadores: disponibilidad, MTBF, costo de repuestos, activos de mayor riesgo  <pending>
    [ ] Frontend: panel de operario, supervisor y gerente según rol  <pending>
    [ ] Auditoría de aislamiento entre tenants automatizada + pruebas e2e (Playwright) de flujos críticos  <pending>
    [ ] Checklist OWASP Top 10 y verificación de secretos  <pending>
    [ ] Documentación técnica y manual de usuario finales  <pending>

AVANCE GLOBAL: 30/50 tareas (60%)
```

### Módulos del backend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `app.api.v1.comun` | api | 7 | 5 | 83 | — |
| `app.api.v1.router` | api | 9 | 1 | 27 | — |
| `app.api.v1.routes.activos` | api | 9 | 1 | 155 | ✅ |
| `app.api.v1.routes.alertas` | api | 8 | 1 | 87 | ✅ |
| `app.api.v1.routes.auth` | api | 7 | 1 | 210 | ✅ |
| `app.api.v1.routes.campo` | api | 6 | 1 | 23 | ✅ |
| `app.api.v1.routes.componentes` | api | 6 | 1 | 53 | ✅ |
| `app.api.v1.routes.health` | api | 2 | 1 | 9 | ✅ |
| `app.api.v1.routes.lecturas` | api | 9 | 1 | 119 | ✅ |
| `app.api.v1.routes.operador` | api | 9 | 1 | 315 | ✅ |
| `app.api.v1.routes.usuarios` | api | 5 | 1 | 66 | ✅ |
| `app.cli` | cli | 5 | 0 | 189 | ✅ |
| `app.core.almacen` | core | 1 | 6 | 112 | ✅ |
| `app.core.auth` | core | 1 | 5 | 117 | ✅ |
| `app.core.config` | core | 0 | 15 | 80 | — |
| `app.core.cursor` | core | 0 | 4 | 48 | ✅ |
| `app.core.rbac` | core | 2 | 6 | 36 | ✅ |
| `app.core.security` | core | 1 | 17 | 225 | ✅ |
| `app.db.deps` | db | 3 | 9 | 82 | ✅ |
| `app.db.session` | db | 2 | 1 | 78 | ✅ |
| `app.db.tenant` | db | 0 | 1 | 108 | ✅ |
| `app.main` | main | 2 | 0 | 74 | — |
| `app.models.activo` | models | 1 | 7 | 66 | — |
| `app.models.alerta` | models | 1 | 2 | 75 | — |
| `app.models.base` | models | 0 | 8 | 32 | — |
| `app.models.componente` | models | 1 | 2 | 41 | — |
| `app.models.empresa` | models | 1 | 4 | 19 | ✅ |
| `app.models.lectura_horometro` | models | 1 | 3 | 88 | — |
| `app.models.operador` | models | 1 | 3 | 68 | ✅ |
| `app.models.usuario` | models | 2 | 4 | 63 | ✅ |
| `app.schemas.activo` | schemas | 0 | 4 | 78 | — |
| `app.schemas.auth` | schemas | 1 | 4 | 63 | ✅ |
| `app.schemas.campo` | schemas | 0 | 4 | 106 | ✅ |
| `app.schemas.health` | schemas | 0 | 1 | 6 | ✅ |
| `app.schemas.operador` | schemas | 1 | 1 | 66 | ✅ |
| `app.schemas.usuario` | schemas | 1 | 1 | 32 | ✅ |
| `app.services.activos` | services | 4 | 2 | 167 | ✅ |
| `app.services.alertas` | services | 5 | 2 | 145 | ✅ |
| `app.services.auth` | services | 8 | 2 | 298 | ✅ |
| `app.services.campo` | services | 4 | 1 | 101 | ✅ |
| `app.services.capturas` | services | 2 | 6 | 53 | ✅ |
| `app.services.componentes` | services | 1 | 3 | 83 | ✅ |
| `app.services.lecturas` | services | 5 | 2 | 243 | ✅ |
| `app.services.limites` | services | 2 | 5 | 44 | ✅ |
| `app.services.operador` | services | 8 | 1 | 323 | ✅ |
| `app.services.qr` | services | 0 | 2 | 84 | ✅ |
| `app.services.usuarios` | services | 2 | 1 | 114 | ✅ |

### Módulos del frontend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `src/app/activos/[id]/editar/page.tsx` | app | 5 | 0 | 55 | — |
| `src/app/activos/[id]/etiqueta/page.tsx` | app | 5 | 0 | 83 | — |
| `src/app/activos/nuevo/page.tsx` | app | 4 | 0 | 32 | — |
| `src/app/activos/page.tsx` | app | 8 | 0 | 215 | — |
| `src/app/alertas/page.tsx` | app | 8 | 0 | 202 | — |
| `src/app/componentes/page.tsx` | app | 7 | 0 | 207 | — |
| `src/app/equipo/page.tsx` | app | 14 | 0 | 417 | — |
| `src/app/escanear/page.tsx` | app | 6 | 0 | 72 | — |
| `src/app/globals.css` | app | 0 | 1 | 186 | — |
| `src/app/layout.tsx` | app | 2 | 0 | 66 | — |
| `src/app/login/page.tsx` | app | 7 | 0 | 185 | — |
| `src/app/operador/clave/page.tsx` | app | 3 | 0 | 60 | — |
| `src/app/operador/page.tsx` | app | 5 | 0 | 566 | — |
| `src/app/page.tsx` | app | 2 | 0 | 44 | — |
| `src/app/panel/clave/page.tsx` | app | 3 | 0 | 65 | — |
| `src/app/panel/page.tsx` | app | 3 | 0 | 87 | — |
| `src/app/panel/usuarios/page.tsx` | app | 9 | 0 | 267 | — |
| `src/components/barra-sesion.tsx` | components | 3 | 1 | 92 | — |
| `src/components/boton.tsx` | components | 0 | 16 | 72 | — |
| `src/components/campo.tsx` | components | 0 | 9 | 143 | — |
| `src/components/escaner-qr.tsx` | components | 3 | 1 | 153 | — |
| `src/components/estado.tsx` | components | 1 | 6 | 105 | — |
| `src/components/formulario-activo.tsx` | components | 4 | 2 | 147 | — |
| `src/components/formulario-alerta.tsx` | components | 9 | 1 | 147 | — |
| `src/components/formulario-clave.tsx` | components | 3 | 2 | 165 | — |
| `src/components/formulario-horometro.tsx` | components | 9 | 2 | 212 | — |
| `src/components/iconos.tsx` | components | 0 | 7 | 82 | — |
| `src/components/indicador-cola.tsx` | components | 2 | 1 | 77 | — |
| `src/components/lecturas-por-revisar.tsx` | components | 6 | 1 | 119 | — |
| `src/components/marco.tsx` | components | 0 | 15 | 163 | — |
| `src/components/pantalla.tsx` | components | 5 | 10 | 106 | — |
| `src/components/registro-sw.tsx` | components | 0 | 1 | 28 | — |
| `src/lib/acceso.ts` | lib | 3 | 1 | 53 | — |
| `src/lib/activos.ts` | lib | 1 | 12 | 114 | — |
| `src/lib/api.ts` | lib | 0 | 22 | 182 | — |
| `src/lib/auth.ts` | lib | 1 | 17 | 251 | — |
| `src/lib/campo.ts` | lib | 2 | 7 | 141 | — |
| `src/lib/captura.ts` | lib | 5 | 2 | 83 | — |
| `src/lib/formato.ts` | lib | 0 | 7 | 31 | — |
| `src/lib/offline-queue.ts` | lib | 4 | 4 | 332 | — |
| `src/lib/operador.ts` | lib | 1 | 3 | 121 | — |
| `src/lib/qr.ts` | lib | 0 | 4 | 60 | — |
| `src/lib/sesion.ts` | lib | 3 | 2 | 98 | — |
| `src/lib/usuarios.ts` | lib | 2 | 1 | 41 | — |
| `src/proxy.ts` | src | 0 | 0 | 95 | — |

Diagramas: [backend](docs/diagramas/dependencias-backend.md) · [frontend](docs/diagramas/dependencias-frontend.md)
<!-- graph:auto:end -->
