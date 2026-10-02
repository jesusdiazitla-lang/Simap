"""Configuración compartida de las pruebas: detección de la base de datos.

Varias suites (aislamiento entre tenants, autenticación, migraciones) necesitan un PostgreSQL real.
En desarrollo se saltan con un motivo explícito si no lo hay, para que trabajar sin Docker levantado
siga siendo cómodo.

**En CI eso sería un agujero**: un test que se salta no prueba nada, pero tampoco falla, así que la
cobertura de RNF-01 desaparecería sin que nadie lo note y el pipeline seguiría en verde. Por eso,
cuando la variable `CI` está activa, la ausencia de base aborta la ejecución entera con un mensaje
claro en lugar de saltar.
"""

import asyncio
import io
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

#: El rol del backend: ni superusuario ni dueño de las tablas.
URL_APP = "postgresql+asyncpg://app_user:changeme@localhost:5432/simap"
#: Dueño de las tablas, sin superusuario. Corre las migraciones.
URL_DUENO = "postgresql+asyncpg://simap_owner:changeme_owner@localhost:5432/simap"
#: Superusuario. Ignora RLS por diseño de PostgreSQL; solo para administrar y sembrar.
URL_SUPER = "postgresql+asyncpg://simap:simap_dev@localhost:5432/simap"

EN_CI = os.getenv("CI", "").lower() in {"1", "true", "yes"}


async def _puede_consultar(url: str) -> bool:
    motor = create_async_engine(url)
    try:
        async with motor.connect() as conn:
            await conn.execute(text("SELECT 1 FROM usuarios LIMIT 1"))
        return True
    except Exception:
        return False
    finally:
        await motor.dispose()


BASE_MIGRADA = asyncio.run(_puede_consultar(URL_APP))

if EN_CI and not BASE_MIGRADA:
    raise RuntimeError(
        "No hay PostgreSQL migrado y estamos en CI. Saltarse las pruebas de aislamiento "
        "dejaria el pipeline en verde sin haber comprobado RNF-01. "
        "Levantar el servicio y ejecutar 'alembic upgrade head' antes de pytest."
    )

#: Marca para las suites que exigen base. Usar como `pytestmark = requiere_base`.
requiere_base = pytest.mark.skipif(
    not BASE_MIGRADA,
    reason="PostgreSQL no disponible o sin migrar "
    "(docker compose up -d db && alembic upgrade head)",
)


def dar_de_alta(
    monkeypatch: pytest.MonkeyPatch,
    *,
    correo: str,
    password: str,
    empresa: str = "Metalúrgica Prueba",
    nombre: str = "Ana Administradora",
) -> int:
    """Da de alta una empresa por el camino real: el comando de consola, no HTTP.

    Desde que el alta es por invitación no existe `POST /auth/register`, así que las pruebas que
    necesitan una empresa con su administrador tienen que pasar por donde pasa quien opera SIMAP.
    Usarlo aquí tiene una ventaja sobre inventar filas con INSERT: si el comando se rompe, se
    enteran todas las pruebas que dependen de él, no solo la suya.

    Devuelve el código de salida del comando para que quien llame pueda comprobar también los
    fallos (correo duplicado, contraseña corta).
    """
    from app import cli

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{password}\n"))
    return cli.main(
        [
            "crear-empresa",
            "--empresa",
            empresa,
            "--admin-nombre",
            nombre,
            "--admin-correo",
            correo,
            "--password-stdin",
        ]
    )
