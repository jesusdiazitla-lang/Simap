"""Catálogo de componentes de la empresa (05-fase2-activos-y-campo.md, sección 5).

Se renombran y se desactivan; no se borran. Las órdenes de trabajo de la fase 3 dicen qué componente
falló, y el modelo de la fase 4 ajusta una curva por componente: borrar uno dejaría las dos cosas
sin referencia. La base lo impone además: `app_user` no tiene permiso de borrar en esta tabla.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.componente import PLANTILLA_INICIAL, Componente
from app.services.prediccion import ajuste


class ComponenteNoEncontrado(Exception):
    pass


class NombreRepetido(Exception):
    """Ya hay un componente con ese nombre en la empresa."""


async def listar(session: AsyncSession, *, incluir_inactivos: bool = False) -> list[Componente]:
    consulta = select(Componente).order_by(Componente.nombre)
    if not incluir_inactivos:
        consulta = consulta.where(Componente.activo.is_(True))
    return list((await session.scalars(consulta)).all())


async def _guardar(session: AsyncSession, componente: Componente) -> None:
    """Guarda dentro de un savepoint para poder traducir el choque de nombre sin perder la sesión.

    El nombre repetido se detecta con la restricción UNIQUE de la base, no con un SELECT previo: con
    dos administradores creando a la vez el mismo nombre, el SELECT diría que no existe a los dos.
    """
    try:
        async with session.begin_nested():
            session.add(componente)
            await session.flush()
    except IntegrityError as exc:
        if "uq_componentes_empresa_id_nombre" in str(exc.orig):
            raise NombreRepetido(componente.nombre) from exc
        raise


async def crear(
    session: AsyncSession, *, empresa_id: UUID, nombre: str, descripcion: str | None
) -> Componente:
    componente = Componente(empresa_id=empresa_id, nombre=nombre, descripcion=descripcion)
    await _guardar(session, componente)
    return componente


async def editar(
    session: AsyncSession,
    componente_id: UUID,
    *,
    nombre: str | None = None,
    descripcion: str | None = None,
    activo: bool | None = None,
    **vida: int | None,
) -> Componente:
    """Renombra, describe, desactiva o cambia la vida nominal.

    La vida nominal llega por `**vida` para distinguir «no viene» de «viene vacía» (borrarla).
    Cambiarla mueve el conocimiento previo del modelo: marca el componente para reajustar (F4,
    6.2).
    """
    componente: Componente | None = await session.scalar(
        select(Componente).where(Componente.id == componente_id)
    )
    if componente is None:
        raise ComponenteNoEncontrado(str(componente_id))
    if nombre is not None:
        componente.nombre = nombre
    if descripcion is not None:
        componente.descripcion = descripcion
    if activo is not None:
        componente.activo = activo
    cambia_vida = "vida_nominal_horas" in vida and vida["vida_nominal_horas"] != (
        componente.vida_nominal_horas
    )
    if cambia_vida:
        componente.vida_nominal_horas = vida["vida_nominal_horas"]
    await _guardar(session, componente)
    if cambia_vida:
        await ajuste.marcar(session, componente.empresa_id, componente.id)
    return componente


def plantilla_para(empresa_id: UUID) -> list[Componente]:
    """Los componentes con los que nace una empresa nueva.

    Devuelve los objetos sin guardarlos: los añade quien da de alta la empresa, dentro de su misma
    transacción, para que no pueda existir una empresa sin catálogo. Lo usan dos caminos —la consola
    del operador (`app.services.operador`) y el comando `app.cli crear-empresa`— y por eso vive aquí
    y no duplicado en cada uno.
    """
    return [
        Componente(empresa_id=empresa_id, nombre=nombre, descripcion=descripcion)
        for nombre, descripcion in PLANTILLA_INICIAL
    ]


async def cargar_plantilla(session: AsyncSession, *, empresa_id: UUID) -> list[Componente]:
    """Añade al catálogo los componentes de la plantilla que todavía no tenga.

    Para las empresas dadas de alta antes de que existiera la plantilla, y para quien desactivó o
    borró de su lista alguno y quiere recuperarlo. No duplica: compara por nombre, que es único en
    la empresa, y no toca los que ya existen —ni siquiera reactiva uno desactivado, que es una
    decisión que alguien tomó—. Devuelve los que añadió.
    """
    existentes = set((await session.scalars(select(Componente.nombre))).all())
    nuevos = [c for c in plantilla_para(empresa_id) if c.nombre not in existentes]
    session.add_all(nuevos)
    await session.flush()
    return nuevos
