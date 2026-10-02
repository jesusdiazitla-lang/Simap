# Fase 1: Fundamentos — Guía Detallada de Implementación

> Transcripción de `Fase1_Fundamentos_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado).
> Fuente de verdad del **alcance y los criterios de aceptación** de la fase F1 en `docs/PLAN.yaml`.
> Donde este documento contradice a `02-arquitectura.md`, manda este: es posterior y más específico.

## 1. Objetivo de la fase

Dejar lista la base sobre la que se construye todo lo demás: autenticación, aislamiento entre
empresas (multi-tenant) y control de acceso por rol. Ningún módulo de las fases 2 a 5 es seguro si
esta fase queda incompleta o se hace a medias.

## 2. Alcance

**Incluye:** repositorio, estructura y CI/CD; tablas `empresas` y `usuarios` versionadas con Alembic;
registro, login, refresh y logout (JWT + refresh token); RBAC a nivel de API; Row-Level Security
activa desde el primer commit; esqueleto de la PWA con login y enrutamiento por rol.

**No incluye:** activos, QR, alertas, órdenes de trabajo, inventario y motor de predicción (fases 2-4);
paneles de indicadores y auditoría formal (fase 5). El registro básico de intentos de login sí entra aquí.

## 3. Estructura de carpetas propuesta

```
simap/
  backend/
    app/
      main.py
      core/       config.py  security.py  database.py
      models/     empresa.py  usuario.py
      schemas/    empresa.py  usuario.py
      api/v1/     auth.py  usuarios.py
      dependencies/ auth.py
    alembic/versions/
    tests/test_auth.py
    requirements.txt  Dockerfile  .env.example
  frontend/
    app/login/page.tsx  app/layout.tsx  lib/auth.ts  middleware.ts
    package.json  .env.local.example
  .github/workflows/ci.yml
  docker-compose.yml
```

> **Desviación adoptada en este repositorio.** SIMAP ya usa `app/db/` (sesión y dependencias) en lugar
> de `app/core/database.py`, y `app/api/v1/routes/` en lugar de `app/api/v1/*.py` sueltos, porque el
> contrato de capas de `import-linter` (`main → api|jobs → services → db → models → schemas → core`)
> exige que el acceso a datos sea su propia capa. Las dependencias de autenticación viven en
> `app/core/` y `app/db/deps.py`, no en `app/dependencies/`.

## 4. Tareas detalladas

### 4.1 Repositorio y entorno
- Dos carpetas principales: `backend/` (FastAPI) y `frontend/` (Next.js).
- `.gitignore` que excluye `.env`, `__pycache__`, `node_modules` y `.next`.
- Linters desde el primer commit: ruff + black en Python, eslint + prettier en TypeScript.
- `README.md` inicial con los comandos para levantar el proyecto.

### 4.2 Integración continua
- GitHub Actions en cada push y pull request: instala dependencias, ejecuta el linter, corre pytest
  en el backend y el build de Next.js en el frontend.
- Protección de `main`: prohibido el push directo; todo cambio entra por pull request con el
  pipeline en verde.

### 4.3 Modelo de datos base
- Tablas `empresas` y `usuarios` (definición completa en el documento de Arquitectura Técnica).
- Alembic configurado desde el primer commit: ninguna tabla se crea o modifica a mano contra la base.
- Primera migración: extensión `pgcrypto`, tabla `empresas`, tabla `usuarios`.

### 4.4 Autenticación
- ~~`POST /auth/register` — crea una empresa nueva junto con su primer usuario administrador.~~
  **DESVIACIÓN APLICADA (2026-09-26).** Esta ruta no existe en la implementación. Al concretar el
  modelo de negocio, el usuario confirmó que SIMAP **se cobra por equipo monitoreado**, de modo que
  una empresa no puede darse de alta a sí misma: usaría el sistema completo sin haber pagado. El
  alta pasa a ser una operación administrativa por consola,
  `python -m app.cli crear-empresa`, que invoca la misma función de servicio que habría usado la
  ruta. Retirar el endpoint no bastaba por sí solo —FastAPI lo habría seguido anunciando en el
  esquema OpenAPI si se reintrodujera—, así que la revisión `0002` de Alembic estrecha además la
  política RLS de `empresas` para que solo `simap_owner` pueda insertar. Ver README.md, sección
  «Alta de empresas», y `backend/app/cli.py`.
- `POST /auth/login` — valida correo y contraseña; devuelve access token (JWT, 30 min) y refresh
  token (7 días).
- Hash con Argon2id. Parámetros recomendados: `time_cost=3`, `memory_cost=65536` KiB,
  `parallelism=4`; ajustar según el hardware de producción.
- `POST /auth/refresh` — emite un nuevo access token a partir de un refresh token vigente.
- `POST /auth/logout` — revoca el refresh token (requiere tabla o lista de tokens revocados).
- El JWT incluye en su payload: `sub` (id de usuario), `empresa_id`, `rol` y `exp`.

### 4.4.bis AMPLIACIÓN NO PREVISTA: el plano de control (2026-09-26)

Este documento describe un sistema con un solo tipo de usuario: el que pertenece a una empresa. Al
construirlo apareció una pregunta que la especificación no contempla: **quién da de alta a las
empresas clientes**. El PDF lo resolvía con `POST /auth/register`, es decir, autoservicio; el
modelo de negocio confirmado por el usuario (cobro **por equipo monitoreado**) lo descarta.

La ampliación añade un segundo tipo de cuenta, el **operador de SIMAP**, que no pertenece a ninguna
empresa y por tanto rompe la suposición sobre la que descansa todo el aislamiento de la sección 6.3.
Se resolvió separando dos planos, con un cuarto rol de PostgreSQL (`operador_user`) cuyos permisos
se conceden tabla por tabla, de modo que **el operador no puede leer datos de negocio de ningún
cliente**. Detalle completo en `README.md`, sección «Dos planos: control y datos», y en la revisión
`0003` de Alembic.

Consecuencia para las fases siguientes: al crear cualquier tabla de negocio (activos, lecturas,
alertas, órdenes, repuestos) **no se le conceden permisos a `operador_user`**. Queda fuera de su
alcance por omisión.

### 4.5 Control de acceso por rol (RBAC)
- Enum de roles: `operario`, `supervisor`, `tecnico_taller`, `gerente`, `administrador`.
- Dependencia reutilizable `require_role(*roles)` en FastAPI, aplicada explícitamente en cada endpoint.
- Ningún endpoint asume un rol por defecto: si no se declara qué roles pueden usarlo, se rechaza el acceso.

### 4.6 Multi-tenancy y Row-Level Security
- Columna `empresa_id` en `usuarios` y en toda tabla que se agregue en fases posteriores.
- RLS activa sobre `usuarios` desde el primer commit.
- Dependencia `get_db` unificada: valida el JWT, abre una transacción, ejecuta
  `SET LOCAL app.empresa_id` y solo entonces entrega la sesión a la ruta.
- Prueba automatizada desde esta fase: dos empresas con un usuario cada una, verificar que ninguna
  puede leer los datos de la otra ni forzando el request manualmente.

### 4.7 Esqueleto de la PWA
- Next.js (App Router) en TypeScript.
- Configuración base de PWA: manifest, ícono, service worker mínimo.
- Pantalla de login conectada al endpoint real.
- Manejo de sesión en el cliente con el usuario y su rol.
- `middleware.ts` que redirige a `/login` sin sesión activa, y a la vista del rol una vez autenticado.

> **Aplicado así en este repositorio (2026-10-02).** Desde Next.js 16 `middleware.ts` se llama
> `proxy.ts` (`frontend/src/proxy.ts`); es la misma pieza. No mira el token de acceso sino una
> cookie-pista que la API pone junto con el refresh token: el de acceso caduca a los 30 minutos y
> mirarlo echaría a quien todavía puede renovar su sesión en silencio. Nunca desvía `/login`, para
> que una pista caducada no provoque un bucle. El service worker mínimo es `frontend/public/sw.js`:
> solo enseña una página propia cuando no hay red, y no guarda en caché ninguna respuesta de la API.
>
> En el mismo cierre se añadió algo que el documento no pide pero que la ampliación 4.4.bis hacía
> imprescindible: **cambiar la contraseña propia** en los dos planos. El administrador de cada
> planta entra con una clave temporal que vio quien se la dio, y sin esto no podía cambiarla.
> Cambiar o restablecer una clave cierra además las demás sesiones (revisión 0004 de Alembic).

## 5. Flujo de autenticación y aplicación de RLS

1. Cliente envía credenciales — `POST /login` (correo y contraseña).
2. Backend valida y emite JWT — Argon2id + JWT con rol y `empresa_id`.
3. Cliente guarda el token — cookie httpOnly, Secure, SameSite.
4. Cada request incluye el JWT — el backend valida firma y expiración.
5. Backend fija el tenant — `SET LOCAL app.empresa_id = :eid`.
6. PostgreSQL aplica RLS — la consulta solo ve filas de esa empresa.

## 6. Consideraciones de seguridad

### 6.1 Almacenamiento y transporte del token
- El JWT va en cookie `httpOnly`, `Secure`, `SameSite=Strict` (o `Lax`) — **nunca** en `localStorage`
  ni `sessionStorage`, donde un XSS podría leerlo.
- HTTPS obligatorio salvo en desarrollo local.

### 6.2 Contraseñas y mensajes de error
- Argon2id, no bcrypt ni SHA-256: resiste mejor ataques acelerados por GPU o ASIC.
- Mensaje de login siempre genérico ("credenciales inválidas"); nunca distinguir entre usuario
  inexistente y contraseña incorrecta, porque eso revela qué correos existen.
- Rate limiting en `/auth/login` desde el primer commit (p. ej. 5 intentos por minuto por IP y por correo).

### 6.3 Row-Level Security: el detalle que casi siempre se pasa por alto
- Por defecto PostgreSQL **no** aplica las políticas de RLS al dueño de la tabla ni a roles con
  `BYPASSRLS` (como el superusuario). Si el backend se conecta con el mismo usuario que creó las
  tablas, las políticas quedan efectivamente desactivadas sin que nadie lo note.
- Solución: crear un rol de aplicación (`app_user`) sin privilegios de superusuario ni de propietario,
  usar `FORCE ROW LEVEL SECURITY` además de `ENABLE ROW LEVEL SECURITY` en cada tabla, y conectar el
  backend siempre con ese rol limitado.
- El `empresa_id` nunca se toma de lo que envía el cliente (query param, header o cuerpo) — siempre
  se deriva del JWT ya validado por el servidor.

> **Ampliación verificada contra PostgreSQL 16 (no está en el PDF).** El documento dice que `FORCE`
> cierra la puerta del propietario, y es cierto — pero solo si el propietario **no es superusuario**.
> PostgreSQL deja pasar siempre a los superusuarios: ni `ENABLE` ni `FORCE` les afectan, y no hay
> forma de evitarlo. En la imagen oficial de Docker, `POSTGRES_USER` se crea como superusuario y es
> dueño de todas las tablas, así que aplicar solo lo que dice el PDF deja el `FORCE` **decorativo**.
>
> Por eso hay **tres** roles y no dos:
>
> | Rol | Superusuario | Dueño | Uso |
> |---|---|---|---|
> | `simap` | Sí | No | Solo administrar la base. Ignora RLS por diseño. |
> | `simap_owner` | No | Sí | Corre las migraciones. `FORCE` **sí** le aplica. |
> | `app_user` | No | No | El que usa el backend. |
>
> La sección 5 de `backend/db/rls_policies.sql` transfiere la propiedad de todas las tablas a
> `simap_owner`. Lo demuestra `backend/tests/test_aislamiento_tenant.py`, cuyo test del propietario
> fallaba (`2 != 1`) antes de este cambio.

### 6.4 CORS y cabeceras
- Lista blanca explícita de orígenes; nunca `Access-Control-Allow-Origin: *`, sobre todo con la
  sesión viajando en cookie.
- Cabeceras activas desde ya: `Strict-Transport-Security` y `X-Content-Type-Options: nosniff`.

### 6.5 Secretos y validación
- `JWT_SECRET`, cadenas de conexión y credenciales solo en variables de entorno; el `.env` real nunca
  se commitea, solo un `.env.example` sin valores reales.
- Un secreto distinto por ambiente; nunca reutilizar el mismo `JWT_SECRET`.
- Pydantic en modo estricto en cada endpoint: rechazar campos inesperados, tipos incorrectos y
  longitudes fuera de rango antes de tocar la base de datos.

## 7. Consideraciones de escalabilidad

### 7.1 Diseño sin estado
El backend no guarda sesiones en memoria del proceso: toda la información de sesión vive en el JWT o
en Redis. Así se puede correr una o diez instancias sin cambiar una línea de código.

### 7.2 Identificadores y esquema
- UUID como llave primaria en todas las tablas, no enteros autoincrementales: evita colisiones al
  migrar o fusionar datos y no revela cuántos registros existen.
- Índice en `empresa_id` desde el primer commit en cada tabla multiempresa: es gratis ahora y muy
  costoso después con la tabla en producción.

### 7.3 Migraciones disciplinadas
Ningún cambio de esquema se hace a mano contra la base, ni siquiera en desarrollo: todo pasa por una
migración de Alembic.

### 7.4 Conexión a la base de datos
Pool asíncrono de SQLAlchemy correctamente dimensionado. Si más adelante se añade PgBouncer, debe ir
en **session pooling**, no en transaction pooling: este último puede reiniciar la conexión entre
sentencias y perder el valor de `SET LOCAL app.empresa_id` a mitad de una operación — un problema de
escalabilidad y de seguridad a la vez.

### 7.5 Configuración por entorno y modularidad
- Toda configuración (URLs, límites, umbrales) sale de variables de entorno, nunca de valores fijos.
- Monolito modular: los módulos de autenticación, empresas y usuarios se escriben con fronteras
  claras, para que extraer uno como servicio sea trabajo de extracción y no de reescritura.

## 8. Variables de entorno necesarias

`backend/.env.example`:

```
DATABASE_URL=postgresql+asyncpg://app_user:changeme@localhost:5432/simap
JWT_SECRET=<generar uno distinto por ambiente>
JWT_ACCESS_EXPIRE_MINUTES=30
JWT_REFRESH_EXPIRE_DAYS=7
ARGON2_TIME_COST=3
ARGON2_MEMORY_COST=65536
ARGON2_PARALLELISM=4
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

## 9. Definición de "hecho" para la Fase 1

- [ ] Un usuario puede registrarse y su empresa queda creada correctamente.
- [ ] Un usuario puede iniciar sesión y recibe access token y refresh token válidos.
- [ ] El token se guarda en cookie httpOnly y no es accesible desde JavaScript.
- [ ] Un usuario autenticado solo puede leer o modificar datos de su propia empresa, confirmado con
      una prueba automatizada que intenta acceder a datos de otra empresa por API directa.
- [ ] El rol del usuario limita correctamente los endpoints a los que puede acceder.
- [ ] Las políticas de RLS están activas con `FORCE ROW LEVEL SECURITY`, y el backend se conecta con
      un rol de base de datos sin privilegios de superusuario.
- [ ] El pipeline de CI corre pruebas automáticas en cada push y bloquea el merge si fallan.
- [ ] Ningún secreto vive en el repositorio.
- [ ] El endpoint de login tiene rate limiting activo.
- [ ] La pantalla de login del frontend funciona de punta a punta contra el backend real.

## 10. Siguiente paso

Con la fase completa y verificada contra la lista anterior, la Fase 2 (Activos y Registro de Campo)
puede construirse sobre un backend que ya es seguro y multiempresa desde su primer commit.
