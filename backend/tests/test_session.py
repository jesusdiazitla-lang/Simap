"""Pruebas del motor y la fábrica de sesiones.

No abren ninguna conexión: `create_async_engine` es perezoso, así que se puede comprobar la
configuración del pool sin PostgreSQL delante.
"""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def _limpiar_caches() -> Iterator[None]:
    # El motor se cachea por proceso; sin esto un test veria el de otro.
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def test_el_motor_se_reutiliza_entre_llamadas() -> None:
    # Un motor nuevo por request abriria conexiones sin reutilizar el pool.
    assert get_engine() is get_engine()


def test_la_fabrica_de_sesiones_se_reutiliza() -> None:
    assert get_sessionmaker() is get_sessionmaker()


def test_el_motor_usa_el_driver_asincrono() -> None:
    assert get_engine().dialect.is_async is True


def test_el_pool_toma_su_tamano_de_la_configuracion() -> None:
    s = get_settings()
    assert get_engine().pool.size() == s.db_pool_size


def test_cada_sesion_es_una_instancia_distinta() -> None:
    fabrica = get_sessionmaker()
    assert fabrica() is not fabrica()


def test_rnf01_la_url_por_defecto_no_conecta_como_dueno_de_las_tablas() -> None:
    # Conectar como el propietario desactivaria RLS en silencio, porque las
    # politicas no se aplican al dueno salvo FORCE. Ver db/rls_policies.sql.
    assert "//app_user:" in get_settings().database_url
