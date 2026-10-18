"""Cinco empresas de demostración, una por sector, con su maquinaria y su historial de fallas.

QUÉ HACE
--------
1. **Vacía todos los datos de empresas** de la base local: empresas, personal, componentes, equipos,
   lecturas, alertas y órdenes (con su historial). No toca a los operadores de SIMAP (plano de
   control) ni la versión de Alembic.
2. Crea cinco empresas de sectores distintos —logística y transporte pesado, fabricación, biomasa,
   generación eléctrica y agrícola—, cada una con:
   - una persona por rol (administrador, supervisor, técnico de taller, gerente y operario), con
     contraseña generada aquí y mostrada **una sola vez**;
   - sus propias máquinas y su catálogo de componentes, propios del sector;
   - años de historia: lecturas de horómetro cada dos semanas y órdenes **cerradas** cuyas vidas
     salen de una **Weibull conocida** por componente. Cada componente de cada máquina falla según su
     propio proceso de renovación, así que `v_intervalos_entre_fallas` devuelve exactamente las vidas
     sorteadas. Todas las intervenciones son reemplazos, para que cada intervalo sea una vida
     completa;
   - actividad abierta para probar los flujos: dos alertas (una pendiente, una revisada) y tres
     órdenes abiertas, una en cada estado: Reportada, En taller y Reparada (por autorizar).

**Los datos son simulados**, y la tesis tiene que decirlo así.

SEGURIDAD
---------
Como `seed_demo.py`: se conecta como superusuario —es una herramienta de desarrollo, no una ruta de
la aplicación— y se niega a correr si la URL no apunta a `localhost`. Borra **todas** las empresas:
nunca se ejecuta contra una base con datos reales.

Uso (desde la raíz del repositorio, con la base levantada y migrada):

    python tools/seed_sectores.py              # vacía y crea las cinco empresas
    python tools/seed_sectores.py --semilla 7  # otra muestra aleatoria, reproducible
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Se reutilizan el hash de contraseñas y el generador de códigos QR del backend: las cuentas y los
# equipos sembrados funcionan como cualquier otro. La configuración del backend lee `backend/.env`
# desde la carpeta actual; se trabaja desde ahí.
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from app.core.security import generar_clave_temporal, hash_password  # noqa: E402
from app.models.componente import COMPONENTE_POR_IDENTIFICAR  # noqa: E402
from app.services.qr import generar_codigo  # noqa: E402

URL = "postgresql+asyncpg://simap:simap_dev@localhost:5432/simap"
ROLES = ("administrador", "supervisor", "tecnico_taller", "gerente", "operario")

#: De hija a madre. `operador_bitacora` guarda el `empresa_id` sin llave foránea: se limpia también,
#: para que la consola no muestre acciones sobre empresas que ya no existen.
TABLAS = (
    "orden_eventos",
    "ordenes_trabajo",
    "ordenes_contador",
    "alertas",
    "lecturas_horometro",
    "activos",
    "componentes",
    "usuarios",
    "intentos_login",
    "operador_bitacora",
    "empresas",
)


@dataclass(frozen=True)
class Maquina:
    nombre: str
    tipo: str
    marca: str
    modelo: str
    ubicacion: str
    criticidad: str
    #: Horas de uso que lleva hoy (el horómetro sembrado), aproximadas.
    horas: int


@dataclass(frozen=True)
class Empresa:
    nombre: str
    sector: str
    dominio: str
    #: Horas de operación por día: convierte horas acumuladas en fechas creíbles.
    horas_por_dia: float
    personas: tuple[str, ...]  # un nombre por rol, en el orden de ROLES
    #: Componente → (descripción, β, η en horas). β > 1 es desgaste.
    componentes: dict[str, tuple[str, float, float]]
    maquinas: tuple[Maquina, ...]
    #: Falla de ejemplo por componente, para las descripciones de las órdenes.
    sintomas: dict[str, str]


EMPRESAS: tuple[Empresa, ...] = (
    Empresa(
        nombre="Transportes Cordillera",
        sector="Logística y transporte pesado",
        dominio="cordillera.example.com",
        horas_por_dia=11,
        personas=("Ramón Peña", "Yesenia Rosario", "Félix Almonte", "Carolina Méndez", "Julio Batista"),
        componentes={
            "Motor diésel": ("Bloque, culata, pistones y distribución.", 2.4, 9000.0),
            "Caja de cambios": ("Transmisión manual o automatizada y su sincronización.", 2.0, 7500.0),
            "Embrague": ("Disco, plato de presión y collarín.", 1.8, 3200.0),
            "Frenos neumáticos": ("Compresor de aire, válvulas, cámaras y zapatas.", 1.5, 2100.0),
            "Turbocompresor": ("Turbina, compresor y sus cojinetes.", 2.6, 6000.0),
        },
        maquinas=(
            Maquina("Tractocamión Volvo FH 540 · TC-01", "Tractocamión", "Volvo", "FH 540", "Base Santo Domingo", "alta", 15400),
            Maquina("Tractocamión Scania R 450 · TC-02", "Tractocamión", "Scania", "R 450", "Base Santo Domingo", "alta", 12800),
            Maquina("Camión rígido Mercedes-Benz Actros 2645 · CR-03", "Camión rígido", "Mercedes-Benz", "Actros 2645", "Base Santiago", "media", 9900),
            Maquina("Tractocamión Kenworth T680 · TC-04", "Tractocamión", "Kenworth", "T680", "Base Santiago", "alta", 17200),
            Maquina("Volteo Freightliner 114SD · VO-05", "Camión volteo", "Freightliner", "114SD", "Patio Haina", "media", 8300),
        ),
        sintomas={
            "Motor diésel": "Pérdida de potencia en subida y humo negro por el escape",
            "Caja de cambios": "Las marchas altas raspan al engranar y salta la cuarta",
            "Embrague": "El embrague patina con carga completa",
            "Frenos neumáticos": "La presión de aire cae por debajo de 6 bar en ruta",
            "Turbocompresor": "Silbido fuerte y aceite en la admisión",
        },
    ),
    Empresa(
        nombre="Metalmecánica del Caribe",
        sector="Fabricación",
        dominio="metalcaribe.example.com",
        horas_por_dia=16,
        personas=("Andrés Polanco", "Marisol Taveras", "Wilson Reyes", "Patricia Jiménez", "Luis Durán"),
        componentes={
            "Rodamientos": ("Rodamientos de husillo, ejes y motores.", 2.2, 5200.0),
            "Husillo": ("Husillo principal y su conjunto de giro.", 3.0, 14000.0),
            "Sistema hidráulico": ("Bomba, cilindros, mangueras y válvulas hidráulicas.", 1.9, 4800.0),
            "Servomotor": ("Servomotores de ejes y su encoder.", 1.7, 9000.0),
            "Correas y cadenas": ("Transmisiones por correa o cadena.", 1.6, 3100.0),
        },
        maquinas=(
            Maquina("Prensa hidráulica Schuler 400 t · PH-01", "Prensa hidráulica", "Schuler", "MSD 400", "Nave de estampado", "alta", 31000),
            Maquina("Torno CNC Haas ST-20 · TC-02", "Torno CNC", "Haas", "ST-20", "Nave de mecanizado", "media", 24500),
            Maquina("Centro de mecanizado DMG Mori DMU 50 · CM-03", "Centro de mecanizado", "DMG Mori", "DMU 50", "Nave de mecanizado", "alta", 27800),
            Maquina("Compresor de tornillo Atlas Copco GA 75 · CO-04", "Compresor", "Atlas Copco", "GA 75", "Sala de compresores", "alta", 38500),
            Maquina("Robot de soldadura Fanuc ARC Mate 120 · RS-05", "Robot de soldadura", "Fanuc", "ARC Mate 120iD", "Línea de soldadura", "media", 21000),
        ),
        sintomas={
            "Rodamientos": "Ruido metálico y vibración creciente al subir de revoluciones",
            "Husillo": "Holgura radial en el husillo; las piezas salen fuera de tolerancia",
            "Sistema hidráulico": "Fuga de aceite en el cilindro principal y pérdida de presión",
            "Servomotor": "Alarma de sobrecorriente en el eje Z",
            "Correas y cadenas": "La correa patina y chilla al arrancar",
        },
    ),
    Empresa(
        nombre="BioEnergía del Cibao",
        sector="Biomasa",
        dominio="bioenergiacibao.example.com",
        horas_por_dia=20,
        personas=("Rafael Ventura", "Daniela Cruz", "Manuel Santana", "Elena Guzmán", "Pedro Núñez"),
        componentes={
            "Cuchillas": ("Cuchillas y contracuchillas de corte.", 1.4, 900.0),
            "Matriz y rodillos": ("Matriz de peletizado y rodillos de presión.", 2.5, 2600.0),
            "Rodamientos": ("Rodamientos de ejes, tambores y rodillos.", 2.1, 7000.0),
            "Ventilador de tiro inducido": ("Rodete, eje y acoplamiento del ventilador.", 2.3, 11000.0),
            "Reductor": ("Caja reductora de engranajes.", 2.7, 16000.0),
        },
        maquinas=(
            Maquina("Astilladora Bandit 1990XP · AS-01", "Astilladora", "Bandit", "1990XP", "Patio de recepción", "media", 26000),
            Maquina("Caldera de biomasa Vyncke 10 MW · CA-02", "Caldera", "Vyncke", "10 MWth", "Sala de calderas", "alta", 41000),
            Maquina("Secadero rotativo Swiss Combi · SR-03", "Secadero rotativo", "Swiss Combi", "ecoDry", "Nave de secado", "alta", 36500),
            Maquina("Peletizadora CPM 7932 · PE-04", "Peletizadora", "CPM", "7932-12", "Nave de peletizado", "alta", 33000),
            Maquina("Cinta transportadora de astilla · CT-05", "Cinta transportadora", "Continental", "CT-1200", "Patio de recepción", "baja", 39000),
        ),
        sintomas={
            "Cuchillas": "Astilla irregular y sobreconsumo del motor; filo gastado",
            "Matriz y rodillos": "Baja producción de pellet y pellet quebradizo",
            "Rodamientos": "Temperatura alta y ruido en el apoyo del tambor",
            "Ventilador de tiro inducido": "Vibración fuera de rango en el ventilador",
            "Reductor": "Ruido de engranajes y fuga por el retén de salida",
        },
    ),
    Empresa(
        nombre="Generadora Termoeste",
        sector="Generación eléctrica",
        dominio="termoeste.example.com",
        horas_por_dia=22,
        personas=("Héctor Valdez", "Ana Lucía Ortiz", "José Miguel Abreu", "Gabriela Fernández", "Samuel Pérez"),
        componentes={
            "Inyectores": ("Inyectores y bombas de inyección de combustible.", 2.0, 8000.0),
            "Cojinetes": ("Cojinetes de bancada y de biela.", 2.9, 24000.0),
            "Turbocompresor": ("Turbina, compresor y sus cojinetes.", 2.5, 16000.0),
            "Sistema de refrigeración": ("Bombas de agua, intercambiadores y termostatos.", 1.8, 12000.0),
            "Excitatriz": ("Excitatriz y regulador de tensión del alternador.", 1.6, 20000.0),
        },
        maquinas=(
            Maquina("Motogenerador Wärtsilä 20V34SF · MG-01", "Motogenerador", "Wärtsilä", "20V34SF", "Casa de máquinas", "alta", 52000),
            Maquina("Motogenerador Wärtsilä 20V34SF · MG-02", "Motogenerador", "Wärtsilä", "20V34SF", "Casa de máquinas", "alta", 48500),
            Maquina("Grupo electrógeno Caterpillar 3516B · GE-03", "Grupo electrógeno", "Caterpillar", "3516B", "Respaldo subestación", "media", 21000),
            Maquina("Turbina de vapor Siemens SST-300 · TV-04", "Turbina de vapor", "Siemens", "SST-300", "Ciclo combinado", "alta", 57000),
            Maquina("Bomba de alimentación de caldera KSB · BA-05", "Bomba", "KSB", "HGM 4/6", "Ciclo combinado", "alta", 44000),
        ),
        sintomas={
            "Inyectores": "Temperatura de escape desigual entre cilindros",
            "Cojinetes": "Presión de aceite baja y temperatura de bancada en alarma",
            "Turbocompresor": "Caída de la presión de sobrealimentación a plena carga",
            "Sistema de refrigeración": "Alta temperatura del agua de camisas",
            "Excitatriz": "Oscilación de tensión en el alternador y disparo por sobreexcitación",
        },
    ),
    Empresa(
        nombre="Agroindustrial Valle Verde",
        sector="Agrícola",
        dominio="valleverde.example.com",
        horas_por_dia=9,
        personas=("Francisco Mejía", "Rosa Hernández", "Domingo Castillo", "Isabel Rodríguez", "Miguel Ángel Sánchez"),
        componentes={
            "Motor diésel": ("Bloque, culata, pistones y distribución.", 2.4, 7000.0),
            "Transmisión": ("Caja de cambios y diferencial.", 2.1, 6000.0),
            "Sistema hidráulico": ("Bomba, cilindros, mangueras y válvulas hidráulicas.", 1.7, 2400.0),
            "Toma de fuerza (TDF)": ("Eje de toma de fuerza y su embrague.", 1.9, 3500.0),
            "Bomba de agua": ("Bomba de riego o de refrigeración y su sello mecánico.", 1.6, 4000.0),
        },
        maquinas=(
            Maquina("Tractor John Deere 6155M · TR-01", "Tractor", "John Deere", "6155M", "Finca La Esperanza", "alta", 9800),
            Maquina("Tractor New Holland T7.210 · TR-02", "Tractor", "New Holland", "T7.210", "Finca La Esperanza", "media", 7400),
            Maquina("Cosechadora Case IH Axial-Flow 7150 · CO-03", "Cosechadora", "Case IH", "Axial-Flow 7150", "Finca El Arrozal", "alta", 6100),
            Maquina("Pulverizadora Jacto Uniport 3030 · PU-04", "Pulverizadora autopropulsada", "Jacto", "Uniport 3030", "Finca El Arrozal", "media", 5200),
            Maquina("Estación de bombeo de riego Grundfos · BR-05", "Bomba de riego", "Grundfos", "NK 150-400", "Canal principal", "alta", 11500),
        ),
        sintomas={
            "Motor diésel": "Arranque difícil en frío y pérdida de potencia con el arado",
            "Transmisión": "Ruido en el diferencial y la marcha se sale bajo carga",
            "Sistema hidráulico": "El enganche de tres puntos no levanta el implemento",
            "Toma de fuerza (TDF)": "La TDF se desacopla sola con la segadora",
            "Bomba de agua": "Caudal bajo y goteo por el sello mecánico",
        },
    ),
)

#: Qué componentes tiene cada máquina: los primeros N del catálogo según el tipo, para que cada
#: máquina no lleve todos (un volteo no tiene el mismo plan que un tractocamión de larga distancia).
COMPONENTES_POR_MAQUINA = 3


@dataclass
class Falla:
    fecha: datetime
    activo: UUID
    componente: str
    horas: int


async def vaciar(conn: AsyncConnection) -> int:
    empresas = (await conn.execute(text("SELECT count(*) FROM empresas"))).scalar_one()
    for tabla in TABLAS:
        await conn.execute(text(f"DELETE FROM {tabla}"))
    return int(empresas)


async def insertar(conn: AsyncConnection, tabla: str, **valores: object) -> None:
    columnas = ", ".join(valores)
    marcas = ", ".join(f":{c}" for c in valores)
    await conn.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcas})"), valores)


async def evento(
    conn: AsyncConnection,
    empresa_id: UUID,
    orden_id: UUID,
    tipo: str,
    anterior: str | None,
    nuevo: str | None,
    usuario: UUID,
    rol: str,
    cuando: datetime,
    nota: str | None = None,
) -> None:
    await insertar(
        conn, "orden_eventos", id=uuid4(), empresa_id=empresa_id, orden_id=orden_id, tipo=tipo,
        estado_anterior=anterior, estado_nuevo=nuevo, usuario_id=usuario, rol_al_momento=rol,
        creado_en=cuando, nota=nota,
    )


async def crear(conn: AsyncConnection, e: Empresa, azar: random.Random, ahora: datetime) -> list[tuple[str, str, str, str]]:
    empresa_id = uuid4()
    await insertar(conn, "empresas", id=empresa_id, nombre=e.nombre,
                   fecha_registro=(ahora - timedelta(days=30)).date())

    personas: dict[str, UUID] = {}
    cuentas: list[tuple[str, str, str, str]] = []
    for rol, nombre in zip(ROLES, e.personas, strict=True):
        uid, clave, correo = uuid4(), generar_clave_temporal(), f"{rol.replace('_', '-')}@{e.dominio}"
        await insertar(conn, "usuarios", id=uid, empresa_id=empresa_id, nombre=nombre, correo=correo,
                       password_hash=hash_password(clave), rol=rol)
        personas[rol] = uid
        cuentas.append((rol, nombre, correo, clave))

    componentes: dict[str, UUID] = {}
    for nombre, (descripcion, _, _) in e.componentes.items():
        componentes[nombre] = uuid4()
        await insertar(conn, "componentes", id=componentes[nombre], empresa_id=empresa_id,
                       nombre=nombre, descripcion=descripcion)
    await insertar(conn, "componentes", id=uuid4(), empresa_id=empresa_id,
                   nombre=COMPONENTE_POR_IDENTIFICAR,
                   descripcion="Falla cuyo componente aún no se conoce; se corrige en la orden.")

    nombres_componentes = list(e.componentes)
    fallas: list[Falla] = []
    maquinas: list[tuple[UUID, Maquina, datetime, list[str]]] = []
    for i, m in enumerate(e.maquinas):
        activo_id = uuid4()
        # La máquina arrancó hace `horas / horas_por_dia` días, con algo de variación.
        dias = m.horas / e.horas_por_dia
        inicio = ahora - timedelta(days=dias)
        await insertar(
            conn, "activos", id=activo_id, empresa_id=empresa_id, nombre=m.nombre, tipo=m.tipo,
            ubicacion=m.ubicacion, criticidad=m.criticidad, qr_code=generar_codigo(),
            horometro_actual=m.horas, horometro_actualizado_en=ahora - timedelta(hours=azar.randint(2, 30)),
            marca=m.marca, modelo=m.modelo, numero_serie=f"{m.marca[:3].upper()}-{azar.randint(100000, 999999)}",
            fecha_instalacion=inicio.date(), creado_en=ahora - timedelta(days=30),
        )
        # Cada máquina lleva tres componentes del catálogo, rotando para que todos aparezcan.
        suyos = [nombres_componentes[(i + k) % len(nombres_componentes)] for k in range(COMPONENTES_POR_MAQUINA)]
        maquinas.append((activo_id, m, inicio, suyos))
        for componente in suyos:
            _, beta, eta = e.componentes[componente]
            # Proceso de renovación: cada reemplazo deja un componente nuevo, cuya vida es otra
            # muestra de la misma Weibull. Se para antes del horómetro de hoy.
            horas = 0
            while True:
                vida = max(24, round(azar.weibullvariate(eta, beta)))
                if horas + vida >= m.horas - 50:
                    break
                horas += vida
                fecha = inicio + timedelta(days=horas / e.horas_por_dia)
                fallas.append(Falla(fecha, activo_id, componente, horas))

        # Lecturas del operario cada dos semanas, más la de hoy.
        dia = 0.0
        while dia < dias:
            cuando = inicio + timedelta(days=dia)
            await insertar(conn, "lecturas_horometro", id=uuid4(), empresa_id=empresa_id,
                           activo_id=activo_id, registrado_por=personas["operario"],
                           valor_horometro=round(dia * e.horas_por_dia), cliente_id=uuid4(),
                           capturado_en=cuando, fecha=cuando)
            dia += 14
        await insertar(conn, "lecturas_horometro", id=uuid4(), empresa_id=empresa_id,
                       activo_id=activo_id, registrado_por=personas["operario"],
                       valor_horometro=m.horas, cliente_id=uuid4(),
                       capturado_en=ahora - timedelta(hours=2), fecha=ahora - timedelta(hours=2))

    numero = 0
    for f in sorted(fallas, key=lambda x: x.fecha):
        numero += 1
        orden_id = uuid4()
        taller = f.fecha + timedelta(hours=azar.uniform(0.5, 6))
        reparada = taller + timedelta(hours=azar.uniform(2, 30))
        salida = reparada + timedelta(hours=azar.uniform(0.5, 8))
        await insertar(
            conn, "ordenes_trabajo", id=orden_id, empresa_id=empresa_id, numero=numero, cliente_id=uuid4(),
            activo_id=f.activo, componente_id=componentes[f.componente],
            reportado_por=personas["supervisor"], reparado_por=personas["tecnico_taller"],
            autorizado_por=personas["supervisor"], horometro_en_falla=f.horas,
            horas_acumuladas_en_falla=f.horas, descripcion=f"{e.sintomas[f.componente]} (dato simulado).",
            estado="cerrada", trabajo_realizado=f"Reemplazo de {f.componente.lower()} por uno nuevo.",
            tipo_intervencion="reemplazo", requiere_revision=False, fecha_falla=f.fecha, reportada_en=f.fecha,
            en_taller_en=taller, reparada_en=reparada, fecha_salida_taller=salida,
            tiempo_fuera_servicio_min=round((salida - f.fecha).total_seconds() / 60),
        )
        for tipo, anterior, nuevo, quien, cuando in (
            ("creada", None, "reportada", "supervisor", f.fecha),
            ("transicion", "reportada", "en_taller", "tecnico_taller", taller),
            ("transicion", "en_taller", "reparada", "tecnico_taller", reparada),
            ("transicion", "reparada", "cerrada", "supervisor", salida),
        ):
            await evento(conn, empresa_id, orden_id, tipo, anterior, nuevo, personas[quien], quien, cuando)

    # Fecha de la última falla de cada equipo.
    for activo_id, _, _, _ in maquinas:
        ultimas = [f.fecha for f in fallas if f.activo == activo_id]
        if ultimas:
            await conn.execute(text("UPDATE activos SET fecha_ultima_falla = :d WHERE id = :i"),
                               {"d": max(ultimas).date(), "i": activo_id})

    # --- Actividad abierta, para probar los flujos -----------------------------------------
    (a0, m0, _, c0), (a1, m1, _, c1), (a2, m2, _, c2), (a3, _, _, _) = maquinas[:4]
    await insertar(conn, "alertas", id=uuid4(), empresa_id=empresa_id, activo_id=a3,
                   reportado_por=personas["operario"], sintoma="vibracion",
                   nota="Vibra más de lo normal al arrancar.", estado="pendiente", cliente_id=uuid4(),
                   capturado_en=ahora - timedelta(hours=3), fecha=ahora - timedelta(hours=3))
    await insertar(conn, "alertas", id=uuid4(), empresa_id=empresa_id, activo_id=a1,
                   reportado_por=personas["operario"], sintoma="calor",
                   nota="Huele a caliente cerca del motor.", estado="revisada", cliente_id=uuid4(),
                   capturado_en=ahora - timedelta(days=1), fecha=ahora - timedelta(days=1),
                   revisada_por=personas["supervisor"], revisada_en=ahora - timedelta(hours=20))

    abiertas = (
        (a0, m0, c0[0], "reportada", 4),
        (a1, m1, c1[1], "en_taller", 26),
        (a2, m2, c2[2], "reparada", 50),
    )
    for activo_id, m, componente, estado, horas_atras in abiertas:
        numero += 1
        orden_id = uuid4()
        fecha = ahora - timedelta(hours=horas_atras)
        taller = fecha + timedelta(hours=2) if estado != "reportada" else None
        reparada = taller + timedelta(hours=12) if estado == "reparada" and taller else None
        await insertar(
            conn, "ordenes_trabajo", id=orden_id, empresa_id=empresa_id, numero=numero, cliente_id=uuid4(),
            activo_id=activo_id, componente_id=componentes[componente],
            reportado_por=personas["supervisor"],
            reparado_por=personas["tecnico_taller"] if reparada else None,
            horometro_en_falla=m.horas, horas_acumuladas_en_falla=m.horas,
            descripcion=e.sintomas[componente], estado=estado,
            trabajo_realizado=f"Reemplazo de {componente.lower()} por uno nuevo." if reparada else None,
            tipo_intervencion="reemplazo" if reparada else None, requiere_revision=False,
            fecha_falla=fecha, reportada_en=fecha, en_taller_en=taller, reparada_en=reparada,
        )
        await evento(conn, empresa_id, orden_id, "creada", None, "reportada", personas["supervisor"], "supervisor", fecha)
        if taller:
            await evento(conn, empresa_id, orden_id, "transicion", "reportada", "en_taller",
                         personas["tecnico_taller"], "tecnico_taller", taller)
        if reparada:
            await evento(conn, empresa_id, orden_id, "transicion", "en_taller", "reparada",
                         personas["tecnico_taller"], "tecnico_taller", reparada)

    await insertar(conn, "ordenes_contador", empresa_id=empresa_id, ultimo=numero)
    print(f"  {e.nombre:<28} {e.sector:<32} {len(e.maquinas)} equipos, {len(fallas)} órdenes cerradas, 3 abiertas")
    return cuentas


async def principal(semilla: int) -> int:
    if "localhost" not in URL and "127.0.0.1" not in URL:
        print("La URL no apunta a localhost. Abortando por seguridad.", file=sys.stderr)
        return 1
    azar = random.Random(semilla)
    ahora = datetime.now(UTC)
    motor = create_async_engine(URL)
    todas: list[tuple[Empresa, list[tuple[str, str, str, str]]]] = []
    try:
        async with motor.begin() as conn:
            borradas = await vaciar(conn)
            print(f"Borradas {borradas} empresas con todos sus datos.\n")
            for e in EMPRESAS:
                todas.append((e, await crear(conn, e, azar, ahora)))
    finally:
        await motor.dispose()

    print(f"\nDatos SIMULADOS, semilla {semilla}. Las contraseñas no se guardan en ningún sitio; cópialas ahora.")
    for e, cuentas in todas:
        print(f"\n## {e.nombre} — {e.sector}")
        for rol, nombre, correo, clave in cuentas:
            print(f"  {rol:<15} {nombre:<22} {correo:<42} {clave}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--semilla", type=int, default=2026, help="Semilla del sorteo (reproducible).")
    args = parser.parse_args()
    return asyncio.run(principal(args.semilla))


if __name__ == "__main__":
    raise SystemExit(main())
