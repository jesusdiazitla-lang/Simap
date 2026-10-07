"""Reglas comunes a todo lo que se captura en campo: lecturas y alertas (RF-08, RF-09).

Las dos comparten las mismas preguntas antes de guardar nada: ¿el instante que dice el teléfono es
creíble?, ¿el equipo existe, es de esta empresa y sigue en servicio? Viven aquí para que la
respuesta sea la misma por cualquier camino: una petición individual o un ítem de un lote que llegó
horas después (05-fase2-activos-y-campo.md, sección 5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.activo import Activo


class CapturaInvalida(Exception):
    """El dato no se puede aceptar. El mensaje se muestra tal cual a quien lo capturó."""


class ActivoNoDisponible(CapturaInvalida):
    """El equipo no existe, es de otra empresa o está dado de baja.

    «No existe» y «es de otra empresa» dan el mismo mensaje a propósito: distinguirlos confirmaría
    que ese identificador pertenece a alguien. «Dado de baja» sí se distingue (`existe=True`): quien
    pregunta ya ve ese equipo, y saber que está de baja es lo que le explica qué pasa.
    """

    def __init__(self, mensaje: str, *, existe: bool) -> None:
        super().__init__(mensaje)
        self.existe = existe


def validar_instante(capturado_en: datetime, ahora: datetime | None = None) -> None:
    """Rechaza un `capturado_en` imposible (sección 5.1).

    - Más de unos minutos en el futuro: el reloj del teléfono está mal, y una lectura «de mañana»
      quedaría para siempre como la última del equipo.
    - Más antiguo que la ventana admitida: un ítem olvidado semanas en una cola sin conexión ya no
      describe el estado del equipo, y colarlo reescribiría su historia.
    """
    s = get_settings()
    momento = ahora or datetime.now(UTC)
    if capturado_en > momento + timedelta(minutes=s.captura_tolerancia_futuro_minutos):
        raise CapturaInvalida(
            "La hora de captura está en el futuro. Revisa la fecha y hora del teléfono."
        )
    if capturado_en < momento - timedelta(days=s.captura_antiguedad_max_dias):
        raise CapturaInvalida(
            f"El dato tiene más de {s.captura_antiguedad_max_dias} días y ya no se acepta."
        )


async def activo_en_servicio(session: AsyncSession, activo_id: UUID) -> Activo:
    """El equipo, si existe, es de la empresa de la sesión y no está dado de baja.

    La consulta pasa por RLS: un equipo de otra empresa no aparece, igual que uno inexistente.
    """
    activo: Activo | None = await session.scalar(select(Activo).where(Activo.id == activo_id))
    if activo is None:
        raise ActivoNoDisponible("Ese equipo no existe.", existe=False)
    if activo.estado != "activo":
        raise ActivoNoDisponible(
            "Ese equipo está dado de baja y ya no admite registros.", existe=True
        )
    return activo
