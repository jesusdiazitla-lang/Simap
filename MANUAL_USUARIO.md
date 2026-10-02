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
   - [3.1 Cómo se consiguen las cuentas](#31-cómo-se-consiguen-las-cuentas)
   - [3.2 Si el aparato lo usa más gente](#32-si-el-aparato-lo-usa-más-gente)
   - [3.3 Si tu empresa aparece como suspendida](#33-si-tu-empresa-aparece-como-suspendida)
   - [3.4 Qué pasa si te equivocas al entrar](#34-qué-pasa-si-te-equivocas-al-entrar)
   - [3.5 Cómo se ve SIMAP](#35-cómo-se-ve-simap)
4. [Roles y qué puede hacer cada uno](#4-roles-y-qué-puede-hacer-cada-uno)
5. [Funcionalidades](#5-funcionalidades)
   - [5.0 Entrar a SIMAP y ver el panel de tu turno](#50--entrar-a-simap-y-ver-el-panel-de-tu-turno)
   - [5.0.1 Cambiar tu contraseña](#501--cambiar-tu-contraseña)
   - [5.10 La consola del operador de SIMAP](#510--la-consola-del-operador-de-simap)
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

En la práctica esto significa que la separación no depende de que la aplicación "se acuerde" de
filtrar: es la propia base de datos la que, en cada consulta, solo deja ver las filas de la empresa
a la que pertenece quien ha iniciado sesión. La empresa se toma de la sesión firmada al entrar,
nunca de algo que el navegador pueda modificar. Si por un error de programación una consulta
olvidara indicar la empresa, no devolvería datos de más: no devolvería ninguno.

Las contraseñas se guardan cifradas con Argon2id y no pueden recuperarse, ni siquiera por un
administrador: solo restablecerse. La sesión viaja en una cookie que el código JavaScript de la
página no puede leer, para que un script malicioso no pueda robarla.

## 2. Requisitos

- Navegador moderno actualizado (Chrome, Edge, Firefox o Safari), en móvil o escritorio.
- Para escanear códigos QR: un teléfono con cámara y permiso de cámara para el navegador.
- Conexión a la red donde esté publicada la aplicación. En planta puede trabajarse sin señal:
  los reportes se guardan en el dispositivo y se envían al recuperar la conexión.

## 3. Acceso a la aplicación

1. Abre el navegador y entra en la dirección facilitada por el administrador
   (en desarrollo: `http://localhost:3000`).
2. Verás la **hoja de registro de acceso**. Escribe tu **correo** y tu **contraseña** y pulsa
   **Entrar**. La sesión dura 30 minutos de inactividad y se renueva sola mientras uses la
   aplicación, así que no te va a echar en mitad de un reporte.
3. Opcional: en el menú del navegador elige **"Añadir a pantalla de inicio"** para abrir SIMAP como
   una app, con su propio icono.

### 3.1 Cómo se consiguen las cuentas

**No hay botón de «crear cuenta».** SIMAP se contrata por equipo monitoreado, así que:

- La **cuenta de tu empresa** la crea quien opera SIMAP cuando se firma el servicio, desde su
  consola, junto con el primer usuario administrador. El sistema genera una contraseña temporal
  que te entregan a ti y que conviene cambiar en cuanto entres.
- **Tu usuario** lo da de alta el administrador de tu planta, que es también quien te asigna el rol.

Si no puedes entrar o no recuerdas tu contraseña, esa es la persona a la que dirigirte. La pantalla
de acceso lo recuerda al pie.

### 3.2 Si el aparato lo usa más gente

El botón **Cerrar sesión** está siempre visible en el panel, separado del resto de acciones. Si el
teléfono o la tableta pasa entre turnos o entre compañeros, ciérrala antes de dejarlo: **todo lo que
se registre queda firmado con el nombre de quien tenga la sesión abierta**, y ese nombre es el que
aparecerá después en el historial del equipo.

### 3.3 Si tu empresa aparece como suspendida

Al intentar entrar verás un mensaje que lo dice con esas palabras. **No es tu contraseña**: la
cuenta de tu empresa está desactivada, normalmente por una cuestión administrativa, y hay que
hablar con quien contrató SIMAP.

Tus datos siguen intactos. Suspender no borra nada: es solo que nadie de tu empresa puede entrar
hasta que se reactive, y entonces todo vuelve a estar donde estaba.

### 3.4 Qué pasa si te equivocas al entrar

- SIMAP **nunca dice cuál de los dos campos falló**. Si dijera «ese correo no existe», cualquiera
  podría averiguar quién trabaja en la empresa probando correos. El mensaje es siempre
  «Correo o contraseña incorrectos».
- Tras **cinco intentos fallidos seguidos** hay que esperar un minuto. Es lo que impide que alguien
  pruebe contraseñas una tras otra.

### 3.5 Cómo se ve SIMAP

La pantalla es deliberadamente sobria: gris neutro, cajas con borde, un solo color de acción. Está
pensada para parecerse a las herramientas de mantenimiento que ya se usan en la industria, no para
llamar la atención. Una herramienta de trabajo tiene que desaparecer detrás de la tarea.

Tres cosas que sí notarás:

- Los **botones y los campos son grandes**, para poder usarlos con guantes y con una sola mano.
- Funciona igual de bien con la **pantalla clara que con la oscura**, y cambia sola según la
  configuración de tu teléfono, porque la luz de una planta no es la misma en la sala de máquinas
  que en el patio.
- El **azul** marca siempre lo que se puede pulsar, y solo eso. El verde, el ámbar y el rojo quedan
  reservados para decir cómo está una máquina. Además, ningún estado se comunica solo con el color:
  siempre lleva texto, para quien no distinga bien los tonos.

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

### 5.0 ✅ Entrar a SIMAP y ver el panel de tu turno

- **Objetivo:** identificarte para que todo lo que registres quede asociado a tu nombre, y llegar a
  lo que tu rol puede hacer.
- **Quién:** todos los roles.
- **Cómo llegar:** la dirección de SIMAP en el navegador.
- **Pasos:** escribe tu correo → escribe tu contraseña (puedes pulsar **Ver** para comprobar que la
  escribiste bien) → **Entrar**.
- **Resultado:** el panel de tu turno, con tu nombre firmado arriba y la lista de lo que puedes
  hacer. Lo que todavía no está construido aparece en gris con la fase en la que llegará, para que
  sepas qué esperar y no busques algo que aún no existe.
- **Errores habituales:**
  - *«Correo o contraseña incorrectos»* → revisa ambos; SIMAP no dice cuál falló, a propósito
    (ver 3.3).
  - *«Demasiados intentos»* → espera el tiempo que indique el mensaje.
  - *«No se pudo conectar con el servidor de SIMAP»* → no es tu contraseña: el servidor no responde.
    Avisa a quien administra el sistema.

### 5.0.1 ✅ Cambiar tu contraseña

- **Objetivo:** sustituir tu contraseña por otra que solo conozcas tú.
- **Quién:** todos los roles. Imprescindible para el **administrador** de cada planta la primera
  vez: entra con una contraseña temporal que vio quien se la entregó.
- **Cómo llegar:** en el panel, abajo, **Tu cuenta → Cambiar contraseña**.
- **Pasos:** escribe tu contraseña actual → la nueva (al menos 12 caracteres) → repítela →
  **Cambiar contraseña**.
- **Resultado:** desde ese momento se entra con la nueva. En este aparato **sigues dentro**; en
  cualquier otro donde tuvieras la sesión abierta, se cierra y habrá que volver a entrar.
- **Por qué te pide la actual:** para que nadie pueda cambiarla aprovechando una sesión que dejaste
  abierta en un aparato compartido.
- **Errores habituales:**
  - *«La contraseña actual no es correcta»* → aparece junto a ese campo. Tras cinco fallos seguidos
    hay que esperar un minuto, igual que al entrar.
  - *«No coincide con la contraseña nueva»* → las dos copias de la nueva son distintas; vuelve a
    escribirlas.
  - *«Tiene que ser distinta de la actual»* → cambiarla por la misma no te protege de nada.

### 5.9 ⏳ Administrar usuarios y catálogo de componentes
- **Quién:** Administrador.
- **Cómo llegar:** menú **Administración**.
- **Qué puedes hacer:** crear usuarios con su rol; mantener el catálogo de componentes (tren motriz, sistema
  hidráulico, bomba de aceite…) que se usa al reportar fallas.

### 5.10 ✅ La consola del operador de SIMAP

> Esta sección **no es para el personal de una planta**. Es para quien presta el servicio SIMAP y
> da de alta a las empresas clientes.

- **Objetivo:** dar de alta empresas clientes y mantener su cuenta.
- **Quién:** el operador de SIMAP. No es ninguno de los cinco roles de la sección 4: es una cuenta
  de otro tipo, con su propia pantalla de acceso.
- **Cómo llegar:** `/operador` en el navegador.

**Qué puedes hacer**

| Acción | Para qué |
|---|---|
| Dar de alta una empresa | Crea la empresa y su primer administrador. Devuelve una contraseña temporal |
| Suspender / reactivar | Para una empresa que dejó de pagar. No borra nada |
| Restablecer contraseña | Cuando el administrador de una planta se queda fuera. Cierra las sesiones que tuviera abiertas |
| Renombrar | Corregir el nombre de un alta |
| Bitácora | Ver todo lo anterior, con quién lo hizo y cuándo |
| Cambiar mi contraseña | La tuya, desde **Tu cuenta**, al final de la consola. Queda en la bitácora |

**Tu acceso tiene límite de intentos**, igual que el de las plantas: tras cinco fallos seguidos hay
que esperar un minuto. Y tu sesión **no se renueva sola**: a los 30 minutos hay que volver a entrar.
Es la cuenta con más poder del sistema, y una sesión corta reduce lo que vale una olvidada abierta.

**Sobre la contraseña temporal.** La genera SIMAP, no tú, y **se muestra una sola vez**. Cópiala y
entrégasela a la persona. No queda guardada en ningún sitio, así que si cierras el aviso sin
copiarla tendrás que generar otra. Que no puedas elegirla es intencional: si pudieras, tendrías
acceso permanente a la cuenta de tu cliente.

**Qué NO puedes hacer, y por qué importa.** Desde la consola no se ven los equipos, las órdenes de
trabajo, las lecturas ni las alertas de ningún cliente. Solo el nombre de la empresa, quién es su
administrador, cuántos equipos tiene monitoreados —que es lo que se factura— y si está activa.

No es que la pantalla decida no mostrarlo: es que **la base de datos no se lo permite** al programa
que atiende esa consola. La diferencia importa. Si alguien te robara la contraseña de operador, no
obtendría los datos de ninguna planta, porque la restricción no está en el código que se podría
esquivar sino en los permisos del motor de base de datos.

**Errores habituales:**
- *«Ese correo ya pertenece a un usuario de otra empresa»* → cada correo es único en todo SIMAP.
  Usa otro, o averigua en qué empresa está dado de alta.
- *«Esa empresa no tiene ningún administrador activo»* → al restablecer la clave de una empresa
  cuyo administrador fue desactivado. Hay que crearle uno antes.

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
*(Desde la fase 2)* El reporte se guardará en el teléfono y se enviará solo al recuperar la conexión.
Hoy, sin señal, SIMAP muestra su propio aviso «Sin conexión» con un botón para volver a intentarlo;
todavía no guarda nada en el teléfono.

**¿Cómo cambio mi contraseña?**
En el panel, **Tu cuenta → Cambiar contraseña** (sección 5.0.1). Si no recuerdas la actual, pide al
administrador de tu planta que te la restablezca; si el administrador eres tú, pídeselo a quien
opera SIMAP.

**¿Puedo ver los equipos de otra empresa?**
No. Cada empresa solo ve sus datos; la restricción está en la base de datos.

**¿Dónde veo la versión de la aplicación?**
En `http://<servidor>:8000/api/v1/health` aparece `"version"`.

## 8. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La página no carga | El servidor no está en marcha | Avisar al administrador; en desarrollo, arrancar backend y frontend (ver README técnico) |
| Error de red al usar la aplicación | La API no responde | Comprobar `/api/v1/health` |
| Aparece «Sin conexión» | El aparato no tiene red | Recuperar cobertura y pulsar **Volver a intentar** |
| Me pide entrar otra vez en un aparato donde tenía la sesión abierta | Cambiaste la contraseña desde otro aparato, o te la restablecieron | Entra con la contraseña nueva |
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
| 2026-09-25 | 0.2.0 | Fase 1 en marcha: construido el aislamiento de datos entre empresas y el manejo seguro de contraseñas y sesiones. Sin cambios visibles todavía; se amplía la sección 1.3. |
| 2026-09-25 | 0.2.1 | Aislamiento entre empresas **verificado** contra una base de datos real: 7 pruebas automáticas comprueban que ninguna empresa puede ver los datos de otra, ni siquiera saltándose la aplicación. |
| 2026-09-25 | 0.2.2 | Creadas las tablas de **empresas** y **usuarios** con su protección activada, mediante migraciones versionadas. Todavía sin pantalla de login. |
| 2026-09-25 | 0.3.1 | Verificación automática en cada cambio del código: las pruebas de privacidad entre empresas se ejecutan contra una base de datos real antes de aceptar cualquier modificación. |
| 2026-09-25 | 0.3.0 | **Registro e inicio de sesión funcionando**: alta de empresa con su administrador, entrada con correo y contraseña, cierre de sesión y permisos por rol. Incluye bloqueo temporal tras varios intentos fallidos. Aún sin pantalla: solo accesible por API. |
| 2026-09-26 | 0.4.0 | **Pantalla de acceso y panel por rol disponibles.** Ya se entra a SIMAP desde el navegador. La interfaz adopta el aspecto de una bitácora de mantenimiento, funciona en claro y en oscuro, y se puede instalar en el teléfono. Nuevas secciones 3.1 a 3.4 y 5.0. |
| 2026-09-26 | 0.5.0 | **Consola del operador de SIMAP.** Quien presta el servicio ya puede dar de alta empresas clientes, suspenderlas y reactivarlas, restablecer la contraseña de un administrador y consultar la bitácora, todo desde `/operador`. La consola **no puede ver los datos de mantenimiento de ningún cliente**, y es la base de datos quien lo impide. Nueva sección 5.10. |
| 2026-09-26 | 0.5.0 | Nueva sección 3.3: qué significa que una empresa aparezca como suspendida. Reescrita la 3.5: la interfaz pasa a un aspecto sobrio de herramienta industrial, sin la apariencia de cuaderno de la versión anterior. |
| 2026-10-02 | 0.6.0 | **Cambiar tu contraseña**, en el panel y en la consola del operador (nueva sección 5.0.1). Al cambiarla, o cuando te la restablecen, se cierran tus sesiones en otros aparatos. El acceso a la consola del operador pasa a tener límite de intentos. |
| 2026-10-02 | 0.6.0 | Sin conexión, SIMAP muestra su propio aviso en lugar del error del navegador. Quien entra sin sesión va directo a la pantalla de acceso, sin pantallas intermedias. Corregida la sección 3.4, que describía un registro de intentos que ya no aparece en pantalla. |
| 2026-09-26 | 0.4.0 | **Las cuentas pasan a ser por invitación.** Se retira la posibilidad de que una empresa se registre sola: SIMAP se contrata por equipo, así que la cuenta la crea quien administra el servicio. Ver la sección 3.1. |
