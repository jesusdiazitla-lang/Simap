# Especificación Funcional y Técnica — SIMAP

> Transcripción de `Especificacion_Funcional_SIMAP.pdf` (ITLA, TDS — Proyecto Final de Grado).
> Fuente de verdad del **qué** hace el sistema. Ver también `02-arquitectura.md` y `03-requerimientos-casos-de-uso.md`.

**SIMAP — Sistema Inteligente de Mantenimiento Predictivo.**

## 1. Problema que resuelve

En las empresas industriales el mantenimiento preventivo actúa por calendario sin considerar el estado real del
equipo, y el correctivo solo actúa una vez ocurrida la falla; ambos generan pérdida de tiempo operativo. Además,
la mayoría de las empresas no tiene acceso a los sensores internos de sus equipos (los fabricantes lo restringen).
SIMAP basa la predicción en dos fuentes que **sí** están al alcance de cualquier empresa: las **horas de
operación (horómetro)** y los **reportes del personal de planta**.

## 2. Qué hará la aplicación

- Registrar los equipos (activos) de una empresa y llevar su historial de fallas.
- Capturar, desde el personal de planta, alertas tempranas y reportes formales de falla mediante un **código QR por equipo**.
- Calcular y actualizar el **riesgo de falla** de cada activo con base en sus horas de operación entre fallas.
- Generar y dar seguimiento a **órdenes de trabajo**, desde el reporte hasta el cierre y la autorización de salida de taller.
- Controlar el **inventario de repuestos** asociado a cada reparación, con alertas de reorden.
- Mostrar **paneles de control** diferenciados según el rol.
- Aislar completamente los datos de cada empresa cliente (**multi-tenant**).

## 3. Módulos del sistema

| Módulo | Descripción |
|---|---|
| 3.1 Gestión de Activos | Ficha técnica, ubicación, criticidad. Al crear un activo se genera un QR único (`qrcode`) con código corto alfanumérico de respaldo. El QR enlaza a una vista móvil ligera con acciones sobre ese equipo. |
| 3.2 Reportes de Campo | PWA con soporte offline (guarda local y sincroniza). Dos tipos: **Alerta** (operario/supervisor: síntoma ruido/vibración/calor/olor/fuga/otro + nota; el equipo sigue funcionando) y **Reporte de falla** (supervisor: horómetro, temperatura, código de error, componente afectado, descripción, técnico). |
| 3.3 Órdenes de Trabajo | Estados: **Reportada → En taller → Reparada → Cerrada (autorizada)**. Cada cambio queda asociado a un responsable (reportó / reparó / autorizó). Al cerrar: calcula tiempo fuera de servicio y descuenta repuestos. |
| 3.4 Inventario de Repuestos | Catálogo por empresa con stock actual y mínimo; alerta automática de reorden; vinculado a órdenes vía detalle de repuestos usados. |
| 3.5 Motor de Predicción | Riesgo de falla por activo a partir de horas entre fallas, ajustado por alertas recientes (sección 5). |
| 3.6 Panel de Control y Roles | Operario: botones grandes y formulario mínimo. Supervisor: + historial y alertas pendientes. Gerente: indicadores (disponibilidad, MTBF, costos de repuestos). Administrador: usuarios, activos, catálogo de componentes. |

## 4. Roles y permisos

| Rol | Puede hacer |
|---|---|
| Operario | Reportar alertas y registrar lecturas de horómetro mediante el QR del equipo. |
| Supervisor | Lo anterior + reportar fallas, revisar alertas y ver el historial de su planta. |
| Técnico de Taller | Actualizar el estado de una orden de trabajo y registrar el trabajo realizado. |
| Gerente / Stakeholder | Ver paneles y reportes de su empresa, solo lectura. |
| Administrador | Gestionar usuarios, activos, catálogo de componentes y configuración de la empresa. |

Valores en BD: `operario`, `supervisor`, `tecnico_taller`, `gerente`, `administrador`.

## 5. Cómo aprende el sistema de las fallas

### 5.1 Por qué no sensores continuos
Los fabricantes restringen el acceso a los datos internos; instrumentar con sensores propios no es viable en
las primeras fases. Se usan horómetro y reportes del personal.

### 5.2 Señal principal: horas de operación entre fallas
Con cada lectura de horómetro o cierre de orden:
`horas_desde_ultima_falla = horometro_actual − horometro_en_la_ultima_falla_de_ese_componente`.
Se dispara con **cada lectura de ronda**, no solo al fallar: así se advierte antes de la falla.

### 5.3 Modelo estadístico: análisis de supervivencia (Weibull)
Por cada **componente** se ajusta una distribución de Weibull sobre el historial de horas hasta la falla de
las órdenes cerradas (`scipy.stats.weibull_min.fit`, no a mano).

- Confiabilidad: `R(t) = exp(−(t/η)^β)` — η vida característica, β>1 desgaste progresivo.
- Probabilidad condicional de falla en un intervalo Δt, habiendo operado T horas: `1 − R(T+Δt) / R(T)`.

Ejemplo: bomba de aceite falla entre 380–420 h → β≈3.5, η≈430. Con 350 h desde la última falla:
R(350)≈0.61, R(400)≈0.46 → ≈25 % de fallar en las próximas 50 h. Si supera el umbral de la empresa
(`RISK_THRESHOLD`), se genera una **alerta preventiva automática**.

### 5.4 Señal secundaria: alertas de campo
Multiplicador simple y explicable: p. ej. **2+ alertas en los últimos 15 días → riesgo × 1.30**.

### 5.5 Aislamiento del aprendizaje
Cada empresa ajusta su propio modelo solo con su historial; nunca se combinan datos entre tenants.

### 5.6 Actualización continua
Proceso programado diario (APScheduler) que recalcula el riesgo de todos los activos y reajusta β y η de cada
componente cuando hay suficientes órdenes nuevas.

## 6. Modelo de datos (conceptual)

```
EMPRESA ──< USUARIO
EMPRESA ──< ACTIVO ──< LECTURA_HOROMETRO
                  ──< ALERTA
                  ──< ORDEN_TRABAJO >── COMPONENTE (catálogo)
                                    ──< ORDEN_REPUESTO >── REPUESTO
```

Diccionario de datos completo: ver el DDL en `backend/db/schema.sql` (transcrito de `02-arquitectura.md`).

## 7. Arquitectura y tecnología (resumen)

- Backend: Python + FastAPI (un solo lenguaje para negocio y predicción).
- Frontend: Next.js + React como PWA.
- BD: PostgreSQL, sin TimescaleDB (eventos discretos, no series de sensor).
- Procesamiento: tarea programada diaria, sin colas en tiempo real.
- Autenticación: JWT con RBAC por rol y aislamiento estricto entre empresas.

Capas (Figura 2): Portal web (Next.js) → Capa de seguridad (TLS, WAF, rate limiting) → API REST (JWT + RBAC
multi-tenant) → módulos {Gestión de activos, Reportes y predicción, Órdenes de trabajo, Inventario} →
PostgreSQL (RLS) + Redis (caché, sesiones).

## 8. Seguridad (resumen)
RLS en PostgreSQL por empresa; Argon2id; JWT corto con refresh; TLS y cifrado en reposo; auditoría de quién
reportó/reparó/autorizó; copias de seguridad con recuperación a un punto en el tiempo.

## 9. Despliegue (resumen)
Backend en Railway (Docker + tarea programada); PostgreSQL administrado (Supabase); frontend en Vercel; CI/CD
con GitHub Actions.

## 10. Trabajo futuro
Sensores propios de vibración/temperatura; app nativa si la PWA se queda corta; modelos ML más sofisticados
(Random Forest / XGBoost) con más historial; catálogo de códigos de error por marca y modelo.
