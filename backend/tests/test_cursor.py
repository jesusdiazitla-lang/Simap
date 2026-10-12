"""Cursor de paginación opaco (sección 9.1)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.cursor import Cursor, CursorInvalido


def test_ida_y_vuelta_conserva_valor_e_id() -> None:
    original = Cursor("Compresor ñ", uuid4())
    assert Cursor.decodificar(original.codificar()) == original


def test_cursor_de_instante() -> None:
    instante = datetime(2026, 10, 6, 14, 3, tzinfo=UTC)
    cursor = Cursor.decodificar(Cursor.de_instante(instante, uuid4()).codificar())
    assert cursor.instante() == instante


@pytest.mark.parametrize("basura", ["", "no-base64-!!", "e30", "eyJ2IjogMX0"])
def test_un_cursor_ilegible_se_rechaza(basura: str) -> None:
    with pytest.raises(CursorInvalido):
        Cursor.decodificar(basura)


def test_un_valor_que_no_es_fecha_se_rechaza_al_pedir_el_instante() -> None:
    with pytest.raises(CursorInvalido):
        Cursor("no es una fecha", uuid4()).instante()


def test_un_instante_sin_zona_se_rechaza() -> None:
    # Las columnas son timestamptz: compararlas con un instante sin zona es un error de la base.
    with pytest.raises(CursorInvalido):
        Cursor("2026-10-06T14:03:00", uuid4()).instante()


def test_un_valor_con_caracter_nulo_se_rechaza() -> None:
    with pytest.raises(CursorInvalido):
        Cursor.decodificar(Cursor("Compresor\x00", uuid4()).codificar())
