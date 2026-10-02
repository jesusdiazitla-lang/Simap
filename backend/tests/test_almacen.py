"""Pruebas del almacén efímero en memoria (rate limiting y revocación)."""

import asyncio
import time

import pytest

from app.core.almacen import AlmacenMemoria, AlmacenRedis


def _correr(corutina):  # type: ignore[no-untyped-def]
    return asyncio.run(corutina)


def test_incrementar_cuenta_desde_uno() -> None:
    a = AlmacenMemoria()
    assert _correr(a.incrementar("k", 60)) == 1
    assert _correr(a.incrementar("k", 60)) == 2


def test_la_ventana_no_se_renueva_al_incrementar(monkeypatch: pytest.MonkeyPatch) -> None:
    # Si cada intento reiniciara el TTL, un atacante constante mantendria la
    # ventana abierta para siempre y el limite nunca expiraria por si solo.
    a = AlmacenMemoria()
    reloj = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: reloj[0])

    _correr(a.incrementar("k", 10))
    reloj[0] += 9
    assert _correr(a.incrementar("k", 10)) == 2
    reloj[0] += 2  # pasan 11s desde el PRIMER intento
    assert _correr(a.incrementar("k", 10)) == 1, "la ventana debio caducar"


def test_una_marca_caduca_sola(monkeypatch: pytest.MonkeyPatch) -> None:
    a = AlmacenMemoria()
    reloj = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: reloj[0])

    _correr(a.marcar("token", 5))
    assert _correr(a.esta_marcada("token")) is True
    reloj[0] += 6
    assert _correr(a.esta_marcada("token")) is False


def test_olvidar_borra_el_contador() -> None:
    a = AlmacenMemoria()
    _correr(a.incrementar("k", 60))
    _correr(a.olvidar("k"))
    assert _correr(a.incrementar("k", 60)) == 1


def test_una_clave_inexistente_no_esta_marcada() -> None:
    assert _correr(AlmacenMemoria().esta_marcada("nada")) is False


def test_solo_redis_sirve_con_varias_instancias() -> None:
    # La bandera deja el limite comprobable desde un test en vez de descubrirlo
    # al escalar: con AlmacenMemoria cada proceso lleva su propio contador.
    assert AlmacenMemoria.apto_para_multiples_instancias is False
    assert AlmacenRedis.apto_para_multiples_instancias is True
