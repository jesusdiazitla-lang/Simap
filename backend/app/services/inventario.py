"""Inventario de repuestos (RF-23 a RF-26; 07-fase4, secciones 6.5 y 6.6).

EL LIBRO MANDA
--------------
`stock_actual` solo se mueve por el libro: alta con stock inicial, ingreso, consumo al cerrar una
orden y ajuste por conteo. Ningún cuerpo de petición trae el stock. Cada movimiento suma o resta de
forma atómica (`stock_actual = stock_actual ± n`), sin lectura previa que pueda quedar vieja, y
asienta su fila con el stock resultante y el costo del momento.

EL DESCUENTO AL CERRAR (decisiones 1 y 3)
------------------------------------------
Dentro de la transacción del cierre: primero se bloquean los repuestos de la orden **en orden de
id** (dos cierres con repuestos en común los toman en el mismo orden y no pueden bloquearse entre
sí); después cada línea se descuenta con un UPDATE condicionado a que el stock alcance. Si alguna no
alcanza, `StockInsuficiente` revierte el cierre entero: la orden sigue Reparada y el 409 dice qué
falta. Aunque el código corriera dos veces, el índice `ix_stock_movimientos_consumo_unico` impide
descontar dos veces el mismo repuesto de la misma orden.

REORDEN (decisión 12)
---------------------
Tras cada movimiento se revisan solo los repuestos tocados: con el stock **estrictamente** bajo el
mínimo se crea una alerta de reorden (una vigente por repuesto); al volver a igualarlo o superarlo,
se resuelve sola.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.core.cursor import Cursor
from app.models.orden_trabajo import ABIERTOS, OrdenTrabajo
from app.models.prediccion import VIGENTES_REORDEN, AlertaSistema
from app.models.repuesto import OrdenRepuesto, Repuesto, StockMovimiento
from app.services.ordenes import Actor, Conflicto, exigir_activo
from app.services.ordenes import obtener as obtener_orden

CAMPOS_EDITABLES = ("nombre", "stock_minimo", "costo_unitario", "activo")


class RepuestoNoEncontrado(Exception):
    """No existe o es de otra empresa (404)."""


class StockInsuficiente(Conflicto):
    """El cierre no puede descontar alguna línea: 409 `stock_insuficiente` con los faltantes."""

    def __init__(self, faltantes: list[dict[str, Any]]) -> None:
        detalle = ", ".join(
            f"{f['nombre']} ({f['codigo']}): hay {f['disponible']}, se necesitan {f['requerido']}"
            for f in faltantes
        )
        super().__init__(
            "stock_insuficiente",
            f"No hay stock para cerrar la orden. Falta: {detalle}.",
            extra={"faltantes": faltantes},
        )
        self.faltantes = faltantes


@dataclass(frozen=True)
class Linea:
    repuesto_id: UUID
    codigo: str
    nombre: str
    cantidad: int
    stock_actual: int
    costo_unitario: Decimal


# --- Catálogo -------------------------------------------------------------------------------


async def obtener(session: AsyncSession, repuesto_id: UUID, *, bloquear: bool = False) -> Repuesto:
    consulta = select(Repuesto).where(Repuesto.id == repuesto_id)
    if bloquear:
        consulta = consulta.with_for_update()
    repuesto: Repuesto | None = await session.scalar(
        consulta.execution_options(populate_existing=True)
    )
    if repuesto is None:
        raise RepuestoNoEncontrado(str(repuesto_id))
    return repuesto


async def listar(
    session: AsyncSession,
    *,
    buscar: str | None,
    bajo_minimo: bool,
    incluir_inactivos: bool,
    cursor: Cursor | None,
    limite: int,
) -> tuple[list[Repuesto], Cursor | None]:
    """Por código. El cursor es (código, id), como una paginación por nombre."""
    consulta = select(Repuesto)
    if not incluir_inactivos:
        consulta = consulta.where(Repuesto.activo.is_(True))
    if bajo_minimo:
        consulta = consulta.where(Repuesto.stock_actual < Repuesto.stock_minimo)
    if buscar:
        patron = f"%{buscar.lower()}%"
        consulta = consulta.where(
            or_(func.lower(Repuesto.nombre).like(patron), func.lower(Repuesto.codigo).like(patron))
        )
    if cursor is not None:
        consulta = consulta.where(
            or_(
                Repuesto.codigo > cursor.valor,
                and_(Repuesto.codigo == cursor.valor, Repuesto.id > cursor.id),
            )
        )
    consulta = consulta.order_by(Repuesto.codigo, Repuesto.id).limit(limite + 1)
    filas = list((await session.scalars(consulta)).all())
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], Cursor(ultima.codigo, ultima.id)


def _asiento(
    actor: Actor,
    repuesto: Repuesto,
    *,
    tipo: str,
    delta: int,
    orden_id: UUID | None = None,
    nota: str | None = None,
) -> StockMovimiento:
    return StockMovimiento(
        empresa_id=actor.empresa_id,
        repuesto_id=repuesto.id,
        tipo=tipo,
        delta=delta,
        stock_resultante=repuesto.stock_actual,
        costo_unitario=repuesto.costo_unitario,
        orden_id=orden_id,
        usuario_id=actor.usuario_id,
        nota=nota,
    )


async def crear(
    session: AsyncSession,
    actor: Actor,
    *,
    nombre: str,
    codigo: str,
    stock_inicial: int,
    stock_minimo: int,
    costo_unitario: Decimal,
) -> Repuesto:
    """Alta (administrador). Si hay stock inicial, el libro lo registra como `inicial`."""
    await exigir_activo(session, actor)
    repuesto = Repuesto(
        empresa_id=actor.empresa_id,
        nombre=nombre,
        codigo=codigo,
        stock_actual=stock_inicial,
        stock_minimo=stock_minimo,
        costo_unitario=costo_unitario,
    )
    try:
        async with session.begin_nested():
            session.add(repuesto)
            await session.flush()
    except IntegrityError as exc:
        if "uq_repuestos_codigo" in str(exc.orig):
            raise Conflicto(
                "codigo_repuesto_duplicado", f"Ya existe un repuesto con el código {codigo}."
            ) from exc
        raise
    if stock_inicial > 0:
        session.add(_asiento(actor, repuesto, tipo="inicial", delta=stock_inicial))
        await session.flush()
    await revisar_reorden(session, actor.empresa_id, [repuesto.id])
    return repuesto


async def editar(
    session: AsyncSession, actor: Actor, repuesto_id: UUID, cambios: dict[str, Any]
) -> Repuesto:
    """Nombre, mínimo, costo y activo (administrador). Nunca el stock: ese lo mueve el libro."""
    await exigir_activo(session, actor)
    repuesto = await obtener(session, repuesto_id)
    for campo, valor in cambios.items():
        if campo in CAMPOS_EDITABLES:
            setattr(repuesto, campo, valor)
    await session.flush()
    if "stock_minimo" in cambios:
        await revisar_reorden(session, actor.empresa_id, [repuesto.id])
    return repuesto


async def ingreso(
    session: AsyncSession, actor: Actor, repuesto_id: UUID, cantidad: int, nota: str | None
) -> Repuesto:
    """Entrada de mercancía (supervisor o administrador). La suma es atómica."""
    await exigir_activo(session, actor)
    resultado = await session.execute(
        update(Repuesto)
        .where(Repuesto.id == repuesto_id)
        .values(stock_actual=Repuesto.stock_actual + cantidad)
        .returning(Repuesto.id)
        .execution_options(synchronize_session=False)
    )
    if resultado.scalar() is None:
        raise RepuestoNoEncontrado(str(repuesto_id))
    repuesto = await obtener(session, repuesto_id)
    session.add(_asiento(actor, repuesto, tipo="ingreso", delta=cantidad, nota=nota))
    await session.flush()
    await revisar_reorden(session, actor.empresa_id, [repuesto_id])
    registro.evento("inventario.ingreso")
    return repuesto


async def ajustar(
    session: AsyncSession, actor: Actor, repuesto_id: UUID, conteo: int, nota: str
) -> Repuesto:
    """Conteo físico (solo administrador, con nota). Bloquea el repuesto, fija el stock contado y
    asienta la diferencia; si el conteo coincide con el sistema, no asienta nada."""
    await exigir_activo(session, actor)
    repuesto = await obtener(session, repuesto_id, bloquear=True)
    antes = repuesto.stock_actual
    if conteo == antes:
        return repuesto
    repuesto.stock_actual = conteo
    await session.flush()
    session.add(_asiento(actor, repuesto, tipo="ajuste", delta=conteo - antes, nota=nota))
    await session.flush()
    await revisar_reorden(session, actor.empresa_id, [repuesto_id])
    registro.evento("inventario.ajuste")
    return repuesto


async def movimientos(
    session: AsyncSession, repuesto_id: UUID, *, cursor: Cursor | None, limite: int
) -> tuple[list[StockMovimiento], Cursor | None]:
    await obtener(session, repuesto_id)
    consulta = select(StockMovimiento).where(StockMovimiento.repuesto_id == repuesto_id)
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(
                StockMovimiento.creado_en < instante,
                and_(StockMovimiento.creado_en == instante, StockMovimiento.id < cursor.id),
            )
        )
    consulta = consulta.order_by(StockMovimiento.creado_en.desc(), StockMovimiento.id.desc()).limit(
        limite + 1
    )
    filas = list((await session.scalars(consulta)).all())
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], Cursor.de_instante(ultima.creado_en, ultima.id)


async def conciliacion(session: AsyncSession) -> list[dict[str, Any]]:
    """Repuestos cuyo stock no es la suma de su libro (6.6). Debe devolver una lista vacía."""
    suma = func.coalesce(func.sum(StockMovimiento.delta), 0)
    filas = await session.execute(
        select(Repuesto.id, Repuesto.codigo, Repuesto.stock_actual, suma.label("suma_libro"))
        .outerjoin(
            StockMovimiento,
            and_(
                StockMovimiento.empresa_id == Repuesto.empresa_id,
                StockMovimiento.repuesto_id == Repuesto.id,
            ),
        )
        .group_by(Repuesto.id, Repuesto.codigo, Repuesto.stock_actual)
        .having(Repuesto.stock_actual != suma)
    )
    return [
        {
            "repuesto_id": f.id,
            "codigo": f.codigo,
            "stock_actual": f.stock_actual,
            "suma_libro": int(f.suma_libro),
        }
        for f in filas
    ]


# --- Reorden (RF-26) --------------------------------------------------------------------------


async def revisar_reorden(session: AsyncSession, empresa_id: UUID, ids: list[UUID]) -> None:
    """Crea la alerta de los repuestos bajo el mínimo y resuelve la de los que ya no lo están."""
    if not ids:
        return
    bajos = (
        await session.scalars(
            select(Repuesto).where(
                Repuesto.id.in_(ids), Repuesto.stock_actual < Repuesto.stock_minimo
            )
        )
    ).all()
    for repuesto in bajos:
        vigente = await session.scalar(
            select(AlertaSistema.id).where(
                AlertaSistema.tipo == "reorden",
                AlertaSistema.repuesto_id == repuesto.id,
                AlertaSistema.estado.in_(VIGENTES_REORDEN),
            )
        )
        if vigente is not None:
            continue
        try:
            async with session.begin_nested():
                session.add(
                    AlertaSistema(
                        empresa_id=empresa_id,
                        tipo="reorden",
                        repuesto_id=repuesto.id,
                        stock_al_alertar=repuesto.stock_actual,
                        stock_minimo_al_alertar=repuesto.stock_minimo,
                    )
                )
                await session.flush()
        except IntegrityError:
            continue  # otra transacción la creó: una sola vigente
    await session.execute(
        update(AlertaSistema)
        .where(
            AlertaSistema.tipo == "reorden",
            AlertaSistema.estado.in_(VIGENTES_REORDEN),
            AlertaSistema.repuesto_id.in_(
                select(Repuesto.id).where(
                    Repuesto.id.in_(ids), Repuesto.stock_actual >= Repuesto.stock_minimo
                )
            ),
        )
        .values(estado="resuelta", gestionada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


# --- Líneas de repuestos de una orden (RF-24) ---------------------------------------------------


async def _orden(session: AsyncSession, orden_id: UUID) -> OrdenTrabajo:
    return await obtener_orden(session, orden_id)


async def lineas(session: AsyncSession, orden_id: UUID) -> list[Linea]:
    await _orden(session, orden_id)
    filas = await session.execute(
        select(
            OrdenRepuesto.repuesto_id,
            Repuesto.codigo,
            Repuesto.nombre,
            OrdenRepuesto.cantidad,
            Repuesto.stock_actual,
            Repuesto.costo_unitario,
        )
        .join(
            Repuesto,
            and_(
                Repuesto.empresa_id == OrdenRepuesto.empresa_id,
                Repuesto.id == OrdenRepuesto.repuesto_id,
            ),
        )
        .where(OrdenRepuesto.orden_id == orden_id)
        .order_by(Repuesto.codigo)
    )
    return [Linea(*f) for f in filas]


def _orden_cerrada(orden: OrdenTrabajo) -> Conflicto:
    return Conflicto(
        "estado_cambiado",
        "La orden ya no está abierta: sus repuestos no se pueden cambiar.",
        orden_id=orden.id,
        numero=orden.numero,
    )


async def guardar_linea(
    session: AsyncSession, actor: Actor, orden_id: UUID, repuesto_id: UUID, cantidad: int
) -> None:
    """Agrega o corrige un repuesto de una orden abierta: un repuesto aparece una vez por orden y
    corregir es volver a guardar la cantidad. El trigger de la base rechaza órdenes cerradas."""
    await exigir_activo(session, actor)
    orden = await _orden(session, orden_id)
    if orden.estado not in ABIERTOS:
        raise _orden_cerrada(orden)
    repuesto = await obtener(session, repuesto_id)
    if not repuesto.activo:
        raise RepuestoNoEncontrado(str(repuesto_id))
    actualizar = (
        update(OrdenRepuesto)
        .where(OrdenRepuesto.orden_id == orden_id, OrdenRepuesto.repuesto_id == repuesto_id)
        .values(cantidad=cantidad, registrado_por=actor.usuario_id)
        .execution_options(synchronize_session=False)
    )
    if (await session.execute(actualizar)).rowcount:
        return
    try:
        async with session.begin_nested():
            session.add(
                OrdenRepuesto(
                    empresa_id=actor.empresa_id,
                    orden_id=orden_id,
                    repuesto_id=repuesto_id,
                    cantidad=cantidad,
                    registrado_por=actor.usuario_id,
                )
            )
            await session.flush()
    except IntegrityError as exc:
        if "check_violation" in str(exc.orig) or "no se pueden modificar" in str(exc.orig):
            raise _orden_cerrada(orden) from exc
        await session.execute(actualizar)


async def quitar_linea(
    session: AsyncSession, actor: Actor, orden_id: UUID, repuesto_id: UUID
) -> None:
    await exigir_activo(session, actor)
    orden = await _orden(session, orden_id)
    if orden.estado not in ABIERTOS:
        raise _orden_cerrada(orden)
    linea = await session.get(OrdenRepuesto, (actor.empresa_id, orden_id, repuesto_id))
    if linea is not None:
        await session.delete(linea)
        await session.flush()


async def consumir(session: AsyncSession, actor: Actor, orden: OrdenTrabajo) -> list[UUID]:
    """El descuento del cierre (6.5). Devuelve los repuestos descontados.

    1. Bloquea los repuestos de la orden en orden de id.
    2. Con las filas bloqueadas, sus existencias ya no cambian hasta el commit: si alguna línea no
       alcanza, `StockInsuficiente` antes de descontar nada, y la excepción revierte el cierre.
    3. Descuenta cada línea con un UPDATE condicionado a que el stock alcance, y la asienta.
    """
    ids_lineas = select(OrdenRepuesto.repuesto_id).where(OrdenRepuesto.orden_id == orden.id)
    await session.execute(
        select(Repuesto.id)
        .where(Repuesto.id.in_(ids_lineas))
        .order_by(Repuesto.id)
        .with_for_update()
    )
    filas = (
        await session.execute(
            select(
                OrdenRepuesto.repuesto_id,
                OrdenRepuesto.cantidad,
                Repuesto.codigo,
                Repuesto.nombre,
                Repuesto.stock_actual,
            )
            .join(
                Repuesto,
                and_(
                    Repuesto.empresa_id == OrdenRepuesto.empresa_id,
                    Repuesto.id == OrdenRepuesto.repuesto_id,
                ),
            )
            .where(OrdenRepuesto.orden_id == orden.id)
            .order_by(OrdenRepuesto.repuesto_id)
        )
    ).all()
    faltantes = [
        {
            "codigo": f.codigo,
            "nombre": f.nombre,
            "disponible": f.stock_actual,
            "requerido": f.cantidad,
        }
        for f in filas
        if f.stock_actual < f.cantidad
    ]
    if faltantes:
        raise StockInsuficiente(sorted(faltantes, key=lambda f: str(f["codigo"])))
    descontados: list[UUID] = []
    for repuesto_id, cantidad, *_ in filas:
        resultado = await session.execute(
            update(Repuesto)
            .where(Repuesto.id == repuesto_id, Repuesto.stock_actual >= cantidad)
            .values(stock_actual=Repuesto.stock_actual - cantidad)
            .returning(Repuesto.id)
            .execution_options(synchronize_session=False)
        )
        if resultado.scalar() is None:
            continue
        repuesto = await obtener(session, repuesto_id)
        session.add(_asiento(actor, repuesto, tipo="consumo", delta=-cantidad, orden_id=orden.id))
        descontados.append(repuesto_id)
    if len(descontados) < len(filas):
        # Imposible con las filas bloqueadas; si ocurriera, mejor revertir que cerrar a medias.
        raise StockInsuficiente([])
    await session.flush()
    await revisar_reorden(session, actor.empresa_id, descontados)
    if descontados:
        registro.evento("inventario.consumo", lineas=len(descontados))
    return descontados
