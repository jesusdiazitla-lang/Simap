# SIMAP — Guía rápida para usuarios

> Esta guía es para quien **usa** SIMAP en la planta o en la oficina, no para quien lo programa.
> La documentación técnica está en [README.md](README.md) y el manual completo en
> [MANUAL_USUARIO.md](MANUAL_USUARIO.md).

## ¿Qué es SIMAP?

**SIMAP (Sistema Inteligente de Mantenimiento Predictivo)** ayuda a una empresa industrial a
anticiparse a las fallas de sus equipos sin necesitar sensores del fabricante. Se alimenta de dos cosas
que el personal de planta ya conoce:

- las **horas de operación** de cada equipo (el horómetro), y
- lo que el personal **observa** en el día a día (ruidos, vibración, calor, olores, fugas).

Con eso, SIMAP calcula el **riesgo de falla** de cada equipo, avisa cuando conviene intervenir antes de
que se rompa, y lleva el ciclo completo de cada reparación: desde el reporte hasta que el taller autoriza
que el equipo vuelva a producción, incluyendo los repuestos usados.

## ¿Quién usa SIMAP y para qué?

| Si tú eres… | SIMAP te sirve para… |
|---|---|
| **Operario** | Escanear el QR del equipo, anotar el horómetro y reportar una alerta en tres toques. |
| **Supervisor** | Reportar fallas, revisar las alertas de tu planta y seguir las órdenes de trabajo. |
| **Técnico de taller** | Registrar qué reparaste y qué repuestos usaste; marcar la orden como reparada. |
| **Gerente** | Ver indicadores: disponibilidad, tiempo medio entre fallas, costo de repuestos, equipos en riesgo. |
| **Administrador** | Dar de alta usuarios, equipos (con su QR imprimible), el catálogo de componentes y el inventario. |

## Cómo acceder

| Entorno | Dirección |
|---|---|
| Desarrollo | http://localhost:3000 |
| Producción | _(pendiente: URL de Vercel)_ |

SIMAP es una **aplicación web progresiva**: se abre en el navegador del teléfono sin instalar nada, y se
puede "añadir a la pantalla de inicio". Si en la planta no hay señal, los reportes se guardan en el
teléfono y se envían solos cuando vuelve la conexión.

## Primeros pasos (cuando esté disponible)

1. Abre la dirección en el navegador e inicia sesión con tu correo y contraseña.
2. Verás el panel de tu rol.
3. En planta: escanea el **código QR** pegado en el equipo → elige **Horómetro** o **Alerta** → envía.

## Estado actual de la aplicación

| Funcionalidad | Fase | Estado |
|---|---|---|
| Inicio de sesión y roles | 1 | ⏳ En construcción |
| Equipos con código QR, horómetro y alertas | 2 | ⏳ Pendiente |
| Órdenes de trabajo con trazabilidad | 3 | ⏳ Pendiente |
| Predicción de riesgo e inventario de repuestos | 4 | ⏳ Pendiente |
| Paneles por rol | 5 | ⏳ Pendiente |
| API en funcionamiento (`/api/v1/health`) | — | ✅ Disponible |

## ¿Problemas?

- Si la página no carga, comprueba que el servidor esté encendido (ver
  "Puesta en marcha" en el [README técnico](README.md#puesta-en-marcha)).
- Para incidencias, abre un *issue* en el repositorio indicando qué hacías,
  qué esperabas y qué ocurrió.

---
_Este documento se revisa en cada publicación a la rama principal._
