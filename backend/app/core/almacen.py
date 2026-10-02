"""Almacén efímero con expiración: contadores de rate limiting y lista de tokens revocados.

POR QUÉ EXISTE
--------------
Dos necesidades de F1 comparten la misma forma —un valor que caduca solo—:

* **Rate limiting de `/auth/login`** (sección 6.2): contar intentos por correo y por IP dentro de
  una ventana de tiempo.
* **Revocación de refresh tokens** en `/auth/logout` (sección 4.4): un JWT es válido hasta que
  expira, así que cerrar sesión de verdad exige una lista de los revocados hasta su caducidad.

Ninguna de las dos pertenece a la base de datos relacional: son datos de vida corta y alta rotación
que ensuciarían el esquema y habría que purgar a mano.

POR QUÉ UNA INTERFAZ Y NO REDIS DIRECTAMENTE
--------------------------------------------
El backend debe seguir siendo sin estado (sección 7.1) para poder correr en varias instancias, y eso
exige Redis en producción. Pero atar el código a Redis obligaría a levantarlo para cualquier prueba.
Con esta interfaz, los tests usan la implementación en memoria y la aplicación usa Redis, sin que el
servicio de autenticación sepa cuál tiene delante.

`AlmacenMemoria` NO sirve en producción con más de una instancia: cada proceso tendría su propio
contador y su propia lista de revocados. `apto_para_multiples_instancias` lo deja comprobable desde
un test en lugar de ser una sorpresa al escalar.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from functools import lru_cache


class AlmacenEfimero(ABC):
    """Contadores y marcas con expiración automática."""

    #: False si el estado vive dentro del proceso y no se comparte entre instancias.
    apto_para_multiples_instancias: bool = False

    @abstractmethod
    async def incrementar(self, clave: str, ttl_segundos: int) -> int:
        """Suma uno a `clave` y devuelve el total. Fija el TTL en el primer incremento."""

    @abstractmethod
    async def marcar(self, clave: str, ttl_segundos: int) -> None:
        """Deja una marca que caduca sola (p. ej. «este token está revocado»)."""

    @abstractmethod
    async def esta_marcada(self, clave: str) -> bool:
        """True si la marca sigue vigente."""

    @abstractmethod
    async def olvidar(self, clave: str) -> None:
        """Borra la clave.

        Se usa al acertar la contraseña, para no penalizar al usuario legítimo.
        """


class AlmacenMemoria(AlmacenEfimero):
    """Implementación en memoria del proceso. Para tests y desarrollo de una sola instancia."""

    apto_para_multiples_instancias = False

    def __init__(self) -> None:
        # clave -> (valor, instante de expiracion)
        self._datos: dict[str, tuple[int, float]] = {}

    def _vigente(self, clave: str) -> tuple[int, float] | None:
        entrada = self._datos.get(clave)
        if entrada is None:
            return None
        if entrada[1] <= time.monotonic():
            # Purga perezosa: sin proceso de limpieza, una clave caducada
            # desaparece la primera vez que alguien la mira.
            del self._datos[clave]
            return None
        return entrada

    async def incrementar(self, clave: str, ttl_segundos: int) -> int:
        entrada = self._vigente(clave)
        if entrada is None:
            self._datos[clave] = (1, time.monotonic() + ttl_segundos)
            return 1
        valor, expira = entrada
        # El TTL no se renueva al incrementar: la ventana cuenta desde el primer
        # intento, no desde el ultimo, o un atacante constante la extenderia sin fin.
        self._datos[clave] = (valor + 1, expira)
        return valor + 1

    async def marcar(self, clave: str, ttl_segundos: int) -> None:
        self._datos[clave] = (1, time.monotonic() + ttl_segundos)

    async def esta_marcada(self, clave: str) -> bool:
        return self._vigente(clave) is not None

    async def olvidar(self, clave: str) -> None:
        self._datos.pop(clave, None)


class AlmacenRedis(AlmacenEfimero):
    """Implementación sobre Redis. La de producción: el estado se comparte entre instancias."""

    apto_para_multiples_instancias = True

    def __init__(self, url: str) -> None:
        # Import diferido: asi los tests que usan AlmacenMemoria no cargan redis.
        from redis.asyncio import from_url

        # redis-py no publica stubs, asi que mypy ve from_url como no tipada. El ignore va aqui,
        # en la unica linea que la llama, en vez de relajar la regla para todo el modulo.
        self._redis = from_url(url, decode_responses=True)  # type: ignore[no-untyped-call]

    async def incrementar(self, clave: str, ttl_segundos: int) -> int:
        # INCR y EXPIRE en una sola ida y vuelta. El EXPIRE con NX solo fija el
        # TTL si la clave aun no lo tiene, para que la ventana no se renueve.
        async with self._redis.pipeline(transaction=True) as tuberia:
            tuberia.incr(clave)
            tuberia.expire(clave, ttl_segundos, nx=True)
            resultado = await tuberia.execute()
        return int(resultado[0])

    async def marcar(self, clave: str, ttl_segundos: int) -> None:
        await self._redis.set(clave, "1", ex=ttl_segundos)

    async def esta_marcada(self, clave: str) -> bool:
        return bool(await self._redis.exists(clave))

    async def olvidar(self, clave: str) -> None:
        await self._redis.delete(clave)

    async def cerrar(self) -> None:
        await self._redis.aclose()


@lru_cache
def get_almacen() -> AlmacenEfimero:
    """Almacén configurado: Redis si hay URL, memoria si no.

    La memoria basta para tests y para un único proceso en desarrollo. En producción con más de una
    instancia hace falta Redis, o cada proceso llevaría su propio contador de intentos y su propia
    lista de revocados —y un atacante repartiría los intentos entre instancias para esquivar el
    límite.
    """
    from app.core.config import get_settings

    url = get_settings().redis_url
    if not url:
        return AlmacenMemoria()
    return AlmacenRedis(url)
