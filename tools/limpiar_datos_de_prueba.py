"""Borra de la base de datos de DESARROLLO lo que dejan las pruebas automatizadas.

POR QUÉ EXISTE
--------------
La batería de pruebas de integración corre contra un PostgreSQL real —es lo que hace que las
pruebas de aislamiento valgan algo— y cada ejecución deja empresas, usuarios y operadores creados
con nombres generados al azar. Tras unas cuantas ejecuciones la consola del operador muestra
cientos de empresas basura y deja de servir para enseñar nada.

POR QUÉ NO ES UN COMANDO DE `app.cli`
--------------------------------------
`app.cli` es una herramienta de **producción**: la usa quien opera SIMAP en el servidor. Un comando
que borra filas por patrón de nombre no tiene por qué estar a un tecleo de distancia de una base de
datos con clientes reales. Vive aquí, en `tools/`, junto al resto del utillaje de desarrollo.

SEGURIDAD
---------
- Solo borra lo que coincide con los patrones **declarados explícitamente** más abajo. No infiere
  «lo que parezca de prueba»: borrar por corazonada es como se pierden datos de verdad.
- Sin `--ejecutar` no borra nada: enseña lo que haría y termina.
- Se niega a correr si la URL no apunta a `localhost`, para que un `.env` de producción mal
  cargado no se lleve por delante la base equivocada.

Uso:

    python tools/limpiar_datos_de_prueba.py              # solo muestra
    python tools/limpiar_datos_de_prueba.py --ejecutar   # borra
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

#: Superusuario: es el único rol que puede ver y borrar filas de todas las empresas a la vez.
#: Precisamente por eso esto es una herramienta de desarrollo y no una ruta de la aplicación.
URL = "postgresql+asyncpg://simap:simap_dev@localhost:5432/simap"

#: Nombres de empresa que crean las pruebas. Explícitos y exhaustivos, no heurísticos.
#: Si añades un nombre nuevo en una prueba, añádelo también aquí.
EMPRESAS_DE_PRUEBA = [
    "Empresa A %",  # tests/test_aislamiento_tenant.py
    "Empresa B %",
    "Intento %",  # tests/test_aislamiento_tenant.py, _puede_insertar_empresa
    "Metalúrgica Prueba",  # tests/conftest.py, dar_de_alta
    "Cliente %",  # tests/test_operador.py
    "Planta E2E %",  # frontend/e2e/consola-operador.spec.ts
    *[f"Planta {c}%" for c in "0123456789abcdef"],  # tests/test_operador.py, nombres hex
]

#: Correo de los operadores que crean las pruebas.
OPERADORES_DE_PRUEBA = "op-%@simap.do"

#: Lo que las pruebas e2e de la fase 2 crean DENTRO de la empresa de demostración (que no se borra):
#: un equipo y un operario por ejecución. Explícito, igual que lo de arriba.
EQUIPOS_E2E = "Compresor E2E %"
PERSONAS_E2E = "operario-e2e-%@example.com"

#: Tablas de negocio, de hija a madre: el orden en que hay que vaciarlas para no chocar con las
#: llaves foráneas. Al añadir una tabla con empresa_id en una fase nueva, añadirla aquí.
TABLAS_DE_NEGOCIO = ("alertas", "lecturas_horometro", "activos", "componentes")


async def limpiar(ejecutar: bool) -> int:
    if "localhost" not in URL and "127.0.0.1" not in URL:
        print("La URL no apunta a localhost. Abortando por seguridad.", file=sys.stderr)
        return 1

    motor = create_async_engine(URL)
    condicion = " OR ".join(f"nombre LIKE :p{i}" for i in range(len(EMPRESAS_DE_PRUEBA)))
    params: dict[str, str] = {f"p{i}": v for i, v in enumerate(EMPRESAS_DE_PRUEBA)}
    params["op"] = OPERADORES_DE_PRUEBA

    try:
        async with motor.begin() as conn:
            empresas = (
                await conn.execute(
                    text(f"SELECT count(*) FROM empresas WHERE {condicion}"), params
                )
            ).scalar_one()
            usuarios = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM usuarios WHERE empresa_id IN"
                        f" (SELECT id FROM empresas WHERE {condicion})"
                    ),
                    params,
                )
            ).scalar_one()
            operadores = (
                await conn.execute(
                    text("SELECT count(*) FROM operadores WHERE correo LIKE :op"), params
                )
            ).scalar_one()
            intentos = (
                await conn.execute(text("SELECT count(*) FROM intentos_login"))
            ).scalar_one()

            print(f"  empresas de prueba .......... {empresas}")
            print(f"  usuarios de esas empresas ... {usuarios}")
            print(f"  operadores de prueba ........ {operadores}")
            print(f"  filas de intentos_login ..... {intentos}")

            if not ejecutar:
                print("\nNada borrado. Repite con --ejecutar para hacerlo de verdad.")
                return 0

            # El orden importa: la bitácora tiene una clave foránea RESTRICT hacia `operadores`,
            # así que hay que vaciar sus asientos antes de poder borrar a quien los escribió.
            await conn.execute(
                text(
                    "DELETE FROM operador_bitacora WHERE operador_id IN"
                    " (SELECT id FROM operadores WHERE correo LIKE :op)"
                    f" OR empresa_id IN (SELECT id FROM empresas WHERE {condicion})"
                ),
                params,
            )
            await conn.execute(
                text("DELETE FROM operadores WHERE correo LIKE :op"), params
            )
            # Datos de negocio de las empresas de prueba, de las tablas hijas a las madres.
            for tabla in TABLAS_DE_NEGOCIO:
                await conn.execute(
                    text(
                        f"DELETE FROM {tabla} WHERE empresa_id IN"
                        f" (SELECT id FROM empresas WHERE {condicion})"
                    ),
                    params,
                )
            # Lo que dejan las pruebas e2e dentro de la empresa de demostración.
            params_e2e = {"eq": EQUIPOS_E2E, "pe": PERSONAS_E2E}
            for tabla in ("alertas", "lecturas_horometro"):
                await conn.execute(
                    text(
                        f"DELETE FROM {tabla} WHERE activo_id IN"
                        " (SELECT id FROM activos WHERE nombre LIKE :eq)"
                        " OR registrado_por IN (SELECT id FROM usuarios WHERE correo LIKE :pe)"
                        if tabla == "lecturas_horometro"
                        else f"DELETE FROM {tabla} WHERE activo_id IN"
                        " (SELECT id FROM activos WHERE nombre LIKE :eq)"
                        " OR reportado_por IN (SELECT id FROM usuarios WHERE correo LIKE :pe)"
                    ),
                    params_e2e,
                )
            await conn.execute(text("DELETE FROM activos WHERE nombre LIKE :eq"), params_e2e)
            await conn.execute(text("DELETE FROM usuarios WHERE correo LIKE :pe"), params_e2e)

            await conn.execute(
                text(
                    "DELETE FROM usuarios WHERE empresa_id IN"
                    f" (SELECT id FROM empresas WHERE {condicion})"
                ),
                params,
            )
            await conn.execute(text(f"DELETE FROM empresas WHERE {condicion}"), params)
            # `intentos_login` es enteramente registro de pruebas en desarrollo: no hay nada que
            # conservar y crece sin parar.
            await conn.execute(text("TRUNCATE intentos_login"))

            restantes = (await conn.execute(text("SELECT count(*) FROM empresas"))).scalar_one()
            print(f"\nHecho. Quedan {restantes} empresas.")
    finally:
        await motor.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ejecutar",
        action="store_true",
        help="Borra de verdad. Sin esta opcion solo muestra lo que haria.",
    )
    return asyncio.run(limpiar(parser.parse_args().ejecutar))


if __name__ == "__main__":
    raise SystemExit(main())
