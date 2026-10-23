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
    # Fase 3 y 4: `montar_planta(..., "X")` añade un sufijo de 6 hex; `sembrar("X")`, uno de 8.
    # `_` es un carácter exacto en LIKE: «A ______» no alcanza a una empresa real que empiece por A.
    "Planta A ______",  # tests/test_ordenes.py
    "Planta B ______",
    "A ______",  # tests/test_inventario.py, tests/test_prediccion.py
    "B ______",
    "Otra ______",  # tests/test_inventario.py
    "Flota ________",  # tests/test_prediccion_base.py
    "RNF-04 ________",  # tests/test_prediccion_base.py
]

#: Correo de los operadores que crean las pruebas.
OPERADORES_DE_PRUEBA = "op-%@simap.do"

#: Lo que las pruebas e2e crean DENTRO de la empresa de demostración (que no se borra): equipos y
#: personas por ejecución (fase 2: un compresor y un operario; fase 3: una prensa, una supervisora y
#: un técnico). Explícito, igual que lo de arriba.
EQUIPOS_E2E = ("Compresor E2E %", "Prensa E2E %", "Bomba E2E %")
#: Fase 4: el componente y los repuestos que crea `frontend/e2e/fase4.spec.ts` en la empresa Demo.
COMPONENTES_E2E = "Rodamiento E2E %"
REPUESTOS_E2E = "E2E-%"
PERSONAS_E2E = (
    "operario-e2e-%@example.com",
    "supervisor-e2e-%@example.com",
    "tecnico_taller-e2e-%@example.com",
)

#: Tablas de negocio, de hija a madre: el orden en que hay que vaciarlas para no chocar con las
#: llaves foráneas. Al añadir una tabla con empresa_id en una fase nueva, añadirla aquí.
TABLAS_DE_NEGOCIO = (
    "orden_eventos",
    "stock_movimientos",
    "orden_repuesto",
    "riesgos",
    "ordenes_trabajo",
    "ordenes_contador",
    "alertas_sistema",
    "modelos_historial",
    "modelos_componente",
    "reajustes_pendientes",
    "activo_componentes",
    "repuestos",
    "configuracion_empresa",
    "alertas",
    "lecturas_horometro",
    "activos",
    "componentes",
)


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

            # Las líneas de órdenes cerradas no se pueden borrar (trigger `orden_repuesto_inmutable`)
            # salvo en una transacción que fije `app.correccion`, el escape de la corrección administrativa.
            await conn.execute(text("SELECT set_config('app.correccion', 'on', true)"))
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
            # Lo que dejan las pruebas e2e dentro de la empresa de demostración. Las órdenes van
            # primero: apuntan a los equipos, a las alertas, a las lecturas y a las personas.
            params_e2e: dict[str, str] = {
                **{f"eq{i}": v for i, v in enumerate(EQUIPOS_E2E)},
                **{f"pe{i}": v for i, v in enumerate(PERSONAS_E2E)},
                "co": COMPONENTES_E2E,
                "re": REPUESTOS_E2E,
            }
            componentes = "SELECT id FROM componentes WHERE nombre LIKE :co"
            repuestos = "SELECT id FROM repuestos WHERE codigo LIKE :re"
            equipos = "SELECT id FROM activos WHERE " + " OR ".join(
                f"nombre LIKE :eq{i}" for i in range(len(EQUIPOS_E2E))
            )
            personas = "SELECT id FROM usuarios WHERE " + " OR ".join(
                f"correo LIKE :pe{i}" for i in range(len(PERSONAS_E2E))
            )
            ordenes = (
                f"SELECT id FROM ordenes_trabajo WHERE activo_id IN ({equipos})"
                f" OR reportado_por IN ({personas}) OR reparado_por IN ({personas})"
                f" OR autorizado_por IN ({personas})"
            )
            ordenes = f"{ordenes} OR componente_id IN ({componentes})"
            for sentencia in (
                f"DELETE FROM orden_eventos WHERE orden_id IN ({ordenes})"
                f" OR usuario_id IN ({personas})",
                # Fase 4: el libro y las líneas de esas órdenes y de los repuestos de prueba, y lo
                # que la predicción calculó para esos equipos y componentes.
                f"DELETE FROM stock_movimientos WHERE orden_id IN ({ordenes})"
                f" OR repuesto_id IN ({repuestos}) OR usuario_id IN ({personas})",
                f"DELETE FROM orden_repuesto WHERE orden_id IN ({ordenes})"
                f" OR repuesto_id IN ({repuestos}) OR registrado_por IN ({personas})",
                f"DELETE FROM riesgos WHERE activo_id IN ({equipos})"
                f" OR componente_id IN ({componentes})",
                f"DELETE FROM ordenes_trabajo WHERE id IN ({ordenes})",
                f"DELETE FROM alertas_sistema WHERE activo_id IN ({equipos})"
                f" OR componente_id IN ({componentes}) OR repuesto_id IN ({repuestos})"
                f" OR gestionada_por IN ({personas})",
                f"DELETE FROM activo_componentes WHERE activo_id IN ({equipos})"
                f" OR componente_id IN ({componentes})",
                f"DELETE FROM modelos_historial WHERE componente_id IN ({componentes})",
                f"DELETE FROM modelos_componente WHERE componente_id IN ({componentes})",
                f"DELETE FROM reajustes_pendientes WHERE componente_id IN ({componentes})",
                f"DELETE FROM repuestos WHERE id IN ({repuestos})",
                f"DELETE FROM alertas WHERE activo_id IN ({equipos})"
                f" OR reportado_por IN ({personas}) OR revisada_por IN ({personas})",
                f"DELETE FROM lecturas_horometro WHERE activo_id IN ({equipos})"
                f" OR registrado_por IN ({personas}) OR revisada_por IN ({personas})",
                f"DELETE FROM activos WHERE id IN ({equipos})",
                f"DELETE FROM componentes WHERE id IN ({componentes})",
                f"DELETE FROM usuarios WHERE id IN ({personas})",
            ):
                await conn.execute(text(sentencia), params_e2e)

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
