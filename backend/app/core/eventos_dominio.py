"""Eventos de dominio en proceso, publicados solo después del commit (06-fase3, sección 12.3).

Al cerrar una orden, el módulo de órdenes avisa `orden_cerrada`. Hoy nadie escucha; en la fase 4 el
módulo de predicción se suscribirá para reajustar el modelo del componente. Es la frontera que pide
RNF-08: órdenes no importa nada de predicción, y los dos podrían separarse en servicios distintos.

DESPUÉS DEL COMMIT, NUNCA DENTRO
--------------------------------
El servicio no publica: **anota** el evento en la sesión (`emitir_al_confirmar`). Un oyente de
SQLAlchemy lo publica cuando la transacción se confirma y lo descarta si se revierte. Así:

- nadie reacciona a una orden cerrada que al final no se cerró (la transacción falló después);
- nada lento (el reajuste del modelo) ocurre con la fila de la orden bloqueada.

Un evento en memoria se pierde si el proceso cae justo después del commit. Por eso la fase 4 añade
una tarea diaria que busca órdenes cerradas aún no procesadas: este mecanismo es un atajo, no la
única vía.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core import registro

Oyente = Callable[[dict[str, Any]], None]

_CLAVE = "eventos_dominio_pendientes"
_oyentes: dict[str, list[Oyente]] = defaultdict(list)


def suscribir(nombre: str, oyente: Oyente) -> Callable[[], None]:
    """Registra un oyente y devuelve la función que lo da de baja (útil en las pruebas)."""
    _oyentes[nombre].append(oyente)
    return lambda: _oyentes[nombre].remove(oyente)


def emitir_al_confirmar(session: AsyncSession, nombre: str, **datos: Any) -> None:
    """Anota un evento para publicarlo cuando la transacción de `session` se confirme."""
    session.sync_session.info.setdefault(_CLAVE, []).append((nombre, datos))


@event.listens_for(Session, "after_commit")
def _publicar(session: Session) -> None:
    for nombre, datos in session.info.pop(_CLAVE, []):
        # También queda en el registro estructurado: es una métrica de negocio (sección 12.5).
        registro.evento(f"dominio.{nombre}", **{k: str(v) for k, v in datos.items()})
        for oyente in list(_oyentes[nombre]):
            try:
                oyente(datos)
            except Exception:  # noqa: BLE001 — un oyente roto no deshace un commit ya hecho.
                registro.evento("dominio.oyente_fallido", evento=nombre)


@event.listens_for(Session, "after_rollback")
def _descartar(session: Session) -> None:
    session.info.pop(_CLAVE, None)
