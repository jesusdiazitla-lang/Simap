"""RNF-01 en las tablas de negocio de la fase 2, contra PostgreSQL real.

`docs/contexto/05-fase2-activos-y-campo.md` exige cerrar la «puerta de entrada» (sección 3) y cubrir
los dos huecos que RLS no tapa por sí sola (sección 8.5): las llaves foráneas, que PostgreSQL
comprueba ignorando RLS, y el olvido de activar RLS en una tabla nueva. Este archivo lo demuestra
contra la base de verdad.

Ninguna prueba se conecta como superusuario (sección 8.5): se siembra con `simap_owner`, al que
`FORCE ROW LEVEL SECURITY` también alcanza, fijando el tenant igual que lo haría la aplicación. Los
UUID se generan en Python porque un `INSERT ... RETURNING` sin tenant fijado fallaría: RLS aplica la
política de lectura a la fila devuelta (ver README, «Esquema de base de datos»).
"""

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import URL_APP, URL_DUENO, requiere_base
from tests.test_operador import URL_OPERADOR

T = TypeVar("T")

pytestmark = requiere_base


def _correr(corutina: Awaitable[T]) -> T:
    return asyncio.run(corutina)  # type: ignore[arg-type]


async def _fijar(conn: AsyncConnection, empresa_id: UUID | None) -> None:
    await conn.execute(
        text("SELECT set_config('app.empresa_id', :v, true)"),
        {"v": str(empresa_id) if empresa_id else ""},
    )


@dataclass(frozen=True)
class Planta:
    empresa_id: UUID
    usuario_id: UUID
    activo_id: UUID


async def _sembrar_planta(conn: AsyncConnection, nombre: str) -> Planta:
    planta = Planta(uuid4(), uuid4(), uuid4())
    await conn.execute(
        text("INSERT INTO empresas (id, nombre) VALUES (:i, :n)"),
        {"i": planta.empresa_id, "n": f"{nombre} {uuid4().hex[:8]}"},
    )
    await _fijar(conn, planta.empresa_id)
    await conn.execute(
        text(
            "INSERT INTO usuarios (id, empresa_id, nombre, correo, password_hash, rol)"
            " VALUES (:i, :e, 'Persona', :c, 'x', 'operario')"
        ),
        {"i": planta.usuario_id, "e": planta.empresa_id, "c": f"{uuid4().hex}@example.com"},
    )
    await conn.execute(
        text(
            "INSERT INTO activos (id, empresa_id, nombre, qr_code)"
            " VALUES (:i, :e, 'Compresor', :q)"
        ),
        {"i": planta.activo_id, "e": planta.empresa_id, "q": uuid4().hex[:8].upper()},
    )
    return planta


async def _sembrar() -> tuple[Planta, Planta]:
    motor = create_async_engine(URL_DUENO)
    try:
        async with motor.begin() as conn:
            a = await _sembrar_planta(conn, "Empresa A")
        async with motor.begin() as conn:
            b = await _sembrar_planta(conn, "Empresa B")
        return a, b
    finally:
        await motor.dispose()


@pytest.fixture(scope="module")
def plantas() -> tuple[Planta, Planta]:
    return _correr(_sembrar())


async def _como(url: str, empresa_id: UUID | None, sql: str, params: dict[str, object]) -> object:
    """Ejecuta una sentencia con el rol de la URL y el tenant dado. Devuelve filas o el error."""
    motor = create_async_engine(url)
    try:
        async with motor.begin() as conn:
            await _fijar(conn, empresa_id)
            resultado = await conn.execute(text(sql), params)
            return list(resultado.all()) if resultado.returns_rows else resultado.rowcount
    except DBAPIError as exc:
        return exc
    finally:
        await motor.dispose()


# --- Sección 3: la puerta de entrada ------------------------------------------


def test_rnf01_sin_tenant_cero_filas_en_conexion_reutilizada(
    plantas: tuple[Planta, Planta],
) -> None:
    """Una conexión del pool que ya fijó el tenant devuelve '' y no NULL (sección 8.5).

    Sin `NULLIF`, convertir esa cadena vacía a uuid lanza un error: el usuario vería un 500 en vez
    de cero filas. Para verlo hay que usar LA MISMA conexión en dos transacciones seguidas.
    """
    a, _ = plantas

    async def escenario() -> tuple[int, int]:
        motor = create_async_engine(URL_APP, pool_size=1, max_overflow=0)
        try:
            async with motor.connect() as conn:
                async with conn.begin():
                    await _fijar(conn, a.empresa_id)
                    con_tenant = (
                        await conn.execute(text("SELECT count(*) FROM activos"))
                    ).scalar_one()
                # Misma conexión, transacción nueva, sin fijar nada.
                async with conn.begin():
                    sin_tenant = (
                        await conn.execute(text("SELECT count(*) FROM activos"))
                    ).scalar_one()
            return int(con_tenant), int(sin_tenant)
        finally:
            await motor.dispose()

    con_tenant, sin_tenant = _correr(escenario())
    assert con_tenant >= 1
    assert sin_tenant == 0


def test_rnf01_tablas_con_empresa_id_tienen_rls_forzada() -> None:
    """Test de guardia (sección 4.4): toda tabla con `empresa_id` tiene RLS habilitada Y forzada.

    Convierte «no olvidar activar RLS» en una regla que falla sola cuando la fase 3 o la 4 creen
    una tabla nueva y alguien se despiste.
    """
    filas = _correr(
        _como(
            URL_DUENO,
            None,
            """
            SELECT c.relname
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND EXISTS (SELECT 1 FROM information_schema.columns col
                          WHERE col.table_schema = 'public' AND col.table_name = c.relname
                            AND col.column_name = 'empresa_id')
              AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
            """,
            {},
        )
    )
    assert filas == [], f"Tablas con empresa_id sin RLS forzada: {filas}"


# --- Aislamiento de lectura y escritura ---------------------------------------


def test_rnf01_listado_de_activos_aislado_por_empresa(plantas: tuple[Planta, Planta]) -> None:
    a, b = plantas
    filas = _correr(_como(URL_APP, a.empresa_id, "SELECT id FROM activos", {}))
    assert isinstance(filas, list)
    ids = {fila[0] for fila in filas}
    assert a.activo_id in ids
    assert b.activo_id not in ids


def test_rnf01_no_puede_crear_lectura_sobre_activo_ajeno(plantas: tuple[Planta, Planta]) -> None:
    """La referencia compuesta (sección 4.2) cierra lo que RLS no ve.

    La lectura se declara de la empresa A —así pasa la política, que solo mira `empresa_id`— pero
    apunta a un equipo de B. Con una llave foránea simple entraría, porque PostgreSQL comprueba las
    llaves foráneas ignorando RLS y el equipo de B existe.
    """
    a, b = plantas
    resultado = _correr(
        _como(
            URL_APP,
            a.empresa_id,
            "INSERT INTO lecturas_horometro"
            " (empresa_id, activo_id, registrado_por, valor_horometro, cliente_id, capturado_en)"
            " VALUES (:e, :activo, :autor, 10, :c, now())",
            {"e": a.empresa_id, "activo": b.activo_id, "autor": a.usuario_id, "c": uuid4()},
        )
    )
    assert isinstance(resultado, IntegrityError), resultado
    assert "fk_lecturas_horometro_activo_mismo_tenant" in str(resultado.orig)


def test_rnf01_no_puede_atribuir_una_alerta_a_alguien_de_otra_empresa(
    plantas: tuple[Planta, Planta],
) -> None:
    a, b = plantas
    resultado = _correr(
        _como(
            URL_APP,
            a.empresa_id,
            "INSERT INTO alertas"
            " (empresa_id, activo_id, reportado_por, sintoma, cliente_id, capturado_en)"
            " VALUES (:e, :activo, :autor, 'ruido', :c, now())",
            {"e": a.empresa_id, "activo": a.activo_id, "autor": b.usuario_id, "c": uuid4()},
        )
    )
    assert isinstance(resultado, IntegrityError), resultado
    assert "fk_alertas_autor_mismo_tenant" in str(resultado.orig)


def test_rnf01_no_puede_escribir_filas_declaradas_de_otra_empresa(
    plantas: tuple[Planta, Planta],
) -> None:
    """WITH CHECK explícito: con el tenant de A no se puede insertar una fila que diga ser de B."""
    a, b = plantas
    resultado = _correr(
        _como(
            URL_APP,
            a.empresa_id,
            "INSERT INTO componentes (id, empresa_id, nombre) VALUES (:i, :e, :n)",
            {"i": uuid4(), "e": b.empresa_id, "n": f"Intruso {uuid4().hex[:6]}"},
        )
    )
    assert isinstance(resultado, DBAPIError)
    assert "row-level security" in str(resultado.orig)


# --- Solo adición (sección 8.1) -------------------------------------------------


@pytest.mark.parametrize("tabla", ["componentes", "activos", "lecturas_horometro", "alertas"])
def test_la_aplicacion_no_puede_borrar_datos_de_negocio(
    plantas: tuple[Planta, Planta], tabla: str
) -> None:
    a, _ = plantas
    resultado = _correr(_como(URL_APP, a.empresa_id, f"DELETE FROM {tabla}", {}))
    assert isinstance(resultado, DBAPIError)
    assert "permission denied" in str(resultado.orig)


def test_una_lectura_no_se_puede_reescribir(plantas: tuple[Planta, Planta]) -> None:
    a, _ = plantas
    resultado = _correr(
        _como(URL_APP, a.empresa_id, "UPDATE lecturas_horometro SET valor_horometro = 0", {})
    )
    assert isinstance(resultado, DBAPIError)
    assert "permission denied" in str(resultado.orig)


def test_una_alerta_solo_puede_cambiar_de_estado(plantas: tuple[Planta, Planta]) -> None:
    a, _ = plantas
    resultado = _correr(_como(URL_APP, a.empresa_id, "UPDATE alertas SET nota = 'otra'", {}))
    assert isinstance(resultado, DBAPIError)
    assert "permission denied" in str(resultado.orig)


# --- El plano de control: contar sin leer -----------------------------------------


def test_el_operador_puede_contar_equipos_por_empresa(plantas: tuple[Planta, Planta]) -> None:
    a, b = plantas
    filas = _correr(
        _como(
            URL_OPERADOR,
            None,
            "SELECT empresa_id, count(*) FROM activos WHERE estado = 'activo'"
            " AND empresa_id IN (:a, :b) GROUP BY empresa_id",
            {"a": a.empresa_id, "b": b.empresa_id},
        )
    )
    assert isinstance(filas, list)
    assert dict((fila[0], fila[1]) for fila in filas) == {a.empresa_id: 1, b.empresa_id: 1}


@pytest.mark.parametrize("columna", ["nombre", "ubicacion", "qr_code", "horometro_actual"])
def test_el_operador_no_puede_leer_los_datos_de_un_equipo(columna: str) -> None:
    resultado = _correr(_como(URL_OPERADOR, None, f"SELECT {columna} FROM activos LIMIT 1", {}))
    assert isinstance(resultado, DBAPIError)
    assert "permission denied" in str(resultado.orig)


@pytest.mark.parametrize("tabla", ["componentes", "lecturas_horometro", "alertas"])
def test_el_operador_no_puede_leer_el_resto_de_tablas_de_negocio(tabla: str) -> None:
    resultado = _correr(_como(URL_OPERADOR, None, f"SELECT count(*) FROM {tabla}", {}))
    assert isinstance(resultado, DBAPIError)
    assert "permission denied" in str(resultado.orig)


def test_una_lectura_solo_cambia_su_resolucion(plantas: tuple[Planta, Planta]) -> None:
    """Revisión 0006: app_user puede escribir la resolución, pero no el valor."""
    a, _ = plantas
    permitido = _correr(
        _como(URL_APP, a.empresa_id, "UPDATE lecturas_horometro SET revisada_en = now()", {})
    )
    assert not isinstance(permitido, DBAPIError), permitido
    prohibido = _correr(
        _como(URL_APP, a.empresa_id, "UPDATE lecturas_horometro SET capturado_en = now()", {})
    )
    assert isinstance(prohibido, DBAPIError)
    assert "permission denied" in str(prohibido.orig)
