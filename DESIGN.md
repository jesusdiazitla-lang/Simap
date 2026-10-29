---
name: SIMAP
description: Consola de mantenimiento sobria al estilo CMMS; gris neutro, paneles planos con borde de 1 px, controles con caja visible y un único azul que significa «aquí se puede actuar».
colors:
  lienzo: "#f1f3f5"
  superficie: "#ffffff"
  superficie-alterna: "#f7f8f9"
  borde: "#d2d8de"
  borde-fuerte: "#7f8891"
  texto: "#15202b"
  texto-suave: "#4b5763"
  texto-tenue: "#5f6b77"
  accion: "#16528f"
  accion-relleno: "#16528f"
  accion-viva: "#0f3d6d"
  accion-texto: "#ffffff"
  accion-halo: "#16528f1f"
  error: "#a32015"
  error-fondo: "#a3201512"
  estado-ok: "#1d6b39"
  estado-aviso: "#7a5200"
  estado-falla: "#a32015"
  lienzo-oscuro: "#0f1215"
  superficie-oscuro: "#181c20"
  superficie-alterna-oscuro: "#1e2328"
  borde-oscuro: "#2c3238"
  borde-fuerte-oscuro: "#68737e"
  texto-oscuro: "#e7eaed"
  texto-suave-oscuro: "#a6b0ba"
  texto-tenue-oscuro: "#8a949e"
  serie-planificado: "#6250d6"
  serie-falla: "#eb6834"
  serie-planificado-oscuro: "#9085e9"
  serie-falla-oscuro: "#d95926"
  accion-oscuro: "#74a9ee"
  accion-relleno-oscuro: "#1e5da8"
  accion-viva-oscuro: "#9cc4f5"
  accion-texto-oscuro: "#ffffff"
  accion-halo-oscuro: "#74a9ee29"
  error-oscuro: "#f0918a"
  error-fondo-oscuro: "#f0918a14"
  estado-ok-oscuro: "#5cc27f"
  estado-aviso-oscuro: "#dfa33c"
  estado-falla-oscuro: "#f0918a"
typography:
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: "1.75rem"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: "1.5rem"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: "1.5rem"
    fontFeature: "\"tnum\" 1"
  body-sm:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: "1.25rem"
  caption:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: "1rem"
    letterSpacing: "0.025em"
  input:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: "1.5rem"
  cifra-grande:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    letterSpacing: "0.025em"
  codigo:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    letterSpacing: "0.06em"
rounded:
  control: "3px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accion-relleno}"
    textColor: "{colors.accion-texto}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.accion-viva}"
    textColor: "{colors.accion-texto}"
  button-primary-disabled:
    backgroundColor: "{colors.superficie-alterna}"
    textColor: "{colors.texto-tenue}"
  button-secondary:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "48px"
  button-secondary-hover:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.accion}"
  button-secondary-disabled:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto-tenue}"
  input:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    typography: "{typography.input}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "48px"
  input-grande:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    typography: "{typography.cifra-grande}"
    rounded: "{rounded.control}"
    height: "56px"
  input-disabled:
    backgroundColor: "{colors.superficie-alterna}"
    textColor: "{colors.texto-tenue}"
  panel:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    padding: "20px 24px"
  panel-pie:
    backgroundColor: "{colors.superficie-alterna}"
    textColor: "{colors.texto-tenue}"
    padding: "16px 24px"
  insignia-ok:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.estado-ok}"
    typography: "{typography.caption}"
    rounded: "{rounded.control}"
    height: "24px"
  insignia-aviso:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.estado-aviso}"
    rounded: "{rounded.control}"
    height: "24px"
  insignia-falla:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.estado-falla}"
    rounded: "{rounded.control}"
    height: "24px"
  insignia-neutra:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto-suave}"
    rounded: "{rounded.control}"
    height: "24px"
  baldosa-opcion:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    height: "56px"
  baldosa-opcion-elegida:
    backgroundColor: "{colors.accion-halo}"
    textColor: "{colors.accion}"
  nav-enlace:
    textColor: "{colors.texto-suave}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "36px"
  nav-enlace-actual:
    backgroundColor: "{colors.superficie-alterna}"
    textColor: "{colors.texto}"
---

# Design System: SIMAP

## Overview

**Creative North Star: "La consola de planta"**

SIMAP tiene que poder confundirse con un CMMS bien hecho (Fiix, UpKeep, Limble): un lienzo gris neutro, paneles blancos planos separados por un borde de 1 px, controles con caja visible, densidad alta y un solo color de acción. La pantalla desaparece detrás de la tarea. La familiaridad gana a la distinción; cuando una decisión puede ir hacia lo expresivo o hacia el estándar de la categoría bien ejecutado, va hacia el estándar.

La estructura se comunica con espaciado, alineación y bordes, nunca con sombras, texturas ni objetos simulados. Lo que hay de carácter es funcional: dos vocabularios de color que no se mezclan, claro y oscuro igual de cuidados porque la luz de una planta cambia dentro del mismo turno, y objetivos táctiles de 48 px porque se usa de pie y con guantes.

Nota histórica: una primera versión construida, «La bitácora de mantenimiento» (papel reglado, margen perforado, sello de fecha, violeta de anilina, Libre Franklin, radio 0), fue rechazada por el usuario al verla terminada por poco sobria para empresas industriales. De ella solo sobrevivieron las reglas funcionales; ningún rasgo decorativo.

**Key Characteristics:**
- Lienzo gris, paneles blancos con borde de 1 px, sin sombras.
- Un único azul, reservado a lo que se puede pulsar o escribir.
- Verde, ámbar y rojo solo para el estado de una máquina, siempre con palabra.
- Una sola familia (Inter), jerarquía por peso y tamaño, cifras tabulares en todo el producto.
- Radio pequeño y constante de 3 px en todo control y contenedor.
- Claro y oscuro normativos por igual; contraste 4.5:1 en texto y 3:1 en bordes de control.

## Colors

Neutros grises sin tinte, un azul de acción y tres colores de estado de máquina que nunca se usan para interacción. Cada token tiene valor claro y valor oscuro (sufijo `-oscuro`); los dos son normativos y se auditan por separado.

### Primary
- **Azul de acción** (`accion`, relleno `accion-relleno`, hover `accion-viva`): enlaces, borde y halo de foco de los campos, caret, anillo de foco, selección de una baldosa o de un filtro, relleno del botón primario. En oscuro, la tinta (`accion-oscuro`) y el relleno del botón (`accion-relleno-oscuro`) son valores distintos porque contrastan contra cosas distintas: la tinta contra el panel, el relleno contra el texto blanco de encima.
- **Halo de acción** (`accion-halo`): fondo translúcido de una opción elegida y de la selección de texto; también el anillo de 2 px alrededor de un campo enfocado.

### Tertiary
- **Estado en servicio** (`estado-ok`), **estado de aviso** (`estado-aviso`), **estado de falla** (`estado-falla`): borde y texto de insignias de estado, de avisos de envío y del indicador de cola. Fondo siempre neutro.
- **Error de formulario** (`error`, `error-fondo`): texto de la ranura de error, borde del campo inválido y caja del error de envío. Es la voz del formulario, no de la máquina.

### Neutral
- **Lienzo** (`lienzo`): fondo de página y color de la barra del navegador (`themeColor`).
- **Superficie** (`superficie`): paneles, barra superior, pie, campos, insignias.
- **Superficie alterna** (`superficie-alterna`): pie de panel, enlace de navegación actual, hover de filas, controles deshabilitados, esqueleto de carga.
- **Borde** (`borde`): contorno de paneles y separadores de filas.
- **Borde fuerte** (`borde-fuerte`): caja de campos, botones secundarios y baldosas; tiene que cumplir 3:1.
- **Texto, texto suave, texto tenue** (`texto`, `texto-suave`, `texto-tenue`): contenido, descripciones y metadatos respectivamente.

### Named Rules
**The Two Vocabularies Rule.** El azul significa «aquí se puede hacer algo»; verde, ámbar y rojo significan «este es el estado de una máquina». No se cruzan nunca: una insignia de estado no es pulsable, y una selección hecha por el usuario se marca en azul aunque sea un síntoma de avería.

**The Lost Blue Rule.** Un control deshabilitado pierde el azul por completo: fondo `superficie-alterna`, borde `borde-fuerte`, texto `texto-tenue`. Un gris azulado o un azul atenuado sigue diciendo «pulsable».

**The One Live Blue Rule.** Un solo azul relleno activo por pantalla. Los botones de envío nacen apagados y solo se encienden cuando hay algo que enviar («Elige un síntoma» → «Reportar vibración»).

**The Never Alone Rule.** El color nunca es el único portador de significado: todo estado lleva palabra, y los que piden atención (pendiente, sin conexión, error) además un icono.

**The Neutral Criticality Rule.** La criticidad de un equipo es importancia, no estado: va siempre en insignia neutra. Un equipo crítico que funciona bien nunca se pinta de rojo.

**The Third Vocabulary Rule.** Las gráficas tienen sus propios colores de serie (`serie-planificado`
violeta, `serie-falla` naranja), validados con el validador de paletas en los dos temas (diferencia
con daltonismo y contraste contra la superficie). No son ni el azul de acción ni los colores de
estado: una columna de «por falla» no es una máquina en falla. Una sola serie va en tinta (`texto`).

**The Both Themes Rule.** Claro y oscuro son de primera clase. Ningún valor se decide en un tema y se deriva en el otro sin auditar su contraste.

## Typography

**Display Font:** ninguna; no hay tipo de titulares.
**Body Font:** Inter (con ui-sans-serif, system-ui, sans-serif), pesos 400, 500, 600 y 700, `display: swap`.
**Label/Mono Font:** monoespaciada del sistema, solo para códigos de equipo y claves temporales.

**Character:** la letra neutra de las herramientas de trabajo; legible a tamaño pequeño, sin opinión propia. La jerarquía la llevan el peso y el tamaño, no una segunda familia.

### Hierarchy
- **Headline** (600, 1.375rem, 1.75rem): título de pantalla («Equipos», nombre del equipo) y la cifra principal del horómetro en la ficha.
- **Title** (600, 1.0625rem, 1.5rem): título de panel.
- **Body** (400, 0.9375rem, 1.5rem): texto de trabajo, botones (en 600), celdas de tabla en escritorio. Párrafos largos limitados a 60–70ch.
- **Body small** (400, 0.875rem, 1.25rem): descripciones de panel, navegación, mensajes de error de envío.
- **Label** (500, 0.8125rem, 1.25rem): etiquetas de campo, ayudas, metadatos, controles de la barra superior.
- **Caption** (500, 0.75rem, mayúsculas con espaciado ancho): cabeceras de columna de tabla y etiquetas de dato (`<dt>`); también la palabra «obligatorio» y el pie de página, en caja normal.
- **Cifra grande** (600, 1.5rem, espaciado ancho): el dato que se viene a escribir, en el campo del horómetro.
- **Código** (mono, 0.8125rem–1.0625rem, espaciado 0.06–0.08em): códigos cortos de equipo y contraseñas temporales.

### Named Rules
**The Tabular Figures Rule.** Cifras tabulares en todo el producto (`font-variant-numeric: tabular-nums` en `body`): un horómetro o una hora que cambian de ancho hacen saltar la columna.

**The es-DO Rule.** Toda cifra, fecha y hora pasa por el formateador común con la configuración regional `es-DO`: separador de miles con coma («4,821 h»), fecha `dd/mm/aaaa`, hora de dos dígitos. La fecha exacta va acompañada del relativo («hace 3 h»), nunca sustituida por él.

**The 16px Input Rule.** El texto de un campo mide exactamente 1rem; por debajo, iOS hace zoom al enfocar.

## Layout

Contenedor centrado de `max-w-6xl` (72rem) con 16 px de margen lateral en móvil y 24 px desde `sm`. La barra superior mide 56 px, con «SIMAP» a la izquierda y la sesión a la derecha; el pie lleva versión y a quién acudir. El contenido baja 32 px (40 px en `sm`); las pantallas de una sola pieza (acceso, carga, error) bajan un desplazamiento fijo de 12vh, nunca un centrado vertical que haría saltar el botón cuando aparece un error. Formularios y avisos aislados se estrechan a `max-w-xl`.

El trabajo vive en paneles apilados con 24 px entre ellos; dentro, 20 px de relleno (24 px en `sm`), cabecera y pie separados por borde de 1 px. El ritmo de espaciado es de 4 en 4 (8, 12, 16, 20, 24, 32 px), con 8 y 12 px como huecos dominantes.

Las tablas son tablas de verdad en escritorio (cabecera en Caption, filas separadas por `borde`, cifras alineadas a la derecha) y se apilan en móvil: la cabecera se oculta y cada fila pasa a una rejilla de dos columnas con el nombre a la izquierda y horómetro y estado a la derecha. Con sesión, la aplicación ocupa todo el ancho: menú lateral de 240 px a la izquierda desde `lg`, fijo bajo una barra superior que también queda fija, y el contenido en su contenedor de `max-w-6xl` a la derecha. Por debajo de `lg` el menú sale en un cajón desde la izquierda con el botón «Menú». La pantalla de carga reserva la columna vacía para que nada salte cuando llega la sesión.

## Elevation & Depth

Sistema plano. La separación entre contenido y fondo la da el contraste entre `superficie` y `lienzo` más un borde de 1 px; nada flota. La única sombra del sistema es la del cajón de navegación móvil, que se superpone de verdad al contenido.

### Shadow Vocabulary
- **Cajón móvil** (`box-shadow: 8px 0 16px -12px rgb(0 0 0 / 0.35)`): solo en el borde derecho del cajón del menú en pantallas estrechas, sobre un fondo atenuado `rgb(0 0 0 / 0.32)` que cierra el cajón al tocarlo.

### Named Rules
**The Flat Panel Rule.** Ningún panel, tarjeta, botón ni campo lleva sombra. Si algo necesita destacarse, se hace con borde, peso o el azul de acción, no con elevación.

## Shapes

Un solo radio, pequeño y constante: 3 px (`--radius-control`) en botones, campos, paneles, insignias, baldosas, filtros segmentados y esqueletos. Ni cero, que hoy se lee como sin terminar, ni redondeado, que aleja la pantalla de una herramienta de trabajo. Los bordes son de 1 px; la única excepción es la selección de una baldosa, que sube a 2 px en azul. Los iconos son SVG propios de 20 × 20, trazo de 1.75 px con extremos redondeados y color heredado; siempre acompañan a una palabra y son `aria-hidden`.

## Components

### Buttons
Dos variantes y ninguna más; sólidos, sin animación de entrada ni de pulsación.
- **Shape:** esquinas de control (3 px), 48 px de alto, 20 px de relleno lateral, Body en 600.
- **Primary:** relleno y borde `accion-relleno`, texto `accion-texto`; hover a `accion-viva`. Uno por pantalla.
- **Secondary:** fondo `superficie`, borde `borde-fuerte`, texto `texto`; hover cambia borde y texto a `accion`.
- **Disabled:** pierde el azul entero (ver The Lost Blue Rule), cursor `not-allowed`.
- **Busy:** ocupado no es deshabilitado. Mientras la petición está en vuelo el botón conserva su color, marca `aria-busy` y sustituye su texto («Enviando…»); el estado nunca depende solo del color.
- **Enlace con forma de botón:** las acciones que llevan a otra pantalla usan la misma geometría y las mismas dos variantes.
- **Focus:** anillo general de 2 px en `accion` separado 2 px.

### Chips (insignias)
- **Style:** 24 px de alto, radio de control, borde y texto del color de estado, fondo `superficie`, Caption en 600. Un relleno saturado convertiría cada fila en un semáforo.
- **State:** tonos `ok`, `aviso`, `falla` y `neutro`; los de atención llevan icono de 14 px. Nunca pulsables. La etiqueta «Consola del operador» y las marcas «Llega en F…» son variantes neutras sobre `superficie-alterna`.
- **Orden de trabajo:** es el estado de la máquina visto desde el taller. Reportada en `falla` con icono de aviso (la máquina está en falla); En taller y «Reparada · por autorizar» en `aviso` con icono de reloj; Cerrada en `ok`; Cancelada en `neutro`, porque no dice nada de la máquina. «Horómetro por confirmar» en `aviso`. «En falla» en la lista de equipos y el aviso de la pantalla del equipo usan `falla`: borde de 1 px en el aviso, nunca relleno.

### Cards / Containers (Panel)
- **Corner Style:** radio de control (3 px).
- **Background:** `superficie`; pie opcional en `superficie-alterna` con texto tenue.
- **Shadow Strategy:** ninguna (ver The Flat Panel Rule).
- **Border:** 1 px `borde`, también entre cabecera, cuerpo y pie.
- **Internal Padding:** 20 px (24 px desde `sm`); cabecera de 16 px vertical. El título es `h1` cuando el panel es la pantalla y `h2` cuando es una sección de ella.

### Inputs / Fields
- **Style:** caja visible de 1 px `borde-fuerte`, fondo `superficie`, 48 px de alto (56 px en la variante grande para la cifra del horómetro), 12 px de relleno, texto a 1rem. Etiqueta encima en Label, con «obligatorio» u «opcional» en palabra; ayuda permanente debajo de la etiqueta, enlazada con `aria-describedby`.
- **Focus:** borde a `accion` más anillo de 2 px en `accion-halo`; el anillo general se suprime en campos para no dibujar tres cercos.
- **Error / Disabled:** borde `error`, mensaje en la ranura de error que está siempre reservada (24 px mínimo) para que la geometría no se mueva; `aria-invalid` y `aria-live`. Deshabilitado: fondo `superficie-alterna`, texto tenue. Las contraseñas llevan un conmutador «Ver/Ocultar» en texto azul con `aria-pressed`, y siempre se puede pegar.

### Navigation
Menú en árbol (`ArbolNavegacion`), agrupado por área de trabajo y no por pantalla: **Inicio** suelto arriba, y las ramas **Campo**, **Mantenimiento** (órdenes de trabajo desde F3; riesgo de falla, alertas del sistema e inventario desde F4), **Equipos**, **Supervisión**, **Administración** (personal y, desde F4, predicción) y **Mi cuenta**. Cada rol ve solo las hojas que puede abrir; una rama sin hojas no se pinta.
- **Rama:** botón de fila completa con icono de área a la izquierda, nombre en Body small 600 `texto` y chevron a la derecha (girado −90° si está plegada, sin animación); `aria-expanded` y `aria-controls`. Las ramas plegadas se recuerdan en el navegador.
- **Hoja:** Body small 500 en `texto-suave`, colgada de una guía vertical de 1 px `borde` alineada con el centro del icono de la rama. Hover y página actual sobre `superficie-alterna` con `texto`; la actual además en 600 y con su tramo de guía oscurecido a `texto` (1 px, neutro: es posición, no acción). `aria-current="page"` en la hoja de ruta más larga que contiene la página abierta.
- **Escritorio (`lg`):** columna de 240 px, `superficie` con borde derecho de 1 px, filas de 36 px, fija bajo la barra superior (que queda fija). La marca «SIMAP» se alinea encima de la columna. Nombre y rol de la sesión a la derecha de la barra desde `lg`; «Cerrar sesión» como control con caja de 36 px.
- **Móvil:** botón con la palabra «Menú» (nunca un icono de tres rayas) a la izquierda de la marca, lejos de «Cerrar sesión»; abre el mismo árbol en un cajón de `min(20rem, 85vw)` desde la izquierda con filas de 48 px y la sesión arriba. Abierto, el botón conserva la palabra y pasa a borde `accion` sobre `accion-halo`. Se cierra con Escape, tocando el fondo o al elegir una página.

### Baldosas de opción
Radios reales presentados como baldosas de un toque (56 px de alto, rejilla de 2 columnas en móvil y 3 en `sm`), para elegir un síntoma o un rol sin listas desplegables. Elegida: borde de 2 px `accion`, fondo `accion-halo`, texto `accion` y marca de verificación; la selección va en azul porque es interacción, no estado de la máquina. El foco se dibuja en la baldosa con `:has(:focus-visible)`. El filtro segmentado de listas usa el mismo lenguaje en una tira con divisores de 1 px.

### Avisos de envío e indicador de cola
Caja con radio de control, fondo `superficie`, borde del tono (`estado-ok` hecho, `estado-aviso` en cola, `error` con `error-fondo` en fallo), icono y frase completa. El indicador de cola de la barra (32 px) dice «Sin conexión», «N pendientes por enviar» o «Enviado» con icono y palabra, y no ocupa sitio si no tiene nada que decir.

### Riesgo de falla (F4)
El riesgo es el estado de una máquina, no una acción: usa los colores de estado, nunca el azul, y no es pulsable.
- **Nivel (`NivelRiesgo`):** insignia con palabra. «Riesgo bajo» en `ok`; «Vigilar» en `aviso` con icono; «Riesgo alto» en `falla` con icono. La escala parte del umbral **de la empresa** (vigilar desde el 80 % del umbral, la misma banda de la histéresis; alto desde el umbral), no de números fijos.
- **Cifra (`Porcentaje`):** Title 600 con cifras tabulares; con confianza baja lleva la palabra «estimado» en Caption `texto-suave` a su lado.
- **Respaldo (`ConfianzaInsignia`):** insignia neutra «Confianza baja/media/alta» y, junto a ella, «N fallas registradas» y «Calculado hace…». Un porcentaje nunca aparece sin respaldo.
- **Explicación (`Explicacion`):** una frase en Body small `texto-suave` («Esta pieza lleva…; a esa edad el modelo estima…»).
- **Sin cálculo (`SinCalculo`):** «Sin edad» y «Sin modelo» son insignias neutras con icono de aviso y la acción que lo resuelve; nunca un 0 % ni una barra vacía.
- **Curva (`CurvaRiesgo`):** SVG propio sin librería: un trazo de 2 px `texto`, rejilla de 1 px `borde`, umbral en línea discontinua `estado-aviso` con su etiqueta, y la edad actual como punto hueco. El SVG mide su contenedor (texto siempre a 12 px) y va en posición absoluta dentro de él para no ensanchar la rejilla; en anchos menores de 420 px muestra tres marcas en el eje en vez de cinco.
- **Sin conexión:** el mismo panel con la descripción «Último cálculo conocido… Sin conexión no se actualiza» y sin enlaces al modelo.

### Inventario y repuestos (F4)
- **Bajo el mínimo:** insignia `aviso` con icono; el stock en la fila sigue en `texto` (la insignia ya lo dice).
- **Libro:** tabla con movimiento, cambio con signo (`+14`, `−2`) en 600 y el stock que queda en `texto-suave`; en móvil se apila. No hay acciones por fila: el libro no se edita.
- **Repuestos de la orden (`RepuestosOrden`):** búsqueda con campo de 48 px y resultados como filas-botón de 48 px con nombre, código en monoespaciada y «N en almacén» a la derecha; al elegir uno, una caja `superficie-alterna` con la cantidad y «Añadir». El aviso de faltantes (`SinStock`) es un aviso con borde `estado-aviso`, icono, la lista «nombre (código): hay X, la orden pide Y» y quién puede resolverlo.

### Paneles por rol y gráficas (F5)
- **Medidas del periodo (`Medida`):** lista de definición en cuatro columnas (dos en tableta, una en
  móvil) separadas por bordes de 1 px; el nombre en Caption `texto-suave`, la cifra en Title 600 con
  cifras tabulares y debajo su nota (rango del MTBF, utilización, reparto del costo). Una cifra sin
  datos dice por qué («Ninguna falla cerrada en el periodo»), nunca un 0.
- **Filtros:** un panel con Planta, Desde y Hasta en cajas de 48 px y «Aplicar», que nace apagado
  (One Live Blue). Debajo, en Caption, que la planta ordena la vista y no limita el acceso.
- **Sección degradada:** si un widget vuelve con error o tiempo agotado, su panel conserva el título
  y en lugar del contenido muestra un icono `estado-aviso` y la frase «Esta información no está
  disponible en este momento…»; bajo el título de la página, un `role="status"` cuenta cuántas
  secciones faltan. El resto se pinta normal.
- **Gráficas (`GraficaDisponibilidad`, `GraficaCosto`):** SVG propio. La disponibilidad es una línea
  de 2 px en `texto` con puntos de 8 px; el costo, columnas apiladas con un hueco de 2 px entre
  planificado y falla y la punta redondeada. Rejilla de 1 px `borde`, texto siempre a 12 px en
  `texto-suave`, nunca del color de la serie. Leyenda con muestras cuadradas y palabra. El SVG mide
  su contenedor (`ResizeObserver`, mínimo 260 px). Cada mes es una zona enfocable más ancha que la
  marca; el detalle sale en una línea `aria-live` encima de la gráfica, sin tapar nada. «Ver como
  tabla» (`details`) da las mismas cifras. Sin consumos, la gráfica de costo no se dibuja: estado
  vacío con su frase.
- **Tablas del panel:** cabeceras y números de orden sin cortes de línea; la tabla se desplaza dentro
  de su panel y la rejilla usa `min-w-0` en sus hijos para que una tabla ancha nunca ensanche la
  página (RNF-05, 390 px sin desplazamiento horizontal).

### Control segmentado (`Segmento`)
Vistas de una bandeja (Riesgo/Reorden, Vigentes/Historial, Todos/Bajo el mínimo): radios nativos ocultos dentro de un `fieldset` con leyenda, presentados como cajas de 48 px en una tira con divisores de 1 px `borde-fuerte`; la elegida en `accion-halo` con texto `accion`. Se navega con flechas. Es una elección del usuario, por eso azul.

### Esqueleto de carga
Barras estáticas en `superficie-alterna` con radio de control, separadas por bordes de fila; sin animación de brillo.

## Do's and Don'ts

### Do:
- **Do** separar contenido y fondo con `superficie` sobre `lienzo` y un borde de 1 px.
- **Do** reservar el azul para lo que se puede pulsar, escribir o elegir, y quitarlo entero cuando el control está deshabilitado.
- **Do** dejar los botones de envío apagados hasta que haya algo que enviar, de modo que solo haya un azul relleno vivo por pantalla.
- **Do** mantener el texto del botón cambiante mientras está ocupado, sin deshabilitarlo visualmente.
- **Do** acompañar todo estado con palabra, y los de atención también con icono.
- **Do** usar insignia neutra para la criticidad.
- **Do** dar 48 px de alto a campos, botones y filas del cajón del menú; 56 px a baldosas y al campo de la cifra.
- **Do** formatear cifras, fechas y horas con `es-DO` desde el formateador común, con cifras tabulares.
- **Do** auditar claro y oscuro por separado: texto a 4.5:1, bordes de control a 3:1.
- **Do** apilar las tablas en móvil en una rejilla de dos columnas en vez de forzar desplazamiento horizontal.

### Don't:
- **Don't** usar fondos con textura, papel, rayado, márgenes perforados, sellos ni ninguna metáfora de objetos físicos.
- **Don't** usar verde, ámbar o rojo en un control pulsable ni para marcar una selección.
- **Don't** rellenar las insignias con el color de estado.
- **Don't** añadir sombras a paneles, botones o campos; la única sombra es la del desplegable móvil.
- **Don't** introducir una segunda familia tipográfica ni un tipo de titulares.
- **Don't** usar otro radio que 3 px ni bordes gruesos fuera de la baldosa elegida.
- **Don't** añadir animaciones de entrada, de pulsación o de brillo; solo transiciones de color.
- **Don't** esconder la navegación móvil tras un icono sin palabra.
- **Don't** centrar verticalmente bloques cuya altura cambia; usar el desplazamiento fijo de 12vh.
- **Don't** bloquear el zoom ni el pegado en campos.
