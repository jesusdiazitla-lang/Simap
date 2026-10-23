"""Datos de demostración: la empresa «Demo» con una flota simulada (06-fase3 §10 y 07-fase4 §11).

QUÉ CREA
--------
- La empresa **Demo**, con una persona por rol (administrador, supervisor, técnico de taller,
  gerente y operario). Las contraseñas se generan aquí y se muestran **una sola vez**.
- Una flota de **14 bombas centrífugas** cuyo rodamiento principal falla según una Weibull de
  parámetros conocidos (**β = 2,5; η = 1000 h**) con reparación mínima: cada falla termina en
  **reparación** (la pieza conserva su edad) o en **reemplazo** (la pieza vuelve a cero), con
  probabilidad ½. Los equipos llevan tiempos de servicio distintos, así que las piezas tienen edades
  distintas. Cada falla es una orden **cerrada** con su historial completo, y cada equipo tiene sus
  lecturas de horómetro.
- **Una orden predictiva cerrada**: una alerta del sistema que se convirtió en un cambio planificado,
  con el rodamiento descontado del almacén. Para la predicción esa vida termina **censurada**.
- **Los dos casos de la demostración** (Definición de Hecho de la fase 4):
  - «Caso A»: una bomba con **tres reparaciones sin reemplazo** y dos alertas de campo recientes:
    componente viejo, **riesgo alto**.
  - «Caso B»: una bomba con la pieza **recién cambiada**: **riesgo bajo**.
- Dos componentes más del catálogo con vida nominal y sin fallas (el riesgo sale del previo), y uno
  sin edad declarada en un equipo, para ver el aviso «Sin edad».
- **Unos 15 repuestos** con su libro (stock inicial y consumos), algunos bajo el mínimo con su alerta
  de reorden, y alertas de campo recientes en un par de equipos.
- Al final ajusta los modelos y calcula el riesgo **de Demo** (como el job nocturno, pero solo esta
  empresa), así que la demostración queda lista sin esperar a la noche.

PARA QUÉ
--------
Probar los flujos con varias personas, y comprobar que el ajuste recupera los parámetros con que se
generaron los datos. El script imprime los verdaderos y los estimados.

**Los datos son simulados**, y la tesis tiene que decirlo así. Nunca se ejecuta contra una empresa
real: se identifica por el nombre exacto «Demo», y antes de crearla se borra entera la anterior.

SEGURIDAD
---------
Como `limpiar_datos_de_prueba.py`: se conecta como superusuario —es una herramienta de desarrollo,
no una ruta de la aplicación— y se niega a correr si la URL no apunta a `localhost`. El cálculo final
va por la conexión del job (`job_user`, sujeto a RLS), igual que en producción.

Uso (desde la raíz del repositorio, con la base levantada y migrada):

    python tools/seed_demo.py            # crea (o recrea) la empresa Demo
    python tools/seed_demo.py --borrar   # solo la borra
    python tools/seed_demo.py --semilla 7  # otra muestra aleatoria, reproducible
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Se reutiliza el backend: el hash de contraseñas (las cuentas de Demo entran como cualquier otra) y
# el cálculo de la fase 4. La configuración lee `backend/.env` desde la carpeta actual.
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from app.core.security import generar_clave_temporal, hash_password  # noqa: E402
from app.db.deps import fijar_tenant  # noqa: E402
from app.db.session import dispose_engine, get_sessionmaker_job  # noqa: E402
from app.services.prediccion.tareas import trabajar_empresa  # noqa: E402

URL = "postgresql+asyncpg://simap:simap_dev@localhost:5432/simap"
NOMBRE = "Demo"
DOMINIO = "demo.example.com"

#: El componente simulado y sus parámetros verdaderos (07-fase4, 11).
COMPONENTE = "Rodamiento principal"
BETA, ETA = 2.5, 1000.0
#: Componentes con vida nominal y sin fallas: su riesgo sale solo del conocimiento previo.
OTROS = {"Sello mecánico": 4000, "Acople flexible": 6000}
ROLES = ("administrador", "supervisor", "tecnico_taller", "gerente", "operario")
#: Horas de operación por día: convierten horas en fechas creíbles.
HORAS_POR_DIA = 16
#: La flota simulada: 12 bombas con horas de servicio distintas, más los dos casos.
FLOTA = 12
SERVICIO = (900, 3200)

#: Unos 15 repuestos: nombre, código, stock inicial, mínimo y costo (RD$). Los dos primeros son los
#: que consumen las órdenes de reemplazo: su stock final sale del libro.
REPUESTOS = (
    ("Rodamiento 6310-2RS", "RP-001", 14, 4, "2350.00"),
    ("Grasa de litio EP2 (cartucho)", "RP-002", 30, 10, "420.00"),
    ("Sello mecánico 45 mm", "RP-003", 3, 2, "7800.00"),
    ("Acople flexible L-100", "RP-004", 1, 2, "5600.00"),
    ("Empaque de carcasa", "RP-005", 12, 6, "650.00"),
    ("Impulsor de bronce 8\"", "RP-006", 1, 1, "18900.00"),
    ("Retén de eje 50x72", "RP-007", 2, 5, "310.00"),
    ("Tornillería de anclaje (juego)", "RP-008", 9, 4, "780.00"),
    ("Manómetro 0-10 bar", "RP-009", 4, 2, "1450.00"),
    ("Filtro de succión", "RP-010", 6, 3, "990.00"),
    ("Aceite ISO 68 (galón)", "RP-011", 8, 4, "1650.00"),
    ("Camisa de eje", "RP-012", 0, 1, "4200.00"),
    ("Chaveta 10x8", "RP-013", 20, 5, "95.00"),
    ("Junta tórica 120 mm", "RP-014", 15, 5, "140.00"),
    ("Motor eléctrico 15 HP (reserva)", "RP-015", 1, 1, "68500.00"),
)
CONSUMIDOS = ("RP-001", "RP-002")

#: De hija a madre, como en `limpiar_datos_de_prueba.py`.
TABLAS = (
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
    "usuarios",
)


@dataclass
class Evento:
    """Una intervención sobre el rodamiento: `horas` del equipo y cómo terminó."""

    horas: int
    tipo: str  # "reparacion", "reemplazo" o "predictiva"


@dataclass
class Equipo:
    nombre: str
    codigo: str
    servicio: int  # horas acumuladas hoy
    eventos: list[Evento] = field(default_factory=list)
    alertas_campo: int = 0


def proxima_falla(azar: random.Random, edad: float) -> float:
    """Reparación mínima: invierte Λ(a) = (a/η)^β a partir de la edad actual."""
    return ETA * ((edad / ETA) ** BETA + azar.expovariate(1.0)) ** (1.0 / BETA)


def simular(azar: random.Random, servicio: int, predictiva_en: int | None = None) -> list[Evento]:
    eventos: list[Evento] = []
    reloj, edad = 0.0, 0.0
    while True:
        siguiente = proxima_falla(azar, edad)
        cuando = reloj + (siguiente - edad)
        if predictiva_en is not None and cuando > predictiva_en > reloj:
            # El modelo pidió el cambio antes de la falla: la pieza se cambia sin haber fallado.
            eventos.append(Evento(predictiva_en, "predictiva"))
            reloj, edad = float(predictiva_en), 0.0
            predictiva_en = None
            continue
        if cuando >= servicio - 24:
            return eventos
        reloj, edad = cuando, siguiente
        if azar.random() < 0.5:
            eventos.append(Evento(round(reloj), "reemplazo"))
            edad = 0.0
        else:
            eventos.append(Evento(round(reloj), "reparacion"))


def flota(azar: random.Random) -> list[Equipo]:
    equipos = []
    for i in range(FLOTA):
        servicio = azar.randint(*SERVICIO)
        e = Equipo(f"Bomba centrífuga BC-{i + 1:02d}", f"DEMO{i:04d}", servicio)
        # La BC-05 tiene la orden predictiva cerrada, a dos tercios de su servicio.
        e.eventos = simular(azar, servicio, predictiva_en=round(servicio * 2 / 3) if i == 4 else None)
        equipos.append(e)
    equipos[2].alertas_campo = 1
    # Caso A: pieza original de 1800 h con tres reparaciones y dos alertas de campo recientes.
    caso_a = Equipo("Bomba centrífuga BC-13 (caso A: pieza vieja)", "DEMO0013", 1800, alertas_campo=2)
    caso_a.eventos = [Evento(690, "reparacion"), Evento(1140, "reparacion"), Evento(1520, "reparacion")]
    # Caso B: el rodamiento falló y se cambió hace 40 h.
    caso_b = Equipo("Bomba centrífuga BC-14 (caso B: pieza nueva)", "DEMO0014", 1900)
    caso_b.eventos = [Evento(1160, "reparacion"), Evento(1860, "reemplazo")]
    return [*equipos, caso_a, caso_b]


async def insertar(conn: AsyncConnection, tabla: str, **valores: object) -> None:
    columnas = ", ".join(valores)
    marcas = ", ".join(f":{c}" for c in valores)
    await conn.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcas})"), valores)


async def borrar(conn: AsyncConnection) -> int:
    ids = [r[0] for r in (await conn.execute(text("SELECT id FROM empresas WHERE nombre = :n"), {"n": NOMBRE})).all()]
    for empresa_id in ids:
        for tabla in TABLAS:
            await conn.execute(text(f"DELETE FROM {tabla} WHERE empresa_id = :e"), {"e": empresa_id})
        await conn.execute(text("DELETE FROM operador_bitacora WHERE empresa_id = :e"), {"e": empresa_id})
        await conn.execute(text("DELETE FROM empresas WHERE id = :e"), {"e": empresa_id})
    return len(ids)


async def crear(conn: AsyncConnection, semilla: int) -> tuple[UUID, list[tuple[str, str, str]], list[Equipo]]:
    azar = random.Random(semilla)
    ahora = datetime.now(UTC).replace(microsecond=0)
    empresa_id = uuid4()
    await insertar(conn, "empresas", id=empresa_id, nombre=NOMBRE)
    await insertar(conn, "configuracion_empresa", empresa_id=empresa_id)

    personas: dict[str, UUID] = {}
    claves: list[tuple[str, str, str]] = []
    for rol in ROLES:
        uid, clave, correo = uuid4(), generar_clave_temporal(), f"{rol.replace('_', '-')}@{DOMINIO}"
        await insertar(
            conn, "usuarios", id=uid, empresa_id=empresa_id, nombre=f"Demo {rol.replace('_', ' ').title()}",
            correo=correo, password_hash=hash_password(clave), rol=rol,
        )
        personas[rol] = uid
        claves.append((rol, correo, clave))
    sup, tec, adm = personas["supervisor"], personas["tecnico_taller"], personas["administrador"]

    componentes = {COMPONENTE: uuid4(), **{n: uuid4() for n in OTROS}}
    for nombre, cid in componentes.items():
        await insertar(conn, "componentes", id=cid, empresa_id=empresa_id, nombre=nombre,
                       vida_nominal_horas=int(ETA) if nombre == COMPONENTE else OTROS[nombre])
        await insertar(conn, "reajustes_pendientes", empresa_id=empresa_id, componente_id=cid)

    equipos = flota(azar)
    # Los equipos empezaron en fechas distintas y todos tienen su última lectura ayer.
    def fecha(e: Equipo, horas: float) -> datetime:
        return ahora - timedelta(days=1) - timedelta(days=(e.servicio - horas) / HORAS_POR_DIA)

    activos: dict[str, UUID] = {}
    for i, e in enumerate(equipos):
        aid = uuid4()
        activos[e.codigo] = aid
        await insertar(
            conn, "activos", id=aid, empresa_id=empresa_id, nombre=e.nombre, qr_code=e.codigo, tipo="Bomba centrífuga",
            ubicacion=f"Nave {i % 3 + 1}", criticidad="alta" if i % 4 == 0 else "media", marca="Grundfos",
            modelo="NK 80-250", horometro_actual=e.servicio, horometro_actualizado_en=fecha(e, e.servicio),
            fecha_instalacion=fecha(e, 0).date(), creado_en=fecha(e, 0),
        )
        # El rodamiento se instaló nuevo con el equipo; los otros dos componentes, en algunos equipos.
        await insertar(conn, "activo_componentes", empresa_id=empresa_id, activo_id=aid,
                       componente_id=componentes[COMPONENTE], horas_instalacion_inicial=0)
        if i < 4:
            await insertar(conn, "activo_componentes", empresa_id=empresa_id, activo_id=aid,
                           componente_id=componentes["Sello mecánico"], horas_instalacion_inicial=0)
        if i == 0:
            # Sin edad declarada: la pantalla debe decir «Sin edad», no un 0 %.
            await insertar(conn, "activo_componentes", empresa_id=empresa_id, activo_id=aid,
                           componente_id=componentes["Acople flexible"], horas_instalacion_inicial=None)
        # Lecturas cada ~2 semanas y la de ayer: de ahí salen las horas por día del equipo.
        marcas = sorted({0, *range(0, e.servicio, HORAS_POR_DIA * 14), e.servicio})
        for h in marcas:
            await insertar(conn, "lecturas_horometro", id=uuid4(), empresa_id=empresa_id, activo_id=aid,
                           registrado_por=personas["operario"], valor_horometro=h,
                           capturado_en=fecha(e, h), fecha=fecha(e, h))
        for k in range(e.alertas_campo):
            cuando = ahora - timedelta(days=2 + 3 * k)
            await insertar(conn, "alertas", id=uuid4(), empresa_id=empresa_id, activo_id=aid,
                           reportado_por=personas["operario"], sintoma=("vibracion", "calor")[k % 2],
                           nota=("Vibración fuerte en el lado acople", "La carcasa del rodamiento quema al tacto")[k % 2],
                           estado="pendiente" if k == 0 else "revisada", capturado_en=cuando, fecha=cuando,
                           revisada_por=None if k == 0 else sup, revisada_en=None if k == 0 else cuando + timedelta(hours=2))

    # Repuestos con su stock inicial en el libro, hace 400 días.
    inicio = ahora - timedelta(days=400)
    repuestos: dict[str, tuple[UUID, int, str]] = {}
    for nombre, codigo, stock, minimo, costo in REPUESTOS:
        rid = uuid4()
        repuestos[codigo] = (rid, stock, costo)
        await insertar(conn, "repuestos", id=rid, empresa_id=empresa_id, nombre=nombre, codigo=codigo,
                       stock_actual=stock, stock_minimo=minimo, costo_unitario=costo, creado_en=inicio)
        if stock > 0:
            await insertar(conn, "stock_movimientos", id=uuid4(), empresa_id=empresa_id, repuesto_id=rid,
                           tipo="inicial", delta=stock, stock_resultante=stock, costo_unitario=costo,
                           usuario_id=adm, creado_en=inicio)

    # Las órdenes, en orden de fecha. Cada reemplazo (y la predictiva) consume un rodamiento y un
    # cartucho de grasa, mientras haya: el stock final sale del libro, no se escribe a mano.
    intervenciones = sorted(
        ((fecha(e, ev.horas), e, ev) for e in equipos for ev in e.eventos), key=lambda x: x[0]
    )
    stock = {c: repuestos[c][1] for c in CONSUMIDOS}
    for numero, (cuando, e, ev) in enumerate(intervenciones, start=1):
        orden_id = uuid4()
        predictiva = ev.tipo == "predictiva"
        alerta_id = None
        if predictiva:
            alerta_id = uuid4()
            await insertar(conn, "alertas_sistema", id=alerta_id, empresa_id=empresa_id, tipo="riesgo",
                           activo_id=activos[e.codigo], componente_id=componentes[COMPONENTE], riesgo="0.2710",
                           umbral="0.2500", confianza="media", fuente="empresa", estado="resuelta",
                           creada_en=cuando - timedelta(days=2), gestionada_por=sup, gestionada_en=cuando)
        taller, reparada, salida = cuando + timedelta(hours=1), cuando + timedelta(hours=5), cuando + timedelta(hours=7)
        intervencion = "reparacion" if ev.tipo == "reparacion" else "reemplazo"
        await insertar(
            conn, "ordenes_trabajo", id=orden_id, empresa_id=empresa_id, numero=numero, activo_id=activos[e.codigo],
            componente_id=componentes[COMPONENTE], reportado_por=sup, reparado_por=tec,
            horometro_en_falla=ev.horas, horas_acumuladas_en_falla=ev.horas,
            descripcion=("Cambio planificado del rodamiento por riesgo (dato simulado)" if predictiva
                         else "Ruido y temperatura alta en el rodamiento (dato simulado)"),
            # Se inserta «reparada» y se cierra después de anotar los repuestos: el trigger
            # `orden_repuesto_inmutable` no deja tocar las líneas de una orden cerrada.
            estado="reparada",
            trabajo_realizado=("Se cambió el rodamiento y se engrasó." if intervencion == "reemplazo"
                               else "Se reengrasó y se ajustó el rodamiento; sigue la misma pieza."),
            tipo_intervencion=intervencion, fecha_falla=cuando, reportada_en=cuando, en_taller_en=taller,
            reparada_en=reparada, es_predictiva=predictiva, alerta_sistema_id=alerta_id,
        )
        for tipo, anterior, nuevo, quien, rol, momento in (
            ("creada", None, "reportada", sup, "supervisor", cuando),
            ("transicion", "reportada", "en_taller", tec, "tecnico_taller", taller),
            ("transicion", "en_taller", "reparada", tec, "tecnico_taller", reparada),
            ("transicion", "reparada", "cerrada", sup, "supervisor", salida),
        ):
            await insertar(conn, "orden_eventos", id=uuid4(), empresa_id=empresa_id, orden_id=orden_id, tipo=tipo,
                           estado_anterior=anterior, estado_nuevo=nuevo, usuario_id=quien, rol_al_momento=rol,
                           creado_en=momento)
        if intervencion == "reemplazo":
            for codigo in CONSUMIDOS:
                rid, _, costo = repuestos[codigo]
                if stock[codigo] < 1:
                    continue
                stock[codigo] -= 1
                await insertar(conn, "orden_repuesto", empresa_id=empresa_id, orden_id=orden_id, repuesto_id=rid,
                               cantidad=1, registrado_por=tec)
                await insertar(conn, "stock_movimientos", id=uuid4(), empresa_id=empresa_id, repuesto_id=rid,
                               tipo="consumo", delta=-1, stock_resultante=stock[codigo], costo_unitario=costo,
                               orden_id=orden_id, usuario_id=sup, creado_en=salida)
        await conn.execute(
            text("UPDATE ordenes_trabajo SET estado = 'cerrada', autorizado_por = :s, fecha_salida_taller = :f,"
                 " tiempo_fuera_servicio_min = 420 WHERE id = :i"),
            {"s": sup, "f": salida, "i": orden_id},
        )
    await insertar(conn, "ordenes_contador", empresa_id=empresa_id, ultimo=len(intervenciones))
    for codigo in CONSUMIDOS:
        await conn.execute(text("UPDATE repuestos SET stock_actual = :s WHERE id = :i"),
                           {"s": stock[codigo], "i": repuestos[codigo][0]})
    # Alerta de reorden de lo que quedó estrictamente bajo el mínimo (decisión 12).
    for nombre, codigo, _, minimo, _ in REPUESTOS:
        actual = stock.get(codigo, repuestos[codigo][1])
        if actual < minimo:
            await insertar(conn, "alertas_sistema", id=uuid4(), empresa_id=empresa_id, tipo="reorden",
                           repuesto_id=repuestos[codigo][0], stock_al_alertar=actual, stock_minimo_al_alertar=minimo,
                           creada_en=ahora - timedelta(days=1))
    for e in equipos:
        ultima = max((ev.horas for ev in e.eventos), default=None)
        if ultima is not None:
            await conn.execute(text("UPDATE activos SET fecha_ultima_falla = :f WHERE id = :i"),
                               {"f": fecha(e, ultima).date(), "i": activos[e.codigo]})
    return empresa_id, claves, equipos


async def calcular(empresa_id: UUID) -> None:
    """Lo que hace el job nocturno, solo para Demo: ajusta los modelos y calcula los riesgos."""
    try:
        async with get_sessionmaker_job()() as session, session.begin():
            await fijar_tenant(session, empresa_id)
            await trabajar_empresa(session, empresa_id)
    finally:
        await dispose_engine()


async def informe(conn: AsyncConnection, empresa_id: UUID, equipos: list[Equipo]) -> None:
    fallas = sum(1 for e in equipos for ev in e.eventos if ev.tipo != "predictiva")
    reemplazos = sum(1 for e in equipos for ev in e.eventos if ev.tipo == "reemplazo")
    print(f"\n{len(equipos)} equipos, {fallas} fallas cerradas ({reemplazos} con reemplazo) y 1 orden predictiva.")
    modelo = (
        await conn.execute(
            text("SELECT m.beta, m.eta, m.n_eventos FROM modelos_componente m JOIN componentes c"
                 " ON c.id = m.componente_id WHERE m.empresa_id = :e AND c.nombre = :n"),
            {"e": empresa_id, "n": COMPONENTE},
        )
    ).first()
    if modelo is not None:
        print(f"\n{COMPONENTE}: verdadero β = {BETA}, η = {ETA:,.0f} h; "
              f"ajustado β = {float(modelo.beta):.2f}, η = {float(modelo.eta):,.0f} h con {modelo.n_eventos} fallas.")
    filas = (
        await conn.execute(
            text("SELECT a.nombre, r.riesgo, r.edad_horas FROM riesgos r JOIN activos a ON a.id = r.activo_id"
                 " JOIN componentes c ON c.id = r.componente_id"
                 " WHERE r.empresa_id = :e AND c.nombre = :n AND r.riesgo IS NOT NULL ORDER BY r.riesgo DESC"),
            {"e": empresa_id, "n": COMPONENTE},
        )
    ).all()
    print("\nRiesgo del rodamiento en las próximas 50 h (los casos A y B deben quedar arriba y abajo):")
    for nombre, r, edad in filas:
        print(f"  {float(r) * 100:5.1f} %  pieza de {float(edad):6,.0f} h  {nombre}")


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
            if solo_borrar:
                return 0
            empresa_id, claves, equipos = await crear(conn, semilla)
        await calcular(empresa_id)
        async with motor.connect() as conn:
            print(f"\nEmpresa «{NOMBRE}» creada (datos SIMULADOS, semilla {semilla}).")
            await informe(conn, empresa_id, equipos)
    finally:
        await motor.dispose()
    print("\nCuentas (las contraseñas no se guardan en ningún sitio; cópialas ahora):")
    for rol, correo, clave in claves:
        print(f"  {rol:<15} {correo:<34} {clave}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--borrar", action="store_true", help="Solo borra la empresa Demo.")
    parser.add_argument("--semilla", type=int, default=2026, help="Semilla del sorteo (reproducible).")
    args = parser.parse_args()
    return asyncio.run(principal(args.borrar, args.semilla))


if __name__ == "__main__":
    raise SystemExit(main())
