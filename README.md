# SIMAP

Documentación **técnica** del proyecto. Para la guía de usuario final ver
[README_USER.md](README_USER.md) y [MANUAL_USUARIO.md](MANUAL_USUARIO.md).

> **Regla del equipo:** cada push a `main` debe dejar actualizados este README,
> `README_USER.md` y `MANUAL_USUARIO.md`. El hook `pre-push` y la GitHub Action
> `docs.yml` lo verifican (ver [Flujo de documentación](#flujo-de-documentación)).

## Stack

| Capa      | Tecnología                                  | Carpeta     |
|-----------|---------------------------------------------|-------------|
| Backend   | Python 3.11 · FastAPI · Pydantic v2 · Uvicorn | `backend/`  |
| Frontend  | Next.js 16 · React 19 · TypeScript · Tailwind 4 | `frontend/` |
| Tooling   | grimp · import-linter · dependency-cruiser · madge | `tools/graph/` |

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
│   │   ├── db/                # acceso a datos
│   │   └── models/            # entidades de dominio / ORM
│   ├── tests/                 # pytest + httpx TestClient
│   ├── pyproject.toml         # ruff, mypy, pytest, import-linter (capas)
│   └── requirements*.txt
├── frontend/
│   ├── src/app/               # App Router de Next.js
│   ├── .dependency-cruiser.cjs
│   └── package.json           # scripts graph:* / lint / build
├── tools/graph/graph.py       # CLI del grafo unificado (ver abajo)
├── docs/
│   ├── PLAN.yaml              # hitos y tareas; alimenta `graph.py status`
│   └── diagramas/             # Mermaid auto-generado
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

# 2) Backend
.\.venv\Scripts\Activate.ps1
cd backend; uvicorn app.main:app --reload      # http://localhost:8000/docs

# 3) Frontend (otra terminal)
cd frontend; npm run dev                      # http://localhost:3000
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

`<mod>` acepta ids completos (`app.services.foo`, `src/lib/api.ts`) o un
fragmento único (`services.foo`, `lib/api`).

### Reglas de arquitectura

**Backend** (`pyproject.toml` → `[tool.importlinter]`): capas de arriba hacia abajo
`main → api → services → db → models → schemas → core`. Una capa solo importa
de las inferiores.

**Frontend** (`.dependency-cruiser.cjs`): sin ciclos; `src/components` no importa
de `src/app`; se avisan huérfanos (salvo convenciones de Next.js).

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

Última actualización: 2026-09-17 12:02 UTC

### Estado del proyecto

```text
=== ESTADO DEL CÓDIGO ===

[backend]  módulos: 5   LOC: 56   TODO/FIXME: 0
  con test: 2/5   stubs/vacíos: 0
  por capa: api=2, core=1, main=1, schemas=1

[frontend]  módulos: 3   LOC: 115   TODO/FIXME: 0
  con test: 0/3   stubs/vacíos: 0
  por capa: app=3

ciclos de importación: 0

=== PLAN (docs/PLAN.yaml) ===

  M0 - Infraestructura del proyecto  (6/6, 100%)
    [x] Repositorio, .gitignore y estructura de carpetas  <done>
    [x] Backend FastAPI base con endpoint /health  <done (auto)>
    [x] Frontend Next.js base  <done (auto)>
    [x] Herramienta de grafo de dependencias (tools/graph)  <done>
    [x] Hook pre-push + GitHub Action de documentación  <done>
    [x] Documentación inicial (README, README_USER, MANUAL_USUARIO)  <done>

  M1 - Dominio SIMAP (pendiente de definir con los documentos de contexto)  (0/3, 0%)
    [ ] Definir entidades y modelos de datos  <pending>
    [ ] Definir endpoints de la API v1  <pending>
    [ ] Definir pantallas del frontend  <pending>

AVANCE GLOBAL: 6/9 tareas (66%)
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
