"""Bandeja de alertas del sistema y orden predictiva (RF-21; 07-fase4, secciones 6.3 y 6.4).

Estados de una alerta:

    activa ──► reconocida ──► atendida ──► resuelta
      │            │              │ (cancelar la orden: vuelve a reconocida)
      └────────────┴──► descartada (con nota; silencia el componente unos días)
      └────────────┴──► resuelta (histéresis: el riesgo bajó del 80 % del umbral)

Cada acción es un UPDATE condicionado al estado de origen: quien llega tarde a algo que otra persona
ya gestionó recibe 409 `alerta_no_disponible`, no un cambio doble.

LA ORDEN PREDICTIVA
-------------------
Desde una alerta activa o reconocida se crea una orden con `es_predictiva`: se cambia la pieza antes
de que falle. Equipo y componente salen de la alerta y las horas de la ficha del equipo; nada de eso
viene del cuerpo de la petición. Para el modelo, solo un **reemplazo** predictivo cuenta, y cuenta
como censura: la vida termina sin falla (decisión 8). Contarlo como falla hundiría la vida estimada
al 2 % de la real (sección 14.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.core.cursor import Cursor
from app.models.activo import Activo
from app.models.componente import Componente
from app.models.orden_trabajo import OrdenTrabajo
from app.models.prediccion import AlertaSistema
from app.models.repuesto import Repuesto
from app.services.ordenes import (
    Actor,
    Conflicto,
    conflicto_abierta,
    exigir_activo,
    registrar_evento,
    siguiente_numero,
)


class AlertaNoEncontrada(Exception):
    """No existe o es de otra empresa (404)."""


@dataclass(frozen=True)
class FilaAlerta:
    alerta: AlertaSistema
    activo_nombre: str | None
    componente_nombre: str | None
    repuesto_nombre: str | None
    repuesto_codigo: str | None
    orden_id: UUID | None
    orden_numero: int | None


def _no_disponible(mensaje: str = "Esa alerta ya la gestionó otra persona.") -> Conflicto:
    return Conflicto("alerta_no_disponible", mensaje)


async def obtener(session: AsyncSession, alerta_id: UUID) -> AlertaSistema:
    alerta: AlertaSistema | None = await session.scalar(
        select(AlertaSistema)
        .where(AlertaSistema.id == alerta_id)
        .execution_options(populate_existing=True)
    )
    if alerta is None:
        raise AlertaNoEncontrada(str(alerta_id))
    return alerta


def _consulta_bandeja() -> Any:
    return (
        select(
            AlertaSistema,
            Activo.nombre,
            Componente.nombre,
            Repuesto.nombre,
            Repuesto.codigo,
            OrdenTrabajo.id,
            OrdenTrabajo.numero,
        )
        .outerjoin(
            Activo,
            and_(
                Activo.empresa_id == AlertaSistema.empresa_id, Activo.id == AlertaSistema.activo_id
            ),
        )
        .outerjoin(
            Componente,
            and_(
                Componente.empresa_id == AlertaSistema.empresa_id,
                Componente.id == AlertaSistema.componente_id,
            ),
        )
        .outerjoin(
            Repuesto,
            and_(
                Repuesto.empresa_id == AlertaSistema.empresa_id,
                Repuesto.id == AlertaSistema.repuesto_id,
            ),
        )
        .outerjoin(
            OrdenTrabajo,
            and_(
                OrdenTrabajo.empresa_id == AlertaSistema.empresa_id,
                OrdenTrabajo.alerta_sistema_id == AlertaSistema.id,
                OrdenTrabajo.estado != "cancelada",
            ),
        )
    )


async def listar(
    session: AsyncSession,
    *,
    tipo: str | None,
    estados: tuple[str, ...],
    activo_id: UUID | None = None,
    cursor: Cursor | None,
    limite: int,
) -> tuple[list[FilaAlerta], Cursor | None]:
    """La bandeja, de la más reciente a la más antigua."""
    consulta = _consulta_bandeja().where(AlertaSistema.estado.in_(estados))
    if tipo is not None:
        consulta = consulta.where(AlertaSistema.tipo == tipo)
    if activo_id is not None:
        consulta = consulta.where(AlertaSistema.activo_id == activo_id)
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(
                AlertaSistema.creada_en < instante,
                and_(AlertaSistema.creada_en == instante, AlertaSistema.id < cursor.id),
            )
        )
    consulta = consulta.order_by(AlertaSistema.creada_en.desc(), AlertaSistema.id.desc()).limit(
        limite + 1
    )
    filas = [FilaAlerta(*f) for f in await session.execute(consulta)]
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1].alerta
    return filas[:limite], Cursor.de_instante(ultima.creada_en, ultima.id)


async def fila(session: AsyncSession, alerta_id: UUID) -> FilaAlerta:
    resultado = (
        await session.execute(_consulta_bandeja().where(AlertaSistema.id == alerta_id))
    ).first()
    if resultado is None:
        raise AlertaNoEncontrada(str(alerta_id))
    return FilaAlerta(*resultado)


async def _gestionar(
    session: AsyncSession,
    actor: Actor,
    alerta_id: UUID,
    *,
    desde: tuple[str, ...],
    hacia: str,
    solo_riesgo: bool = False,
    nota: str | None = None,
) -> AlertaSistema:
    await exigir_activo(session, actor)
    condiciones = [AlertaSistema.id == alerta_id, AlertaSistema.estado.in_(desde)]
    if solo_riesgo:
        condiciones.append(AlertaSistema.tipo == "riesgo")
    valores: dict[str, object] = {
        "estado": hacia,
        "gestionada_por": actor.usuario_id,
        "gestionada_en": datetime.now(UTC),
    }
    if nota is not None:
        valores["nota"] = nota
    resultado = await session.execute(
        update(AlertaSistema)
        .where(*condiciones)
        .values(**valores)
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount == 0:
        await obtener(session, alerta_id)  # 404 si no existe para esta empresa
        raise _no_disponible()
    registro.evento("prediccion.alerta_gestionada", hacia=hacia)
    return await obtener(session, alerta_id)


async def reconocer(session: AsyncSession, actor: Actor, alerta_id: UUID) -> AlertaSistema:
    """«La vi»: no cambia el riesgo ni deja de vigilar."""
    return await _gestionar(session, actor, alerta_id, desde=("activa",), hacia="reconocida")


async def descartar(
    session: AsyncSession, actor: Actor, alerta_id: UUID, nota: str
) -> AlertaSistema:
    """«No actuar ahora», con nota. Silencia el componente los días configurados; pasado el plazo,
    si el riesgo sigue alto, la siguiente corrida crea otra. Una alerta atendida (con orden) ya no
    se descarta: se gestiona desde su orden."""
    return await _gestionar(
        session,
        actor,
        alerta_id,
        desde=("activa", "reconocida"),
        hacia="descartada",
        solo_riesgo=True,
        nota=nota,
    )


async def crear_orden_predictiva(
    session: AsyncSession, actor: Actor, alerta_id: UUID, descripcion: str | None
) -> OrdenTrabajo:
    """Orden predictiva desde una alerta de riesgo (6.4), en una sola transacción.

    1. La alerta pasa a `atendida` con un UPDATE condicionado: cero filas es 409 (otra persona la
       tomó).
    2. Número del contador de la fase 3 y la orden, con `es_predictiva`, en un savepoint. Si el
       componente ya tiene una orden abierta, el índice único la rechaza: 409
       `orden_abierta_existente`, y la excepción revierte la transacción entera, alerta incluida.
    """
    alerta = await _gestionar(
        session,
        actor,
        alerta_id,
        desde=("activa", "reconocida"),
        hacia="atendida",
        solo_riesgo=True,
    )
    assert alerta.activo_id is not None and alerta.componente_id is not None
    activo = await session.scalar(select(Activo).where(Activo.id == alerta.activo_id))
    assert activo is not None
    porcentaje = float(alerta.riesgo or 0) * 100
    orden = OrdenTrabajo(
        empresa_id=actor.empresa_id,
        cliente_id=uuid4(),
        activo_id=alerta.activo_id,
        componente_id=alerta.componente_id,
        alerta_sistema_id=alerta.id,
        es_predictiva=True,
        reportado_por=actor.usuario_id,
        horometro_en_falla=activo.horometro_actual,
        horas_acumuladas_en_falla=activo.horometro_offset + activo.horometro_actual,
        descripcion=descripcion
        or f"Cambio planificado: riesgo de falla del {porcentaje:.0f} % en el horizonte.",
        fecha_falla=datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            orden.numero = await siguiente_numero(session, actor.empresa_id)
            session.add(orden)
            await session.flush()
    except IntegrityError as exc:
        if "ix_ordenes_trabajo_una_abierta_por_componente" in str(exc.orig):
            raise await conflicto_abierta(session, alerta.activo_id, alerta.componente_id) from exc
        if "ix_ordenes_trabajo_una_por_alerta_sistema" in str(exc.orig):
            raise _no_disponible("Esa alerta acaba de originar otra orden.") from exc
        raise
    await registrar_evento(
        session,
        actor,
        orden,
        tipo="creada",
        estado_nuevo="reportada",
        datos={
            "numero": orden.numero,
            "es_predictiva": True,
            "alerta_sistema_id": alerta.id,
            "riesgo": alerta.riesgo,
        },
    )
    registro.evento("prediccion.orden_predictiva")
    return orden


async def resolver_por_cierre(session: AsyncSession, alerta_id: UUID) -> None:
    """Al cerrar la orden predictiva, su alerta queda resuelta."""
    await session.execute(
        update(AlertaSistema)
        .where(AlertaSistema.id == alerta_id, AlertaSistema.estado == "atendida")
        .values(estado="resuelta", gestionada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


async def reabrir_por_cancelacion(session: AsyncSession, alerta_id: UUID) -> None:
    """Al cancelar la orden predictiva, la alerta vuelve a `reconocida` y sigue vigente."""
    await session.execute(
        update(AlertaSistema)
        .where(AlertaSistema.id == alerta_id, AlertaSistema.estado == "atendida")
        .values(estado="reconocida", gestionada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
