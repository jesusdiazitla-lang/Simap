"""Motor y fábrica de sesiones asíncronas de SQLAlchemy.

El motor se crea una sola vez por proceso (`lru_cache`) porque lleva dentro el pool de conexiones:
crear uno por request abriría conexiones nuevas sin reutilizar nada.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.tenant import EstrategiaTenant, estrategia_para


@lru_cache
def get_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        echo=s.db_echo,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        # Descarta conexiones muertas antes de usarlas en vez de fallar el request.
        pool_pre_ping=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        # Tras el commit los objetos siguen siendo legibles sin ir de nuevo a la base.
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache
def get_estrategia_tenant() -> EstrategiaTenant:
    """Estrategia de aislamiento del motor configurado.

    Se deduce del dialecto de la URL de conexión, así que cambiar de motor es cambiar
    `DATABASE_URL` y nada más: no hay que tocar servicios ni rutas. Ver `app.db.tenant`.
    """
    return estrategia_para(get_engine().dialect.name)


# =============================================================================
# Plano de control: motor aparte para la consola del operador.
#
# Es un motor distinto porque se conecta con un ROL de PostgreSQL distinto, y ese rol es toda la
# frontera: tiene permisos tabla por tabla y ninguno sobre las tablas de negocio. Compartir el
# motor con el plano de datos significaría compartir el rol, y entonces la separación existiría
# solo en la intención del código.
# =============================================================================


@lru_cache
def get_engine_operador() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url_operador,
        echo=s.db_echo,
        # Pool pequeño a propósito: la consola la usan una o dos personas, no una planta entera.
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
    )


@lru_cache
def get_sessionmaker_operador() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine_operador(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# =============================================================================
# Job nocturno de la fase 4: motor aparte porque se conecta con job_user (07-fase4, 9.3), el único
# rol que puede listar las empresas. Sigue sujeto a RLS: fija el tenant empresa por empresa.
# =============================================================================


@lru_cache
def get_engine_job() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(s.database_url_job, echo=s.db_echo, pool_size=2, max_overflow=2)


@lru_cache
def get_sessionmaker_job() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine_job(), class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def dispose_engine() -> None:
    """Cierra los pools. Se llama al apagar la aplicación y entre tests."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    if get_engine_operador.cache_info().currsize:
        await get_engine_operador().dispose()
    if get_engine_job.cache_info().currsize:
        await get_engine_job().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_estrategia_tenant.cache_clear()
    get_engine_operador.cache_clear()
    get_sessionmaker_operador.cache_clear()
    get_engine_job.cache_clear()
    get_sessionmaker_job.cache_clear()
