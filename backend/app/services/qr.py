"""Código de cada equipo y su etiqueta imprimible (RF-05; 05-fase2-activos-y-campo.md, sección 6).

EL CÓDIGO
---------
Ocho caracteres de un alfabeto de 32 símbolos sin los que se confunden al leerlos en una etiqueta
sucia o al dictarlos por radio: sin I, O, 0 ni 1. Son 32⁸, más de un billón de combinaciones.

Se generan con `secrets`, nunca con `random` ni con un contador: un código secuencial permitiría
recorrer los equipos de todas las empresas probando el siguiente.

El QR codifica únicamente `{APP_BASE_URL}/a/{código}`. Nada del equipo ni de la empresa: quien
fotografíe una etiqueta no obtiene nada que valga la pena leer, y lo que se ve al escanear lo decide
el servidor, después de comprobar quién pregunta.

Este módulo es lógica pura, sin base de datos: generar, normalizar, presentar y dibujar. Lo usa
`app.services.activos`, que es quien decide cuándo y guarda el resultado.
"""

from __future__ import annotations

import io
import re
import secrets
from xml.sax.saxutils import escape

import qrcode
import qrcode.constants
from qrcode.image.svg import SvgPathImage

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LARGO = 8
#: Lo que se acepta tras normalizar. Cualquier otra cosa se descarta antes de tocar la base.
PATRON = re.compile(rf"^[{ALFABETO}]{{{LARGO}}}$")


def generar_codigo() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(LARGO))


def normalizar(tecleado: str) -> str | None:
    """Convierte lo que alguien tecleó en un código, o `None` si no puede serlo.

    El código corto se imprime en grupos (`XK7P-2QH9`) y se teclea a mano cuando la cámara no lee la
    etiqueta: se aceptan minúsculas, guiones y espacios. No se corrigen confusiones (una O por un 0)
    a propósito: el alfabeto ya las excluye, así que una O tecleada es un error, no un código.
    """
    limpio = re.sub(r"[\s-]", "", tecleado).upper()
    return limpio if PATRON.fullmatch(limpio) else None


def presentar(codigo: str) -> str:
    """`XK7P2QH9` → `XK7P-2QH9`: dos grupos de cuatro se leen y se dictan sin perderse."""
    return f"{codigo[:4]}-{codigo[4:]}"


def url_de(codigo: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/a/{codigo}"


def etiqueta_svg(*, codigo: str, nombre: str, base_url: str) -> bytes:
    """Etiqueta imprimible: QR, código corto debajo y nombre del equipo (sección 6.3).

    - Corrección de errores nivel Q (hasta un 25 % de la imagen dañada): en planta las etiquetas se
      ensucian, se rayan y les cae aceite.
    - Margen blanco de 4 módulos, el mínimo del estándar para que el lector encuentre el código.
    - Vectorial: imprime nítido a 3 × 3 cm o a cualquier tamaño.

    El nombre del equipo va escapado: lo escribe un usuario y acaba dentro de un documento XML que
    alguien abrirá en el navegador.
    """
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4, box_size=10)
    qr.add_data(url_de(codigo, base_url))
    qr.make(fit=True)
    imagen = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    imagen.save(buffer)
    svg_qr = buffer.getvalue().decode()

    # El SVG del QR mide (módulos + 2·margen) unidades de lado, en milímetros. Se incrusta tal cual
    # dentro de un SVG mayor que añade el texto debajo, con las mismas unidades.
    lado = (qr.modules_count + 2 * 4) if qr.modules_count else 0
    alto_texto = 14
    # El nombre se encoge para caber en el ancho de la etiqueta en lugar de salirse del dibujo. Una
    # letra de palo seco mide de media algo más de media eme de ancho; con 0,58 sobra margen.
    nombre_corto = nombre[:40]
    tamano_nombre = min(3.4, (lado - 4) / (0.58 * max(len(nombre_corto), 1)))
    interior = re.sub(r"^<\?xml[^>]*>\s*", "", svg_qr)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lado} {lado + alto_texto}"'
        f' width="{lado}mm" height="{lado + alto_texto}mm">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<svg x="0" y="0" width="{lado}" height="{lado}" viewBox="0 0 {lado} {lado}">'
        f"{_contenido(interior)}</svg>"
        f'<text x="{lado / 2}" y="{lado + 5.5}" text-anchor="middle"'
        f' font-family="monospace" font-size="5" font-weight="700" fill="#000000"'
        f' letter-spacing="0.6">{presentar(codigo)}</text>'
        f'<text x="{lado / 2}" y="{lado + 11}" text-anchor="middle"'
        f' font-family="sans-serif" font-size="{tamano_nombre:.2f}" fill="#000000">'
        f"{escape(nombre_corto)}</text>"
        f"</svg>"
    ).encode()


def _contenido(svg: str) -> str:
    """Devuelve lo que hay dentro del `<svg>` raíz, para incrustarlo en otro."""
    inicio = svg.index(">", svg.index("<svg")) + 1
    fin = svg.rindex("</svg>")
    return svg[inicio:fin]
