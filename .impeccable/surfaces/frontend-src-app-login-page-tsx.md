---
version: 1
slug: "frontend-src-app-login-page-tsx"
primary_target: "frontend/src/app/login/page.tsx"
related_targets: []
---

## Scope

Pantalla de acceso de SIMAP (`src/app/login/page.tsx`) y el vocabulario visual que de ella hereda el
resto de la aplicación. Modo de visitante: **Operate** — quien llega viene a entrar, no a evaluar el
producto. Decisión del usuario: sin texto de presentación.

## Audience, job, constraints

Los cinco roles de una empresa cliente, ninguno anónimo. El operario es el caso que manda: de pie,
con guantes, una mano libre, luz ambiente que cambia dentro del mismo turno. El dispositivo se trata
**siempre como no confiable** (decisión del usuario): sesión corta, cerrar sesión siempre visible,
sin «mantener sesión abierta» indefinido. El alta de empresa **no** es autoservicio, así que esta
pantalla no ofrece ningún camino de registro.

## Direction contract

THESIS: Entrar a SIMAP es firmar el libro. La bitácora de mantenimiento —el cuaderno rayado, la
tarjeta colgada del equipo, el sello de fecha, las iniciales— es lo que SIMAP viene a reemplazar, y
la interfaz lo asume en vez de disimularlo: cada dato del sistema tiene un responsable con nombre, y
autenticarse es el acto de poner el tuyo en el renglón. Rechaza la tarjeta centrada flotando sobre un
fondo neutro, que es lo que esta categoría siempre entrega, y rechaza la lectura blanda y nostálgica
del papel: una bitácora industrial es papel de oficio verde reglado, no pergamino de librería.

OWN-WORLD: Fondo de papel contable verde pálido, reglado en verde de libro mayor de bajo contraste y
espaciado constante. Tinta del cuerpo en azul-negro de pluma, nunca negro puro. **El violeta de
anilina del sello de fecha es el color de acción**, y solo aparece donde algo se puede hacer: un
control deshabilitado lo pierde por completo. Verde, ámbar y rojo quedan **reservados para el estado
de una máquina** (alerta, orden de trabajo, riesgo), nunca para interacción; así los dos vocabularios
no colisionan y el par verde/rojo deja de ser el único portador de significado. Margen de encuadernado
con perforaciones a la izquierda, porque la hoja es una página de un libro y no un lienzo. Una sola
familia de palo seco, cifras tabulares en toda medida. Regla heredada del oficio: **en una bitácora
se escribe en tinta y nada se borra**; una corrección se tacha y se inicia, así que ningún estado de
error hace desaparecer lo que había.

STORY: Quien llega ya sabe qué es SIMAP y viene a trabajar. Entiende en el primer segundo que esto es
un registro con responsables, no un portal corporativo; cree que lo que escriba aquí queda atribuido
a su nombre; y hace una sola cosa: identificarse y pasar a su panel. El operario debe poder hacerlo
con guantes, con una mano, sin leer instrucciones.

FIRST VIEWPORT: La hoja de bitácora ocupa el viewport completo, con su reglado y el margen de
encuadernado perforado en el borde izquierdo. Arriba, la cabecera impresa de la propia hoja —
identificador del formulario a la izquierda, fecha y hora reales en cifras tabulares a la derecha,
donde iría el sello. Los dos campos son dos renglones consecutivos de la hoja: el texto se asienta
**sobre** la línea, sin caja alrededor, y la línea engrosa y toma el violeta al enfocar; el área
táctil no baja de 48 px de alto aunque el dibujo sea una línea. La acción primaria es el sello:
abajo a la izquierda en móvil, dentro del alcance del pulgar. Un único momento autoral en toda la
pantalla — la impresión del sello al enviar, con su leve rotación y su tinta desigual; nada más se
mueve. El error aparece tachado junto al renglón, en rojo, sin desplazar el botón ni refluir la hoja.

FORM: La bitácora de mantenimiento; candidata 1 de mi lista ordenada por resonancia. El sorteo asignó
la candidata 5 (papel de probabilidad Weibull) y el usuario eligió esta desde la tarjeta
IMPECCABLE'S PICK, con su riesgo de familiaridad declarado. Seed key a9bfa4af, scope direction,
mode operate. Retadores competitivos que quedan disponibles: tablero split-flap de estación y
superficie de app de consumo. Disciplinas donadas y ya incorporadas arriba: color solo donde hay
acción (app de consumo), el estado no rompe la rejilla (split-flap), la incertidumbre es un estado
visible y el color se confina a bordes (borde de nube iridiscente), nada se rotula dos veces (funda
de catálogo Factory), un único momento autoral por pantalla (tormenta de alfabeto), legible a
distancia de brazo (escena ASCII).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved decisions

- El esquema claro y el oscuro son **ambos de primera clase**, porque la luz ambiente cambia dentro
  del turno; el oscuro es la misma hoja bajo lámpara de trabajo, no el claro invertido. Ambos deben
  auditarse por separado.
- La navegación por rol se estrena aquí solo como destino tras entrar; su composición se decide
  cuando exista el primer panel real (F2).
