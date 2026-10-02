---
name: SIMAP
description: La bitácora de mantenimiento: hoja reglada de libro mayor, tinta de pluma y un único sello violeta donde se puede actuar.
colors:
  escritorio: "#dbdfd2"
  hoja: "#f2f4ec"
  hoja-borde: "#c3cdb9"
  tinta: "#191f26"
  tinta-suave: "#4b5661"
  tinta-tenue: "#5f6a74"
  reglado: "#c2cfb8"
  reglado-fuerte: "#7c9372"
  sello: "#5b2a86"
  sello-relleno: "#5b2a86"
  sello-vivo: "#4a2170"
  sello-tinta: "#ffffff"
  sello-halo: "#5b2a8626"
  excepcion: "#9e211b"
  excepcion-fondo: "#9e211b14"
  estado-ok: "#1d6b39"
  estado-aviso: "#7f5300"
  estado-falla: "#9e211b"
typography:
  display:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: "1.75rem"
    letterSpacing: "0.06em"
  headline:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "normal"
  title:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: "2rem"
    letterSpacing: "normal"
  body:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: "2rem"
    letterSpacing: "normal"
  body-small:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: "2rem"
    letterSpacing: "normal"
  nota:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: "2rem"
    letterSpacing: "normal"
  label:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.16em"
  accion:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.16em"
  impreso:
    fontFamily: "Libre Franklin, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: "1rem"
    letterSpacing: "0.2em"
rounded:
  none: "0px"
spacing:
  renglon: "32px"
  escritura: "64px"
  fila: "96px"
  campo: "160px"
  control: "56px"
  columna: "34rem"
  hoja: "60rem"
components:
  button-primary:
    backgroundColor: "{colors.sello-relleno}"
    textColor: "{colors.sello-tinta}"
    typography: "{typography.accion}"
    rounded: "{rounded.none}"
    padding: "0 32px"
    height: "{spacing.control}"
  button-primary-hover:
    backgroundColor: "{colors.sello-vivo}"
    textColor: "{colors.sello-tinta}"
  button-primary-busy:
    backgroundColor: "{colors.sello-relleno}"
    textColor: "{colors.sello-tinta}"
  button-primary-disabled:
    backgroundColor: "transparent"
    textColor: "{colors.tinta-tenue}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.tinta-suave}"
    typography: "{typography.accion}"
    rounded: "{rounded.none}"
    padding: "0 24px"
    height: "{spacing.control}"
  button-secondary-hover:
    backgroundColor: "transparent"
    textColor: "{colors.excepcion}"
  field:
    backgroundColor: "transparent"
    textColor: "{colors.tinta}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0 8px"
    height: "{spacing.escritura}"
  field-focus:
    backgroundColor: "transparent"
    textColor: "{colors.tinta}"
  field-error:
    textColor: "{colors.excepcion}"
    typography: "{typography.nota}"
    height: "{spacing.renglon}"
  field-disabled:
    textColor: "{colors.tinta-tenue}"
  hoja:
    backgroundColor: "{colors.hoja}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.none}"
    width: "{spacing.hoja}"
  hoja-cabecera:
    textColor: "{colors.tinta}"
    typography: "{typography.display}"
    height: "{spacing.fila}"
  sello-fecha:
    textColor: "{colors.tinta-suave}"
    typography: "{typography.impreso}"
    rounded: "{rounded.none}"
    padding: "4px 10px"
  fila-accion:
    backgroundColor: "transparent"
    textColor: "{colors.sello}"
    typography: "{typography.title}"
    rounded: "{rounded.none}"
    padding: "32px 0"
  fila-accion-hover:
    backgroundColor: "{colors.sello-halo}"
    textColor: "{colors.sello}"
  fila-accion-pendiente:
    backgroundColor: "transparent"
    textColor: "{colors.tinta-suave}"
---

# Design System: SIMAP

## Overview

**Creative North Star: "La bitácora de mantenimiento"**

Entrar a SIMAP es firmar el libro. El cuaderno rayado, el margen perforado de la encuadernación y el
sello de fecha son el **sustrato** de la interfaz, no un adorno encima de ella: cada dato del sistema
tiene un responsable con nombre, y la hoja es lo que lo dice antes de que nadie lea una palabra. La
lectura del papel es industrial y no nostálgica: papel de oficio verde reglado de libro mayor, tinta
azul-negra de pluma, letra de imprenta comercial. Nada de pergamino, nada de sepia.

La densidad es la de un impreso de taller: un solo tipo de letra, cero radios, cero sombras, y una
rejilla horizontal que no se negocia. La pantalla se ve a distancia de brazo, de pie, con guantes y
con la luz cambiando dentro del mismo turno, así que los objetivos táctiles son grandes aunque el
dibujo sea una línea fina, y el esquema claro y el oscuro son **los dos de primera clase**, medidos
por separado: todos los pares de texto cumplen 4.5:1 y los bordes de control 3:1.

El sistema rechaza por su nombre dos cosas que esta categoría entrega siempre: la tarjeta centrada
flotando con sombra sobre un fondo liso, y el color como decoración. Hay exactamente un color de
acción y aparece en un solo elemento por pantalla.

**Key Characteristics:**
- Hoja a sangre completa; nunca una tarjeta centrada con sombra.
- Reglado cada 32 px que manda sobre la maquetación, no al revés.
- Dos vocabularios de color incompatibles: acción (violeta) y estado de máquina (verde/ámbar/rojo).
- Radio 0 en todo; la profundidad se consigue con reglas y tono, no con sombras.
- Una sola familia tipográfica, cifras tabulares en todo el producto.
- Claro y oscuro auditados por separado, ambos normativos.
- Un único momento animado por pantalla.

## Colors

Paleta de papel contable: verdes desaturados para el sustrato y la estructura, un azul-negro de pluma
para el contenido, y un violeta de anilina que es lo único saturado de la pantalla.

### Primary
- **Violeta de anilina del sello** (`{colors.sello}`): el color de acción, y nada más. Tinta violeta
  sobre la hoja: enlaces, marca de foco en el margen, anillo de foco, caret, texto de la fila de
  acción disponible.
- **Relleno del sello** (`{colors.sello-relleno}`): fondo del único botón primario de la pantalla. Se
  mantiene como token aparte del anterior porque en el tema oscuro **no pueden coincidir**: uno tiene
  que dar 4.5:1 como tinta sobre la hoja, el otro tiene que dejar que el blanco de encima lo dé.
- **Violeta cargado** (`{colors.sello-vivo}`): estado hover del botón y del enlace de la contraseña.
- **Halo del sello** (`{colors.sello-halo}`): selección de texto y fondo hover de una fila pulsable.

### Secondary
- **Excepción** (`{colors.excepcion}`): lo que en el libro se escribe en rojo. Mensajes de error,
  línea del campo inválido, la observación de un intento rechazado y el hover de «Cerrar sesión».
  No es un color de acción: marca una anotación, no una posibilidad.

### Tertiary
Reservado al **estado de una máquina**, y por eso no aparece en ninguna superficie de acceso ni de
panel todavía: `{colors.estado-ok}`, `{colors.estado-aviso}`, `{colors.estado-falla}` son para
alerta, orden de trabajo y riesgo. Están declarados en el sistema y esperando a F2.

### Neutral
- **Escritorio** (`{colors.escritorio}`): el fondo bajo la hoja. Es más oscuro que la hoja a
  propósito, para que la hoja se lea apoyada en algo y no como el lienzo entero. También rellena las
  perforaciones del margen.
- **Hoja** (`{colors.hoja}`): la superficie de trabajo, único fondo de contenido del producto.
- **Borde de la hoja** (`{colors.hoja-borde}`): el aro de cada perforación de la encuadernación.
- **Tinta** (`{colors.tinta}`): todo el texto de contenido y los títulos.
- **Tinta suave** (`{colors.tinta-suave}`): etiquetas, descripciones secundarias, sello de fecha.
- **Tinta tenue** (`{colors.tinta-tenue}`): letra pequeña del pie, códigos, texto deshabilitado.
- **Reglado** (`{colors.reglado}`): las líneas del papel y los separadores finos. Bajo contraste
  porque es estructura, no contenido: guía el ojo sin competir con lo escrito.
- **Reglado fuerte** (`{colors.reglado-fuerte}`): las reglas gruesas (cabecera y banda de acción), la
  vertical del libro mayor, el borde de un control en reposo y la barra de desplazamiento.

### Named Rules

**La Regla de los Dos Vocabularios.** El violeta significa «aquí se puede hacer algo» y solo aparece
en controles activos; verde, ámbar y rojo significan «este es el estado de una máquina» y nunca
significan interacción. No se mezclan nunca. El motivo es de accesibilidad y no de gusto: el par
verde/rojo es justamente el que no distingue alguien con deuteranopía, así que si además cargara con
el significado de «pulsable» no quedaría señal disponible para el estado real del equipo.

**La Regla del Control Apagado.** Un control deshabilitado pierde el violeta **entero**: pasa a borde
`{colors.reglado-fuerte}` y texto `{colors.tinta-tenue}` sobre fondo transparente. No hay violeta
atenuado, ni violeta al 40 %.

**La Regla de Ocupado ≠ Deshabilitado.** Mientras una petición está en vuelo el control **conserva el
color** y cambia el texto («Entrar» → «Comprobando…», «Cerrar sesión» → «Cerrando…»), con
`aria-busy` y cursor `progress`. Apagar a gris el único momento autoral de la pantalla en el instante
exacto en que se dispara hace que no se vea ninguna de las dos cosas.

**La Regla del Color que Nunca Está Solo.** El color no es nunca el único portador de significado. La
disponibilidad de una acción se escribe además en texto («Llega en F2»), el error va en mensaje
enlazado con `aria-describedby`, y el foco cambia de grosor además de tono.

**La Regla de la Tinta Sin Negro.** El texto es azul-negro de pluma, nunca `#000`. El negro puro
sobre papel claro no existe en el mundo del que sale esto y cansa más la vista. En oscuro, tampoco
negro puro de fondo: en OLED los bordes de la hoja flotarían.

**La Regla del Oscuro Que No Es Azul.** El tema oscuro es la misma hoja de papel contable verde bajo
una lámpara de trabajo: solo baja la luz. Un oscuro azul pizarra es el oscuro por defecto de
cualquier interfaz y no el de este mundo.

## Typography

**Familia única:** Libre Franklin (con `ui-sans-serif, system-ui, sans-serif`), pesos 400/500/600/700,
`display: swap`.

**Character:** Franklin Gothic es el tipo de la imprenta comercial e industrial del siglo XX:
facturas, albaranes, etiquetas, formularios de taller. Es literalmente la letra del mundo del que sale
la bitácora, no un palo seco elegido por neutro. La jerarquía la llevan el peso, el interletraje y la
caja; no hay un segundo tipo para titulares.

### Hierarchy
- **Display** (700, 1.375 rem → 1.625 rem en `sm`, interlínea 1.75 rem, `+0.06em`, versales): el
  nombre impreso de la hoja, en la cabecera. Un solo uso por pantalla.
- **Headline** (600, 1.375 rem, interlínea 1): el dato que identifica a la persona del turno (la
  firma).
- **Title** (600, 1.0625 rem, interlínea 2 rem): el nombre de una acción en una fila del panel.
- **Body** (400, 1.0625 rem = 17 px, interlínea 2 rem): texto del cuerpo y **todo input de
  escritura**. Nunca por debajo de 16 px en un campo: iOS hace zoom al enfocar y descoloca la hoja
  entera.
- **Body small** (400, 0.9375 rem, interlínea 2 rem): descripciones de apoyo. Medida acotada a
  46–68 ch según el contenedor.
- **Nota** (400, 0.8125 rem, interlínea 2 rem): la letra pequeña del pie del formulario y el mensaje
  de error del campo.
- **Label** (600, 0.75 rem, `+0.16em`, versales): etiqueta de un renglón del formulario, rótulo de la
  columna de observaciones.
- **Acción** (600, 0.9375 rem, `+0.16em`, versales): texto de cualquier botón.
- **Impreso** (600, 0.6875 rem, `+0.14em`–`+0.2em`, versales): el código del formulario y el sello de
  fecha. Es el registro de «esto salió de una imprenta», no un rótulo de sección.

### Named Rules

**La Regla del Interlineado del Reglado.** Todo texto de varias líneas dentro del cuerpo de la hoja
usa interlínea de 32 px, el mismo paso del reglado. Así cada línea ocupa una banda entera y queda
centrada en ella, en vez de que las líneas de la hoja la atraviesen. Un párrafo puede crecer, pero
siempre de 32 en 32.

**La Regla del Renglón Sin Eyebrow.** Las versales apretadas de la escala `impreso` son el código del
formulario y el sello de fecha, y van al **pie**, donde los imprimen los formularios de verdad.
Ningún rótulo en versalitas se coloca encima de un título para introducirlo.

**La Regla de las Cifras Tabulares.** `font-variant-numeric: tabular-nums` en todo el producto. Un
horómetro, una fecha o un contador de horas que cambien de ancho al actualizarse hacen saltar la
columna.

## Layout

**El reglado manda sobre la maquetación, no al revés.** La hoja dibuja una línea cada 32 px
(`{spacing.renglon}`) con un degradado repetido que arranca en su borde superior, así que **todo lo
que va en el cuerpo mide múltiplos de 32** y el texto se asienta *sobre* una línea de verdad en vez
de flotar cerca de ella. Medidas observadas: cabecera 96 px (`{spacing.fila}`, tres renglones, con la
regla gruesa cayendo sobre la tercera); campo completo 160 px (32 de aire + 32 de etiqueta + 64 de
escritura + 32 de ranura de error); fila de panel y esqueleto de carga 64 px; columna de
observaciones 96 px de altura **fija**, no mínima.

**Anatomía de la hoja.** A sangre completa (`min-h-dvh`), sin borde flotante ni sombra. De arriba
abajo: margen de encuadernado perforado a la izquierda (4 px de filo en móvil, 48 px desde `sm`, con
borde `reglado-fuerte` y ocultado a la accesibilidad); cabecera de 96 px con el título a la izquierda
y el sello de fecha a la derecha, cerrada por regla gruesa de 2 px; **cuerpo reglado**; y una **banda
de acción fuera del área reglada**, abierta por otra regla gruesa de 2 px. La banda va sin reglar
precisamente porque su altura es variable: tiene que poder estirarse para empujar la acción al
alcance del pulgar en móvil. El pie del formulario cierra con regla fina y lleva el código a la
derecha.

**Contenedor y columnas.** El ancho de lectura se controla **dentro** de la hoja, nunca encogiendo la
hoja: caja centrada de 60 rem máximo, con 28 px de sangrado izquierdo (72 px desde `sm`) para dejar
pasar el margen perforado. Desde 1024 px el cuerpo se parte en dos: columna de escritura de 34 rem
(`{spacing.columna}`) y columna de observaciones a su derecha, separadas por **la vertical del libro
mayor**, un filete de 1 px en `reglado-fuerte` que recorre el cuerpo y la banda de acción de punta a
punta.

**Puntos de ruptura.** `sm` 640 px (el margen perforado se abre, la cabecera crece, el botón deja de
ser de ancho completo) y `lg` 1024 px (aparecen la segunda columna y la vertical). No hay nada en
`md`: a 640 px el área útil de la hoja son 528 px y una vertical a 34 rem caería fuera, provocando
desplazamiento horizontal.

**Objetivos táctiles.** Botón 56 px de alto y ancho completo en móvil; área de escritura 64 px de
alto aunque el dibujo sea una línea. El zoom nunca se bloquea: ni `maximumScale` ni
`userScalable: false`, porque quitarlo es quitarle la única ayuda a quien no ve bien el renglón con
guantes y a contraluz.

### Named Rules

**La Regla del Múltiplo de 32.** Cualquier pieza nueva del cuerpo de la hoja mide un múltiplo de
32 px, o descuadra el reglado de toda la pantalla. Test: si una altura no es divisible por 32, no va
dentro del cuerpo.

**La Regla de la Banda Sin Reglar.** Lo de altura variable vive en la banda de acción, no en el
cuerpo. La banda es el único sitio del sistema donde la altura puede ser libre.

**La Regla de la Geometría Inmóvil.** La ranura del error (32 px) y la columna de observaciones
(96 px) están reservadas siempre, vacías o no. Un mensaje que aparece y empuja el botón hacia abajo
hace que quien iba a pulsar «Entrar» pulse otra cosa. Cuando el contenido desborda, se desborda con
scroll y contenedor enfocable: nunca con `overflow: hidden`, porque lo que se recorta es justo la
parte de «cómo salir de aquí».

## Elevation & Depth

**No hay sombras.** Ninguna superficie del sistema proyecta nada: la sombra flotante es exactamente
lo que la tarjeta centrada que este mundo rechaza usaría para levantarse del fondo. La profundidad se
consigue con tres recursos de papel, en este orden:

1. **Tono**: el escritorio es más oscuro que la hoja, así que la hoja se lee apoyada sobre algo.
2. **Reglas**: 2 px en `reglado-fuerte` para separar zonas de la hoja (cabecera, banda de acción),
   1 px en `reglado` para separar registros dentro de una lista.
3. **Perforación y vertical**: el margen perforado y el filete del libro mayor dicen «página de un
   libro» sin levantar nada del plano.

### Shadow Vocabulary
- **Engrosamiento del renglón enfocado** (`box-shadow: inset 0 -3px 0 0 var(--sello)`): la única
  declaración de sombra del sistema, y es interior y funcional. Engorda la línea de escritura al
  enfocar. Se pinta con sombra y **no** subiendo `border-width` porque con `box-sizing: border-box` un
  borde más grueso come 2 px del área de contenido y el texto ya escrito da un salto.

### Named Rules

**La Regla del Plano Único.** Todo está en el mismo plano. Si una superficie nueva necesita
distinguirse, se separa con una regla o con un cambio de tono de papel; nunca con una sombra, y menos
con una sombra desplazada y dura.

## Shapes

**Radio 0 en todo el sistema**, sin excepción observada: botones, campos, sello de fecha, hoja y
filas son rectángulos rectos. Es la forma del impreso: una caja de formulario no tiene esquinas
redondeadas.

El vocabulario de forma se construye con **líneas**, no con contornos cerrados:
- Campo de escritura: **sin caja**. Solo una línea inferior de 2 px, más una marca de lápiz en el
  margen (6 × 16 px en `sello`) que aparece con el foco.
- Botón: borde de 2 px del mismo color que su relleno; el secundario es el mismo rectángulo sin
  relleno.
- Sello de fecha: recuadro de 1.5 px en `reglado-fuerte`, rotado **−1.6°**, con un degradado radial
  que carga más tinta en los bordes y opacidad 0.9. Un sello de goma nunca cae recto ni imprime
  uniforme; lo que lo hace reconocible es la geometría, no el color.
- Margen perforado: círculos de 5 px rellenos de `escritorio` con aro de 1 px en `hoja-borde`, uno
  cada 96 px.

**Movimiento.** Un único momento animado por pantalla: `estampar`, 420 ms
`cubic-bezier(0.16, 1, 0.3, 1)`, que imprime el sello **al pulsar** el botón primario, no al cargar la
página. Arranca desde un estado ya visible, así que si no corre no se pierde nada. Todo lo demás son
transiciones de color de 200 ms. Con `prefers-reduced-motion: reduce`, la animación se anula y toda
transición baja a 1 ms.

### Named Rules

**La Regla del Rectángulo Recto.** Radio 0 siempre. Si algo parece necesitar una esquina redondeada,
lo que necesita es no ser una tarjeta.

**La Regla del Momento Único.** Una pantalla tiene como máximo un momento animado, y es una respuesta
a una acción del usuario, nunca una entrada coreografiada.

## Components

Carácter general: piezas de impreso de taller. Grandes al dedo, finas al ojo, sin caja donde el
oficio no la pondría.

### Buttons
- **Shape:** rectángulo recto (radio 0), borde de 2 px, alto 56 px, ancho completo en móvil y
  `min-width: 11rem` desde `sm`.
- **Primary (el sello):** relleno y borde en `{colors.sello-relleno}`, texto `{colors.sello-tinta}`,
  escala `accion` en versales con `+0.16em`. Es el único sitio de la pantalla donde el violeta aparece
  relleno, y hay **uno solo por pantalla**.
- **Hover / Focus:** relleno y borde pasan a `{colors.sello-vivo}` en 200 ms; el foco es el anillo
  global de 2 px en `{colors.sello}` con 2 px de separación.
- **Ocupado:** conserva relleno y color, cambia el texto al de curso, `aria-busy`, cursor `progress`.
- **Deshabilitado:** pierde el violeta entero — fondo transparente, borde `{colors.reglado-fuerte}`,
  texto `{colors.tinta-tenue}`, cursor `not-allowed`. Sin animación.
- **Secondary (cerrar sesión):** mismo rectángulo, sin relleno, borde `{colors.reglado-fuerte}` y
  texto `{colors.tinta-suave}`; al hover borde y texto pasan a `{colors.excepcion}`. No lleva violeta
  porque no es una acción del turno: es la que saca a alguien del sistema, y en un aparato compartido
  tiene que estar siempre a la vista sin poder confundirse con lo demás.
- **Enlace de utilidad dentro de un control** («Ver» / «Ocultar» la contraseña): texto en
  `{colors.sello}`, versales 0.75 rem, subrayado de 1 px con 4 px de separación; alto 64 px para
  coincidir con el área de escritura.

### Inputs / Fields
- **Style:** sin caja. Fondo transparente, texto `body` (17 px), 8 px de sangrado horizontal, alto de
  escritura 64 px y línea inferior de 2 px en `{colors.reglado-fuerte}`. El campo completo mide
  160 px: aire, etiqueta, escritura, ranura de error.
- **Focus:** la línea toma `{colors.sello}` **y** engorda con la sombra interior de 3 px; además
  aparece la marca de lápiz en el margen. El anillo rectangular del navegador se anula aquí a
  propósito: un rectángulo alrededor contradice un campo cuya idea entera es no tener caja, y el
  grosor cambia además del color para que el foco no dependa de distinguir dos tonos.
- **Error:** la línea pasa a `{colors.excepcion}` y la mantiene incluso con el foco; el mensaje ocupa
  la ranura de 32 px reservada, en escala `nota` y color `{colors.excepcion}`, con `aria-live="polite"`,
  `aria-invalid` y `aria-describedby`. **El valor escrito nunca se borra ni se limpia**: en una
  bitácora se tacha y se anota al lado.
- **Disabled:** texto `{colors.tinta-tenue}`, línea `{colors.reglado}`, cursor `not-allowed`.
- **Etiqueta:** escala `label` en `{colors.tinta-suave}`, 32 px de alto; la palabra «obligatorio» va
  en caja baja y `{colors.tinta-tenue}` al lado, no como asterisco.
- Se permite pegar siempre; no existe `onPaste` bloqueado en este proyecto.

### Cards / Containers
No existen tarjetas. El único contenedor es **la hoja** (ver el componente firma). Las listas se
separan con regla fina de 1 px en `{colors.reglado}` sobre el propio papel.

### Navigation
La navegación del panel es una **lista de renglones**, no un menú: cada acción es un renglón de la
hoja separado por regla fina, con nombre en escala `title` y descripción en `body-small` (máx. 62 ch),
ambos con interlínea de 32 px. Disponible: nombre en `{colors.sello}`, fondo hover
`{colors.sello-halo}`. Pendiente: nombre en `{colors.tinta-suave}`, opacidad 0.7 y una etiqueta
flotada a la derecha en escala `impreso` que dice en texto **cuándo llega** («Llega en F2»). Lo
pendiente se muestra desactivado con su fase, no escondido, y sin violeta.

### La hoja (componente firma)
El sustrato de todas las pantallas: `titulo`, `codigo`, cuerpo reglado, banda `accion` y `pie`. A
sangre completa, con margen perforado, cabecera de 96 px, vertical del libro mayor desde 1024 px y pie
con el código del formulario. Cada pantalla es una hoja con su código impreso (`F-ACC-01`,
`F-TUR-01`), incluidos los estados de carga y de error: el esqueleto de carga dibuja la forma real de
lo que va a llegar —tres renglones de 64 px con barras en `{colors.reglado}`— sobre la misma hoja, así
que el desvío entre pantallas nunca parpadea entre dos fondos distintos.

### El sello de fecha (componente firma)
Arriba a la derecha de la cabecera: fecha y hora reales en cifras tabulares, escala `impreso`, color
`{colors.tinta-suave}`, recuadro rotado −1.6° con impresión desigual. Es **contenido**, no adorno: un
asiento de bitácora sin fecha no vale nada. **No va en violeta**, aunque la tinta de sello real lo
sea: en este sistema el violeta significa «aquí se puede hacer algo» y el sello no se pulsa;
teñirlo lo convertía en el segundo elemento más llamativo compitiendo con el único botón.

### La columna de observaciones (componente firma)
A la derecha de la vertical, desde 1024 px: donde en el oficio se anota lo que se sale de lo normal.
Rótulo en escala `impreso` visible solo cuando existe la columna. Una anotación lleva la hora
**tachada** (`line-through`) y el texto en `{colors.excepcion}`: en una bitácora no se borra nada, se
tacha y se anota al lado, así que un intento rechazado queda registrado. Cuando hay errores de campo,
la anotación incluye un enlace «Ir al renglón».

### Superficies del navegador
También llevan el sistema: `caret-color` en `{colors.sello}`, `::selection` con fondo
`{colors.sello-halo}` y texto `{colors.tinta}`, barra de desplazamiento fina en
`{colors.reglado-fuerte}` sobre `{colors.escritorio}`, y anillo de foco global de 2 px en
`{colors.sello}` con 2 px de separación. `color-scheme: light dark`, forzable con `data-tema` en
`<html>` para poder auditar los dos temas sin depender del sistema operativo.

## Do's and Don'ts

### Do:
- **Do** usar el violeta del sello **solo** donde se puede hacer algo, y quitárselo entero a lo
  deshabilitado.
- **Do** reservar verde, ámbar y rojo (`estado-ok`, `estado-aviso`, `estado-falla`) para el estado de
  una máquina, siempre acompañados de texto o icono.
- **Do** mantener el color en un control ocupado y cambiarle el texto («Comprobando…»), con
  `aria-busy`.
- **Do** medir toda pieza del cuerpo de la hoja en múltiplos de 32 px (cabecera 96, campo 160, fila de
  panel 64).
- **Do** poner lo de altura variable en la banda de acción, fuera del área reglada.
- **Do** reservar el espacio de los mensajes antes de que existan, para que nada empuje al botón.
- **Do** dibujar los campos como una línea sobre la que se escribe, con área táctil de 64 px.
- **Do** dar a cada pantalla su hoja con código de formulario, incluidas las de carga y error.
- **Do** auditar el tema claro y el oscuro por separado: 4.5:1 en texto, 3:1 en bordes de control.
- **Do** interlinear a 32 px todo párrafo del cuerpo, para que quede centrado en su banda del reglado.
- **Do** mantener las cifras tabulares en toda medida, fecha u hora.

### Don't:
- **Don't** mezclar los dos vocabularios de color: ni violeta para estado de máquina, ni verde/rojo
  para interacción.
- **Don't** usar el violeta atenuado como estado deshabilitado. Se pierde entero.
- **Don't** presentar una hoja como tarjeta centrada con sombra sobre un fondo liso; la hoja va a
  sangre completa y el ancho de lectura se controla dentro.
- **Don't** añadir sombras de elevación, y menos sombras desplazadas y duras: este mundo no tiene
  ninguna. La única sombra declarada es la interior del renglón enfocado.
- **Don't** redondear esquinas. El radio es 0.
- **Don't** colocar un rótulo en versalitas encima de un título para introducirlo. El código del
  formulario va al pie.
- **Don't** poner un anillo rectangular de foco en un campo sin caja: el foco se marca engordando la
  línea y tiñéndola de violeta.
- **Don't** recortar con `overflow: hidden` un mensaje de error o de espera; desbordar con scroll en
  un contenedor enfocable.
- **Don't** borrar o limpiar lo que el usuario escribió al fallar la validación.
- **Don't** bloquear el zoom (`maximumScale`, `userScalable: false`) ni el pegado en un campo de
  contraseña.
- **Don't** animar la entrada de una pantalla ni añadir un segundo momento animado: la impresión del
  sello ocurre al pulsar.
- **Don't** esconder una acción que aún no existe; se muestra desactivada, sin violeta y con su fase
  escrita en texto.
- **Don't** hacer del tema oscuro un azul pizarra ni un negro puro: es la misma hoja verde bajo
  lámpara de trabajo.
