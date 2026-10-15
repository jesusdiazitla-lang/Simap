"""Máquina de estados de la orden de trabajo (RF-13; 06-fase3-ordenes-de-trabajo.md, 6.1 y 6.4).

    Reportada ──► En taller ──► Reparada ──► Cerrada
       │             ▲  │          │  │
       │             └──┼──────────┘  │      rechazo de cierre (nota obligatoria)
       └─────────────┴──┴─────────────┴──► Cancelada (con motivo)

Quién puede mover cada flecha lo exigen las rutas (`requiere_roles`), con la tabla 11.1 del
documento; aquí está **cuándo** se puede.

UNA SENTENCIA POR TRANSICIÓN
----------------------------
Cada transición es un UPDATE condicionado al estado de origen, sin SELECT previo ni bloqueos
explícitos (sección 6.4). Si el técnico la marca Reparada mientras el supervisor la cancela, la base
evalúa la condición en el instante en que escribe: una de las dos sentencias cambia la fila y la
otra no encuentra nada. La que no encuentra nada responde 409 explicando quién la movió, y 404 si la
orden no existe para esta empresa. La transición y su evento van en la misma transacción.

Cerrada y Cancelada son terminales: ninguna sentencia de aquí las tiene como origen, y además el
trigger `ot_inmutable` de la base rechaza cualquier cambio sobre ellas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos_dominio, registro
from app.models.alerta import Alerta
from app.models.orden_trabajo import ABIERTOS, OrdenTrabajo
from app.services.ordenes import (
    Actor,
    Conflicto,
    ahora,
    exigir_activo,
    explicar_cambio,
    obtener,
    registrar_evento,
)


async def _mover(
    session: AsyncSession,
    actor: Actor,
    orden_id: UUID,
    *,
    desde: str,
    hacia: str,
    valores: dict[str, Any] | None = None,
    nota: str | None = None,
    datos: dict[str, Any] | None = None,
) -> OrdenTrabajo:
    """El UPDATE condicionado y su evento.

    Cero filas: alguien se adelantó (409) o la orden no existe para esta empresa (404).
    """
    await exigir_activo(session, actor)
    resultado = await session.execute(
        update(OrdenTrabajo)
        .where(OrdenTrabajo.id == orden_id, OrdenTrabajo.estado == desde)
        .values(estado=hacia, **(valores or {}))
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount == 0:
        raise await explicar_cambio(session, orden_id)
    orden = await obtener(session, orden_id, refrescar=True)
    await registrar_evento(
        session,
        actor,
        orden,
        tipo="transicion",
        estado_anterior=desde,
        estado_nuevo=hacia,
        nota=nota,
        datos=datos,
    )
    registro.evento("ordenes.transicion", desde=desde, hacia=hacia)
    return orden


async def a_taller(session: AsyncSession, actor: Actor, orden_id: UUID) -> OrdenTrabajo:
    """Reportada a En taller: el equipo entra al taller. Técnico, supervisor o administrador."""
    return await _mover(
        session,
        actor,
        orden_id,
        desde="reportada",
        hacia="en_taller",
        valores={"en_taller_en": ahora()},
    )


async def marcar_reparada(
    session: AsyncSession,
    actor: Actor,
    orden_id: UUID,
    *,
    trabajo_realizado: str,
    tipo_intervencion: str,
) -> OrdenTrabajo:
    """En taller a Reparada. Solo el técnico de taller: «quién reparó» es siempre alguien con ese
    rol (sección 11.1). El tipo de intervención decide si el componente renueva su vida
    (decisión 4): solo `reemplazo` lo hace."""
    return await _mover(
        session,
        actor,
        orden_id,
        desde="en_taller",
        hacia="reparada",
        valores={
            "reparado_por": actor.usuario_id,
            "reparada_en": ahora(),
            "trabajo_realizado": trabajo_realizado,
            "tipo_intervencion": tipo_intervencion,
        },
        datos={"tipo_intervencion": tipo_intervencion},
    )


def minutos_fuera_de_servicio(fecha_falla: datetime, salida: datetime) -> int:
    """Tiempo de calendario de la falla a la autorización de salida (decisión 5, RF-15).

    No negativo: un `capturado_en` que llegó con el reloj del teléfono algo adelantado no produce un
    tiempo fuera de servicio imposible.
    """
    return max(0, int((salida - fecha_falla).total_seconds() // 60))


async def cerrar(
    session: AsyncSession, actor: Actor, orden_id: UUID, *, nota: str | None = None
) -> OrdenTrabajo:
    """Reparada a Cerrada: autoriza la salida del taller (supervisor o administrador).

    El tiempo fuera de servicio se calcula con la hora del servidor, no la del teléfono. Se lee
    `fecha_falla` antes del UPDATE sin riesgo: la aplicación no tiene permiso para modificarla.
    Tras el commit se publica `orden_cerrada`, que la fase 4 usará para reajustar el modelo.
    """
    previa = await obtener(session, orden_id)
    salida = ahora()
    minutos = minutos_fuera_de_servicio(previa.fecha_falla, salida)
    orden = await _mover(
        session,
        actor,
        orden_id,
        desde="reparada",
        hacia="cerrada",
        valores={
            "autorizado_por": actor.usuario_id,
            "fecha_salida_taller": salida,
            "tiempo_fuera_servicio_min": minutos,
        },
        nota=nota or None,
        datos={"tiempo_fuera_servicio_min": minutos},
    )
    eventos_dominio.emitir_al_confirmar(
        session,
        "orden_cerrada",
        empresa_id=orden.empresa_id,
        orden_id=orden.id,
        componente_id=orden.componente_id,
    )
    return orden


async def rechazar_cierre(
    session: AsyncSession, actor: Actor, orden_id: UUID, *, nota: str
) -> OrdenTrabajo:
    """Reparada vuelve a En taller, con nota obligatoria (supervisor o administrador).

    Lo que escribió el técnico no se pierde: el trabajo, el tipo y quién lo hizo pasan a los datos
    del evento, y las columnas se vacían para que la orden no muestre como hecho un trabajo
    rechazado. Cuando el técnico vuelva a marcarla Reparada se escriben de nuevo; la versión
    rechazada sigue en el historial.
    """
    previa = await obtener(session, orden_id)
    rechazado = {
        "trabajo_realizado": previa.trabajo_realizado,
        "tipo_intervencion": previa.tipo_intervencion,
        "reparado_por": previa.reparado_por,
        "reparada_en": previa.reparada_en,
    }
    orden = await _mover(
        session,
        actor,
        orden_id,
        desde="reparada",
        hacia="en_taller",
        valores={
            "trabajo_realizado": None,
            "tipo_intervencion": None,
            "reparado_por": None,
            "reparada_en": None,
        },
        nota=nota,
        datos={"rechazo_de_cierre": True, "trabajo_rechazado": rechazado},
    )
    registro.evento("ordenes.rechazo_de_cierre")
    return orden


async def cancelar(
    session: AsyncSession, actor: Actor, orden_id: UUID, *, motivo: str
) -> OrdenTrabajo:
    """Una orden abierta pasa a Cancelada, con motivo (supervisor o administrador; decisión 1).

    Para lo que se reportó por error o duplicado: no se puede borrar (RNF-06) y cerrarla inventaría
    una reparación que no ocurrió. Libera el componente (puede abrirse otra orden) y, si vino de una
    alerta, la devuelve a `revisada`.

    Puede venir de cualquiera de los tres estados abiertos, así que se lee cuál es y el UPDATE se
    condiciona a **ese**: si cambió entre la lectura y la escritura, 409 y nada se pisa.
    """
    previa = await obtener(session, orden_id)
    if previa.estado not in ABIERTOS:
        raise await explicar_cambio(session, orden_id)
    orden = await _mover(
        session,
        actor,
        orden_id,
        desde=previa.estado,
        hacia="cancelada",
        valores={"motivo_cancelacion": motivo},
        nota=motivo,
    )
    if orden.alerta_origen_id is not None:
        await session.execute(
            update(Alerta)
            .where(Alerta.id == orden.alerta_origen_id, Alerta.estado == "convertida_en_orden")
            .values(estado="revisada")
            .execution_options(synchronize_session=False)
        )
    return orden


__all__ = [
    "Conflicto",
    "a_taller",
    "cancelar",
    "cerrar",
    "marcar_reparada",
    "minutos_fuera_de_servicio",
    "rechazar_cierre",
]
