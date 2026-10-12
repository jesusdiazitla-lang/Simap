"""RNF-01: aislamiento real entre empresas, contra un PostgreSQL de verdad.

Los demás tests usan una sesión falsa y comprueban el lado Python: que `get_db` mande fijar el
tenant con el valor del token. Esto NO demuestra que el aislamiento funcione, porque quien lo impone
es PostgreSQL. Este archivo es el que lo demuestra.

Exige una base levantada (`docker compose up -d db`). Si no la hay, los tests se saltan con un
motivo explícito en vez de fallar — pero saltarse no es aprobar: en CI la base debe estar presente,
o la cobertura de RNF-01 desaparece sin que nadie lo note.

El caso decisivo es `test_rnf01_ni_siquiera_el_dueno_de_las_tablas_ve_otras_empresas`: sin
`FORCE ROW LEVEL SECURITY` ese test falla, que es exactamente el agujero que describe
`docs/contexto/04-fase1-fundamentos.md`, sección 6.3.
"""

import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import URL_APP, URL_DUENO, URL_SUPER, requiere_base

T = TypeVar("T")


def _correr(corutina: Awaitable[T]) -> T:
    return asyncio.run(corutina)  # type: ignore[arg-type]


pytestmark = requiere_base


async def _fijar(conn: AsyncConnection, empresa_id: UUID | None) -> None:
    valor = str(empresa_id) if empresa_id else ""
    await conn.execute(text("SELECT set_config('app.empresa_id', :v, true)"), {"v": valor})


async def _sembrar() -> tuple[UUID, UUID]:
    """Crea dos empresas con un usuario cada una y devuelve sus ids.

    La siembra pasa por el mismo camino que usará POST /auth/register: insertar la empresa
    (permitido por la política `empresa_signup`), fijar el tenant con el id recién creado y solo
    entonces insertar su usuario.
    """
    motor = create_async_engine(URL_SUPER)
    try:
        ids: list[UUID] = []
        async with motor.begin() as conn:
            for nombre in ("Empresa A", "Empresa B"):
                fila = await conn.execute(
                    text("INSERT INTO empresas (nombre) VALUES (:n) RETURNING id"),
                    {"n": f"{nombre} {uuid4().hex[:8]}"},
                )
                empresa_id = fila.scalar_one()
                await _fijar(conn, empresa_id)
                await conn.execute(
                    text(
                        "INSERT INTO usuarios (empresa_id, nombre, correo, password_hash, rol)"
                        " VALUES (:e, :n, :c, 'x', 'administrador')"
                    ),
                    {"e": empresa_id, "n": f"Admin {nombre}", "c": f"{uuid4().hex}@test.local"},
                )
                ids.append(empresa_id)
        return ids[0], ids[1]
    finally:
        await motor.dispose()


async def _contar_usuarios(url: str, empresa_id: UUID | None) -> int:
    motor = create_async_engine(url)
    try:
        async with motor.begin() as conn:
            await _fijar(conn, empresa_id)
            fila = await conn.execute(text("SELECT count(*) FROM usuarios"))
            return int(fila.scalar_one())
    finally:
        await motor.dispose()


async def _empresas_visibles(url: str, empresa_id: UUID | None) -> list[Any]:
    motor = create_async_engine(url)
    try:
        async with motor.begin() as conn:
            await _fijar(conn, empresa_id)
            fila = await conn.execute(text("SELECT id FROM empresas"))
            return list(fila.scalars().all())
    finally:
        await motor.dispose()


@pytest.fixture(scope="module")
def empresas() -> tuple[UUID, UUID]:
    return _correr(_sembrar())


def test_rnf01_cada_empresa_solo_ve_su_propia_fila(empresas: tuple[UUID, UUID]) -> None:
    a, b = empresas
    assert _correr(_empresas_visibles(URL_APP, a)) == [a]
    assert _correr(_empresas_visibles(URL_APP, b)) == [b]


def test_rnf01_cada_empresa_solo_ve_sus_usuarios(empresas: tuple[UUID, UUID]) -> None:
    a, b = empresas
    # Hay al menos dos usuarios en la tabla, pero cada tenant ve exactamente el suyo.
    assert _correr(_contar_usuarios(URL_APP, a)) == 1
    assert _correr(_contar_usuarios(URL_APP, b)) == 1


def test_rnf01_sin_tenant_fijado_no_se_ve_ninguna_fila(empresas: tuple[UUID, UUID]) -> None:
    # Falla cerrado: una transaccion que olvide el set_config no devuelve datos
    # de mas, devuelve cero. Ver el missing_ok de current_setting en las politicas.
    assert _correr(_contar_usuarios(URL_APP, None)) == 0
    assert _correr(_empresas_visibles(URL_APP, None)) == []


def test_rnf01_ni_siquiera_el_dueno_de_las_tablas_ve_otras_empresas(
    empresas: tuple[UUID, UUID],
) -> None:
    # ESTE es el test que justifica FORCE ROW LEVEL SECURITY. Sin FORCE, el
    # propietario ignora las politicas y este contador daria 2 en vez de 1.
    #
    # Y solo funciona porque simap_owner NO es superusuario: por eso la seccion
    # 5 de rls_policies.sql le transfiere la propiedad de las tablas. Mientras
    # el dueno fue el superusuario de la imagen de Docker, FORCE era decorativo.
    a, _b = empresas
    assert _correr(_contar_usuarios(URL_DUENO, a)) == 1


def test_el_dueno_de_las_tablas_no_es_superusuario() -> None:
    # Si alguien vuelve a dejar las tablas en manos de un superusuario, FORCE
    # deja de proteger y el test de arriba pasaria a ser una ilusion.
    async def comprobar() -> tuple[bool, bool]:
        motor = create_async_engine(URL_SUPER)
        try:
            async with motor.begin() as conn:
                fila = await conn.execute(
                    text(
                        "SELECT r.rolsuper, r.rolbypassrls FROM pg_tables t"
                        " JOIN pg_roles r ON r.rolname = t.tableowner"
                        " WHERE t.schemaname = 'public' AND t.tablename = 'usuarios'"
                    )
                )
                super_, bypass = fila.one()
                return bool(super_), bool(bypass)
        finally:
            await motor.dispose()

    es_super, salta_rls = _correr(comprobar())
    assert es_super is False
    assert salta_rls is False


def test_documentado_el_superusuario_si_se_salta_rls(empresas: tuple[UUID, UUID]) -> None:
    """Limitación conocida y aceptada, no un fallo.

    PostgreSQL deja pasar SIEMPRE a los superusuarios: ni ENABLE ni FORCE les afectan, y no hay
    forma de evitarlo. Por eso el superusuario solo se usa para administrar la base, y nunca en
    `DATABASE_URL`. Este test fija esa frontera por escrito: si algún día dejara de cumplirse,
    querría decir que PostgreSQL cambió su semántica y habría que revisar todo el razonamiento.

    La comparación es relativa y no contra un número fijo: la base acumula filas entre ejecuciones,
    así que un `== 2` pasaría suelto y fallaría dentro de la suite completa.
    """
    a, _b = empresas
    visto_por_superusuario = _correr(_contar_usuarios(URL_SUPER, a))
    visto_por_la_aplicacion = _correr(_contar_usuarios(URL_APP, a))
    assert visto_por_la_aplicacion == 1
    assert visto_por_superusuario > visto_por_la_aplicacion


def test_rnf01_el_rol_de_aplicacion_no_puede_saltarse_rls() -> None:
    # app_user no debe tener BYPASSRLS ni ser superusuario: cualquiera de las dos
    # cosas desactivaria el aislamiento entero.
    async def comprobar() -> tuple[bool, bool]:
        motor = create_async_engine(URL_APP)
        try:
            async with motor.begin() as conn:
                fila = await conn.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user'")
                )
                super_, bypass = fila.one()
                return bool(super_), bool(bypass)
        finally:
            await motor.dispose()

    es_super, salta_rls = _correr(comprobar())
    assert es_super is False
    assert salta_rls is False


async def _puede_insertar_empresa(url: str) -> bool:
    """Intenta crear una empresa con el rol de la URL dada. True si la base lo permite."""
    motor = create_async_engine(url)
    try:
        async with motor.begin() as conn:
            await conn.execute(
                text("INSERT INTO empresas (nombre) VALUES (:n)"),
                {"n": f"Intento {uuid4().hex[:8]}"},
            )
        return True
    except Exception:
        return False
    finally:
        await motor.dispose()


def test_el_rol_de_la_aplicacion_no_puede_crear_empresas() -> None:
    """El alta de empresas es administrativa, y la base es quien lo impone (revisión 0002).

    SIMAP se cobra por equipo, así que una empresa no puede darse de alta a sí misma. La ruta
    `POST /auth/register` se retiró, pero retirar una ruta no basta: alguien podría reintroducirla
    sin darse cuenta de la decisión comercial que hay detrás. Esta prueba comprueba el cierre en la
    capa donde no depende de que nadie recuerde nada.

    Antes de la revisión 0002 la política `empresa_signup` permitía este INSERT a cualquiera, así
    que esta prueba falla contra el esquema anterior. Eso es lo que la hace útil.
    """
    assert _correr(_puede_insertar_empresa(URL_APP)) is False


def test_el_dueno_de_las_tablas_si_puede_crear_empresas() -> None:
    # La otra mitad de la afirmación: cerrarle la puerta a app_user no debe haber cerrado también la
    # del comando administrativo, que corre con este rol. Sin esta prueba, un endurecimiento de más
    # dejaría el sistema sin ninguna forma de dar de alta un cliente.
    assert _correr(_puede_insertar_empresa(URL_DUENO)) is True
