"""Alertas de campo: reporte con deduplicación, revisión por el supervisor (RF-09).

Las alertas nunca se borran (la base no le da a `app_user` permiso para hacerlo) y solo cambian de
estado: de `pendiente` a `revisada` o `descartada`, y solo por supervisor o administrador
(05-fase2-activos-y-campo.md, sección 5.2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.core.config import get_settings
from app.core.cursor import Cursor
from app.models.activo import Activo
from app.models.alerta import Alerta
from app.services.capturas import activo_en_servicio, validar_instante


class AlertaNoEncontrada(Exception):
    pass


class TransicionNoPermitida(Exception):
    """Solo una alerta pendiente se puede revisar o descartar."""


async def _por_cliente_id(session: AsyncSession, cliente_id: UUID) -> Alerta | None:
    resultado: Alerta | None = await session.scalar(
        select(Alerta).where(Alerta.cliente_id == cliente_id)
    )
    return resultado


async def _repetida(
    session: AsyncSession,
    *,
    autor_id: UUID,
    activo_id: UUID,
    sintoma: str,
    capturado_en: datetime,
) -> Alerta | None:
    """La misma alerta de la misma persona dentro de la ventana de deduplicación (sección 5.2).

    Razón de negocio: en la fase 4 las alertas recientes multiplican el riesgo calculado del equipo.
    Un botón atascado, o alguien que insiste tres veces porque no vio la confirmación, no debe poder
    inflar ese riesgo. La ventana se mira hacia los dos lados de `capturado_en` porque con la cola
    sin conexión el orden de llegada no es el de captura.

    Otra persona reportando lo mismo **no** es un duplicado: dos testigos independientes son
    justamente la señal que el modelo quiere ver.
    """
    ventana = timedelta(minutes=get_settings().alerta_dedup_minutos)
    resultado: Alerta | None = await session.scalar(
        select(Alerta)
        .where(
            Alerta.reportado_por == autor_id,
            Alerta.activo_id == activo_id,
            Alerta.sintoma == sintoma,
            Alerta.capturado_en.between(capturado_en - ventana, capturado_en + ventana),
        )
        .order_by(Alerta.capturado_en)
        .limit(1)
    )
    return resultado


async def reportar(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    activo_id: UUID,
    sintoma: str,
    nota: str | None,
    capturado_en: datetime,
    cliente_id: UUID,
    ahora: datetime | None = None,
) -> tuple[str, Alerta]:
    """Reporta una alerta. Devuelve `("creado" | "duplicado", alerta)`."""
    existente = await _por_cliente_id(session, cliente_id)
    if existente is not None:
        return "duplicado", existente

    validar_instante(capturado_en, ahora)
    await activo_en_servicio(session, activo_id)

    repetida = await _repetida(
        session, autor_id=autor_id, activo_id=activo_id, sintoma=sintoma, capturado_en=capturado_en
    )
    if repetida is not None:
        # Deduplicación por ventana (sección 5.2). Si sube mucho, quizá la ventana es corta o un
        # botón de algún teléfono se atasca.
        registro.evento("campo.alerta_deduplicada", sintoma=sintoma)
        return "duplicado", repetida

    alerta = Alerta(
        empresa_id=empresa_id,
        activo_id=activo_id,
        reportado_por=autor_id,
        sintoma=sintoma,
        nota=nota or None,
        capturado_en=capturado_en,
        cliente_id=cliente_id,
    )
    try:
        async with session.begin_nested():
            session.add(alerta)
            await session.flush()
    except IntegrityError as exc:
        if "uq_alertas_idempotente" not in str(exc.orig):
            raise
        ganadora = await _por_cliente_id(session, cliente_id)
        if ganadora is None:
            raise
        return "duplicado", ganadora
    return "creado", alerta


async def listar(
    session: AsyncSession,
    *,
    solo_de: UUID | None,
    estado: str | None,
    activo_id: UUID | None,
    cursor: Cursor | None,
    limite: int,
) -> tuple[list[tuple[Alerta, str, str]], Cursor | None]:
    """Bandeja de alertas, de la más reciente a la más antigua, con nombre y código de su equipo.

    `solo_de` restringe a las alertas de una persona: es como ve la bandeja un operario (sección
    5.2). Lo decide la ruta según el rol; aquí solo se aplica.
    """
    consulta = select(Alerta, Activo.nombre, Activo.qr_code).join(
        Activo, Activo.id == Alerta.activo_id
    )
    if solo_de is not None:
        consulta = consulta.where(Alerta.reportado_por == solo_de)
    if estado is not None:
        consulta = consulta.where(Alerta.estado == estado)
    if activo_id is not None:
        consulta = consulta.where(Alerta.activo_id == activo_id)
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(Alerta.fecha < instante, and_(Alerta.fecha == instante, Alerta.id < cursor.id))
        )
    consulta = consulta.order_by(Alerta.fecha.desc(), Alerta.id.desc()).limit(limite + 1)
    filas = [(a, nombre, codigo) for a, nombre, codigo in (await session.execute(consulta)).all()]
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1][0]
    return filas[:limite], Cursor.de_instante(ultima.fecha, ultima.id)


async def revisar(
    session: AsyncSession, *, revisor_id: UUID, alerta_id: UUID, estado: str
) -> Alerta:
    """Marca una alerta pendiente como revisada o descartada, y anota quién y cuándo.

    Escritura condicionada (sección 9.4): la comprobación «sigue pendiente» va en el propio UPDATE.
    Leer primero y escribir después deja pasar a dos supervisores que actúan a la vez: los dos leen
    `pendiente` y el segundo pisa al primero. Con la condición en el WHERE, el segundo espera al
    bloqueo de fila, vuelve a evaluarla, ya no se cumple y no toca nada.
    """
    resultado = await session.execute(
        update(Alerta)
        .where(Alerta.id == alerta_id, Alerta.estado == "pendiente")
        .values(estado=estado, revisada_por=revisor_id, revisada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount == 0:
        actual = await session.scalar(select(Alerta.estado).where(Alerta.id == alerta_id))
        if actual is None:
            raise AlertaNoEncontrada(str(alerta_id))
        raise TransicionNoPermitida(actual)
    alerta = await session.scalar(
        select(Alerta).where(Alerta.id == alerta_id).execution_options(populate_existing=True)
    )
    assert alerta is not None
    return alerta
