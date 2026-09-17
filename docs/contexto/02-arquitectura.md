# Arquitectura Técnica y Guía de Inicio — SIMAP

> Transcripción de `Arquitectura_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado).
> Fuente de verdad del **cómo** se construye. El DDL y las políticas RLS están copiados tal cual en
> `backend/db/schema.sql` y `backend/db/rls_policies.sql`.

## 2. Stack tecnológico

### 2.1 Backend (Python 3.12)

| Componente | Uso |
|---|---|
| FastAPI | API REST + OpenAPI automático |
| Pydantic v2 | Validación y serialización |
| SQLAlchemy 2.0 (async) + asyncpg | ORM y driver asíncrono de PostgreSQL |
| Alembic | Migraciones del esquema |
| python-jose | Emisión y verificación de JWT |
| argon2-cffi | Hash de contraseñas Argon2id |
| qrcode[pil] | Generación del QR de cada activo |
| scipy | Ajuste de Weibull por componente |
| APScheduler | Tarea diaria que recalcula el riesgo |
| redis-py | Caché y sesiones |
| pytest + httpx | Pruebas unitarias y de integración |

### 2.2 Frontend (Node 20 / TypeScript)

| Componente | Uso |
|---|---|
| Next.js (App Router) | Framework principal |
| React 18 | Interfaz |
| Tailwind CSS | Estilos |
| next-pwa | PWA instalable con soporte offline |
| TanStack Query | Datos del servidor, caché y sincronización |
| react-hook-form + zod | Formularios y validación |
| html5-qrcode | Lectura de QR con la cámara |
| Playwright | Pruebas end-to-end |

### 2.3 Infraestructura

| Componente | Uso |
|---|---|
| Docker / Docker Compose | Empaquetado del backend y entorno local |
| GitHub Actions | CI/CD |
| Railway | Hosting del backend y de la tarea programada |
| Vercel | Hosting del frontend (CDN, PWA nativa) |
| Supabase | PostgreSQL administrado |
| Upstash | Redis administrado |

> **Desviaciones del scaffold actual respecto al documento** (decididas al montar el repo; revisar si importa):
> Python **3.11.9** instalado localmente (doc: 3.12) · React **19** y Next **16** (doc: React 18; Next 16 exige
> React 19) · Node **22** (doc: 20). Ninguna afecta la funcionalidad descrita.

## 3. Motor de base de datos

PostgreSQL, sin extensión de series de tiempo: el sistema se alimenta de horómetro y reportes de campo, volumen
transaccional normal. Se eligió sobre NoSQL porque el dominio es fuertemente relacional y porque el modelo
multiempresa depende de **Row-Level Security**. Proveedor: **Supabase** (construido alrededor de RLS, respaldos
automáticos, panel SQL, capa gratuita suficiente).

## 4. Modelo de base de datos

Cada tabla que pertenece a una empresa lleva su propia columna `empresa_id`, **incluso las que ya la heredan**
(p. ej. `alertas` depende de `activos`): es intencional, así cada política RLS filtra directamente por
`empresa_id` sin resolver relaciones.

Tablas: `empresas`, `usuarios`, `componentes`, `activos`, `lecturas_horometro`, `alertas`, `ordenes_trabajo`,
`repuestos`, `orden_repuesto`. DDL completo: `backend/db/schema.sql`.

Índices recomendados: `activos(empresa_id)`, `ordenes_trabajo(activo_id)`, `ordenes_trabajo(estado)`,
`lecturas_horometro(activo_id, fecha)`.

## 5. Gestión de la seguridad

### 5.1 Aislamiento entre empresas (RLS)
Política `USING (empresa_id = current_setting('app.empresa_id')::UUID)` en las ocho tablas multiempresa
(`backend/db/rls_policies.sql`). La aplicación fija la variable en cada transacción **a partir del `empresa_id`
firmado en el JWT**, nunca desde un valor manipulable por el cliente:

```python
async def get_db(token: TokenData = Depends(verify_jwt)):
    async with async_session() as session:
        await session.execute(text("SET LOCAL app.empresa_id = :eid"), {"eid": str(token.empresa_id)})
        yield session
```

### 5.2 Autenticación y control de acceso
- Argon2id; nunca se almacena ni loguea la contraseña en claro.
- JWT de 30 min con refresh token; incluye `rol` y `empresa_id`.
- RBAC verificado en **cada endpoint**, no solo ocultando opciones en la UI.
- Transiciones de estado de orden restringidas por rol a nivel de servicio (solo técnico marca "reparada").

### 5.3 Datos en tránsito y en reposo
TLS en todo; cifrado en reposo por Supabase; secretos solo en variables de entorno (`.env.example` sin valores).

### 5.4 Validación, límites y auditoría
Pydantic (backend) y zod (frontend); rate limiting en login y API pública; auditoría de reportó/reparó/autorizó
sin edición retroactiva; `pip-audit` y `npm audit` en CI.

### 5.5 Checklist antes de cada entrega
- Prueba automatizada: un usuario de una empresa nunca lee ni modifica filas de otra, incluso por API directa.
- Revisar OWASP Top 10 sobre formularios y endpoints nuevos.
- Verificar que ningún secreto quedó en el repo ni en logs.

## 6. Empaquetado

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml` (desarrollo): servicios `db` (postgres:16, simap/simap_dev, puerto 5432, volumen
`pgdata`), `redis` (redis:7, 6379) y `api` (build ./backend, env_file ./backend/.env, 8000).

`.env.example`:
```
DATABASE_URL=postgresql+asyncpg://simap:simap_dev@localhost:5432/simap
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change_me_in_production
JWT_EXPIRE_MINUTES=30
RISK_THRESHOLD=0.25
```

## 7. Despliegue

| Componente | Dónde y cómo |
|---|---|
| Base de datos | Supabase: crear proyecto, correr `schema.sql` y `rls_policies.sql`, copiar cadena de conexión. |
| Backend | Railway desde el Dockerfile; variables en su panel; despliegue automático en cada push a `main`. |
| Tarea programada | Segundo proceso (worker) en Railway con APScheduler, una vez al día. |
| Frontend | Vercel conectado al repo; despliega en cada push. |
| Caché / colas | Upstash Redis. |
| CI/CD | GitHub Actions: pytest y Playwright en cada push; solo si pasan despliegan Railway y Vercel. |

## 8. Guía de inicio rápido

1. `git clone <url> && cd simap`
2. `docker compose up -d db redis`
3. Backend: venv, `pip install -r requirements.txt`, copiar `.env.example` a `.env`
4. `alembic upgrade head`
5. `uvicorn app.main:app --reload`
6. Frontend: `npm install`, copiar `.env.local.example` a `.env.local`, `npm run dev`
7. `python scripts/seed.py` (primera empresa + administrador)
8. Verificar aislamiento con dos usuarios de empresas distintas.
