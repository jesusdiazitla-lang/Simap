"""Código de equipo y etiqueta: lógica pura, sin base de datos (RF-05; sección 6)."""

import xml.etree.ElementTree as ET

from app.services import qr


def test_rf05_codigo_qr_unico_aleatorio_sin_ambiguos() -> None:
    codigos = {qr.generar_codigo() for _ in range(2000)}
    assert len(codigos) == 2000, "2000 códigos aleatorios no deberían repetirse"
    for codigo in codigos:
        assert len(codigo) == 8
        assert not set(codigo) & set("IO01"), codigo
        assert qr.PATRON.fullmatch(codigo)


def test_normalizar_acepta_lo_que_se_teclea_a_mano() -> None:
    assert qr.normalizar("xk7p-2qh9") == "XK7P2QH9"
    assert qr.normalizar("  XK7P 2QH9 ") == "XK7P2QH9"


def test_normalizar_rechaza_lo_que_no_puede_ser_un_codigo() -> None:
    for malo in ("XK7P2QH", "XK7P2QH99", "XK7O2QH9", "XK7P2QH1", "", "../etc/passwd"):
        assert qr.normalizar(malo) is None, malo


def test_presentar_en_dos_grupos() -> None:
    assert qr.presentar("XK7P2QH9") == "XK7P-2QH9"


def test_el_qr_solo_codifica_la_url_de_la_pantalla_del_equipo() -> None:
    assert qr.url_de("XK7P2QH9", "https://simap.example/") == "https://simap.example/a/XK7P2QH9"


def test_la_etiqueta_es_svg_valido_con_codigo_y_nombre_escapado() -> None:
    svg = qr.etiqueta_svg(codigo="XK7P2QH9", nombre="Bomba <&> 3", base_url="http://x")
    raiz = ET.fromstring(svg)  # noqa: S314 - lo genera el propio servidor
    textos = [t.text for t in raiz.iter("{http://www.w3.org/2000/svg}text")]
    assert textos == ["XK7P-2QH9", "Bomba <&> 3"]
    assert raiz.get("width", "").endswith("mm")
