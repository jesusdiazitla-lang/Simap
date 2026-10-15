"""RNF-01 en las tablas de la fase 3, contra PostgreSQL real (06-fase3, secciones 7.8, 7.9 y 11.3).

Lo que más relaciones tiene del sistema es lo que más expone si el aislamiento falla: órdenes,
historial, contador y la vista que consumirá la fase 4.
"""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.base_ordenes import (
    Empresa,
    correr,
    fijar,
    fila_orden,
    insertar_ordenes,
    motor_app,
    sembrar,
)
from tests.conftest import URL_DUENO, requiere_base

pytestmark = requiere_base

TABLAS = ("ordenes_trabajo", "orden_eventos", "ordenes_contador", "v_intervalos_entre_fallas")


async def _contar(empresa_id: UUID, tabla: str) -> int:
    motor = motor_app()
    try:
        async with motor.connect() as conn, conn.begin():
            await fijar(conn, empresa_id)
            return int((await conn.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one())
    finally:
        await motor.dispose()


async def _sembrar_con_historial() -> tuple[Empresa, Empresa]:
    a, b = await sembrar("Empresa A", "Empresa B")
    fila = fila_orden(a, numero=1, horas=800)
    await insertar_ordenes(a, [fila])
    motor = create_async_engine(URL_DUENO)
    try:
        async with motor.begin() as conn:
            await fijar(conn, a.empresa_id)
            await conn.execute(
                text(
                    "INSERT INTO orden_eventos (id, empresa_id, orden_id, tipo, usuario_id,"
                    " rol_al_momento) VALUES (:i, :e, :o, 'creada', :u, 'supervisor')"
                ),
                {"i": uuid4(), "e": a.empresa_id, "o": fila["id"], "u": a.usuario_id},
            )
            await conn.execute(
                text("INSERT INTO ordenes_contador (empresa_id, ultimo) VALUES (:e, 1)"),
                {"e": a.empresa_id},
            )
    finally:
        await motor.dispose()
    return a, b


def test_rnf01_eventos_y_contador_aislados_por_empresa() -> None:
    """A ve lo suyo en las cuatro relaciones; B, cero filas en cada una (vista incluida)."""

    async def escenario() -> tuple[list[int], list[int]]:
        a, b = await _sembrar_con_historial()
        de_a = [await _contar(a.empresa_id, t) for t in TABLAS]
        de_b = [await _contar(b.empresa_id, t) for t in TABLAS]
        return de_a, de_b

    de_a, de_b = correr(escenario())
    assert all(n >= 1 for n in de_a), de_a
    assert de_b == [0, 0, 0, 0]


def test_rnf01_sin_tenant_cero_filas_en_conexion_reutilizada() -> None:
    """Tras una transacción que fijó el tenant, la siguiente en la misma conexión sin fijarlo ve
    cero filas y no da error: `current_setting` devuelve '' y `app_empresa_id()` lo vuelve NULL."""

    async def escenario() -> list[int]:
        a, _ = await _sembrar_con_historial()
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                async with conn.begin():
                    await fijar(conn, a.empresa_id)
                    await conn.execute(text("SELECT count(*) FROM ordenes_trabajo"))
                async with conn.begin():
                    return [
                        int((await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one())
                        for t in TABLAS
                    ]
        finally:
            await motor.dispose()

    assert correr(escenario()) == [0, 0, 0, 0]


def test_rnf01_guardia_rls_forzada_y_vistas_security_invoker() -> None:
    """Las dos consultas de guardia (7.10) devuelven cero filas.

    Toda tabla con `empresa_id` tiene RLS habilitada y forzada, y toda vista del esquema público
    corre con los permisos de quien consulta: sin `security_invoker` saltaría RLS y devolvería las
    fallas de todas las empresas.
    """

    async def escenario() -> tuple[list[str], list[str]]:
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                sin_rls = await conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c"
                        " JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'empresa_id'"
                        " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                        " AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"
                    )
                )
                vistas = await conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c"
                        " JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'public' AND c.relkind = 'v'"
                        " AND NOT COALESCE(c.reloptions::text LIKE '%security_invoker=true%',"
                        " false)"
                    )
                )
                return [r[0] for r in sin_rls.all()], [r[0] for r in vistas.all()]
        finally:
            await motor.dispose()

    assert correr(escenario()) == ([], [])


def test_una_sola_politica_permisiva_sobre_ordenes_trabajo() -> None:
    """Las permisivas se combinan con OR: una política vieja viva ampliaría el acceso (7.8)."""

    async def escenario() -> list[str]:
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                filas = await conn.execute(
                    text(
                        "SELECT policyname FROM pg_policies"
                        " WHERE tablename = 'ordenes_trabajo' AND permissive = 'PERMISSIVE'"
                    )
                )
                return [r[0] for r in filas.all()]
        finally:
            await motor.dispose()

    assert correr(escenario()) == ["tenant_isolation_ordenes_trabajo"]


def test_el_historial_no_admite_politicas_de_cambio() -> None:
    """`orden_eventos` solo tiene políticas de lectura e inserción: sin una de UPDATE o DELETE, RLS
    los deniega aunque algún día se concediera el permiso por error. Dos cerrojos."""

    async def escenario() -> set[str]:
        motor = motor_app()
        try:
            async with motor.connect() as conn:
                filas = await conn.execute(
                    text("SELECT cmd FROM pg_policies WHERE tablename = 'orden_eventos'")
                )
                return {r[0] for r in filas.all()}
        finally:
            await motor.dispose()

    assert correr(escenario()) == {"SELECT", "INSERT"}
