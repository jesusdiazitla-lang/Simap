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
| 3.3 Órdenes de Trabajo | Estados: **Reportada → En taller → Reparada → Cerrada (autorizada)**, y **Cancelada** con motivo desde cualquier estado abierto. Cada cambio queda asociado a un responsable (reportó / reparó / autorizó). Al cerrar: calcula tiempo fuera de servicio y descuenta repuestos. *[Actualizado en F3, decisión 1 de `06-fase3-ordenes-de-trabajo.md` §4, confirmada el 2026-10-14.]* |
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
Por cada **componente** se ajusta una distribución de Weibull con el historial de órdenes cerradas de la empresa.

*[Actualizado en F4, decisión 11 de `07-fase4-prediccion-e-inventario.md` §4, confirmada el 2026-10-18.]* El ajuste no
es `scipy.stats.weibull_min.fit` sobre los intervalos entre fallas, porque ese método no ve las piezas que siguen
funcionando (censura) y en las simulaciones se equivoca de 4 a 7 veces más. Es un **máximo a posteriori** de Weibull con
reparación mínima, sobre las **vidas** de cada pieza (fallas, edades y horas observadas, incluida la pieza instalada
hoy), con un conocimiento previo centrado en la **vida nominal** del componente (`07-fase4…` §5). scipy se usa para
verificarlo.

- Confiabilidad: `R(t) = exp(−(t/η)^β)` — η vida característica, β>1 desgaste progresivo.
- Probabilidad condicional de falla en un intervalo Δt, habiendo operado T horas: `1 − R(T+Δt) / R(T)`.

Ejemplo **ilustrativo** (β y η no salen de ajustar esas fallas, que darían β≈30): bomba de aceite falla entre
380–420 h → β≈3.5, η≈430. Con 350 h de **edad de la pieza**:
R(350)≈0.61, R(400)≈0.46 → ≈25 % de fallar en las próximas 50 h. Si supera el umbral de la empresa
(`configuracion_empresa.umbral_riesgo`, 25 % por defecto), se genera una **alerta preventiva automática**. *[Actualizado
en F4, decisión 5.]*

### 5.4 Señal secundaria: alertas de campo
Multiplicador simple y explicable: p. ej. **2+ alertas en los últimos 15 días → riesgo × 1.30**. *[Actualizado en F4,
`07-fase4…` §5.4.]* El 1,30 multiplica la intensidad de falla, no la probabilidad, para que el resultado nunca pase de
1: con el ejemplo de 5.3 el riesgo pasa de 25,2 % a 31,4 %.

### 5.5 Aislamiento del aprendizaje
Cada empresa ajusta su propio modelo solo con su historial; nunca se combinan datos entre tenants.

### 5.6 Actualización continua
Proceso programado diario (APScheduler) que recalcula el riesgo de todos los activos y reajusta β y η de cada
componente cuando hay suficientes órdenes nuevas. *[Actualizado en F4, decisión 13.]* Además, cada cierre de orden deja
una marca durable y el modelo de ese componente se reajusta en segundo plano al momento; el job de la madrugada recoge
lo que quede pendiente.

### 5.7 Indicadores del gerente *[Actualizado en F5, `08-fase5-dashboard-y-cierre.md` §22.]*
Definiciones fijadas antes que las consultas (`08-fase5…` §5), para leerlas como hechos:

- **Parada:** una falla para al equipo desde su fecha de falla; una intervención predictiva, desde que
  entra al taller (no desde que se crea la orden). Las canceladas no cuentan. Dos órdenes solapadas son
  una sola parada, y el solape entre una falla y una planificada se atribuye a la falla.
- **Disponibilidad** = 1 − horas de parada ÷ horas de calendario de 24 h, desde que se observa cada
  equipo (`activos.creado_en`) hasta su baja o ahora; nunca horas futuras. Se muestra también sin las
  paradas planificadas y junto a la **utilización** (horas operadas ÷ horas de calendario).
- **MTBF** = horas operadas (horómetro) ÷ fallas no planificadas, siempre con su intervalo de confianza
  del 90 %; sin fallas, una cota inferior. **MTTR** = duración media, de la falla a la salida del
  taller, de las fallas cerradas del periodo.
- **Costo de repuestos:** del libro de movimientos, al precio del momento del consumo, separado entre
  fallas y trabajo planificado.
- Meses cortados en America/Santo_Domingo; las razones se arman sobre los totales del periodo, nunca
  como promedio de razones mensuales.

## 6. Modelo de datos (conceptual)

```
EMPRESA ──< USUARIO
EMPRESA ──< ACTIVO ──< LECTURA_HOROMETRO
                  ──< ALERTA
                  ──< ORDEN_TRABAJO >── COMPONENTE (catálogo)
                                    ──< ORDEN_REPUESTO >── REPUESTO
```

Diccionario de datos completo: ver el DDL en `backend/db/schema.sql` (transcrito de `02-arquitectura.md`).

*[Actualizado en F5, `08-fase5-dashboard-y-cierre.md` §22.]* Añadidos de la fase 5: `activos.creado_en` (desde cuándo se observa el equipo; el administrador
puede adelantarla), `lecturas_horometro.horas_acumuladas` (horas del equipo en esa lectura, mantenida por
un trigger y nula si la lectura es dudosa) y la vista `v_paradas` (una fila por parada, con su inicio,
su fin y si fue planificada). Una orden predictiva cuenta su tiempo fuera de servicio desde que entra al
taller.

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
