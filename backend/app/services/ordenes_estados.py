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

FASE 4 (07-fase4, 6.4 y 6.7)
----------------------------
El cierre descuenta los repuestos de la orden y marca su componente para reajustar el modelo, en la
misma transacción; si la orden nació de una alerta del sistema, la resuelve. Cancelar una orden
predictiva devuelve su alerta a `reconocida`. Una orden predictiva cuyo equipo falla antes de la
intervención se convierte en falla real (`convertir_en_falla`): deja de contar como censura.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos_dominio, registro
from app.models.activo import Activo
from app.models.alerta import Alerta
from app.models.orden_trabajo import ABIERTOS, OrdenTrabajo
from app.services import inventario
from app.services.capturas import validar_instante
from app.services.ordenes import (
    Actor,
    Conflicto,
    ReferenciaInvalida,
    ahora,
    exigir_activo,
    explicar_cambio,
    horas_acumuladas,
    obtener,
    registrar_evento,
)
from app.services.prediccion import ajuste, alertas


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
    `fecha_falla` antes del UPDATE sin riesgo: solo la cambia la conversión en falla, y esa exige
    una orden abierta.

    Fase 4 (6.7), en la misma transacción corta: descuento de los repuestos (409
    `stock_insuficiente` revierte el cierre entero), alerta del sistema resuelta y marca durable de
    reajuste. El reajuste en sí ocurre después del commit, en segundo plano.
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
    descontados = await inventario.consumir(session, actor, orden)
    if orden.alerta_sistema_id is not None:
        await alertas.resolver_por_cierre(session, orden.alerta_sistema_id)
    await ajuste.marcar(session, actor.empresa_id, orden.componente_id)
    if descontados:
        registro.evento("ordenes.cierre_con_repuestos", repuestos=len(descontados))
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
    if orden.alerta_sistema_id is not None:
        await alertas.reabrir_por_cancelacion(session, orden.alerta_sistema_id)
    return orden


async def convertir_en_falla(
    session: AsyncSession,
    actor: Actor,
    orden_id: UUID,
    *,
    horometro: int,
    fecha_falla: datetime,
) -> OrdenTrabajo:
    """La orden predictiva pasa a ser una falla real (07-fase4, 6.4; decisión 9).

    Si el equipo falla mientras se esperaba el repuesto, ese dato es una falla y no puede quedar
    como censura. Solo con la orden abierta y predictiva; una que ya es falla no se convierte otra
    vez (409 `estado_cambiado`). Las horas acumuladas usan el offset vigente en la fecha de la falla
    (F3, 5.1). El trigger `ot_datos_de_falla` solo deja reescribir dial, horas y fecha en esta
    misma escritura que apaga `es_predictiva`.
    """
    await exigir_activo(session, actor)
    validar_instante(fecha_falla, None)
    previa = await obtener(session, orden_id)
    activo = await session.scalar(select(Activo).where(Activo.id == previa.activo_id))
    assert activo is not None
    horas = await horas_acumuladas(session, activo, fecha_falla, horometro)
    if horas is None:
        raise ReferenciaInvalida(
            "No se sabe qué offset tenía el horómetro en esa fecha: revisa el reinicio del equipo."
        )
    resultado = await session.execute(
        update(OrdenTrabajo)
        .where(
            OrdenTrabajo.id == orden_id,
            OrdenTrabajo.es_predictiva.is_(True),
            OrdenTrabajo.estado.in_(ABIERTOS),
        )
        .values(
            es_predictiva=False,
            horometro_en_falla=horometro,
            horas_acumuladas_en_falla=horas,
            fecha_falla=fecha_falla,
        )
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount == 0:
        raise Conflicto(
            "estado_cambiado",
            "La orden ya no es predictiva o ya no está abierta: no se puede convertir en falla.",
            orden_id=previa.id,
            numero=previa.numero,
        )
    orden = await obtener(session, orden_id, refrescar=True)
    await registrar_evento(
        session,
        actor,
        orden,
        tipo="nota",
        nota="El equipo falló antes de la intervención: la orden pasa a ser una falla.",
        datos={
            "convertida_en_falla": True,
            "horometro": horometro,
            "horas_acumuladas": horas,
            "fecha_falla": fecha_falla,
        },
    )
    registro.evento("ordenes.convertida_en_falla")
    return orden


__all__ = [
    "Conflicto",
    "a_taller",
    "cancelar",
    "cerrar",
    "convertir_en_falla",
    "marcar_reparada",
    "minutos_fuera_de_servicio",
    "rechazar_cierre",
]
