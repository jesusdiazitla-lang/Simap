"""Límite de intentos compartido por todo lo que verifica una contraseña (sección 6.2).

Son pruebas unitarias contra el almacén en memoria: lo que se comprueba es la aritmética de la
ventana y que cada puerta lleve su propio contador, no Redis.
"""

import asyncio

import pytest

from app.core.almacen import AlmacenMemoria
from app.core.config import get_settings
from app.services.limites import DemasiadosIntentos, comprobar, olvidar


def test_deja_pasar_hasta_el_maximo_y_corta_el_siguiente() -> None:
    almacen = AlmacenMemoria()
    maximo = get_settings().login_max_attempts

    async def escenario() -> None:
        for _ in range(maximo):
            await comprobar(almacen, ["puerta:a"])
        with pytest.raises(DemasiadosIntentos) as error:
            await comprobar(almacen, ["puerta:a"])
        assert error.value.espera_segundos == get_settings().login_attempt_window_seconds

    asyncio.run(escenario())


def test_basta_con_que_una_de_las_claves_se_pase() -> None:
    # Correo e IP se cuentan por separado: un ataque contra una cuenta desde muchas IP se corta por
    # el correo, y un barrido de muchas cuentas desde una IP se corta por la IP.
    almacen = AlmacenMemoria()
    maximo = get_settings().login_max_attempts

    async def escenario() -> None:
        for i in range(maximo):
            await comprobar(almacen, [f"correo:{i}", "ip:1.2.3.4"])
        with pytest.raises(DemasiadosIntentos):
            await comprobar(almacen, ["correo:otro", "ip:1.2.3.4"])

    asyncio.run(escenario())


def test_olvidar_reinicia_el_contador() -> None:
    almacen = AlmacenMemoria()
    maximo = get_settings().login_max_attempts

    async def escenario() -> None:
        for _ in range(maximo):
            await comprobar(almacen, ["puerta:a"])
        await olvidar(almacen, ["puerta:a"])
        for _ in range(maximo):
            await comprobar(almacen, ["puerta:a"])

    asyncio.run(escenario())
