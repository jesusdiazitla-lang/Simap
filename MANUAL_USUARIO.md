# Manual de usuario de SIMAP

**Sistema Inteligente de Mantenimiento Predictivo**
**Versión del manual:** 0.2 · **Versión de la aplicación:** 0.1.0

> Documento vivo: se actualiza con cada publicación a la rama principal. Las secciones marcadas
> ⏳ describen funcionalidad definida en la especificación pero todavía no disponible; se completan
> con capturas y detalles a medida que cada fase se entrega.
> Guía rápida: [README_USER.md](README_USER.md). Documentación técnica: [README.md](README.md).

## Índice

1. [Introducción](#1-introducción)
2. [Requisitos](#2-requisitos)
3. [Acceso a la aplicación](#3-acceso-a-la-aplicación)
4. [Roles y qué puede hacer cada uno](#4-roles-y-qué-puede-hacer-cada-uno)
5. [Funcionalidades](#5-funcionalidades)
6. [Cómo calcula SIMAP el riesgo de un equipo](#6-cómo-calcula-simap-el-riesgo-de-un-equipo)
7. [Preguntas frecuentes](#7-preguntas-frecuentes)
8. [Solución de problemas](#8-solución-de-problemas)
9. [Glosario](#9-glosario)
10. [Historial de cambios](#10-historial-de-cambios)

---

## 1. Introducción

### 1.1 Propósito de SIMAP
En una planta industrial el mantenimiento suele ser **preventivo por calendario** (se interviene aunque el
equipo esté bien) o **correctivo** (se interviene cuando ya se rompió). Ambos cuestan tiempo de producción.
SIMAP añade una tercera vía: **predictiva**, estimando el riesgo de falla de cada equipo a partir de sus
horas de operación entre fallas y de lo que el personal reporta, sin depender de los sensores del fabricante.

### 1.2 A quién va dirigido
A todo el personal de una empresa cliente: operarios, supervisores, técnicos de taller, gerentes y
administradores. Cada rol ve solo lo que necesita (sección 4).

### 1.3 Privacidad entre empresas
Cada empresa ve **únicamente sus propios datos**. El aislamiento se aplica en la base de datos, no solo en
pantalla, y el modelo de predicción de cada empresa se entrena solo con su propio historial.

## 2. Requisitos

- Navegador moderno actualizado (Chrome, Edge, Firefox o Safari), en móvil o escritorio.
- Para escanear códigos QR: un teléfono con cámara y permiso de cámara para el navegador.
- Conexión a la red donde esté publicada la aplicación. En planta puede trabajarse sin señal:
  los reportes se guardan en el dispositivo y se envían al recuperar la conexión.

## 3. Acceso a la aplicación

1. Abre el navegador y entra en la dirección facilitada por el administrador
   (en desarrollo: `http://localhost:3000`).
2. ⏳ Inicia sesión con tu **correo** y **contraseña**. La sesión dura 30 minutos de inactividad y se renueva
   sola mientras uses la aplicación.
3. Opcional: en el menú del navegador elige **"Añadir a pantalla de inicio"** para abrir SIMAP como una app.

## 4. Roles y qué puede hacer cada uno

| Rol | Puede hacer |
|---|---|
| **Operario** | Escanear el QR de un equipo, registrar lecturas de horómetro y reportar alertas. |
| **Supervisor** | Todo lo del operario, además de reportar fallas, revisar alertas y ver el historial de su planta. |
| **Técnico de taller** | Cambiar el estado de una orden de trabajo (en taller / reparada) y registrar el trabajo y repuestos. |
| **Gerente / Stakeholder** | Ver paneles e indicadores de su empresa, en modo de solo lectura. Autorizar cierres. |
| **Administrador** | Gestionar usuarios, equipos, catálogo de componentes, inventario y configuración de la empresa. |

## 5. Funcionalidades

Cada funcionalidad se documenta con el mismo esquema:
**Objetivo · Quién · Cómo llegar · Pasos · Resultado · Errores habituales.**

### 5.1 ⏳ Registrar un equipo (activo) y obtener su código QR
- **Objetivo:** dar de alta un equipo para que reciba lecturas, alertas y órdenes.
- **Quién:** Administrador.
- **Cómo llegar:** menú **Equipos → Nuevo equipo**.
- **Pasos:** 1) nombre o código interno; 2) tipo (bomba, motor, compresor…); 3) ubicación (planta/área/línea);
  4) criticidad (alta, media, baja); 5) **Guardar**.
- **Resultado:** SIMAP genera un **código QR único** y un **código corto de respaldo**. Imprime la etiqueta y
  pégala en el equipo. Si la etiqueta se daña, desde la ficha del equipo puedes **reimprimir** el QR.

### 5.2 ⏳ Registrar una lectura de horómetro
- **Objetivo:** que SIMAP conozca las horas acumuladas del equipo (es la señal principal de la predicción).
- **Quién:** Operario o Supervisor.
- **Cómo llegar:** escanea el QR del equipo → **Horómetro**.
- **Pasos:** 1) escribe el valor que marca el horómetro; 2) **Enviar**. Máximo tres toques desde el escaneo.
- **Resultado:** la lectura queda asociada al equipo y a ti, y SIMAP recalcula el riesgo del equipo.
- **Errores habituales:** un valor menor que la última lectura se rechaza (el horómetro no retrocede).

### 5.3 ⏳ Reportar una alerta (el equipo sigue funcionando)
- **Objetivo:** avisar de algo raro (ruido, vibración, calor, olor, fuga u otro) antes de que sea una falla.
- **Quién:** Operario o Supervisor.
- **Cómo llegar:** escanea el QR → **Reportar alerta**.
- **Pasos:** 1) elige el síntoma de la lista; 2) opcionalmente escribe una nota; 3) **Enviar**.
- **Resultado:** la alerta queda en estado **Pendiente** y la ve el supervisor de tu planta. Dos o más
  alertas en 15 días elevan el riesgo estimado del equipo.
- **Sin conexión:** verás "Guardado en el dispositivo"; se enviará sola cuando vuelva la señal.

### 5.4 ⏳ Reportar una falla (se genera una orden de trabajo)
- **Objetivo:** documentar una falla real y abrir la orden de trabajo.
- **Quién:** Supervisor.
- **Cómo llegar:** escanea el QR o busca el equipo → **Reportar falla**. Si partes de una alerta pendiente,
  el formulario viene pre-llenado y la alerta queda vinculada a la orden.
- **Pasos:** 1) horómetro actual; 2) temperatura (si aplica); 3) código de error del panel (si tiene);
  4) componente afectado (del catálogo); 5) descripción; 6) **Enviar**.
- **Resultado:** se crea una **orden de trabajo en estado "Reportada"**, el equipo queda marcado en falla y
  se actualizan su horómetro y fecha de última falla.

### 5.5 ⏳ Seguir y cerrar una orden de trabajo
- **Objetivo:** llevar la reparación de principio a fin con trazabilidad.
- **Quién:** Técnico de taller (reparación); Supervisor o Gerente (autorización de cierre).
- **Cómo llegar:** menú **Órdenes** → selecciona la orden.
- **Estados:** `Reportada → En taller → Reparada → Cerrada`.
- **Pasos:** 1) el técnico marca **En taller** al recibir el equipo; 2) repara y registra **qué hizo** y **qué
  repuestos usó**; 3) marca **Reparada** (SIMAP descuenta los repuestos del inventario); 4) un supervisor o
  gerente revisa y **Autoriza el cierre**.
- **Resultado:** la orden queda **Cerrada** con quién reportó, reparó y autorizó, y con el **tiempo fuera de
  servicio** calculado. Si el cierre se rechaza, la orden vuelve a "En taller" con una nota.

### 5.6 ⏳ Gestionar el inventario de repuestos
- **Objetivo:** saber qué repuestos hay y avisar antes de quedarse sin ellos.
- **Quién:** Administrador o Supervisor.
- **Cómo llegar:** menú **Inventario**.
- **Pasos:** registra un repuesto (nombre, código, stock inicial, stock mínimo) o ajusta el stock de uno existente.
- **Resultado:** cuando el stock cae por debajo del mínimo (por ejemplo al cerrar una orden), SIMAP genera una
  **alerta de reorden**.

### 5.7 ⏳ Consultar el riesgo de un equipo y las alertas automáticas
- **Objetivo:** saber qué equipos conviene revisar antes de que fallen.
- **Quién:** Supervisor, Gerente.
- **Cómo llegar:** ficha del equipo (desde el QR o el listado) o panel del supervisor.
- **Qué verás:** el **riesgo de falla** estimado para el próximo periodo y, si supera el umbral de tu empresa,
  una **alerta preventiva** generada por el sistema. Si el equipo aún tiene poco historial, el riesgo aparece
  marcado como **"estimado"** (se calcula con un modelo genérico).

### 5.8 ⏳ Paneles por rol
- **Operario:** tus reportes recientes.
- **Supervisor:** alertas pendientes de revisión y órdenes abiertas de tu planta.
- **Gerente:** disponibilidad, tiempo medio entre fallas (MTBF), costo de repuestos usados y equipos de mayor riesgo.

### 5.9 ⏳ Administrar usuarios y catálogo de componentes
- **Quién:** Administrador.
- **Cómo llegar:** menú **Administración**.
- **Qué puedes hacer:** crear usuarios con su rol; mantener el catálogo de componentes (tren motriz, sistema
  hidráulico, bomba de aceite…) que se usa al reportar fallas.

## 6. Cómo calcula SIMAP el riesgo de un equipo

Sin tecnicismos: para cada **componente** (por ejemplo, la bomba de aceite) SIMAP mira cuántas horas de
operación duró entre una falla y la siguiente en el historial de tu empresa. Con esas duraciones construye
una curva de **confiabilidad** que responde a la pregunta *"si lleva T horas sin fallar, ¿qué probabilidad
hay de que falle en las próximas X horas?"*.

Ejemplo: si una bomba suele fallar entre las 380 y 420 horas y hoy lleva 350, la probabilidad de que falle
en las próximas 50 horas ronda el **25 %**. Si ese valor supera el **umbral** que configuró tu empresa, SIMAP
genera una alerta preventiva.

Además, si el equipo acumula **dos o más alertas de campo en los últimos 15 días**, el riesgo estimado sube
un 30 %: lo que ve el personal cuenta.

El cálculo se repite con **cada lectura de horómetro** y una vez al día para todos los equipos, y la curva de
cada componente se reajusta a medida que se cierran más órdenes de trabajo: cuanto más se usa SIMAP, más
acertado es.

## 7. Preguntas frecuentes

**¿Necesito instalar algo en el teléfono?**
No. Se usa desde el navegador. Puedes añadirlo a la pantalla de inicio para abrirlo como una app.

**¿Qué pasa si reporto sin señal?**
El reporte se guarda en el teléfono y se envía automáticamente al recuperar la conexión.

**¿Puedo ver los equipos de otra empresa?**
No. Cada empresa solo ve sus datos; la restricción está en la base de datos.

**¿Dónde veo la versión de la aplicación?**
En `http://<servidor>:8000/api/v1/health` aparece `"version"`.

## 8. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La página no carga | El servidor no está en marcha | Avisar al administrador; en desarrollo, arrancar backend y frontend (ver README técnico) |
| Error de red al usar la aplicación | La API no responde | Comprobar `/api/v1/health` |
| El escáner no abre la cámara | Permiso de cámara denegado | Permitir la cámara para el sitio en los ajustes del navegador; o escribe el **código corto** de la etiqueta |
| "Guardado en el dispositivo" no cambia a "Enviado" | Sigue sin conexión | Al recuperar señal se envía solo; no borres los datos del navegador mientras tanto |
| No puedo marcar una orden como "Reparada" | Tu rol no lo permite | Solo el técnico de taller puede; el cierre lo autoriza supervisor o gerente |

## 9. Glosario

| Término | Significado |
|---|---|
| Activo | Un equipo industrial registrado en SIMAP (bomba, motor, compresor…). |
| Horómetro | Contador de horas de operación del equipo. |
| Alerta | Aviso de un síntoma observado; el equipo sigue funcionando. |
| Falla / Orden de trabajo | El equipo dejó de operar correctamente; se abre una orden para repararlo. |
| Componente | Parte del equipo que falla (catálogo: tren motriz, sistema hidráulico…). |
| Criticidad | Importancia del equipo para la producción: alta, media o baja. |
| Riesgo de falla | Probabilidad estimada de que el equipo falle en el próximo periodo. |
| Umbral | Valor de riesgo a partir del cual SIMAP genera una alerta preventiva. |
| MTBF | Tiempo medio entre fallas. |
| Disponibilidad | Porcentaje del tiempo en que el equipo estuvo operativo. |
| API | Servicio que la interfaz usa para leer y guardar datos. |

## 10. Historial de cambios

| Fecha | Versión | Cambios |
|---|---|---|
| 2026-09-17 | 0.1.0 | Creación del proyecto: estructura base, página inicial y API de salud. |
| 2026-09-17 | 0.1.0 | Manual reescrito a partir de la Especificación Funcional y los Casos de Uso: roles, 9 funcionalidades previstas, explicación del riesgo, FAQ y glosario. |
