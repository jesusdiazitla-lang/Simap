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
│   │   ├── schemas/           # modelos Pydantic de entrada/salida
│   │   ├── services/          # lógica de negocio (sin FastAPI)
│   │   ├── db/                # sesión async y dependencia get_db (fija app.empresa_id)
│   │   ├── models/            # entidades SQLAlchemy (espejo de db/schema.sql)
│   │   └── jobs/              # tareas APScheduler (recalculo diario de riesgo)
│   ├── db/schema.sql          # DDL de referencia + rls_policies.sql
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
├── .github/workflows/docs.yml # CI: grafo + tests + docs en cada push a main
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
docker compose up -d db redis

# 3) Backend
.\.venv\Scripts\Activate.ps1
cd backend; Copy-Item .env.example .env         # ajustar JWT_SECRET
uvicorn app.main:app --reload                   # http://localhost:8000/docs

# 4) Frontend (otra terminal)
cd frontend; Copy-Item .env.local.example .env.local; npm run dev   # http://localhost:3000
```

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

1. Toda tabla de empresa lleva `empresa_id` y tiene RLS activada (`backend/db/rls_policies.sql`).
2. `app.db.deps.get_db` ejecuta `SET LOCAL app.empresa_id = <empresa_id del JWT>` en cada transacción.
   El valor sale **del token firmado**, jamás de un parámetro del cliente.
3. RBAC se verifica en cada endpoint con una dependencia (`app.core.rbac`), no solo en la UI.
4. Antes de cada entrega: test automatizado de aislamiento entre tenants, OWASP Top 10 sobre lo nuevo,
   sin secretos en repo ni logs (`pip-audit` / `npm audit` en CI).

## Flujo de documentación

1. **Local (`.githooks/pre-push`)** — al hacer push a `main`:
   - regenera grafo y diagramas, ejecuta `check` y los tests;
   - refresca la sección auto-generada del README (`graph.py docs`);
   - si los commits tocan `backend/` o `frontend/` pero ninguno toca
     `README.md`, `README_USER.md` o `MANUAL_USUARIO.md`, **bloquea el push**.
2. **Remoto (`.github/workflows/docs.yml`)** — en cada push a `main`:
   - repite `build`, `check`, tests y `docs`;
   - si el README auto-generado cambió, lo commitea como `docs: actualizar grafo y estado [skip ci]`.

Para saltar el hook en una emergencia: `git push --no-verify` (queda registrado en el historial que no se validó).

## Calidad

```powershell
cd backend
ruff check . ; ruff format . ; mypy app ; pytest
cd ../frontend
npm run lint ; npm run graph:check
```

<!-- graph:auto:start -->
_Sección generada por `python tools/graph/graph.py docs`. No editar a mano; se sobrescribe en cada push a `main`._

Última actualización: 2026-09-17 12:21 UTC

### Estado del proyecto

```text
=== ESTADO DEL CÓDIGO ===

[backend]  módulos: 5   LOC: 57   TODO/FIXME: 0
  con test: 2/5   stubs/vacíos: 0
  por capa: api=2, core=1, main=1, schemas=1

[frontend]  módulos: 3   LOC: 115   TODO/FIXME: 0
  con test: 0/3   stubs/vacíos: 0
  por capa: app=3

ciclos de importación: 0

=== PLAN (docs/PLAN.yaml) ===

  F0 - Infraestructura del repositorio  (5/5, 100%)
    [x] Repositorio, .gitignore, estructura backend/frontend  <done>
    [x] Herramienta de grafo de dependencias (tools/graph)  <done>
    [x] Hook pre-push + GitHub Action de documentación  <done>
    [x] Documentación inicial (README, README_USER, MANUAL_USUARIO)  <done>
    [x] Documentos de contexto transcritos en docs/contexto y DDL en backend/db  <done>

  F1 - Fundamentos: auth, multi-tenant y RLS (semanas 1-2)  (2/9, 22%)
    cubre: RF-01, RF-02, RF-03, RNF-01, RNF-07, RNF-08
    hecho cuando: Un usuario se registra e inicia sesión; el sistema deniega datos de otra empresa incluso por API directa.
    [x] Dependencias del stack (SQLAlchemy async, asyncpg, Alembic, python-jose, argon2, redis, scipy, APScheduler, qrcode)  <done>
    [x] docker-compose con postgres:16 y redis:7; Dockerfile del backend  <done>
    [ ] Sesión async de SQLAlchemy y dependencia get_db que fija app.empresa_id desde el JWT  <pending>
    [ ] Modelos Empresa y Usuario + migración inicial Alembic (schema.sql + rls_policies.sql)  <pending>
    [ ] Registro e inicio de sesión: Argon2id, JWT 30 min + refresh token  <pending>
    [ ] RBAC: dependencia require_roles verificada en cada endpoint  <pending>
    [ ] Test automatizado de aislamiento entre tenants (RNF-01)  <pending>
    [ ] Frontend: login, cliente API con JWT, navegación básica por rol, base PWA  <pending>
    [ ] CI: pytest + lint + pip-audit/npm audit en cada push  <pending>

  F2 - Activos y registro de campo (semanas 3-6)  (0/8, 0%)
    cubre: RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RNF-03, RNF-05
    hecho cuando: Un operario escanea el QR y registra horómetro o alerta; el reporte llega aunque se hiciera offline.
    [ ] CRUD de activos con ficha técnica, ubicación y criticidad; baja lógica  <pending>
    [ ] Generación de QR único + código corto de respaldo al crear el activo  <pending>
    [ ] Catálogo de componentes editable por el administrador  <pending>
    [ ] Lecturas de horómetro  <pending>
    [ ] Alertas de campo (síntoma + nota) con estados  <pending>
    [ ] Frontend: escáner QR (html5-qrcode) y vista móvil del activo con acciones por rol  <pending>
    [ ] Frontend: formularios de horómetro y alerta (react-hook-form + zod), máx. 3 pasos  <pending>
    [ ] Frontend: PWA offline con cola local y sincronización automática  <pending>

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

AVANCE GLOBAL: 7/40 tareas (17%)
```

### Módulos del backend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `app.api.v1.router` | api | 1 | 1 | 5 | — |
| `app.api.v1.routes.health` | api | 2 | 1 | 9 | ✅ |
| `app.core.config` | core | 0 | 2 | 14 | — |
| `app.main` | main | 2 | 0 | 18 | — |
| `app.schemas.health` | schemas | 0 | 1 | 6 | ✅ |

### Módulos del frontend

| Módulo | Capa | Importa | Importado por | LOC | Test |
|---|---|---:|---:|---:|:---:|
| `src/app/globals.css` | app | 0 | 1 | 22 | — |
| `src/app/layout.tsx` | app | 1 | 0 | 25 | — |
| `src/app/page.tsx` | app | 0 | 0 | 68 | — |

Diagramas: [backend](docs/diagramas/dependencias-backend.md) · [frontend](docs/diagramas/dependencias-frontend.md)
<!-- graph:auto:end -->
