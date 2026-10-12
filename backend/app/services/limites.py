"""Límite de peticiones: contraseñas (04-fase1-fundamentos.md, 6.2) y registro de campo (F2, 8.4).

POR QUÉ ES UN MÓDULO APARTE
---------------------------
Empezó dentro de `app.services.auth`, protegiendo solo `/auth/login`. Pero hay más puertas que
comparan una contraseña: el login de la consola del operador y el cambio de clave de cualquiera de
los dos planos. Una puerta sin límite es la que elige quien quiere adivinar claves, y la del
operador es justo la que más premio da.

El límite vive aquí para que las dos mitades del sistema lo compartan sin que el plano de control
tenga que importar el servicio del plano de datos. Lo que **no** comparten es el contador: cada
puerta pasa sus propias claves, de modo que golpear una no cierra la otra.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.almacen import AlmacenEfimero
from app.core.config import get_settings


class DemasiadosIntentos(Exception):
    """Se superó el límite de intentos en la ventana configurada."""

    def __init__(self, espera_segundos: int) -> None:
        super().__init__("Demasiados intentos")
        self.espera_segundos = espera_segundos


async def comprobar(
    almacen: AlmacenEfimero,
    claves: Sequence[str],
    *,
    maximo: int | None = None,
    ventana_segundos: int | None = None,
) -> None:
    """Cuenta un intento en cada clave y corta si alguna supera el máximo.

    Se cuenta ANTES de verificar la contraseña, no después de fallar: si solo contaran los fallos,
    el intento que acierta tras el bloqueo pasaría, y el límite no limitaría nada.

    Sin `maximo` ni `ventana_segundos` se aplican los del login. Las rutas de campo de la fase 2
    pasan los suyos: un operario en ronda registra muchas lecturas seguidas, y cinco por minuto lo
    dejaría fuera a media ronda.
    """
    s = get_settings()
    ventana = ventana_segundos if ventana_segundos is not None else s.login_attempt_window_seconds
    tope = maximo if maximo is not None else s.login_max_attempts
    for clave in claves:
        if await almacen.incrementar(clave, ventana) > tope:
            raise DemasiadosIntentos(ventana)


async def comprobar_login(almacen: AlmacenEfimero, *, clave_correo: str, clave_ip: str) -> None:
    """Límite de una puerta de login: por correo con el tope normal y por IP con el suyo.

    Tras un acierto solo se olvida `clave_correo` (ver `login_max_intentos_por_ip`).
    """
    await comprobar(almacen, [clave_correo])
    await comprobar(almacen, [clave_ip], maximo=get_settings().login_max_intentos_por_ip)


async def olvidar(almacen: AlmacenEfimero, claves: Sequence[str]) -> None:
    """Pone a cero los contadores tras un acierto, para no penalizar a quien solo se equivocó."""
    for clave in claves:
        await almacen.olvidar(clave)
