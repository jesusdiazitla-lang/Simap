"""Cuándo y cómo se reajusta el modelo de un componente (07-fase4, sección 6.2; decisión 13).

LA MARCA DURABLE
----------------
El cierre de una orden (y el cambio de vida nominal, la corrección administrativa o la edad
declarada) escribe una marca en `reajustes_pendientes` **en su misma transacción**. Si el proceso
cae justo después del commit, la marca sigue ahí y el job de la madrugada la procesa. Reemplaza al
evento en memoria y al barrido diario que proponía la fase 3.

LA GENERACIÓN
-------------
Cada marca lleva un contador que sube con cada marca nueva. Quien la procesa la borra solo si el
contador no cambió mientras ajustaba: un cierre que llega durante el ajuste deja la marca viva y el
siguiente ciclo vuelve a ajustar. Así un cierre concurrente nunca se pierde.

`ON CONFLICT` de la guía se sustituye por UPDATE condicionado + INSERT en savepoint, por la
portabilidad del motor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.models.componente import COMPONENTE_POR_IDENTIFICAR, Componente
from app.models.prediccion import (
    ActivoComponente,
    ModeloComponente,
    ModeloHistorial,
    ReajustePendiente,
    v_vidas,
)
from app.services.prediccion import weibull

#: La vida abierta suma horas cada día aunque no haya fallas nuevas, y esa exposición mueve el
#: ajuste: un modelo de más de una semana se reajusta en el job aunque no tenga marca (6.2).
REFRESCO = timedelta(days=7)


@dataclass(frozen=True)
class Pendiente:
    componente_id: UUID
    vida_nominal: int | None
    generacion: int


async def marcar(session: AsyncSession, empresa_id: UUID, componente_id: UUID) -> None:
    """Marca durable de «este componente tiene datos nuevos». Sube la generación si ya existía."""
    nombre = await session.scalar(select(Componente.nombre).where(Componente.id == componente_id))
    if nombre is None or nombre == COMPONENTE_POR_IDENTIFICAR:
        return
    subir = (
        update(ReajustePendiente)
        .where(ReajustePendiente.componente_id == componente_id)
        .values(generacion=ReajustePendiente.generacion + 1)
        .execution_options(synchronize_session=False)
    )
    if (await session.execute(subir)).rowcount:
        return
    try:
        async with session.begin_nested():
            session.add(ReajustePendiente(empresa_id=empresa_id, componente_id=componente_id))
            await session.flush()
    except IntegrityError:
        # Otra transacción la creó a la vez: se sube la suya.
        await session.execute(subir)


async def a_reajustar(session: AsyncSession, solo: UUID | None = None) -> list[Pendiente]:
    """Componentes que hay que ajustar: con marca, sin modelo o con un modelo de más de 7 días."""
    limite = datetime.now(UTC) - REFRESCO
    consulta = (
        select(
            ActivoComponente.componente_id,
            Componente.vida_nominal_horas,
            ReajustePendiente.generacion,
        )
        .distinct()
        .join(
            Componente,
            (Componente.empresa_id == ActivoComponente.empresa_id)
            & (Componente.id == ActivoComponente.componente_id),
        )
        .outerjoin(
            ReajustePendiente,
            (ReajustePendiente.empresa_id == ActivoComponente.empresa_id)
            & (ReajustePendiente.componente_id == ActivoComponente.componente_id),
        )
        .outerjoin(
            ModeloComponente,
            (ModeloComponente.empresa_id == ActivoComponente.empresa_id)
            & (ModeloComponente.componente_id == ActivoComponente.componente_id),
        )
        .where(
            or_(
                ReajustePendiente.componente_id.is_not(None),
                ModeloComponente.componente_id.is_(None),
                ModeloComponente.ajustado_en < limite,
            )
        )
    )
    if solo is not None:
        consulta = consulta.where(ActivoComponente.componente_id == solo)
    filas = await session.execute(consulta)
    return [Pendiente(f[0], f[1], int(f[2] or 0)) for f in filas]


async def datos_ajuste(
    session: AsyncSession, componente_id: UUID
) -> list[tuple[int, float | None, float | None]]:
    """Tres números por vida de `v_vidas`, de todos los equipos de la empresa con ese componente."""
    filas = await session.execute(
        select(v_vidas.c.n_eventos, v_vidas.c.suma_ln_edades, v_vidas.c.exposicion).where(
            v_vidas.c.componente_id == componente_id, v_vidas.c.exposicion.is_not(None)
        )
    )
    return [(int(f[0]), f[1], f[2]) for f in filas]


async def guardar(
    session: AsyncSession, empresa_id: UUID, componente_id: UUID, modelo: dict[str, Any]
) -> int:
    """Reemplaza el modelo vigente (la versión sube) y, si cambió el número de fallas, agrega una
    fila al historial: la curva de aprendizaje (6.2). Devuelve la versión guardada.

    La versión sube en la base (`version + 1`), no en Python: dos ajustes simultáneos no pueden
    escribir la misma.
    """
    campos = {k: modelo[k] for k in ("beta", "eta", "n_eventos", "n_vidas", "fuente", "confianza")}
    campos["exposicion_horas"] = modelo["exposicion"]
    campos["convergio"] = modelo["convergio"]
    previo = await session.scalar(
        select(ModeloComponente.n_eventos).where(ModeloComponente.componente_id == componente_id)
    )
    resultado = await session.execute(
        update(ModeloComponente)
        .where(ModeloComponente.componente_id == componente_id)
        .values(**campos, version=ModeloComponente.version + 1, ajustado_en=datetime.now(UTC))
        .returning(ModeloComponente.version)
        .execution_options(synchronize_session=False)
    )
    version = resultado.scalar()
    if version is None:
        try:
            async with session.begin_nested():
                session.add(
                    ModeloComponente(empresa_id=empresa_id, componente_id=componente_id, **campos)
                )
                await session.flush()
            version = 1
        except IntegrityError:
            # Otro ajuste lo creó a la vez: se reemplaza el suyo.
            return await guardar(session, empresa_id, componente_id, modelo)
    if previo != modelo["n_eventos"]:
        session.add(
            ModeloHistorial(
                empresa_id=empresa_id,
                componente_id=componente_id,
                version=version,
                beta=modelo["beta"],
                eta=modelo["eta"],
                n_eventos=modelo["n_eventos"],
                fuente=modelo["fuente"],
                confianza=modelo["confianza"],
            )
        )
        await session.flush()
    return int(version)


async def liberar(session: AsyncSession, componente_id: UUID, generacion: int) -> bool:
    """Borra la marca solo si nadie la renovó mientras se ajustaba. `False`: hay datos nuevos."""
    resultado = await session.execute(
        delete(ReajustePendiente)
        .where(
            ReajustePendiente.componente_id == componente_id,
            ReajustePendiente.generacion == generacion,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(resultado.rowcount)


async def reajustar(
    session: AsyncSession, empresa_id: UUID, pendiente: Pendiente
) -> dict[str, Any] | None:
    """Ajusta, guarda y libera la marca. `None` si el componente no tiene base para un modelo."""
    filas = await datos_ajuste(session, pendiente.componente_id)
    modelo = weibull.ajustar_componente(filas, pendiente.vida_nominal)
    if modelo is not None:
        await guardar(session, empresa_id, pendiente.componente_id, modelo)
        registro.evento(
            "prediccion.modelo_ajustado",
            n_eventos=modelo["n_eventos"],
            convergio=modelo["convergio"],
        )
    if pendiente.generacion:
        await liberar(session, pendiente.componente_id, pendiente.generacion)
    return modelo


async def reajustar_componente(
    session: AsyncSession, empresa_id: UUID, componente_id: UUID
) -> dict[str, Any] | None:
    """Reajusta un componente concreto si tiene marca, no tiene modelo o el suyo es viejo."""
    pendientes = await a_reajustar(session, solo=componente_id)
    if not pendientes:
        return None
    return await reajustar(session, empresa_id, pendientes[0])


@dataclass(frozen=True)
class ModeloConHistorial:
    componente: Componente
    modelo: ModeloComponente | None
    historial: list[ModeloHistorial]


class ComponenteNoEncontrado(Exception):
    """No existe o es de otra empresa (404)."""


async def modelo_de(session: AsyncSession, componente_id: UUID) -> ModeloConHistorial:
    """El modelo vigente del componente y su curva de aprendizaje (`modelos_historial`)."""
    componente = await session.scalar(select(Componente).where(Componente.id == componente_id))
    if componente is None:
        raise ComponenteNoEncontrado(str(componente_id))
    modelo = await session.scalar(
        select(ModeloComponente).where(ModeloComponente.componente_id == componente_id)
    )
    historial = (
        await session.scalars(
            select(ModeloHistorial)
            .where(ModeloHistorial.componente_id == componente_id)
            .order_by(ModeloHistorial.ajustado_en, ModeloHistorial.version)
        )
    ).all()
    return ModeloConHistorial(componente, modelo, list(historial))
