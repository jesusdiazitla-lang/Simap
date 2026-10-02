"""Pruebas del alta administrativa de empresas (`python -m app.cli crear-empresa`, RF-01).

Desde que SIMAP se cobra por equipo, el alta de una empresa no es autoservicio: no existe ruta HTTP
y la única forma de crear un tenant es este comando, que ejecuta quien opera el sistema. Por eso las
reglas que antes protegían el endpoint (correo válido, contraseña mínima, correo único) tienen que
seguir vivas aquí; si se relajaran, la regla real del sistema pasaría a ser la más laxa de las dos.

Exigen PostgreSQL migrado, porque el comando no tiene sentido sin base: lo que se comprueba es que
las filas se crean de verdad y con el rol correcto.
"""

import io
import sys
from uuid import uuid4

import pytest

from app import cli
from tests.conftest import dar_de_alta, requiere_base

pytestmark = requiere_base

PASSWORD = "contrasena-larga-de-prueba"


def _correo() -> str:
    return f"{uuid4().hex}@example.com"


def test_rf01_el_alta_crea_la_empresa_y_su_administrador(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    correo = _correo()
    assert dar_de_alta(monkeypatch, correo=correo, password=PASSWORD) == 0
    salida = capsys.readouterr().out
    # El comando tiene que devolver los identificadores: quien opera SIMAP los necesita para
    # comprobar el alta contra la base sin tener que buscarlos a mano.
    assert "empresa_id:" in salida
    assert "usuario_id:" in salida
    assert correo in salida


def test_el_correo_duplicado_falla_sin_crear_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    correo = _correo()
    assert dar_de_alta(monkeypatch, correo=correo, password=PASSWORD) == 0
    assert dar_de_alta(monkeypatch, correo=correo, password=PASSWORD) == cli.SALIDA_ERROR_DE_USO


def test_se_rechaza_una_contrasena_demasiado_corta(monkeypatch: pytest.MonkeyPatch) -> None:
    assert dar_de_alta(monkeypatch, correo=_correo(), password="corta") == cli.SALIDA_ERROR_DE_USO


def test_se_rechaza_un_correo_malformado(monkeypatch: pytest.MonkeyPatch) -> None:
    salida = dar_de_alta(monkeypatch, correo="no-es-un-correo", password=PASSWORD)
    assert salida == cli.SALIDA_ERROR_DE_USO


def test_se_rechaza_un_nombre_de_empresa_vacio(monkeypatch: pytest.MonkeyPatch) -> None:
    salida = dar_de_alta(monkeypatch, correo=_correo(), password=PASSWORD, empresa="")
    assert salida == cli.SALIDA_ERROR_DE_USO


def test_la_contrasena_no_se_acepta_como_argumento() -> None:
    """La contraseña no puede viajar en argv: queda en el historial y la ve cualquier proceso.

    Se comprueba sobre el parser, no ejecutando el comando: lo que se quiere fijar es que la opción
    no exista, y un `--password` añadido en el futuro haría fallar esta prueba antes de llegar a
    producción.
    """
    opciones = {
        cadena
        for accion in cli.construir_parser()._subparsers._group_actions  # type: ignore[union-attr]
        for sub in accion.choices.values()  # type: ignore[attr-defined]
        for a in sub._actions
        for cadena in a.option_strings
    }
    assert "--password" not in opciones
    assert "--password-stdin" in opciones


def test_sin_subcomando_el_comando_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    # argparse sale con codigo 2 cuando falta un argumento obligatorio. Se comprueba para que nadie
    # convierta el comando en algo que "no hace nada" cuando se invoca mal.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as salida:
        cli.main([])
    assert salida.value.code != 0
