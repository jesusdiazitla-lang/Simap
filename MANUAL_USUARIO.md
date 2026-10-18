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
   - [3.5 Moverte por SIMAP: el menú](#35-moverte-por-simap-el-menú)
   - [3.6 Cómo se ve SIMAP](#36-cómo-se-ve-simap)
4. [Roles y qué puede hacer cada uno](#4-roles-y-qué-puede-hacer-cada-uno)
5. [Funcionalidades](#5-funcionalidades)
   - [5.0 Entrar a SIMAP y ver el panel de tu turno](#50--entrar-a-simap-y-ver-el-panel-de-tu-turno)
   - [5.0.1 Cambiar tu contraseña](#501--cambiar-tu-contraseña)
   - [5.1 Registrar un equipo y obtener su etiqueta QR](#51--registrar-un-equipo-y-obtener-su-etiqueta-qr)
   - [5.2 Registrar una lectura de horómetro](#52--registrar-una-lectura-de-horómetro)
   - [5.3 Reportar una alerta](#53--reportar-una-alerta-el-equipo-sigue-funcionando)
   - [5.3.1 Trabajar sin cobertura](#531--trabajar-sin-cobertura)
   - [5.3.2 Revisar alertas y lecturas que no cuadran](#532--revisar-alertas-y-lecturas-que-no-cuadran)
   - [5.4 Reportar una falla](#54--reportar-una-falla-se-abre-una-orden-de-trabajo)
   - [5.5 Seguir y cerrar una orden de trabajo](#55--seguir-y-cerrar-una-orden-de-trabajo)
   - [5.9 Administrar el personal y el catálogo de componentes](#59--administrar-el-personal-y-el-catálogo-de-componentes)
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

### 3.5 Moverte por SIMAP: el menú

En el ordenador, el **menú está siempre a la izquierda**, agrupado por lo que vas a hacer:

- **Inicio**: tu panel del turno.
- **Campo**: escanear un equipo y, si eres operario, tus alertas.
- **Equipos**: la lista de equipos y, si administras la planta, dar de alta uno nuevo y el catálogo
  de componentes.
- **Supervisión**: las alertas y las lecturas por revisar.
- **Administración**: el personal de la empresa.
- **Mi cuenta**: cambiar tu contraseña.

Solo ves las partes que tu rol puede usar. Pulsa el nombre de un grupo para plegarlo o desplegarlo;
SIMAP recuerda cómo lo dejaste en ese aparato. La página en la que estás aparece resaltada.

En el **teléfono**, el menú no ocupa pantalla: pulsa **Menú**, arriba a la izquierda, y se abre
desde ese lado. Se cierra al elegir una página, al tocar fuera o con el mismo botón.

### 3.6 Cómo se ve SIMAP

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
| **Supervisor** | Todo lo del operario, además de reportar fallas, revisar alertas, y autorizar, rechazar o cancelar órdenes de trabajo. |
| **Técnico de taller** | Llevar una orden al taller, registrar el trabajo realizado y marcarla como reparada. Es el único rol que puede marcarla reparada. (Los repuestos llegan en la fase 4.) |
| **Gerente / Stakeholder** | Consultar las órdenes de trabajo y, más adelante, los indicadores de su empresa. Solo lectura: no autoriza cierres. |
| **Administrador** | Gestionar usuarios, equipos y catálogo de componentes; lo mismo que el supervisor con las órdenes, además de corregir una orden cerrada y reiniciar un horómetro. |

## 5. Funcionalidades

Cada funcionalidad se documenta con el mismo esquema:
**Objetivo · Quién · Cómo llegar · Pasos · Resultado · Errores habituales.**

### 5.1 ✅ Registrar un equipo y obtener su etiqueta QR
- **Objetivo:** dar de alta un equipo para que reciba lecturas, alertas y, más adelante, órdenes.
- **Quién:** Administrador.
- **Cómo llegar:** **Equipos → Dar de alta un equipo**.
- **Pasos:** escribe el nombre (es lo único obligatorio); si los sabes, tipo, ubicación, criticidad,
  marca, modelo, número de serie y fecha de instalación; y el **horómetro de hoy** → **Dar de alta y
  crear etiqueta**.
- **Resultado:** SIMAP genera un **código único** de ocho caracteres y te lleva a su etiqueta, con el
  QR, el código corto (`XK7P-2QH9`) y el nombre. Pulsa **Imprimir**. El horómetro de hoy queda como
  primera lectura del equipo.
- **La etiqueta:** al menos 3 × 3 cm, en vinilo o poliéster laminado, sobre una superficie plana y
  visible, lejos del calor. Antes de imprimir todas, prueba a escanear una a unos 50 cm con el
  teléfono más modesto de la planta.
- **Más tarde, desde la ficha del equipo:** **Editar ficha**, **Imprimir etiqueta** (reimprimir no
  cambia el código), **Regenerar código** (solo si la etiqueta se copió o se dañó: la vieja deja de
  funcionar en ese momento) y **Dar de baja** (el equipo deja de admitir registros, pero conserva su
  historial y su etiqueta sigue abriendo la ficha).

### 5.2 ✅ Registrar una lectura de horómetro
- **Objetivo:** que SIMAP conozca las horas acumuladas del equipo, que son la señal principal de la
  predicción.
- **Quién:** Operario o Supervisor.
- **Cómo llegar:** apunta la cámara del teléfono a la etiqueta QR del equipo.
- **Pasos:** 1) comprueba que el nombre de arriba es el de la máquina que tienes delante; 2) escribe
  las horas que marca el horómetro; 3) **Registrar lectura**.
- **Solo horas enteras.** Si el horómetro marca decimales (por ejemplo 4821.5), escribe solo la
  parte entera: 4821. SIMAP no acepta el punto ni la coma decimal, porque quitarlos sin más
  convertiría 4821.5 en 48 215. Puedes escribir el separador de miles si te es más cómodo: 4,821.
- **Resultado:** «Lectura registrada», y el horómetro del equipo se actualiza.
- **Si no cuadra:** si el valor es menor que el último, o sube más horas de las que han pasado,
  SIMAP te pregunta antes de enviar. Puedes **Corregir** o **Enviar igualmente**. Si lo envías, se
  guarda **para revisar**: el supervisor decide si era correcto, y mientras tanto el horómetro del
  equipo no cambia. Así un dígito de más no estropea los cálculos.
- **Sin cobertura:** ver 5.3.1.

### 5.3 ✅ Reportar una alerta (el equipo sigue funcionando)
- **Objetivo:** avisar de algo raro antes de que sea una falla.
- **Quién:** Operario o Supervisor.
- **Cómo llegar:** escanea la etiqueta del equipo → **Reportar alerta**.
- **Pasos:** 1) toca el síntoma: ruido, vibración, calor, olor, fuga u otro; 2) si quieres, escribe
  una nota (hasta 500 caracteres); 3) **Reportar**.
- **Resultado:** la alerta queda **Pendiente** y el supervisor la ve en su bandeja. En **Mis alertas**
  ves las tuyas y qué se hizo con ellas.
- **Repetida:** si reportas el mismo síntoma del mismo equipo dos veces en pocos minutos, cuenta como
  una sola: así un toque de más no hace parecer el equipo más grave de lo que está. Si lo reporta
  otra persona, sí cuenta.

### 5.3.1 ✅ Trabajar sin cobertura
- En una zona sin red, escanea y registra igual. Arriba verás **«Sin conexión · 1 por enviar»**: lo
  que enviaste quedó guardado en el teléfono.
- Si ya habías escaneado ese equipo antes con cobertura, su pantalla se abre con los datos de
  entonces y un aviso de que pueden no estar al día.
- Cuando vuelve la red se envía solo y verás **«Enviado»**. Aunque se envíe varias veces por mala
  cobertura, llega **una sola vez**.
- Lo pendiente es tuyo: si otra persona usa el mismo teléfono, no se envía con su sesión; se envía
  cuando tú vuelvas a entrar. Cerrar sesión no lo borra.
- Instala SIMAP en la pantalla de inicio del teléfono: algunos teléfonos borran los datos de las
  páginas que no se usan, y así lo pendiente está a salvo.
- **Si algo no se pudo guardar**, verás arriba un aviso con el equipo, lo que registraste y el
  motivo (por ejemplo, el equipo se dio de baja mientras no tenías red). No se volverá a enviar: si
  sigue siendo necesario, regístralo otra vez desde el equipo y pulsa **Entendido**.
- Si en un teléfono compartido alguien dejó registros sin enviar y no volvió a entrar en 7 días, se
  descartan y SIMAP lo avisa a quien tenga la sesión.

### 5.3.2 ✅ Revisar alertas y lecturas que no cuadran
- **Quién:** Supervisor o Administrador (el gerente solo consulta).
- **Cómo llegar:** **Alertas**.
- **Alertas pendientes:** marca cada una como **Revisada** o **Descartar**. Queda anotado quién y
  cuándo, y no se deshace.
- **Lecturas por revisar** (arriba, solo si hay alguna): lecturas que no cuadraban con el historial
  del equipo. Para cada una:
  - **Es correcta** — el salto era real. Pasa a contar y actualiza el horómetro del equipo.
  - **Error al teclear** — se conserva, pero no cuenta para nada.
  - **Se cambió el horómetro** (solo el administrador) — el equipo tiene un horómetro nuevo o se
    puso a cero. A partir de esa lectura, las siguientes se comparan con ella.
- **Si dos personas revisan lo mismo a la vez**, cuenta la decisión de la primera. La segunda ve un
  aviso de que otra persona ya la atendió: nadie pisa la decisión de otro. Recarga la página para
  ver qué se decidió.

### 5.4 ✅ Reportar una falla (se abre una orden de trabajo)
- **Objetivo:** documentar una falla real y abrir la orden de trabajo para el taller.
- **Quién:** Supervisor o Administrador.
- **Cómo llegar:**
  - **Desde el equipo:** escanea su QR → **Reportar falla** → **Reportar una falla**.
  - **Desde una alerta:** en **Supervisión → Alertas**, en una alerta pendiente o revisada, pulsa
    **Convertir en orden**. La orden queda vinculada a la alerta, y la alerta pasa a «En orden de
    trabajo».
- **Pasos:** 1) toca el **componente** que falló (si son muchos, escribe en el buscador); si no sabes
  cuál es, elige **Otro (por identificar)** y corrígelo después en la orden; 2) escribe las **horas
  del horómetro**; 3) si la tiene, la **temperatura** y el **código de error** del panel del equipo;
  4) describe **qué pasó**; 5) **Reportar falla**.
- **Resultado:** nace la orden con su número (**OT-0001**, **OT-0002**…, una secuencia propia de tu
  empresa), en estado **Reportada**. El equipo aparece **En falla** en su pantalla y en la lista de
  equipos, para todo el personal, mientras la orden esté abierta.
- **Cosas que conviene saber:**
  - Un componente que ya tiene una orden abierta en ese equipo aparece **gris, con su número**: no
    se puede abrir otra para lo mismo. Si dos personas lo intentan a la vez, SIMAP abre una sola y a
    la otra le dice cuál existe.
  - El horómetro se comprueba igual que una lectura (5.2). Si no cuadra con el historial, la orden
    se abre igualmente, marcada **Horómetro por confirmar**: un supervisor lo confirma desde la orden.
  - Lo que escribas queda **para siempre** en la orden: no pongas datos personales.
  - **Sin cobertura** (supervisor): la falla se guarda en el teléfono y se envía sola al volver la
    red. Arriba verás **«Un reporte de falla sin enviar»** hasta que llegue; todavía no tiene número.
    Si al llegar resulta que ese componente ya tenía orden abierta, verás **«No se creó: ya existe
    OT-0009»** con el enlace. El administrador necesita conexión para reportar.

### 5.5 ✅ Seguir y cerrar una orden de trabajo
- **Objetivo:** llevar la reparación de principio a fin, con cada responsable registrado.
- **Cómo llegar:** **Mantenimiento → Órdenes de trabajo**. Se abre en **Abiertas**; **Cerradas** y
  **Canceladas** son el historial. La lista y la orden se actualizan solas cada 30 segundos.
- **Estados:** `Reportada → En taller → Reparada → Cerrada`, más **Cancelada**.

**Técnico de taller**
1. Abre la orden y pulsa **Llevar al taller** cuando el equipo entra.
2. Al terminar, escribe el **trabajo realizado** y elige el **tipo de intervención**:
   - **Reemplazo**: se cambió el componente por uno nuevo. Su vida vuelve a empezar.
   - **Reparación** o **Ajuste**: el mismo componente sigue; no cuenta como nuevo.
3. **Marcar como reparada**. La orden queda «Reparada · por autorizar».

**Supervisor o administrador**
1. En una orden reparada, **Revisar y autorizar** muestra lo que vas a firmar: el trabajo, el técnico,
   el tipo de intervención y el tiempo fuera de servicio hasta ese momento.
2. **Autorizar y cerrar**: la orden queda **Cerrada** y el equipo sale del taller. SIMAP calcula el
   **tiempo fuera de servicio**: el tiempo de calendario desde la falla hasta tu autorización.
3. Si el trabajo no está bien: **Rechazar el cierre**, con el motivo. La orden vuelve a «En taller»;
   lo que escribió el técnico no se pierde, queda en el historial.
4. **Cancelar la orden**, con motivo, si se reportó por error o está duplicada. No se borra: queda en
   el historial, el componente queda libre y, si venía de una alerta, la alerta vuelve a «Revisada».
5. Mientras está abierta puedes **corregir los datos de la falla** (componente, descripción, código
   de error); queda anotado en el historial.

**Todos los que la ven**: el **Historial** dice quién hizo cada paso, con qué rol y cuándo, aunque esa
persona ya no esté en la empresa. Técnico, supervisor y administrador pueden **añadir una nota** en
cualquier momento, también con la orden cerrada. El **gerente** consulta las órdenes pero no las mueve.

- **Si otra persona se adelantó** (por ejemplo, alguien la canceló mientras tú la autorizabas), la
  orden se recarga y un aviso te dice quién la movió y a qué estado.
- **Sin conexión**, los botones de la orden se desactivan: un cambio de estado necesita saber cómo
  está la orden en ese momento.
- Una orden **Cerrada** o **Cancelada** ya no cambia. La única excepción es la **corrección
  administrativa** (5.5.1).

#### 5.5.1 ✅ Corregir una orden cerrada (administrador)
- **Para qué:** un error de digitación en una orden ya cerrada: el tipo de intervención, el trabajo
  realizado, el código de error.
- **Cómo:** en la orden cerrada, **Corrección administrativa → Corregir…**, cambia lo necesario y
  escribe **por qué se corrige**. Queda en el historial con los valores de antes y de después.
- No se pueden corregir el estado, el número, las fechas ni los responsables.
- Cambiar el tipo de intervención cambia cómo cuenta esa falla para el cálculo de riesgo.

#### 5.5.2 ✅ Cambio o reinicio del horómetro (administrador)
- **Para qué:** cuando a un equipo se le cambia el horómetro o se pone a cero. El aparato vuelve a un
  número bajo, pero las horas que el equipo ha trabajado no se pierden.
- **Cómo:** en la pantalla del equipo, **Gestión del equipo → Cambio o reinicio del horómetro…**,
  escribe lo que marca ahora y **Reiniciar**.
- Las lecturas que alguien tomó antes del cambio y llegan después (desde un teléfono sin red) quedan
  marcadas para revisar.
- Lo mismo con una **falla** reportada antes del cambio que llega después: la orden queda **Horómetro
  por confirmar**, y SIMAP ya cuenta sus horas como eran **antes** del reinicio. Al confirmarla no
  cambian, y no se suman dos veces las horas que el equipo llevaba.

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
- **Supervisor:** alertas pendientes de revisión y órdenes abiertas de tu planta. *(Las órdenes ya
  están en **Mantenimiento → Órdenes de trabajo**; el panel con indicadores llega en la fase 5.)*
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

### 5.9 ✅ Administrar el personal y el catálogo de componentes
- **Quién:** Administrador.
- **Personal** (**Administración → Personal** en el menú): da de alta a cada persona con su correo y su rol. SIMAP
  genera una **contraseña temporal** que se muestra **una sola vez**: cópiala y entrégasela; al
  entrar deberá cambiarla. Desde la misma lista puedes cambiarle el rol, darle una **Nueva clave** si
  se quedó fuera, o **Dar de baja** (no podrá entrar, su sesión abierta se cierra y lo que registró
  se conserva con su nombre).
- No puedes quitarte a ti mismo el rol de administrador ni darte de baja, y la empresa nunca se
  queda sin un administrador activo: da de alta a otro antes.
- **Catálogo de componentes** (**Equipos → Componentes** en el menú): las partes de los equipos que pueden
  fallar. Toda empresa empieza con ocho (motor, tren motriz, sistema hidráulico, bomba de aceite,
  rodamientos, correas y cadenas, refrigeración, eléctrico y control); si el tuyo está vacío,
  **Cargar catálogo inicial**. Puedes añadir, renombrar y desactivar, pero no borrar: las órdenes
  de trabajo los usarán.

### 5.10 ✅ La consola del operador de SIMAP

> Esta sección **no es para el personal de una planta**. Es para quien presta el servicio SIMAP y
> da de alta a las empresas clientes.

- **Objetivo:** dar de alta empresas clientes y mantener su cuenta.
- **Quién:** el operador de SIMAP. No es ninguno de los cinco roles de la sección 4: es una cuenta
  de otro tipo, separada de las empresas.
- **Cómo llegar:** la misma pantalla de acceso que todo el mundo. Con tu correo y tu contraseña,
  SIMAP te lleva a la consola, marcada arriba como **Consola del operador**. Usa para ella un correo
  que no tengas en ninguna planta: si el mismo correo y la misma contraseña valieran en las dos,
  entrarías como usuario de la planta.

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
Se guarda en el teléfono y se envía solo al recuperar la conexión, una sola vez aunque se reintente
(sección 5.3.1).

**¿Por qué mi lectura dice «Para revisar»?**
Porque no cuadraba con las anteriores del equipo. Se guardó, pero no cambia el horómetro del equipo
hasta que el supervisor decide si era correcta (sección 5.3.2).

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
| «Por enviar» no cambia a «Enviado» | Sigue sin conexión, o tu sesión caducó | Al recuperar señal se envía solo; si te pide entrar, entra y se enviará. No borres los datos del navegador mientras tanto |
| «No encontramos este equipo» al escanear | La etiqueta se regeneró, o es de otra empresa | Avisa a tu supervisor; puede que haya que reimprimirla |
| «Ese equipo está dado de baja» | El administrador lo retiró | Si sigue funcionando, avísale |
| «Sin decimales» al registrar el horómetro | Escribiste un punto o una coma decimal | Escribe solo la parte entera de las horas |
| «Demasiados intentos» al entrar, aunque tu contraseña es correcta | Desde la red de la planta se han hecho muchos intentos fallidos en el último minuto | Espera un minuto y vuelve a entrar; si se repite, avisa al administrador |
| La cámara no abre dentro de SIMAP | Falta permiso, o la conexión no es segura (HTTPS) | Usa la cámara del teléfono directamente, o teclea el código de la etiqueta |
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
| 2026-10-07 | 0.7.0 | **Fase 2: equipos y registro de campo.** Equipos con etiqueta QR imprimible (5.1); horómetro (5.2) y alertas (5.3) desde el teléfono en tres pasos; **funciona sin cobertura** y lo pendiente se envía solo (5.3.1); bandeja de alertas y de lecturas que no cuadran, con reinicio del horómetro (5.3.2); el administrador gestiona su personal y el catálogo de componentes (5.9). |
| 2026-10-15 | 0.8.1 | Corrección: una falla reportada sin cobertura **antes** de un reinicio del horómetro, que llega después, ya no cuenta dos veces las horas que el equipo llevaba antes del cambio (5.5.2). Afecta a la vida de los componentes que usará el cálculo de riesgo. |
| 2026-10-14 | 0.8.0 | **Fase 3: órdenes de trabajo.** Reportar una falla desde el equipo o desde una alerta abre una orden numerada (5.4); el taller la lleva de «Reportada» a «Reparada» y un supervisor autoriza su salida, con el tiempo fuera de servicio calculado; rechazo de cierre, cancelación con motivo, notas e historial completo con cada responsable (5.5). Corrección administrativa de una orden cerrada (5.5.1) y reinicio del horómetro sin perder las horas del equipo (5.5.2). Los equipos con una orden abierta aparecen **En falla**. Nueva rama **Mantenimiento** en el menú. |
| 2026-10-11 | 0.7.2 | **Menú lateral en árbol**, agrupado por área de trabajo; en el teléfono se abre con el botón **Menú** (3.5). Las lecturas por revisar tienen su propia entrada en el menú. |
| 2026-10-11 | 0.7.1 | El horómetro solo admite horas enteras: un decimal se rechaza con un aviso en vez de convertirse en un dígito de más (5.2). Si dos supervisores revisan lo mismo a la vez, cuenta la primera decisión (5.3.2). |
| 2026-10-11 | 0.7.0 | Lo enviado sin conexión que el servidor no acepta se avisa a quien lo capturó, con el motivo (5.3.1). |
| 2026-10-07 | 0.7.0 | **Una sola pantalla de acceso para todos.** El operador de SIMAP entra por el mismo acceso que las plantas y SIMAP lo lleva a su consola (5.10). La dirección vieja de la consola lleva al acceso común. |
| 2026-09-26 | 0.4.0 | **Las cuentas pasan a ser por invitación.** Se retira la posibilidad de que una empresa se registre sola: SIMAP se contrata por equipo, así que la cuenta la crea quien administra el servicio. Ver la sección 3.1. |
