"""Dependencias de FastAPI para acceso a datos con aislamiento por empresa.

`get_db` es el único punto por el que las rutas obtienen una sesión. Antes de entregarla, fija
`app.empresa_id` en la transacción, que es lo que las políticas RLS de PostgreSQL leen para decidir
qué filas existen (ver `backend/db/rls_policies.sql`).

El `empresa_id` sale SIEMPRE del token ya verificado por `app.core.auth`, nunca de un parámetro,
cabecera o cuerpo enviado por el cliente (04-fase1-fundamentos.md, sección 6.3).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ClaimsActuales
from app.core.security import Claims
from app.db.session import (
    get_estrategia_tenant,
    get_sessionmaker,
    get_sessionmaker_job,
    get_sessionmaker_operador,
)


async def get_db(claims: ClaimsActuales) -> AsyncIterator[AsyncSession]:
    """Entrega una sesión dentro de una transacción con el tenant ya fijado.

    Cómo se fija el tenant depende del motor y lo resuelve `app.db.tenant`: en PostgreSQL se
    traduce a Row-Level Security; en motores sin RLS no hay nada que fijar en la conexión y el
    aislamiento recae en los servicios. Aquí no se escribe SQL de ningún motor concreto.

    La transacción envuelve todo el request: se confirma al terminar bien y se revierte ante
    cualquier excepción. Eso importa para PostgreSQL, donde el tenant vive exactamente lo que dure
    la transacción y por tanto nunca se filtra a la siguiente petición que reutilice la conexión.
    """
    sessionmaker = get_sessionmaker()
    estrategia = get_estrategia_tenant()
    async with sessionmaker() as session:
        async with session.begin():
            await estrategia.fijar_empresa(session, claims.empresa_id)
            yield session


async def get_db_sin_tenant() -> AsyncIterator[AsyncSession]:
    """Sesión sin tenant fijado, para lo que ocurre ANTES de haber token: login y registro.

    No es un agujero en el aislamiento: como las políticas comparan contra
    `current_setting('app.empresa_id', true)`, que aquí es NULL, esta sesión no ve ninguna fila de
    las tablas con RLS. Solo sirve para las operaciones que consultan tablas sin
    RLS (`intentos_login`) o que tienen su propia política de alcance mínimo (`login_lookup`).
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            yield session


async def get_db_operador() -> AsyncIterator[AsyncSession]:
    """Sesión del plano de control, con el rol `operador_user`.

    No fija ningún tenant, y no le hace falta: este rol tiene sus propias políticas RLS, que le dan
    acceso completo a `empresas` pero solo a los usuarios con rol `administrador`, y **ningún
    permiso sobre las tablas de negocio**. Ver la revisión 0003 de Alembic.
    """
    sessionmaker = get_sessionmaker_operador()
    async with sessionmaker() as session:
        async with session.begin():
            yield session


@asynccontextmanager
async def sesion_de_empresa(empresa_id: UUID) -> AsyncIterator[AsyncSession]:
    """Sesión con el tenant fijado, fuera de un request (07-fase4, 9.2).

    La usan las tareas en segundo plano que recalculan el riesgo después del commit: abren su propia
    transacción con el `empresa_id` que ya traía la petición, nunca uno que venga de otro sitio.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            await get_estrategia_tenant().fijar_empresa(session, empresa_id)
            yield session


@asynccontextmanager
async def sesion_de_lectura(empresa_id: UUID) -> AsyncIterator[AsyncSession]:
    """Transacción propia de un widget del panel (08-fase5, 8.3 y 8.6).

    Solo lectura y con una foto fija de los datos, con el tenant de la sesión. Cada widget abre la
    suya: si uno falla, PostgreSQL aborta solo esa transacción y los demás siguen (RNF-02).
    """
    estrategia = get_estrategia_tenant()
    async with get_sessionmaker()() as session:
        async with session.begin():
            await estrategia.lectura_consistente(session)
            await estrategia.fijar_empresa(session, empresa_id)
            yield session


@asynccontextmanager
async def sesion_del_job() -> AsyncIterator[AsyncSession]:
    """Sesión del job nocturno, con `job_user` y **sin** tenant: no ve ninguna fila de empresa.

    Solo sirve para pedir la lista de empresas; cada empresa se trabaja después en su propia
    transacción con su tenant fijado (`fijar_tenant`).
    """
    async with get_sessionmaker_job()() as session:
        async with session.begin():
            yield session


async def fijar_tenant(session: AsyncSession, empresa_id: UUID) -> None:
    """Fija el tenant en una sesión ya abierta.

    Lo necesita el alta administrativa de empresas: primero inserta la empresa (permitido por
    `empresa_alta_administrativa`) y, con el id recién generado, fija el tenant para poder insertar
    su primer usuario.
    """
    await get_estrategia_tenant().fijar_empresa(session, empresa_id)


async def permitir_busqueda_por_correo(session: AsyncSession, correo: str) -> None:
    """Habilita al login leer la fila de un correo concreto. Ver `app.db.tenant`."""
    await get_estrategia_tenant().permitir_busqueda_por_correo(session, correo)


#: Alias para anotar rutas sin repetir el Depends en cada firma.
SesionDB = Annotated[AsyncSession, Depends(get_db)]
SesionSinTenant = Annotated[AsyncSession, Depends(get_db_sin_tenant)]
#: Sesión del plano de control. NUNCA se use en una ruta del plano de datos ni al revés.
SesionOperador = Annotated[AsyncSession, Depends(get_db_operador)]

__all__ = [
    "Claims",
    "ClaimsActuales",
    "SesionDB",
    "SesionOperador",
    "SesionSinTenant",
    "fijar_tenant",
    "sesion_de_empresa",
    "sesion_del_job",
    "permitir_busqueda_por_correo",
    "get_db",
    "get_db_operador",
    "get_db_sin_tenant",
]
