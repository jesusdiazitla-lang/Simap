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
| [docs/contexto/06-fase3-ordenes-de-trabajo.md](docs/contexto/06-fase3-ordenes-de-trabajo.md) | Alcance de F3: órdenes de trabajo, máquina de estados, reinicio del horómetro. Anexo con la implementación |
| [docs/contexto/07-fase4-prediccion-e-inventario.md](docs/contexto/07-fase4-prediccion-e-inventario.md) | Alcance de F4: Weibull con censura, riesgo, alertas del sistema, orden predictiva, inventario. Anexo con las desviaciones |
| [docs/contexto/anexos/experimentos-fase4.md](docs/contexto/anexos/experimentos-fase4.md) | Resultados reproducidos de la validación del método con simulaciones (F4, sección 14) |
| [backend/db/schema.sql](backend/db/schema.sql) · [rls_policies.sql](backend/db/rls_policies.sql) | DDL de PostgreSQL y políticas de aislamiento por empresa |
| [docs/PLAN.yaml](docs/PLAN.yaml) | Las 5 fases como tareas rastreables por `graph.py status` |

> **Regla del equipo:** cada push a `main` debe dejar actualizados este README,
> `README_USER.md` y `MANUAL_USUARIO.md`. El hook `pre-push` y la GitHub Action
> `docs.yml` lo verifican (ver [Flujo de documentación](#flujo-de-documentación)).

## Stack

| Capa | Tecnología | Carpeta |
|---|---|---|
| Backend | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 async + asyncpg · Alembic · python-jose (JWT) · argon2-cffi · qrcode · scipy (Weibull) · APScheduler · redis | `backend/` |
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 · TanStack Query · react-hook-form + zod · idb · BarcodeDetector con jsQR de respaldo · service worker propio (PWA) · Playwright | `frontend/` |
| Datos | PostgreSQL 16 con Row-Level Security · Redis 7 | `docker-compose.yml` |
| Despliegue | Docker (backend) · Railway · Vercel · Supabase · Upstash · GitHub Actions | `backend/Dockerfile`, `.github/` |
| Tooling | grimp · import-linter · dependency-cruiser · madge | `tools/graph/` |

Desviaciones respecto a `02-arquitectura.md`, decididas al montar el repo: Python 3.11 local (doc: 3.12; el
Dockerfile sí usa 3.12) · React 19 / Next 16 (doc: React 18; Next 16 exige React 19) · **service worker propio**
(`public/sw.js`) en lugar de `next-pwa`, sin mantenimiento (ver «Service worker») · **BarcodeDetector**
del navegador con **jsQR** de respaldo en lugar de `html5-qrcode`.

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

**Día a día**, con todo ya instalado: dos terminales.

```powershell
.	ools\levantar-backend.ps1     # base de datos, migraciones y API en :8000
.	ools\levantar-frontend.ps1    # compila y arranca en :3000 (con -Dev, modo desarrollo)
```

Cada uno libera su puerto si quedó un servidor colgado. El del frontend arranca por defecto la
versión de producción, la única con modo sin conexión y acceso desde el teléfono, y muestra la
dirección para abrirla en él. La instalación desde cero, paso a paso:

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
cd backend; Copy-Item .env.example .env         # poner un JWT_SECRET propio: sin él no arranca
python -c "import secrets; print(secrets.token_urlsafe(48))"   # genera uno
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

La resolución, igual que revisar o descartar una alerta, es también una **escritura condicionada**
(`UPDATE … WHERE resolucion IS NULL`, `… WHERE estado = 'pendiente'`): si dos supervisores actúan a
la vez, el segundo recibe 409 en lugar de pisar la decisión del primero (sección 9.4).

El horómetro es un **entero**: el formulario rechaza los decimales («4821.5») en vez de quitar el
separador, que lo convertía en 48 215. Acepta separadores de miles bien puestos («4,821»). El alta
de un equipo aplica el mismo tope `HOROMETRO_MAX` al horómetro inicial que a cada lectura.

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
malo vuelve como `rechazado` con su motivo y los demás entran. En el teléfono, lo rechazado y lo
descartado de otras personas se le muestra a quien corresponde en todas las pantallas con sesión
(`src/components/avisos-cola.tsx`), con el motivo tal como lo escribe el servidor: callarlo haría
creer a alguien que su lectura está en el sistema.

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
real, uvicorn arranca con `--proxy-headers` (`backend/Dockerfile`) y solo cree a `X-Forwarded-For`
si la petición viene de una IP de `FORWARDED_ALLOW_IPS`. En local es `127.0.0.1`, que es donde
corre Next; en el despliegue hay que poner la IP o la red del proxy real, nunca `*`: con `*`
cualquiera se inventa la cabecera y esquiva el límite. Next solo rellena `X-Forwarded-For` si la
petición no la trae: en producción la reescribe el hosting, pero en local un cliente podría
inventarla. Aun así, el límite por correo sigue en pie.

El límite tiene dos contadores. Por correo, `LOGIN_MAX_ATTEMPTS` (5), y un acierto lo pone a cero.
Por IP, `LOGIN_MAX_INTENTOS_POR_IP` (30), más alto porque una planta entera sale a internet por una
sola IP y al empezar el turno entra todo el mundo; un acierto **no** lo reinicia, o quien tuviera
una cuenta válida podría intercalar su propio login entre intentos contra cuentas ajenas.

### Registro y métricas

Cada petición deja una línea JSON en la salida estándar (`app.core.registro`) con `request_id`,
método, **plantilla** de la ruta (`/activos/{activo_id}`, nunca los valores), estado y duración, y la
empresa y el usuario (u operador) cuando hay sesión. El `request_id` se devuelve en `X-Request-ID`;
si la petición trae uno con forma válida, se respeta, para seguirla a través del proxy.

Eventos de negocio, que son las métricas que pide la sección 9.7:

| Evento | Campos | Para qué |
|---|---|---|
| `campo.lote` | `recibidos`, `creados`, `duplicados`, `rechazados` | Un salto en duplicados o rechazados delata un fallo de sincronización en los teléfonos |
| `campo.lectura_marcada` | `activo_id` | Lecturas que no cuadran: muchas en un equipo apuntan a un horómetro averiado |
| `campo.lectura_resuelta` | `resolucion` | Qué se hace con ellas |
| `campo.alerta_deduplicada` | `sintoma` | Si sube mucho, la ventana es corta o un botón se atasca |

**Nunca** se registran contraseñas, tokens, cookies, cuerpos de petición ni el texto de las notas:
solo se escriben los campos que se pasan explícitamente. `tests/test_registro.py` lo comprueba. Son
registros y no una librería de métricas para no atar el backend a un proveedor; cualquier recolector
de logs los agrega.

### Nota sobre TLS en máquinas con Avast

Avast Web Shield intercepta TLS. Node ya confía en su CA vía `NODE_EXTRA_CA_CERTS`;
para pip, `tools/setup.ps1` genera un bundle combinado (certifi + CA de Avast) en
`~/.certs/ca-bundle-avast.pem` y lo registra en `.venv/pip.ini`. **No** se desactiva
la verificación de certificados.

## Fase 3: órdenes de trabajo

Alcance y criterios en [`docs/contexto/06-fase3-ordenes-de-trabajo.md`](docs/contexto/06-fase3-ordenes-de-trabajo.md).
Las **ocho decisiones** de su sección 4 las confirmó el usuario el 2026-10-14 tal como se proponían:
estado **Cancelada** con motivo; cierran supervisor y administrador (el gerente solo lee); quien
repara no autoriza, quien reportó sí puede; solo el tipo **reemplazo** renueva la vida de un
componente; tiempo fuera de servicio de calendario, de la falla a la autorización; sin conexión solo
el reporte de falla; una orden cerrada solo la corrige el administrador, con nota y evento; y el
reinicio del horómetro se resuelve en esta fase.

### Máquina de estados

```
Reportada ──► En taller ──► Reparada ──► Cerrada
   │             ▲  │          │  │
   │             └──┼──────────┘  │     rechazo de cierre (nota obligatoria)
   └─────────────┴──┴─────────────┴──► Cancelada (con motivo)
```

| Transición | Ruta | Roles |
|---|---|---|
| Nueva → Reportada | `POST /activos/{id}/fallas` | supervisor, administrador |
| Reportada → En taller | `POST /ordenes/{id}/en-taller` | técnico, supervisor, administrador |
| En taller → Reparada | `POST /ordenes/{id}/reparada` | **solo** técnico de taller |
| Reparada → Cerrada | `POST /ordenes/{id}/cerrar` | supervisor, administrador |
| Reparada → En taller | `POST /ordenes/{id}/rechazar-cierre` | supervisor, administrador |
| Abierta → Cancelada | `POST /ordenes/{id}/cancelar` | supervisor, administrador |

Además: `GET /ordenes` (cursor, filtros por estado, equipo, componente y fechas, con **ETag**: 304 si
nada cambió), `GET /ordenes/{id}` (detalle con responsables e historial), `GET /activos/{id}/ordenes`,
`PATCH /ordenes/{id}` (solo abiertas), `POST /ordenes/{id}/notas`, `POST /ordenes/{id}/confirmar-horometro`,
`POST /ordenes/{id}/correccion` (administrador, solo cerradas) y `POST /activos/{id}/reinicio-horometro`
(administrador). El operario no ve las órdenes (403), pero la ficha del equipo (`GET /activos/{id}`)
trae `ordenes_abiertas` y la lista `en_falla`, para todos.

Cada transición tiene **su propia ruta**: el rol exigido y el estado de origen son parte de la
definición del endpoint, no un parámetro manipulable. Y cada una es un **UPDATE condicionado al
estado de origen** (`app.services.ordenes_estados`), sin leer antes ni bloquear: si dos personas
actúan a la vez, la base decide, una gana y la otra recibe 409 con quién la movió. La transición y su
evento van en la misma transacción. `tests/test_ordenes_estados.py` recorre **la tabla de roles
entera** (11 acciones × 5 roles), y `tests/test_concurrencia_ordenes.py` lo prueba con conexiones
simultáneas reales (`asyncio.gather`), no con peticiones en fila.

Los 409 llevan `detail` con un código estable (`orden_abierta_existente`, `estado_cambiado`,
`alerta_no_disponible`, `sin_revision`, `no_corregible`), el mensaje para la persona y, si aplica, la
orden existente (`orden_id`, `numero`). El cliente lo lee en `ErrorApi.conflicto`.

### Reporte de falla

`ordenes.reportar_falla`, en una transacción: reenvío por `cliente_id` primero (200 con la misma
orden); equipo, componente y alerta bajo RLS; la **lectura de horómetro** de la falla con las reglas
de la fase 2 (su `cliente_id` se deriva del de la falla con uuid5, así un reenvío no crea dos); el
número y el INSERT en un savepoint; la alerta a `convertida_en_orden` con UPDATE condicionado; el
evento `creada`. Si la lectura queda marcada, la orden **hereda** la marca y la fase 4 la ignora hasta
`confirmar-horometro`, que confirma también la lectura (una lectura enlazada a una orden responde 409
en `PATCH /lecturas/{id}`: se confirma desde la orden).

**Decisión: no hay `POST /lecturas/{id}/confirmar`.** La guía (5.3) la pide, pero la fase 2 ya tenía
`PATCH /lecturas/{id}` con `resolucion` `confirmada`, `descartada` o `reinicio`: hace lo mismo y más,
y una segunda ruta para lo mismo serían dos sitios que mantener iguales.

**Número correlativo sin huecos** (`ordenes_contador`): un `UPDATE … SET ultimo = ultimo + 1` del ORM
en la misma transacción que la orden. Si la transacción se revierte, el número vuelve. El precio,
asumido: dos fallas de la misma empresa se numeran en fila. Como en F2, nada de `ON CONFLICT`: el
savepoint y la traducción del choque por **nombre** de restricción dan el mismo resultado sin atarse
al motor. Ante cualquier choque se mira primero si la orden con ese `cliente_id` ya existe, porque
dos reenvíos simultáneos violan a la vez la idempotencia y la única abierta por componente.

### Lo que impone la base (revisión 0007)

La guía la llama «migración 0003» y la escribe como `ALTER TABLE`; aquí la tabla nunca se había
creado, así que la 0007 la **crea** con su forma final.

- **CHECK de coherencia**: no existe una orden Reparada sin reparador, trabajo y tipo; ni Cerrada sin
  quien autorizó y tiempo fuera de servicio; ni Cancelada sin motivo.
- **Siete referencias compuestas** `(empresa_id, x) → (empresa_id, id)`.
- **Índices únicos parciales**: una orden abierta por equipo y componente; una vigente por alerta.
- **Trigger `ot_inmutable`**: rechaza cualquier UPDATE de una orden cerrada o cancelada salvo que la
  transacción haya fijado `app.correccion` (`set_config(…, true)`: no se filtra a la siguiente).
  Lo abre solo `EstrategiaTenant.permitir_correccion`, en `app.db.tenant`, porque es de PostgreSQL.
- **UPDATE por columna** para `app_user`: número, empresa, fecha de la falla y quién reportó no se
  pueden reescribir. Sin DELETE en ninguna de las tres tablas.
- **Horas acumuladas** (revisión 0008): solo cambian en la misma escritura que quita la marca de
  revisión; lo impone el trigger `ot_horas_solo_al_confirmar` (en F4 lo sustituye `ot_datos_de_falla`,
  que además deja cambiarlas al convertir una orden predictiva en falla). Una cifra confirmada no se
  reescribe.
- **`orden_eventos`** solo con políticas de SELECT e INSERT, y sin permiso de UPDATE ni DELETE.
- **`v_intervalos_entre_fallas`** con `security_invoker = true`: sin la opción la vista saltaría RLS.
  *(La revisión 0009 de F4 la elimina y la sustituye `v_vidas`, que también ve las piezas que siguen
  funcionando.)*
  `tests/test_aislamiento_fase3.py` tiene la guardia que falla si una vista del esquema no la lleva.

### Horas acumuladas y reinicio del horómetro

`activos.horometro_offset` separa **el dial** (lo que se lee y se teclea) de **las horas del equipo**
(lo que mide el modelo): `horas = offset + dial`. Cada orden guarda las dos (`horometro_en_falla` y
`horas_acumuladas_en_falla`). Un reinicio —por `POST /activos/{id}/reinicio-horometro` o por la
resolución `reinicio` de una lectura marcada de la fase 2— pasa por `activos.reiniciar_horometro`, que
ajusta el offset para que las horas no se interrumpan. Un dial nuevo mayor que las horas acumuladas no
puede ser un reinicio y lo rechaza el CHECK del offset.

**El offset de su momento, no el de hoy** (revisión 0008). Cada reinicio guarda el offset que deja
(`lecturas_horometro.offset_resultante`), y las horas de una falla usan el **vigente en su fecha**
(`activos.offset_en`: el del último reinicio capturado en o antes de ella, o 0). Sin esto, una falla
capturada antes de un reinicio y recibida después por la cola contaba dos veces todo lo anterior al
cambio: con 1000 h, reinicio a 0 y dial 1005, quedaba en 2005 h en vez de 1005, y esa vida inflada
entraba en `v_intervalos_entre_fallas`. La falla sigue quedando marcada, y `confirmar-horometro`
recalcula las horas por si un reinicio se resolvió después del reporte. Los reinicios anteriores a la
0008 que no eran el último de su equipo no tienen offset reconstruible: una falla de esa época queda
marcada en vez de medirse con una cifra inventada.

### Evento de dominio y datos de demostración

Al cerrar, `orden_cerrada` se **anota** en la sesión (`app.core.eventos_dominio`) y se publica solo
si la transacción se confirma; si se revierte, se descarta. F4 no lo usa para reajustar el modelo: la
guía (decisión 13) prefiere una **marca durable** escrita en la misma transacción del cierre, que no se
pierde si el proceso cae (ver [Fase 4](#fase-4-predicción-e-inventario)).

```powershell
python tools/seed_demo.py            # empresa «Demo»: 5 roles y la flota simulada de F4 (ver abajo)
python tools/seed_demo.py --borrar
```

Las vidas se sortean de una Weibull **conocida** por componente, y el script imprime sus parámetros:
que la fase 4 los recupere prueba que el ajuste funciona. **Son datos simulados** y la tesis tiene
que decirlo. Las contraseñas de Demo se generan y se muestran una sola vez.

## Fase 4: predicción e inventario

Alcance y criterios en [`docs/contexto/07-fase4-prediccion-e-inventario.md`](docs/contexto/07-fase4-prediccion-e-inventario.md).
Las **trece decisiones** de su sección 4 las confirmó el usuario el 2026-10-18 tal como se proponían.
Las que cambian el comportamiento: el stock se descuenta **al cerrar** y un cierre sin stock es 409;
el horizonte se mide en **horas de operación** (50); umbral 25 %, multiplicador 1,30 y silencio de 7
días configurables por empresa; el modelo de partida es la **vida nominal** de cada componente (no un
dataset público); el administrador declara la **edad** de cada pieza y sin ella no hay riesgo; el
reemplazo predictivo es **censura**; el ajuste es un **máximo a posteriori con censura** y no
`weibull_min.fit` sobre intervalos; la reorden salta con el stock **estrictamente** bajo el mínimo; y
el aprendizaje al cerrar usa una **marca durable**.

### El modelo (`app.services.prediccion`)

| Módulo | Qué hace |
|---|---|
| `weibull` | Ajuste MAP de Weibull con reparación mínima sobre los estadísticos de `v_vidas` (L-BFGS-B, gradiente analítico, ≈ 1 ms), riesgo `1 − exp(−m·[((a+h)/η)^β − (a/η)^β])` y etiquetas fuente/confianza por número de fallas |
| `componentes_equipo` | Qué componentes tiene cada equipo y a qué horas del equipo se instaló la pieza inicial (`PUT /activos/{id}/componentes/{cid}`) |
| `configuracion` | Parámetros de la empresa (umbral, horizonte, alertas mínimas, ventana, multiplicador, silencio) |
| `ajuste` | Marca de reajuste con **generación** (un cierre concurrente nunca se pierde), lectura de vidas, guardado con versión e historial (curva de aprendizaje) |
| `riesgo` | Recalcula el riesgo de la empresa o de un equipo, crea alertas (dedup por índice único parcial + savepoint) y las resuelve por histéresis (0,8 × umbral) |
| `alertas` | Bandeja, reconocer, descartar (con nota y silencio), orden predictiva, resolver al cerrar, reabrir al cancelar |
| `tareas` | Lo que corre **después del commit** (lectura, cierre, ajuste) con su propia sesión: si falla, se registra y la petición ya respondió (RNF-02) |

`v_vidas` (revisión 0009) es el corazón: una fila por vida de pieza con fallas, Σ ln(edad) y horas
observadas, **incluida la vida abierta** (censura por la derecha). Una reparación no renueva la pieza;
un reemplazo sí; un reemplazo **predictivo** cierra la vida sin falla. Es `security_invoker` y usa
`NOT MATERIALIZED` para que el filtro por equipo baje al índice `ix_ot_cerradas_vida`: RNF-04 medido
en PostgreSQL real, **123 ms** con 60.000 órdenes (`test_rnf04_…`).

### Tres disparadores

1. **Lectura de horómetro** (y alertas de campo, reinicios, cambios de vida nominal o de edad):
   `BackgroundTasks` recalcula ese equipo después del commit.
2. **Cierre de orden**: en la misma transacción se descuenta el stock y se escribe la marca de
   reajuste; después, en segundo plano, se ajusta el modelo y se recalcula.
3. **Job nocturno** `python -m app.jobs.diario`: se conecta como **`job_user`** (miembro de
   `app_user`, sujeto a RLS), pide los ids con `empresas_activas()` (SECURITY DEFINER, solo para
   `job_user`) y trabaja cada empresa en su transacción, con su tenant, un candado consultivo y
   `statement_timeout`. En producción será un cron de Railway a las 06:00 UTC; en local lo programa
   APScheduler dentro del backend si `JOB_DIARIO_EN_PROCESO=true` (`app.jobs.programador`, a las
   `JOB_DIARIO_HORA` de `JOB_ZONA_HORARIA`).

`job_user` lo crea `backend/db/roles.sql`, que Docker solo ejecuta al **inicializar** el volumen. En
una base ya creada, aplicarlo una vez como superusuario:

```powershell
Get-Content backend\db\roles.sql | docker exec -i simap-db-1 psql -U simap -d simap
```

### Portabilidad: como en F3

La guía escribe cada servicio con `INSERT … ON CONFLICT` y calcula el riesgo en una sentencia SQL.
Aquí las consultas de negocio van por el ORM: `UPDATE` y, si no hubo fila, `INSERT` en un savepoint
que absorbe la carrera; la fórmula del riesgo se evalúa en Python (un solo lugar para ella). Las
garantías siguen en la base —índices únicos parciales, CHECK, triggers, RLS— y lo específico de
PostgreSQL (candado consultivo, `statement_timeout`, `empresas_activas()`) está en
`EstrategiaTenant` (`app.db.tenant`).

### Inventario (`app.services.inventario`)

- `stock_actual` y el **libro** `stock_movimientos` (solo se agrega: inicial, ingreso, consumo,
  ajuste) deben coincidir; `GET /inventario/conciliacion` lo comprueba y debe devolver `[]`.
- Las líneas (`orden_repuesto`) solo se tocan con la orden abierta: lo impone el trigger
  `orden_repuesto_inmutable` (con `FOR SHARE` sobre la orden).
- Al cerrar: se bloquean los repuestos de la orden **en orden de id**, se comprueban los faltantes
  **antes** de descontar y, si alguno no alcanza, se revierte todo con 409 `stock_insuficiente` y la
  lista `faltantes` (código, nombre, disponible, requerido). El índice `ix_stock_movimientos_consumo_unico`
  impide descontar dos veces.
- Reorden: stock **< mínimo** crea una alerta (una vigente por repuesto); al volver al mínimo se
  resuelve sola.

### Endpoints

| Ruta | Roles |
|---|---|
| `GET /activos/{id}/riesgo` | supervisor, técnico, gerente, administrador |
| `GET /riesgos` | supervisor, gerente, administrador |
| `GET /activos/{id}/componentes` · `PUT …/{cid}` | lectura: supervisor, gerente, administrador · PUT: administrador |
| `GET /componentes/{id}/modelo` | supervisor, gerente, administrador |
| `GET` · `PUT /configuracion/prediccion` | lectura: supervisor, gerente, administrador · PUT: administrador |
| `GET /alertas-sistema` | supervisor, gerente, administrador |
| `POST /alertas-sistema/{id}/reconocer` · `/descartar` · `/orden` | supervisor, administrador |
| `POST /ordenes/{id}/convertir-en-falla` | supervisor, administrador (registra la lectura con las reglas de F2, como un reporte de falla; revisión 0010) |
| `GET /repuestos` · `GET /repuestos/{id}` | supervisor, técnico, gerente, administrador |
| `POST /repuestos` · `PATCH /repuestos/{id}` · `POST /repuestos/{id}/ajuste` | administrador |
| `POST /repuestos/{id}/ingresos` | supervisor, administrador |
| `GET /repuestos/{id}/movimientos` | supervisor, gerente, administrador |
| `GET` · `PUT` · `DELETE /ordenes/{id}/repuestos[/{rid}]` | técnico, supervisor, administrador (escritura solo con la orden abierta) |
| `GET /inventario/conciliacion` | administrador |

El operario no tiene acceso a nada de F4 (403). `tests/test_prediccion.py` recorre la matriz de
roles 12.1 completa. Nuevos códigos de 409: `stock_insuficiente`, `alerta_no_disponible`,
`codigo_repuesto_duplicado`; de 422: `edad_invalida`.

### Datos de demostración y experimentos

```powershell
python tools/seed_demo.py                    # «Demo»: flota simulada, modelos y riesgos ya calculados
python tools/seed_sectores.py --solo-fase4   # datos de F4 para las cinco empresas sectoriales (no toca claves)
python tools/experimentos_fase4.py           # validación de la sección 14 (≈ 1 min; --completo ≈ 3 min)
```

`seed_demo` crea 14 bombas cuyo rodamiento falla según una Weibull **conocida** (β = 2,5; η = 1000 h),
con reparaciones y reemplazos, una orden predictiva cerrada, 15 repuestos con su libro y los dos
casos de la Definición de Hecho: **caso A** (pieza vieja, tres reparaciones, dos alertas de campo:
riesgo alto y alerta) y **caso B** (pieza recién cambiada: riesgo bajo). Al final ajusta y calcula
solo Demo e imprime el resultado (con la semilla 2026: β = 2,44, η = 1104 h con 51 fallas).
`experimentos_fase4` usa **el mismo código de ajuste** que el backend; la versión completa está en
`docs/contexto/anexos/experimentos-fase4.md`. **Todo son datos simulados**, y la tesis debe decirlo.

## Fase 5: paneles, indicadores y cierre

Alcance y criterios en [`docs/contexto/08-fase5-dashboard-y-cierre.md`](docs/contexto/08-fase5-dashboard-y-cierre.md).
Las **catorce decisiones** de su sección 4 las confirmó el usuario el 2026-10-28 tal como se
proponían, con las consultas por el ORM y el cálculo en Python (como en F3 y F4) y la web como
cliente con CSP de nonce. Las desviaciones respecto a la guía están en el anexo del mismo documento.

### Un panel por rol (`app.services.paneles`)

`GET /panel` devuelve los widgets del rol de la sesión. Cada widget es una función con su consulta;
la tabla `WIDGETS` (`widgets.py`) dice quién lo ve:

| Widget | Roles | Qué muestra |
|---|---|---|
| `mis_lecturas`, `mis_alertas` | operario | Sus últimas lecturas y alertas, con su estado |
| `cola_taller`, `mis_trabajos` | técnico | Órdenes en espera o en taller; lo que reparó |
| `contadores`, `alertas_campo`, `alertas_sistema`, `ordenes_abiertas` | supervisor, administrador | Lo que espera revisión |
| `indicadores`, `repuestos_costo`, `riesgo_top`, `riesgo_cobertura` | gerente, administrador | Disponibilidad, MTBF, MTTR, costos y riesgo |
| `salud` | administrador | Lecturas en revisión, modelos, último job, conciliación del inventario |

El **ensamblador** (`ensamblador.py`) corre cada widget en su propia transacción de solo lectura
(`sesion_de_lectura`, `REPEATABLE READ READ ONLY` vía `EstrategiaTenant.lectura_consistente`), con
un límite de 3 s para los indicadores y 2 s para los demás y como mucho tres a la vez. Si uno falla
o se pasa de tiempo vuelve como `error` o `tiempo_agotado`, el texto del error se queda en el
registro (`simap.paneles`) y el resto del panel responde (RNF-02). La cancelación se propaga.

### Indicadores (`indicadores.py`)

Las definiciones están en 08-fase5 §5 y en `01-especificacion-funcional.md` §5.7. Se calculan en
Python sobre cuatro conjuntos (equipos, paradas, lecturas y consumos) leídos con una sola foto:

- **Meses** cortados en `America/Santo_Domingo`; el periodo por defecto son los últimos 12 meses y
  el máximo 24 (más da 422).
- **Paradas** de `v_paradas`: una falla desde su fecha de falla; una predictiva desde que entra al
  taller (`inicio_de_parada`, también al cerrar). La unión de intervalos evita contar dos veces y
  el solape se atribuye a la falla.
- **Horas operadas** desde `lecturas_horometro.horas_acumuladas`, que mantiene un trigger (nula si
  la lectura está en revisión); la última lectura antes del periodo sirve de base.
- **Razones sobre totales**, nunca promedios de razones mensuales. El MTBF lleva su intervalo de
  confianza del 90 % (chi-cuadrado); sin fallas, una cota inferior.

`tests/test_indicadores.py` los compara con casos hechos a mano y con 80 flotas al azar contra una
implementación independiente (barrido de eventos); `test_rf28_indicadores_coinciden_con_el_calculo_a_mano`
hace lo mismo sobre datos sembrados en PostgreSQL.

### Lo que añade la base (revisión 0011)

- `activos.creado_en` rellenado (desde cuándo se observa el equipo). El administrador puede
  **adelantarlo** con `PATCH /activos/{id}` y `observado_desde` (422 si es posterior o futuro): así
  carga historia de antes de usar SIMAP sin poder esconder horas de calendario.
- `lecturas_horometro.horas_acumuladas` con su trigger y su CHECK.
- Vista `v_paradas` (`security_invoker`, sin escritura para la aplicación).
- Índices para el cierre de órdenes, las fallas reales, los consumos por fecha y los paneles por
  usuario. JIT apagado para `app_user` y `job_user` (`roles.sql`; en una base existente, aplicarlo
  como en F4).

### Endpoints

| Ruta | Roles |
|---|---|
| `GET /panel?planta=&desde=&hasta=` | todos (cada uno recibe sus widgets; un rol sin widgets, 403) |
| `GET /indicadores?planta=&desde=&hasta=` | gerente, administrador |
| `GET /plantas` | supervisor, gerente, administrador |

La empresa y el usuario salen siempre del token. La planta es la ubicación del equipo: **ordena la
vista, no es frontera de seguridad** (decisión 1).

### Seguridad del cierre

- **Auditoría de aislamiento** (`tests/test_auditoria_aislamiento.py`): controles de catálogo C1–C13
  (RLS forzada, políticas con `app_empresa_id()`, roles sin privilegios, nada para PUBLIC, vistas
  sin escritura, tablas de solo agregar) y un recorrido de **todas** las rutas de la API: sin sesión
  401; con un usuario de otra empresa, la misma respuesta que para un id que no existe.
- **Cabeceras de la API** (`app.core.seguridad_http`): middleware ASGI que envuelve toda la pila,
  así también los 500 las llevan. `/docs`, `/redoc` y `/openapi.json` se apagan con
  `EXPONER_DOCS=false` (en producción).
- **CSP de la web** con nonce por petición (ver «Desvío por sesión»).
- **Dependencias**: `python-jose` se sustituyó por **PyJWT 2.15.0** y `python-dotenv` subió a 1.2.2;
  `pip-audit` y `npm audit --omit=dev` sin hallazgos el 2026-10-28. CI con `permissions: contents:
  read`, gitleaks sobre todo el historial y Dependabot semanal.
- Checklist completa en [`docs/contexto/anexos/owasp-top10-2025.md`](docs/contexto/anexos/owasp-top10-2025.md)
  y trazabilidad en [`anexos/matriz-trazabilidad.md`](docs/contexto/anexos/matriz-trazabilidad.md).

Si `uvicorn` corre con otro intérprete que el del `.venv`, instalar ahí también `requirements.txt`
(PyJWT sustituye a `python-jose` y sin él la API no arranca).

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
21. **El secreto de las sesiones no tiene valor por defecto.** `JWT_SECRET` es obligatorio, de al
   menos 32 caracteres, y la API no arranca con el valor de `.env.example`: con un valor por
   defecto, un despliegue al que le faltara la variable firmaría las sesiones con un secreto que está
   en el repositorio (04-fase1, sección 6.5).
22. **Una entrada mal formada es un 422, nunca un 500.** Un `null` en un campo que la base no admite,
   un número que no cabe en la columna o un cursor manipulado se rechazan al validar, antes de llegar
   a PostgreSQL.
23. **Una orden cerrada no cambia, y el historial no se toca.** Lo impone la base (trigger,
   permisos por columna, sin políticas de UPDATE/DELETE en `orden_eventos`), no solo el código. La
   corrección administrativa es el único camino, y siempre deja su evento.
   **Las horas de una falla se miden con el offset de su fecha**, nunca con el de hoy.
   **Un relleno de datos en una migración** desactiva `FORCE ROW LEVEL SECURITY` mientras dura:
   FORCE alcanza también al dueño, y sin empresa fijada el UPDATE no vería ninguna fila.
24. **«Quién reparó» es siempre un técnico.** Ni el administrador puede marcar Reparada: en una
   empresa sin técnico, se da de alta uno en vez de suplantar el campo.
25. **El riesgo nunca se muestra sin su respaldo**: fallas registradas, confianza, «estimado» con
    confianza baja y la hora del cálculo. «Sin edad» y «sin modelo» son avisos, nunca un 0 %.
26. **El stock solo cambia por el libro.** Ningún cuerpo de petición lleva stock; los repuestos se
    desactivan, no se borran.
27. **El cálculo va después del commit.** Ninguna lectura, reporte o cierre espera ni falla por el
    modelo; lo que quede pendiente lo recoge el job.
28. **Una alerta del sistema no es una alerta de campo.** Viven en tablas distintas para que una
    alerta nunca alimente el multiplicador que la originó.
29. Antes de cada entrega: test automatizado de aislamiento entre tenants, OWASP Top 10 sobre lo nuevo,
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
| `/panel` | Panel de cada rol (F5): lo del turno para operario, técnico y supervisor; indicadores, costos y riesgo para gerente y administrador. Filtros de planta y periodo en la URL |
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
| `/ordenes`, `/ordenes/{id}` | Bandeja y detalle de órdenes de trabajo (técnico, supervisor, gerente, administrador) |
| `/activos/{id}/falla` | Reportar una falla; con `?alerta=id`, la convierte en orden |
| `/riesgo` | Equipos por riesgo de falla (supervisor, gerente, administrador) |
| `/alertas-sistema` | Bandeja de alertas del sistema: pestañas Riesgo y Reorden |
| `/componentes/{id}/modelo` | Modelo del componente: β, η, curva de riesgo y curva de aprendizaje |
| `/activos/{id}/componentes` | Componentes del equipo y edad de la pieza inicial (administrador) |
| `/configuracion/prediccion` | Parámetros de la predicción de la empresa (administrador) |
| `/inventario`, `/inventario/{id}` | Repuestos, stock, libro de movimientos, ingresos y conteos |

### Menú lateral (`src/components/arbol-navegacion.tsx`)

La navegación es un árbol por área de trabajo (Campo, Equipos, Supervisión, Administración, Mi
cuenta) definido en una sola tabla, `ARBOL` en `src/lib/auth.ts`: cada hoja declara qué roles la
ven y `arbolPara(rol)` descarta las ramas que se quedan vacías. Las fases siguientes cuelgan sus
pantallas de ahí (órdenes en F3, riesgo e inventario en F4) sin tocar el componente.

- `Marco` recibe el árbol por `lateral` y lo fija a la izquierda desde `lg`; por debajo, `MenuMovil`
  (en la barra, a la izquierda de la marca) lo abre en un cajón. Toda pantalla con sesión pasa por
  `Pantalla`, que monta los dos; la de carga reserva la columna para que nada salte.
- La hoja activa es la de ruta más larga que contiene la página (`hojaActual`), así `/activos/nuevo`
  marca «Nuevo equipo» y no también «Todos los equipos».
- «Lecturas por revisar» es un ancla dentro de `/alertas`; el panel se pinta siempre para quien
  revisa, con estado vacío, para que el enlace nunca lleve a nada.
- Las ramas plegadas se guardan en `localStorage` (`simap.menu.plegadas`) como preferencia del
  aparato, con respaldo en memoria si el almacenamiento falla.

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

Desde F5 también pone la **política de contenido**: un nonce nuevo en cada petición, `'strict-dynamic'`,
sin `unsafe-inline` ni `unsafe-eval`, `frame-ancestors 'none'` y `upgrade-insecure-requests` solo con
HTTPS. Por eso `layout.tsx` espera `connection()`: la página se pinta en cada petición para que
Next ponga el nonce en sus scripts. El resto de cabeceras fijas está en `next.config.ts`
(`Permissions-Policy`, HSTS solo en producción). Lo comprueba
`e2e/fase5.spec.ts` (`test_csp_con_nonce_por_peticion_y_script_inyectado_no_se_ejecuta`).

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

`ordenes.spec.ts` cubre la fase 3: **el ciclo completo con tres personas** en tres navegadores
(supervisora reporta desde el QR en el móvil, técnico la repara, administrador revisa lo que firma y
la cierra) y **la falla sin conexión que llega una sola vez**, aunque la red vaya y venga.

Para correrlas sin tocar el servidor que esté sirviendo el 3000, `next.config.ts` acepta otra carpeta
de compilación (`NEXT_DIST_DIR`). Next añade esa carpeta a `tsconfig.json` al compilar: hay que
devolverlo a su estado antes de hacer commit.

```powershell
# API aparte en el 8001 (otra terminal), con el origen del 3001 permitido
$env:COOKIE_SECURE="false"; $env:CORS_ORIGINS='["http://localhost:3001"]'; $env:APP_BASE_URL="http://localhost:3001"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001          # desde backend/

$env:NEXT_DIST_DIR=".next-e2e"; $env:API_ORIGEN="http://127.0.0.1:8001"
npx next build --webpack; npx next start --port 3001                       # desde frontend/
$env:E2E_BASE_URL="http://localhost:3001"; $env:E2E_API_URL="http://localhost:8001/api/v1"
npx playwright test
```

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

Última actualización: 2026-10-29 02:53 UTC

### Estado del proyecto

```text
=== ESTADO DEL CÓDIGO ===

[backend]  módulos: 77   LOC: 11975   TODO/FIXME: 0
  con test: 55/77   stubs/vacíos: 0
  por capa: api=15, cli=1, core=9, db=3, jobs=3, main=1, models=11, schemas=9, services=25

[frontend]  módulos: 70   LOC: 13726   TODO/FIXME: 0
  con test: 0/70   stubs/vacíos: 0
  por capa: app=27, components=24, lib=18, src=1

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

  F3 - Órdenes de trabajo (semanas 7-8)  (11/12, 91%)
    cubre: RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RNF-06
    hecho cuando: Una falla sigue su ciclo completo hasta cerrarse, con cada responsable visible en el historial.
    [x] Migración 0007: órdenes, contador, eventos, trigger de inmutabilidad, vista security_invoker, offset del horómetro  <done>
    [x] Reporte de falla del supervisor → crea orden en 'reportada' con número correlativo y lectura  <done (auto)>
    [x] Máquina de estados con Cancelada y rechazo de cierre, transiciones por rol y UPDATE condicionado  <done (auto)>
    [x] Trazabilidad reportado_por / reparado_por / autorizado_por y tiempo fuera de servicio  <done>
    [x] Vincular alerta previa a la orden (alerta_origen_id) y pre-llenar el formulario  <done>
    [x] Reinicio del horómetro (offset) y confirmación del horómetro desde la orden  <done>
    [x] Offset histórico: la falla usa el offset vigente en su fecha (revisión 0008)  <done>
    [x] Evento de dominio orden_cerrada, publicado después del commit  <done (auto)>
    [x] Frontend: formulario de falla, bandeja y detalle de orden con acciones por rol  <done (auto)>
    [x] Falla sin conexión sobre la cola de la fase 2  <done>
    [x] Datos de demostración (empresa Demo, Weibull conocida)  <done>
    [ ] Prueba con un teléfono real: reportar una falla desde el QR  <pending>

  F4 - Predicción e inventario (semanas 9-12)  (14/15, 93%)
    cubre: RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25, RF-26, RNF-02, RNF-04
    hecho cuando: Al cerrar una orden real el modelo se reajusta; un activo con fallas frecuentes muestra riesgo visiblemente mayor.
    [x] Migración 0009: inventario, componentes por equipo, alertas del sistema, modelos, riesgos, v_vidas, RLS y empresas_activas()  <done>
    [x] Modelo Weibull con censura y prior (MAP), riesgo y nivel de confianza  <done (auto)>
    [x] Componentes de cada equipo y edad de la pieza; configuración por empresa  <done (auto)>
    [x] Reajuste con marca durable y generación; historial (curva de aprendizaje)  <done (auto)>
    [x] Riesgo por lectura, cierre y job; multiplicador por alertas de campo (RF-18..20)  <done (auto)>
    [x] Alertas del sistema con deduplicación, histéresis y silencio; orden predictiva y conversión en falla (RF-21)  <done (auto)>
    [x] Job nocturno como job_user, con candado por empresa (RF-22)  <done (auto)>
    [x] Inventario: repuestos, libro, líneas, descuento al cerrar con 409, reorden y conciliación (RF-23..26)  <done (auto)>
    [x] Frontend: riesgo, bandeja de alertas, modelo del componente, edades, configuración  <done (auto)>
    [x] Frontend: inventario, libro y repuestos en la orden  <done (auto)>
    [x] e2e: alerta → orden predictiva → cierre con repuesto, y cierre sin stock  <done>
    [x] Datos de demostración (flota Weibull β=2,5 η=1000, casos A y B) y datos de fase 4 de las empresas sectoriales  <done>
    [x] Experimentos de validación de la sección 14  <done>
    [x] Riesgo sin conexión como último valor conocido (10.2)  <done>
    [ ] Despliegue del job como cron de Railway  <pending>

  F5 - Dashboard y cierre (semanas 13-16)  (9/10, 90%)
    cubre: RF-27, RF-28, RNF-01, RNF-02, RNF-04
    hecho cuando: Los tres paneles muestran datos reales; las pruebas de aislamiento entre tenants pasan sin excepción.
    [x] Migración 0011: activos.creado_en, horas_acumuladas con trigger, v_paradas, índices, JIT apagado  <done>
    [x] Indicadores: disponibilidad, utilización, MTBF con IC 90 %, MTTR, costos por mes (RF-28)  <done (auto)>
    [x] Widgets por rol con ensamblador aislado (timeout, degradación, RNF-02) y endpoints /panel, /indicadores, /plantas (RF-27)  <done (auto)>
    [x] Frontend: panel de cada rol con filtros, gráficas accesibles y tabla  <done (auto)>
    [x] Adelantar desde cuándo se observa un equipo (decisión 8)  <done>
    [x] Auditoría de aislamiento entre tenants automatizada + pruebas e2e (Playwright) de flujos críticos  <done>
    [x] Checklist OWASP Top 10 y verificación de secretos  <done>
    [x] Cabeceras de seguridad de la API y CSP con nonce en la web  <done (auto)>
    [x] Documentación técnica y manual de usuario finales  <done>
    [ ] Auditoría de aislamiento contra staging y RNF-04 con latencia real  <pending>

AVANCE GLOBAL: 64/69 tareas (92%)
```

### Módulos del backend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `app.api.v1.comun` | api | 7 | 8 | 97 | — |
| `app.api.v1.router` | api | 13 | 1 | 38 | — |
| `app.api.v1.routes.activos` | api | 12 | 1 | 219 | ✅ |
| `app.api.v1.routes.alertas` | api | 9 | 1 | 96 | ✅ |
| `app.api.v1.routes.auth` | api | 7 | 1 | 210 | ✅ |
| `app.api.v1.routes.campo` | api | 7 | 1 | 43 | ✅ |
| `app.api.v1.routes.componentes` | api | 7 | 1 | 61 | ✅ |
| `app.api.v1.routes.health` | api | 2 | 1 | 9 | ✅ |
| `app.api.v1.routes.lecturas` | api | 10 | 1 | 137 | ✅ |
| `app.api.v1.routes.operador` | api | 9 | 1 | 315 | ✅ |
| `app.api.v1.routes.ordenes` | api | 13 | 3 | 404 | ✅ |
| `app.api.v1.routes.paneles` | api | 5 | 1 | 75 | ✅ |
| `app.api.v1.routes.prediccion` | api | 17 | 1 | 318 | ✅ |
| `app.api.v1.routes.repuestos` | api | 10 | 1 | 208 | — |
| `app.api.v1.routes.usuarios` | api | 5 | 1 | 66 | ✅ |
| `app.cli` | cli | 5 | 0 | 189 | ✅ |
| `app.core.almacen` | core | 1 | 6 | 112 | ✅ |
| `app.core.auth` | core | 2 | 5 | 123 | ✅ |
| `app.core.config` | core | 0 | 20 | 122 | ✅ |
| `app.core.cursor` | core | 0 | 9 | 57 | ✅ |
| `app.core.eventos_dominio` | core | 1 | 1 | 45 | ✅ |
| `app.core.rbac` | core | 2 | 10 | 36 | ✅ |
| `app.core.registro` | core | 0 | 15 | 99 | ✅ |
| `app.core.security` | core | 1 | 21 | 225 | ✅ |
| `app.core.seguridad_http` | core | 0 | 1 | 56 | — |
| `app.db.deps` | db | 3 | 15 | 118 | ✅ |
| `app.db.session` | db | 2 | 4 | 95 | ✅ |
| `app.db.tenant` | db | 1 | 1 | 174 | ✅ |
| `app.jobs.diario` | jobs | 3 | 0 | 29 | — |
| `app.jobs.programador` | jobs | 3 | 1 | 32 | — |
| `app.jobs.recalculo_riesgo` | jobs | 5 | 2 | 59 | — |
| `app.main` | main | 6 | 0 | 123 | — |
| `app.models.activo` | models | 1 | 13 | 72 | — |
| `app.models.alerta` | models | 1 | 6 | 80 | — |
| `app.models.base` | models | 0 | 11 | 32 | — |
| `app.models.componente` | models | 1 | 9 | 59 | — |
| `app.models.empresa` | models | 1 | 5 | 19 | ✅ |
| `app.models.lectura_horometro` | models | 1 | 6 | 125 | — |
| `app.models.operador` | models | 1 | 3 | 68 | ✅ |
| `app.models.orden_trabajo` | models | 1 | 9 | 236 | ✅ |
| `app.models.prediccion` | models | 1 | 8 | 318 | ✅ |
| `app.models.repuesto` | models | 1 | 4 | 134 | — |
| `app.models.usuario` | models | 2 | 6 | 61 | ✅ |
| `app.schemas.activo` | schemas | 2 | 7 | 121 | — |
| `app.schemas.auth` | schemas | 1 | 4 | 63 | ✅ |
| `app.schemas.campo` | schemas | 1 | 4 | 118 | ✅ |
| `app.schemas.health` | schemas | 0 | 1 | 6 | ✅ |
| `app.schemas.inventario` | schemas | 0 | 1 | 87 | ✅ |
| `app.schemas.operador` | schemas | 1 | 1 | 66 | ✅ |
| `app.schemas.orden_trabajo` | schemas | 0 | 5 | 153 | ✅ |
| `app.schemas.prediccion` | schemas | 0 | 2 | 151 | ✅ |
| `app.schemas.usuario` | schemas | 1 | 1 | 40 | ✅ |
| `app.services.activos` | services | 6 | 6 | 312 | ✅ |
| `app.services.alertas` | services | 6 | 2 | 160 | ✅ |
| `app.services.auth` | services | 8 | 2 | 300 | ✅ |
| `app.services.campo` | services | 6 | 1 | 163 | ✅ |
| `app.services.capturas` | services | 2 | 9 | 53 | ✅ |
| `app.services.componentes` | services | 2 | 3 | 97 | ✅ |
| `app.services.inventario` | services | 6 | 2 | 452 | ✅ |
| `app.services.lecturas` | services | 8 | 4 | 288 | ✅ |
| `app.services.limites` | services | 2 | 5 | 50 | ✅ |
| `app.services.operador` | services | 8 | 1 | 323 | ✅ |
| `app.services.ordenes` | services | 14 | 7 | 677 | ✅ |
| `app.services.ordenes_estados` | services | 11 | 1 | 342 | ✅ |
| `app.services.paneles.consultas` | services | 9 | 1 | 583 | — |
| `app.services.paneles.ensamblador` | services | 0 | 2 | 90 | ✅ |
| `app.services.paneles.indicadores` | services | 0 | 3 | 320 | ✅ |
| `app.services.paneles.widgets` | services | 4 | 1 | 119 | — |
| `app.services.prediccion.ajuste` | services | 4 | 6 | 214 | — |
| `app.services.prediccion.alertas` | services | 8 | 2 | 267 | ✅ |
| `app.services.prediccion.componentes_equipo` | services | 4 | 2 | 147 | — |
| `app.services.prediccion.configuracion` | services | 1 | 3 | 49 | — |
| `app.services.prediccion.riesgo` | services | 7 | 2 | 429 | — |
| `app.services.prediccion.tareas` | services | 5 | 8 | 102 | — |
| `app.services.prediccion.weibull` | services | 0 | 2 | 172 | ✅ |
| `app.services.qr` | services | 0 | 2 | 84 | ✅ |
| `app.services.usuarios` | services | 2 | 1 | 114 | ✅ |

### Módulos del frontend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `src/app/activos/[id]/componentes/page.tsx` | app | 10 | 0 | 285 | — |
| `src/app/activos/[id]/editar/page.tsx` | app | 8 | 0 | 104 | — |
| `src/app/activos/[id]/etiqueta/page.tsx` | app | 5 | 0 | 83 | — |
| `src/app/activos/[id]/falla/page.tsx` | app | 6 | 0 | 89 | — |
| `src/app/activos/nuevo/page.tsx` | app | 4 | 0 | 32 | — |
| `src/app/activos/page.tsx` | app | 9 | 0 | 224 | — |
| `src/app/alertas-sistema/page.tsx` | app | 12 | 0 | 366 | — |
| `src/app/alertas/page.tsx` | app | 8 | 0 | 210 | — |
| `src/app/componentes/[id]/modelo/page.tsx` | app | 8 | 0 | 185 | — |
| `src/app/componentes/page.tsx` | app | 7 | 0 | 269 | — |
| `src/app/configuracion/prediccion/page.tsx` | app | 7 | 0 | 196 | — |
| `src/app/equipo/page.tsx` | app | 20 | 0 | 696 | — |
| `src/app/escanear/page.tsx` | app | 6 | 0 | 72 | — |
| `src/app/globals.css` | app | 0 | 1 | 197 | — |
| `src/app/inventario/[id]/page.tsx` | app | 10 | 0 | 351 | — |
| `src/app/inventario/page.tsx` | app | 10 | 0 | 247 | — |
| `src/app/layout.tsx` | app | 2 | 0 | 73 | — |
| `src/app/login/page.tsx` | app | 7 | 0 | 185 | — |
| `src/app/operador/clave/page.tsx` | app | 3 | 0 | 60 | — |
| `src/app/operador/page.tsx` | app | 5 | 0 | 566 | — |
| `src/app/ordenes/[id]/page.tsx` | app | 13 | 0 | 241 | — |
| `src/app/ordenes/page.tsx` | app | 8 | 0 | 201 | — |
| `src/app/page.tsx` | app | 2 | 0 | 44 | — |
| `src/app/panel/clave/page.tsx` | app | 4 | 0 | 55 | — |
| `src/app/panel/page.tsx` | app | 13 | 0 | 726 | — |
| `src/app/panel/usuarios/page.tsx` | app | 9 | 0 | 267 | — |
| `src/app/riesgo/page.tsx` | app | 8 | 0 | 173 | — |
| `src/components/acciones-orden.tsx` | components | 7 | 1 | 855 | — |
| `src/components/arbol-navegacion.tsx` | components | 2 | 2 | 169 | — |
| `src/components/avisos-cola.tsx` | components | 7 | 1 | 149 | — |
| `src/components/barra-sesion.tsx` | components | 4 | 1 | 114 | — |
| `src/components/boton.tsx` | components | 0 | 29 | 72 | — |
| `src/components/campo.tsx` | components | 0 | 15 | 143 | — |
| `src/components/escaner-qr.tsx` | components | 3 | 1 | 153 | — |
| `src/components/estado.tsx` | components | 1 | 15 | 149 | — |
| `src/components/formulario-activo.tsx` | components | 4 | 2 | 147 | — |
| `src/components/formulario-alerta.tsx` | components | 9 | 1 | 147 | — |
| `src/components/formulario-clave.tsx` | components | 3 | 2 | 165 | — |
| `src/components/formulario-falla.tsx` | components | 11 | 2 | 452 | — |
| `src/components/formulario-horometro.tsx` | components | 10 | 3 | 195 | — |
| `src/components/graficas.tsx` | components | 1 | 1 | 317 | — |
| `src/components/historial-orden.tsx` | components | 3 | 1 | 120 | — |
| `src/components/iconos.tsx` | components | 0 | 19 | 137 | — |
| `src/components/indicador-cola.tsx` | components | 2 | 1 | 77 | — |
| `src/components/lecturas-por-revisar.tsx` | components | 6 | 1 | 139 | — |
| `src/components/marco.tsx` | components | 0 | 22 | 209 | — |
| `src/components/pantalla.tsx` | components | 7 | 21 | 121 | — |
| `src/components/registro-sw.tsx` | components | 0 | 1 | 28 | — |
| `src/components/repuestos-orden.tsx` | components | 5 | 1 | 321 | — |
| `src/components/riesgo.tsx` | components | 5 | 5 | 319 | — |
| `src/components/segmento.tsx` | components | 0 | 2 | 42 | — |
| `src/lib/acceso.ts` | lib | 3 | 1 | 53 | — |
| `src/lib/activos.ts` | lib | 1 | 20 | 155 | — |
| `src/lib/api.ts` | lib | 0 | 40 | 221 | — |
| `src/lib/auth.ts` | lib | 1 | 35 | 368 | — |
| `src/lib/campo.ts` | lib | 2 | 9 | 141 | — |
| `src/lib/captura.ts` | lib | 5 | 2 | 83 | — |
| `src/lib/formato.ts` | lib | 0 | 21 | 31 | — |
| `src/lib/horometro.ts` | lib | 2 | 3 | 42 | — |
| `src/lib/inventario.ts` | lib | 2 | 6 | 114 | — |
| `src/lib/offline-queue.ts` | lib | 4 | 6 | 378 | — |
| `src/lib/operador.ts` | lib | 1 | 3 | 121 | — |
| `src/lib/ordenes.ts` | lib | 4 | 11 | 227 | — |
| `src/lib/paneles.ts` | lib | 2 | 2 | 255 | — |
| `src/lib/prediccion.ts` | lib | 3 | 8 | 222 | — |
| `src/lib/qr.ts` | lib | 0 | 4 | 60 | — |
| `src/lib/sesion.ts` | lib | 3 | 2 | 98 | — |
| `src/lib/sondeo.ts` | lib | 0 | 4 | 41 | — |
| `src/lib/usuarios.ts` | lib | 2 | 1 | 41 | — |
| `src/proxy.ts` | src | 0 | 0 | 138 | — |

Diagramas: [backend](docs/diagramas/dependencias-backend.md) · [frontend](docs/diagramas/dependencias-frontend.md)
<!-- graph:auto:end -->
