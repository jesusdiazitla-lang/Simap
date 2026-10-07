"""Equipos de la empresa: alta con código QR, ficha técnica y baja lógica (RF-04 a RF-07).

Todas las consultas pasan por la sesión de `get_db`, con el tenant fijado: ninguna función de este
módulo filtra por `empresa_id` a mano. RLS ya lo hace, y un filtro duplicado solo serviría para
creer que hay dos protecciones donde el código podría desincronizarlas. Lo que sí se escribe aquí es
la empresa de las filas **nuevas**, que sale siempre del token.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import Cursor
from app.models.activo import Activo
from app.models.lectura_horometro import LecturaHorometro
from app.services import qr

#: Reintentos ante un choque de código (sección 6.1). Con 32⁸ combinaciones, dos seguidos ya serían
#: extraordinarios; cinco convierten en imposible práctico que el alta falle por mala suerte.
INTENTOS_CODIGO = 5


class ActivoNoEncontrado(Exception):
    """No existe, o es de otra empresa: desde fuera son lo mismo (404 en los dos casos)."""


class SinCodigoLibre(Exception):
    """No se encontró un código libre tras varios intentos. No debería ocurrir nunca."""


def _ahora() -> datetime:
    return datetime.now(UTC)


async def _guardar_con_codigo_nuevo(session: AsyncSession, activo: Activo) -> None:
    """Asigna un código aleatorio y guarda, reintentando si ya lo tiene otro equipo.

    El choque se detecta con la restricción UNIQUE global de `qr_code`, dentro de un savepoint para
    no perder la transacción. El error de la base nunca llega al cliente: o hay código, o
    `SinCodigoLibre` (sección 6.1).
    """
    for _ in range(INTENTOS_CODIGO):
        activo.qr_code = qr.generar_codigo()
        try:
            async with session.begin_nested():
                session.add(activo)
                await session.flush()
            return
        except IntegrityError as exc:
            if "uq_activos_qr_code" not in str(exc.orig):
                raise
    raise SinCodigoLibre


async def crear(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    datos: dict[str, Any],
    horometro_inicial: int = 0,
) -> Activo:
    """Da de alta un equipo con su código.

    Si se conoce el horómetro del día del alta, se guarda además como la primera lectura del
    historial, firmada por quien dio de alta el equipo. Sin ella, la primera lectura de campo no
    tendría con qué compararse y no se podría detectar un dígito de más. Con horómetro 0 no se crea:
    un cero que solo significa «no lo sé» haría que la primera lectura real pareciera un salto
    imposible.
    """
    ahora = _ahora()
    activo = Activo(
        empresa_id=empresa_id,
        horometro_actual=horometro_inicial,
        horometro_actualizado_en=ahora if horometro_inicial > 0 else None,
        **datos,
    )
    await _guardar_con_codigo_nuevo(session, activo)
    if horometro_inicial > 0:
        session.add(
            LecturaHorometro(
                empresa_id=empresa_id,
                activo_id=activo.id,
                registrado_por=autor_id,
                valor_horometro=horometro_inicial,
                cliente_id=uuid4(),
                capturado_en=ahora,
            )
        )
        await session.flush()
    return activo


async def obtener(session: AsyncSession, activo_id: UUID) -> Activo:
    activo: Activo | None = await session.scalar(select(Activo).where(Activo.id == activo_id))
    if activo is None:
        raise ActivoNoEncontrado(str(activo_id))
    return activo


async def por_codigo(session: AsyncSession, tecleado: str) -> Activo:
    """Resuelve lo que codifica un QR o lo que alguien tecleó de la etiqueta (sección 6.2).

    Un código mal formado, uno inexistente y uno de otra empresa dan exactamente el mismo resultado.
    Nunca un 403: confirmaría que el código existe y permitiría usar la respuesta para barrer
    códigos ajenos. Un equipo dado de baja sí resuelve, con su estado: quien escanea una etiqueta
    vieja tiene que entender qué pasa.
    """
    codigo = qr.normalizar(tecleado)
    if codigo is None:
        raise ActivoNoEncontrado(tecleado)
    activo: Activo | None = await session.scalar(select(Activo).where(Activo.qr_code == codigo))
    if activo is None:
        raise ActivoNoEncontrado(tecleado)
    return activo


async def listar(
    session: AsyncSession,
    *,
    estado: str | None = None,
    tipo: str | None = None,
    ubicacion: str | None = None,
    texto: str | None = None,
    cursor: Cursor | None = None,
    limite: int,
) -> tuple[list[Activo], Cursor | None]:
    """Listado por nombre, paginado por cursor (sección 9.1).

    Se pide una fila de más para saber si hay página siguiente sin un COUNT aparte.
    """
    consulta = select(Activo)
    if estado is not None:
        consulta = consulta.where(Activo.estado == estado)
    if tipo:
        consulta = consulta.where(Activo.tipo == tipo)
    if ubicacion:
        consulta = consulta.where(Activo.ubicacion == ubicacion)
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(
                Activo.nombre.ilike(patron),
                Activo.ubicacion.ilike(patron),
                Activo.tipo.ilike(patron),
                Activo.qr_code.ilike(patron.replace("-", "")),
            )
        )
    if cursor is not None:
        # «Después de» la última fila entregada, desempatando por id. Se escribe con OR/AND y no
        # con una comparación de tuplas para que valga en cualquier motor.
        consulta = consulta.where(
            or_(
                Activo.nombre > cursor.valor,
                and_(Activo.nombre == cursor.valor, Activo.id > cursor.id),
            )
        )
    consulta = consulta.order_by(Activo.nombre, Activo.id).limit(limite + 1)
    filas = list((await session.scalars(consulta)).all())
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], Cursor(ultima.nombre, ultima.id)


async def editar(session: AsyncSession, activo_id: UUID, cambios: dict[str, Any]) -> Activo:
    """Cambia la ficha técnica. `cambios` ya viene validado y sin `qr_code` ni `empresa_id`."""
    activo = await obtener(session, activo_id)
    for campo, valor in cambios.items():
        setattr(activo, campo, valor)
    await session.flush()
    return activo


async def dar_de_baja(session: AsyncSession, activo_id: UUID) -> Activo:
    """Baja lógica (RF-06): el equipo deja de admitir registros, pero su código sigue resolviendo y
    su historial sigue ahí. Dar de baja dos veces no cambia la fecha de la primera."""
    activo = await obtener(session, activo_id)
    if activo.estado != "baja":
        activo.estado = "baja"
        activo.dado_de_baja_en = _ahora()
        await session.flush()
    return activo


async def regenerar_codigo(session: AsyncSession, activo_id: UUID) -> Activo:
    """Código nuevo para una etiqueta copiada o comprometida (sección 6.3).

    El anterior deja de resolver en ese mismo momento: cualquiera que escanee la etiqueta vieja
    obtiene un 404. Hay que reimprimir.
    """
    activo = await obtener(session, activo_id)
    await _guardar_con_codigo_nuevo(session, activo)
    return activo
