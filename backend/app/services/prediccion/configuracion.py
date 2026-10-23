"""Parámetros de la predicción de cada empresa (07-fase4, decisión 5 y sección 7.1).

La migración creó la fila de las empresas que ya existían; las nuevas la crean al primer uso
(`asegurar`), con los valores por defecto de la tabla.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediccion import ConfiguracionEmpresa

#: Lo que el administrador puede cambiar. Los límites los imponen el esquema y las CHECK de la base.
CAMPOS = (
    "umbral_riesgo",
    "horizonte_horas",
    "alertas_minimas",
    "ventana_alertas_dias",
    "multiplicador_alertas",
    "descarte_silencio_dias",
)


async def asegurar(session: AsyncSession, empresa_id: UUID) -> ConfiguracionEmpresa:
    """La configuración de la empresa; si no existe, la crea con los valores por defecto.

    Dos peticiones que la crean a la vez: una inserta y la otra choca con la llave primaria dentro
    de un savepoint, y lee la que ganó. Sin `ON CONFLICT`, por la portabilidad del motor.
    """
    actual = await session.get(ConfiguracionEmpresa, empresa_id)
    if actual is not None:
        return actual
    nueva = ConfiguracionEmpresa(empresa_id=empresa_id)
    try:
        async with session.begin_nested():
            session.add(nueva)
            await session.flush()
    except IntegrityError:
        ganadora = await session.scalar(
            select(ConfiguracionEmpresa).where(ConfiguracionEmpresa.empresa_id == empresa_id)
        )
        assert ganadora is not None
        return ganadora
    return nueva


async def actualizar(
    session: AsyncSession, empresa_id: UUID, cambios: dict[str, Any]
) -> ConfiguracionEmpresa:
    config = await asegurar(session, empresa_id)
    for campo, valor in cambios.items():
        if campo in CAMPOS:
            setattr(config, campo, valor)
    await session.flush()
    return config
