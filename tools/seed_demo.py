"""Datos de demostración de la fase 3: la empresa «Demo» con fallas simuladas (06-fase3, sección 10).

QUÉ CREA
--------
- La empresa **Demo**, con una persona por rol (administrador, supervisor, técnico de taller,
  gerente y operario). Las contraseñas se generan aquí y se muestran **una sola vez**.
- Tres equipos y cuatro componentes.
- Doce órdenes de trabajo **cerradas**, cada una con su historial completo (creada, en taller,
  reparada, cerrada), cuyas horas de vida salen de una distribución de **Weibull conocida** por
  componente. Todas son reemplazos: cada intervalo entre dos fallas del mismo componente en el mismo
  equipo es una vida completa, así que `v_intervalos_entre_fallas` devuelve exactamente las vidas
  sorteadas.

PARA QUÉ
--------
Probar el flujo con varias personas, y alimentar la fase 4: que el ajuste recupere los parámetros
con que se generaron los datos es una prueba de que funciona. El script imprime esos parámetros.

**Los datos son simulados**, y la tesis tiene que decirlo así. Nunca se ejecuta contra una empresa
real: se identifica por el nombre exacto «Demo», y antes de crearla se borra entera la anterior.

SEGURIDAD
---------
Como `limpiar_datos_de_prueba.py`: se conecta como superusuario —es una herramienta de desarrollo,
no una ruta de la aplicación— y se niega a correr si la URL no apunta a `localhost`.

Uso (desde la raíz del repositorio, con la base levantada y migrada):

    python tools/seed_demo.py            # crea (o recrea) la empresa Demo
    python tools/seed_demo.py --borrar   # solo la borra
    python tools/seed_demo.py --semilla 7  # otra muestra aleatoria, reproducible
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Se reutiliza el hash de contraseñas del backend: las cuentas de Demo entran como cualquier otra.
# La configuración del backend lee `backend/.env` desde la carpeta actual; se trabaja desde ahí.
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from app.core.security import generar_clave_temporal, hash_password  # noqa: E402

URL = "postgresql+asyncpg://simap:simap_dev@localhost:5432/simap"
NOMBRE = "Demo"
DOMINIO = "demo.example.com"

#: Parámetros «verdaderos» de cada componente: forma β y escala η (horas). β > 1 es desgaste: cuanto
#: más vive un componente, más probable es que falle. La fase 4 debería recuperarlos.
WEIBULL: dict[str, tuple[float, float]] = {
    "Rodamientos": (2.2, 1800.0),
    "Correas y cadenas": (1.6, 1100.0),
    "Bomba de aceite": (2.8, 2600.0),
    "Sistema hidráulico": (1.9, 1500.0),
}
EQUIPOS = ("Prensa hidráulica P-200", "Compresor de tornillo C-75", "Torno CNC T-40")
ROLES = ("administrador", "supervisor", "tecnico_taller", "gerente", "operario")
#: Horas de operación por día: convierte horas acumuladas en fechas creíbles.
HORAS_POR_DIA = 16
#: Doce órdenes: cuatro componentes × tres fallas, repartidas por los tres equipos.
FALLAS_POR_COMPONENTE = 3

#: De hija a madre, como en `limpiar_datos_de_prueba.py`.
TABLAS = (
    "orden_eventos",
    "ordenes_trabajo",
    "ordenes_contador",
    "alertas",
    "lecturas_horometro",
    "activos",
    "componentes",
    "usuarios",
)


async def borrar(conn: AsyncConnection) -> int:
    ids = [r[0] for r in (await conn.execute(text("SELECT id FROM empresas WHERE nombre = :n"), {"n": NOMBRE})).all()]
    for empresa_id in ids:
        for tabla in TABLAS:
            await conn.execute(text(f"DELETE FROM {tabla} WHERE empresa_id = :e"), {"e": empresa_id})
        await conn.execute(text("DELETE FROM operador_bitacora WHERE empresa_id = :e"), {"e": empresa_id})
        await conn.execute(text("DELETE FROM empresas WHERE id = :e"), {"e": empresa_id})
    return len(ids)


async def crear(conn: AsyncConnection, semilla: int) -> None:
    azar = random.Random(semilla)
    empresa_id = uuid4()
    await conn.execute(text("INSERT INTO empresas (id, nombre) VALUES (:i, :n)"), {"i": empresa_id, "n": NOMBRE})

    personas: dict[str, UUID] = {}
    claves: list[tuple[str, str, str]] = []
    for rol in ROLES:
        uid, clave, correo = uuid4(), generar_clave_temporal(), f"{rol.replace('_', '-')}@{DOMINIO}"
        await conn.execute(
            text(
                "INSERT INTO usuarios (id, empresa_id, nombre, correo, password_hash, rol)"
                " VALUES (:i, :e, :n, :c, :h, :r)"
            ),
            {"i": uid, "e": empresa_id, "n": f"Demo {rol.replace('_', ' ').title()}", "c": correo, "h": hash_password(clave), "r": rol},
        )
        personas[rol] = uid
        claves.append((rol, correo, clave))

    componentes: dict[str, UUID] = {}
    for nombre in WEIBULL:
        componentes[nombre] = uuid4()
        await conn.execute(
            text("INSERT INTO componentes (id, empresa_id, nombre) VALUES (:i, :e, :n)"),
            {"i": componentes[nombre], "e": empresa_id, "n": nombre},
        )

    equipos: dict[str, UUID] = {}
    for i, nombre in enumerate(EQUIPOS):
        equipos[nombre] = uuid4()
        await conn.execute(
            text(
                "INSERT INTO activos (id, empresa_id, nombre, qr_code, ubicacion, criticidad)"
                " VALUES (:i, :e, :n, :q, :u, 'alta')"
            ),
            {"i": equipos[nombre], "e": empresa_id, "n": nombre, "q": f"DEMO{i:04d}", "u": f"Nave {i + 1}"},
        )

    # Las fallas: por componente, en un equipo fijo, una tras otra. Cada vida se sortea de su Weibull
    # y se suma a las horas acumuladas del equipo, que nunca retroceden.
    inicio = datetime.now(UTC) - timedelta(days=400)
    horas_equipo = {e: 0 for e in equipos}
    fallas: list[tuple[datetime, str, str, int]] = []
    for n, (componente, (beta, eta)) in enumerate(WEIBULL.items()):
        equipo = EQUIPOS[n % len(EQUIPOS)]
        for _ in range(FALLAS_POR_COMPONENTE):
            vida = max(1, round(azar.weibullvariate(eta, beta)))
            horas_equipo[equipo] += vida
            fecha = inicio + timedelta(days=horas_equipo[equipo] / HORAS_POR_DIA)
            fallas.append((fecha, equipo, componente, horas_equipo[equipo]))
    # Ninguna falla en el futuro: si las horas sorteadas pasan de hoy, se comprime la escala de fechas.
    ultima = max(f[0] for f in fallas)
    if ultima > datetime.now(UTC) - timedelta(days=2):
        factor = (datetime.now(UTC) - timedelta(days=2) - inicio) / (ultima - inicio)
        fallas = [(inicio + (f - inicio) * factor, e, c, h) for f, e, c, h in fallas]

    for numero, (fecha, equipo, componente, horas) in enumerate(sorted(fallas), start=1):
        orden_id = uuid4()
        taller, reparada, salida = fecha + timedelta(hours=1), fecha + timedelta(hours=5), fecha + timedelta(hours=7)
        await conn.execute(
            text(
                "INSERT INTO ordenes_trabajo (id, empresa_id, numero, activo_id, componente_id,"
                " reportado_por, reparado_por, autorizado_por, horometro_en_falla,"
                " horas_acumuladas_en_falla, descripcion, estado, trabajo_realizado,"
                " tipo_intervencion, fecha_falla, reportada_en, en_taller_en, reparada_en,"
                " fecha_salida_taller, tiempo_fuera_servicio_min)"
                " VALUES (:i, :e, :num, :a, :c, :sup, :tec, :sup, :h, :h, :d, 'cerrada', :t,"
                " 'reemplazo', :f, :f, :taller, :rep, :sal, 420)"
            ),
            {
                "i": orden_id, "e": empresa_id, "num": numero, "a": equipos[equipo], "c": componentes[componente],
                "sup": personas["supervisor"], "tec": personas["tecnico_taller"], "h": horas,
                "d": f"Falla de {componente.lower()} (dato simulado)", "t": f"Reemplazo de {componente.lower()}.",
                "f": fecha, "taller": taller, "rep": reparada, "sal": salida,
            },
        )
        for tipo, anterior, nuevo, quien, rol, cuando in (
            ("creada", None, "reportada", "supervisor", "supervisor", fecha),
            ("transicion", "reportada", "en_taller", "tecnico_taller", "tecnico_taller", taller),
            ("transicion", "en_taller", "reparada", "tecnico_taller", "tecnico_taller", reparada),
            ("transicion", "reparada", "cerrada", "supervisor", "supervisor", salida),
        ):
            await conn.execute(
                text(
                    "INSERT INTO orden_eventos (id, empresa_id, orden_id, tipo, estado_anterior,"
                    " estado_nuevo, usuario_id, rol_al_momento, creado_en)"
                    " VALUES (:i, :e, :o, :t, :a, :n, :u, :r, :c)"
                ),
                {"i": uuid4(), "e": empresa_id, "o": orden_id, "t": tipo, "a": anterior, "n": nuevo, "u": personas[quien], "r": rol, "c": cuando},
            )
    await conn.execute(
        text("INSERT INTO ordenes_contador (empresa_id, ultimo) VALUES (:e, :n)"), {"e": empresa_id, "n": len(fallas)}
    )
    for equipo, horas in horas_equipo.items():
        await conn.execute(
            text("UPDATE activos SET horometro_actual = :h, horometro_actualizado_en = now() WHERE id = :i"),
            {"h": horas, "i": equipos[equipo]},
        )

    print(f"\nEmpresa «{NOMBRE}» creada con {len(fallas)} órdenes cerradas (datos SIMULADOS, semilla {semilla}).")
    print("\nCuentas (las contraseñas no se guardan en ningún sitio; cópialas ahora):")
    for rol, correo, clave in claves:
        print(f"  {rol:<15} {correo:<34} {clave}")
    print("\nParámetros Weibull con que se generaron las vidas (la fase 4 debería recuperarlos):")
    for componente, (beta, eta) in WEIBULL.items():
        print(f"  {componente:<20} β = {beta}   η = {eta:,.0f} h")


async def principal(solo_borrar: bool, semilla: int) -> int:
    if "localhost" not in URL and "127.0.0.1" not in URL:
        print("La URL no apunta a localhost. Abortando por seguridad.", file=sys.stderr)
        return 1
    motor = create_async_engine(URL)
    try:
        async with motor.begin() as conn:
            borradas = await borrar(conn)
            if borradas:
                print(f"Borrada la empresa «{NOMBRE}» anterior.")
            if not solo_borrar:
                await crear(conn, semilla)
    finally:
        await motor.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--borrar", action="store_true", help="Solo borra la empresa Demo.")
    parser.add_argument("--semilla", type=int, default=2026, help="Semilla del sorteo (reproducible).")
    args = parser.parse_args()
    return asyncio.run(principal(args.borrar, args.semilla))


if __name__ == "__main__":
    raise SystemExit(main())
