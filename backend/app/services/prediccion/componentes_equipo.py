"""Componentes de cada equipo y edad de la pieza instalada (07-fase4, sección 6.1; decisión 7).

`activo_componentes` dice qué componentes tiene un equipo y a qué horas **del equipo** (dial más
offset) se instaló la unidad actual. Sin esa edad no hay riesgo: el equipo muestra «sin edad»,
porque inventarla produciría alarmas o tranquilidad falsas. Al primer reemplazo la edad pasa a
conocerse sola: la pieza nueva empieza en las horas del reemplazo.

El componente comodín «Otro (por identificar)» no se registra: no es un componente, es un hueco en
la información, y la fase 4 no ajusta modelo con él.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activo import Activo
from app.models.componente import COMPONENTE_POR_IDENTIFICAR, Componente
from app.models.prediccion import ActivoComponente, Riesgo
from app.services.prediccion import ajuste


class ComponenteNoValido(Exception):
    """El componente no es del catálogo de la empresa, está inactivo o es el comodín (422)."""


class EdadInvalida(Exception):
    """La edad declarada supera las horas acumuladas del equipo (422 `edad_invalida`)."""


class EquipoNoEncontrado(Exception):
    """El equipo no existe o es de otra empresa (404)."""


@dataclass(frozen=True)
class ComponenteDelEquipo:
    componente_id: UUID
    nombre: str
    horas_instalacion_inicial: int | None
    estado_calculo: str | None
    riesgo: float | None
    #: Edad de la pieza en el último cálculo: cuenta las renovaciones de las órdenes cerradas, así
    #: que puede ser menor que «horas del equipo − instalación inicial».
    edad_horas: float | None = None


async def es_comodin(session: AsyncSession, componente_id: UUID) -> bool:
    nombre = await session.scalar(select(Componente.nombre).where(Componente.id == componente_id))
    return nombre == COMPONENTE_POR_IDENTIFICAR


async def registrar_si_falta(
    session: AsyncSession, empresa_id: UUID, activo_id: UUID, componente_id: UUID
) -> None:
    """Al reportar una falla: registra el par con edad desconocida si el equipo aún no lo tenía.

    Nunca pisa una edad que el administrador ya declaró. Si dos fallas lo registran a la vez, la
    segunda choca con la llave primaria dentro de un savepoint y no hace nada.
    """
    if await es_comodin(session, componente_id):
        return
    existe = await session.get(ActivoComponente, (empresa_id, activo_id, componente_id))
    if existe is not None:
        return
    try:
        async with session.begin_nested():
            session.add(
                ActivoComponente(
                    empresa_id=empresa_id, activo_id=activo_id, componente_id=componente_id
                )
            )
            await session.flush()
    except IntegrityError:
        return


async def declarar(
    session: AsyncSession,
    empresa_id: UUID,
    activo_id: UUID,
    componente_id: UUID,
    horas_instalacion: int | None,
) -> ActivoComponente:
    """El administrador declara el componente y a qué horas del equipo se instaló (PUT, 6.1).

    0 si el equipo era nuevo; `None` si no se sabe. Una edad mayor que las horas acumuladas del
    equipo es imposible (422). Marca el componente para reajustar: la edad cambia sus vidas.
    """
    activo = await session.scalar(select(Activo).where(Activo.id == activo_id))
    if activo is None:
        raise EquipoNoEncontrado(str(activo_id))
    componente = await session.scalar(select(Componente).where(Componente.id == componente_id))
    if (
        componente is None
        or not componente.activo
        or componente.nombre == COMPONENTE_POR_IDENTIFICAR
    ):
        raise ComponenteNoValido("Ese componente no está en el catálogo de la empresa.")
    acumuladas = activo.horometro_offset + activo.horometro_actual
    if horas_instalacion is not None and horas_instalacion > acumuladas:
        raise EdadInvalida(
            f"El equipo acumula {acumuladas:,} h: la pieza no pudo instalarse a las "
            f"{horas_instalacion:,} h."
        )
    par = await session.get(ActivoComponente, (empresa_id, activo_id, componente_id))
    if par is None:
        par = ActivoComponente(
            empresa_id=empresa_id,
            activo_id=activo_id,
            componente_id=componente_id,
            horas_instalacion_inicial=horas_instalacion,
        )
        try:
            async with session.begin_nested():
                session.add(par)
                await session.flush()
        except IntegrityError:
            # Otra petición lo registró a la vez: se actualiza el que ganó.
            par = await session.get(
                ActivoComponente, (empresa_id, activo_id, componente_id), populate_existing=True
            )
            assert par is not None
            par.horas_instalacion_inicial = horas_instalacion
            await session.flush()
    else:
        par.horas_instalacion_inicial = horas_instalacion
        await session.flush()
    await ajuste.marcar(session, empresa_id, componente_id)
    return par


async def listar(session: AsyncSession, activo_id: UUID) -> list[ComponenteDelEquipo]:
    """Los componentes del equipo con su edad y el estado de su último cálculo de riesgo."""
    filas = await session.execute(
        select(
            ActivoComponente.componente_id,
            Componente.nombre,
            ActivoComponente.horas_instalacion_inicial,
            Riesgo.estado_calculo,
            Riesgo.riesgo,
            Riesgo.edad_horas,
        )
        .join(
            Componente,
            (Componente.empresa_id == ActivoComponente.empresa_id)
            & (Componente.id == ActivoComponente.componente_id),
        )
        .outerjoin(
            Riesgo,
            (Riesgo.empresa_id == ActivoComponente.empresa_id)
            & (Riesgo.activo_id == ActivoComponente.activo_id)
            & (Riesgo.componente_id == ActivoComponente.componente_id),
        )
        .where(ActivoComponente.activo_id == activo_id)
        .order_by(Componente.nombre)
    )
    return [
        ComponenteDelEquipo(
            componente_id=f.componente_id,
            nombre=f.nombre,
            horas_instalacion_inicial=f.horas_instalacion_inicial,
            estado_calculo=f.estado_calculo,
            riesgo=float(f.riesgo) if f.riesgo is not None else None,
            edad_horas=f.edad_horas,
        )
        for f in filas
    ]
