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
| **Supervisor** | Reportar fallas, revisar las alertas de tu planta, seguir las órdenes de trabajo y adelantarte a las fallas con las alertas del sistema. |
| **Técnico de taller** | Tomar las órdenes del taller, anotar los repuestos usados, registrar qué reparaste y marcarlas como reparadas. |
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

## Primeros pasos

1. Abre la dirección en el navegador. Verás la pantalla de acceso.
2. Escribe tu correo y tu contraseña y pulsa **Entrar**.
3. Verás el panel de tu turno, con lo que tu rol puede hacer. El **menú está a la izquierda**,
   agrupado por área (Campo, Equipos, Supervisión, Administración, Mi cuenta); en el teléfono se
   abre con el botón **Menú**.
4. En planta: apunta la **cámara del teléfono** a la etiqueta QR del equipo. Se abre su pantalla:
   comprueba que el nombre es el de la máquina que tienes delante, escribe el horómetro o elige el
   síntoma, y envía. Tres pasos.

### En planta, con o sin cobertura

- **Horómetro:** escribe lo que marca, en horas enteras: si marca 4821.5, escribe 4821. Al lado
  ves la última lectura; si lo que escribes no cuadra (es menor, o sube más horas de las que han
  pasado), SIMAP te pregunta antes de enviar. Suele ser un dígito de más.
- **Alerta:** toca el síntoma (ruido, vibración, calor, olor, fuga u otro) y, si quieres, añade una
  nota. Si reportas lo mismo dos veces en pocos minutos, cuenta como una sola.
- **Sin cobertura:** registra igual. Lo que envíes se guarda en el teléfono y arriba verás
  «Sin conexión · 1 por enviar». Cuando vuelva la red se envía solo y verás «Enviado». Aunque se
  reintente varias veces, llega una sola vez. Si algo no se pudo guardar (por ejemplo, el equipo
  se dio de baja mientras tanto), SIMAP te lo dice con el motivo.
- **Si la cámara no lee la etiqueta**, en **Escanear** puedes teclear el código impreso bajo el QR
  (por ejemplo `XK7P-2QH9`).

Instala SIMAP en la pantalla de inicio del teléfono («añadir a la pantalla de inicio»): así el
teléfono no borra lo que tengas pendiente de enviar.

### No hay botón de «crear cuenta», y es a propósito

SIMAP se contrata por equipo, así que las empresas **entran por invitación**: la cuenta de tu
empresa la crea quien opera SIMAP, y tu usuario lo da de alta el administrador de tu planta.
Si no tienes acceso o no recuerdas tu contraseña, habla con esa persona.

### La primera vez entrarás con una contraseña temporal

Si eres el **administrador** de tu planta, quien opera SIMAP te habrá dado una contraseña generada
por el sistema. Cámbiala en cuanto entres: quien te la entregó la vio al crearla, aunque no se
guarde en ningún sitio. En el panel, abajo, en **Tu cuenta → Cambiar contraseña**.

### Cambiar tu contraseña

Desde el panel, **Tu cuenta → Cambiar contraseña**. Te pedirá la actual —para que nadie pueda
cambiarla con una sesión que dejaste abierta— y la nueva dos veces, con al menos 12 caracteres.

Al cambiarla, **se cierra tu sesión en cualquier otro aparato** donde la tuvieras abierta; en el que
estás sigues dentro. Si la cambias porque crees que alguien la vio, eso es justo lo que quieres.

### Si tu empresa aparece como suspendida

Verás un mensaje que lo dice claramente al intentar entrar. No es un problema de tu contraseña: la
cuenta de tu empresa está desactivada y hay que hablar con quien contrató SIMAP. **Tus datos no se
han borrado**; vuelven a estar disponibles en cuanto se reactive.

### Cierra la sesión si el aparato no es solo tuyo

El botón **Cerrar sesión** está siempre a la vista en el panel. Si el teléfono o la tableta pasa
entre turnos o entre compañeros, ciérrala antes de dejarlo: todo lo que se registre queda asociado
al nombre de quien tenga la sesión abierta.

## Estado actual de la aplicación

| Funcionalidad | Fase | Estado |
|---|---|---|
| Inicio de sesión y panel por rol | 1 | ✅ Disponible |
| Consola del operador: alta de clientes, suspensión, claves | 1 | ✅ Disponible |
| Cambiar tu contraseña (usuarios y operador) | 1 | ✅ Disponible |
| Aviso propio cuando no hay conexión | 1 | ✅ Disponible |
| Equipos con código QR y etiqueta imprimible | 2 | ✅ Disponible |
| Horómetro y alertas desde el teléfono, también sin cobertura | 2 | ✅ Disponible |
| Revisión de alertas y de lecturas que no cuadran | 2 | ✅ Disponible |
| Personal de la empresa y catálogo de componentes | 2 | ✅ Disponible |
| Órdenes de trabajo: reportar una falla, taller, autorizar el cierre | 3 | ✅ Disponible |
| Riesgo de falla por equipo, alertas del sistema y orden predictiva | 4 | ✅ Disponible |
| Inventario de repuestos con libro, ingresos, conteos y reorden | 4 | ✅ Disponible |
| Paneles por rol: lo del turno e indicadores del gerente | 5 | ✅ Disponible |
| API en funcionamiento (`/api/v1/health`) | — | ✅ Disponible |

**La fase 5 está construida.** Al entrar, cada persona ve **su** panel: el operario, sus lecturas
y alertas y en qué quedaron; el técnico, la cola del taller; el supervisor, lo que espera su
revisión. El gerente ve cómo va la planta: **disponibilidad**, **tiempo medio entre fallas** (siempre
con su rango, para no fiarse de una cifra con pocas fallas detrás), **tiempo medio de reparación** y
**costo de repuestos**, mes a mes y con su tabla, más los equipos de mayor riesgo. Se filtra por
planta y por periodo, y si una sección falla, el resto del panel sigue funcionando. Ver la sección
5.8 del manual.

Con las cuentas de demostración, los indicadores salen de **datos simulados**; con datos reales
hacen falta unas semanas de uso para que digan algo.

**La fase 4 está construida.** SIMAP calcula, para cada pieza de cada equipo, la probabilidad de
que falle en las próximas horas de operación, y la enseña siempre con cuántas fallas la respaldan y
con qué confianza («estimado» si son pocas). Cuando el riesgo supera el umbral de tu empresa aparece
una **alerta del sistema**, y desde ella el supervisor abre una **orden predictiva** para cambiar la
pieza antes de que falle. El modelo aprende solo: cada orden cerrada lo reajusta. El almacén lleva un
**libro** de cada entrada y salida; los repuestos que anota el técnico se descuentan al autorizar el
cierre, y si no alcanzan, el cierre no se hace y SIMAP dice qué falta. Cuando un repuesto baja de su
mínimo, avisa. Sin cobertura, la pantalla del equipo enseña el último riesgo conocido con su hora.
Un horómetro que no cuadra —también el de una orden predictiva que se convierte en falla— no
entra al cálculo hasta que alguien lo confirma: un error al teclear no estropea el modelo.

Las cuentas de demostración (empresa «Demo») traen una flota simulada con dos casos para verlo: una
bomba con la pieza vieja, reparada tres veces sin cambiarla (riesgo alto), y otra con la pieza recién
cambiada (riesgo bajo). **Son datos simulados.**

**La fase 3 está construida.** Una falla se reporta desde la etiqueta del equipo (o desde una
alerta) y abre una **orden de trabajo** numerada. El técnico la lleva al taller y registra lo que
hizo; el supervisor revisa lo que va a firmar y **autoriza la salida** del equipo, y SIMAP calcula
cuánto tiempo estuvo fuera de servicio. Cada paso queda con el nombre y el rol de quien lo dio, y una
orden cerrada ya no se puede cambiar (salvo una corrección del administrador, que también queda
anotada). Mientras haya una orden abierta, el equipo aparece **En falla** para todo el personal.
Si a un equipo se le reinicia el horómetro, una falla anotada antes del cambio que llega después
(desde un teléfono sin cobertura) se cuenta con las horas de su momento. Queda probarla en un
teléfono real.

**La fase 2 está construida.** Los equipos llevan su etiqueta QR, el personal registra el
horómetro y las alertas desde el teléfono —también sin cobertura—, y el supervisor revisa lo que no
cuadra. El administrador de cada planta da de alta a su propia gente. Queda probarla en teléfonos
reales con etiquetas impresas.

**La fase 1 está terminada.** Ya se puede entrar a SIMAP desde el navegador, con correo y
contraseña, y cada persona ve el panel de su rol. Incluye protección contra quien intente adivinar
contraseñas a base de reintentos: tras cinco fallos seguidos hay que esperar un momento.

Debajo de eso está lo que garantiza que una empresa **nunca** vea los datos de otra: la propia base
de datos separa la información por empresa, no el programa. Se hizo primero a propósito; añadir el
aislamiento después, con datos reales ya cargados, sería mucho más arriesgado.

**Sobre la pantalla.** SIMAP es deliberadamente sobrio: se parece a las herramientas de
mantenimiento que ya se usan en la industria, no a una aplicación llamativa. Una herramienta de
trabajo tiene que desaparecer detrás de la tarea. Funciona igual de bien con la pantalla clara que
con la oscura —la luz de una planta cambia a lo largo del turno— y los botones son grandes a
propósito, para poder usarlos con guantes y con una sola mano. Todo lo que registres queda
asociado a tu nombre.

También se puede **instalar en el teléfono** como una aplicación: al abrirla en el navegador, el
propio teléfono ofrece «añadir a la pantalla de inicio». Si te quedas sin cobertura, la pantalla del
equipo se abre igual con lo que se guardó la última vez, y lo que registres se envía al volver la
red.

> Cada cambio en el código pasa por una verificación automática que, entre otras cosas, comprueba
> contra una base de datos real que ninguna empresa pueda ver los datos de otra. Si esa comprobación
> falla, el cambio no se acepta.

## Si tú eres quien opera SIMAP

Esta sección no es para el personal de una planta, sino para quien presta el servicio.

Entras por la **misma pantalla de acceso** que todo el mundo: SIMAP reconoce tu cuenta y te lleva
a tu consola, marcada como **Consola del operador**. Desde ahí puedes:

- **Dar de alta una empresa cliente** con su primer administrador. SIMAP genera la contraseña y te
  la muestra **una sola vez**: cópiala y entrégasela. No se guarda en ningún sitio, así que si la
  pierdes hay que generar otra.
- **Suspender y reactivar** una empresa que dejó de pagar. Sus datos no se tocan; simplemente su
  gente no puede entrar.
- **Restablecer la contraseña del administrador** de una planta que se quedó fuera. Es el caso de
  soporte más frecuente, porque no hay nadie por encima de él que pueda ayudarlo.
- **Renombrar** una empresa y consultar la **bitácora** de todo lo anterior.
- **Cambiar tu propia contraseña**, abajo en la consola, en **Tu cuenta**. Queda en la bitácora.

Restablecer la contraseña de un administrador **cierra las sesiones que tuviera abiertas**: si te
lo piden porque alguien perdió el control de la cuenta, el intruso queda fuera.

Lo que **no** puedes hacer, y es a propósito: ver los equipos, las órdenes de trabajo o las
lecturas de ningún cliente. La consola solo muestra el nombre de cada empresa, quién es su
administrador, cuántos equipos tiene monitoreados y si está activa. No es que la pantalla no lo
pinte: es que la base de datos no se lo permite al programa que atiende esa consola. Así, si
alguien te robara la contraseña, no obtendría los datos de tus clientes.

## ¿Problemas?

- Si la página no carga, comprueba que el servidor esté encendido (ver
  "Puesta en marcha" en el [README técnico](README.md#puesta-en-marcha)).
- Para incidencias, abre un *issue* en el repositorio indicando qué hacías,
  qué esperabas y qué ocurrió.

---
_Este documento se revisa en cada publicación a la rama principal._
