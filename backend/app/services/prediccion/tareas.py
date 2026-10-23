"""Lo que corre después del commit, en segundo plano (07-fase4, sección 9; RNF-02).

Tres disparadores, cada uno suficiente por sí solo y cada uno cubre la falla de los otros:

- **Cada lectura de horómetro** (o falla reportada, reinicio, confirmación): recalcula ese equipo.
- **Cada cierre de orden**: reajusta el modelo de su componente y recalcula el equipo.
- **El job de las 02:00** (`app.jobs.diario`): reajusta lo pendiente y recalcula todo.

RNF-02: la lectura o el cierre ya están confirmados cuando esto empieza. La tarea abre su propia
sesión con el `empresa_id` que traía la petición, y si algo falla lo registra y termina: nunca
deshace un reporte. Una tarea perdida (el proceso cayó) solo cuesta horas de latencia en un riesgo:
la marca de reajuste sigue escrita y el job lo repite.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.db.deps import sesion_de_empresa
from app.services.prediccion import ajuste, configuracion, riesgo

#: Punto de inyección para las pruebas de RNF-02: si se le asigna una función, se llama al empezar
#: cada tarea y puede lanzar una excepción.
antes_de_calcular: Callable[[], None] | None = None


async def _proteger(nombre: str, empresa_id: UUID, trabajo: Callable[[], Awaitable[None]]) -> bool:
    """Ejecuta el trabajo; si falla, lo registra con la empresa y no lo propaga (RNF-02)."""
    try:
        if antes_de_calcular is not None:
            antes_de_calcular()
        await trabajo()
        return True
    except Exception as exc:  # noqa: BLE001 — la lectura ya está guardada: nada debe tumbarla.
        registro.evento(
            "prediccion.tarea_fallida",
            tarea=nombre,
            empresa_id=str(empresa_id),
            error=type(exc).__name__,
        )
        return False


async def tras_lectura(empresa_id: UUID, activo_id: UUID) -> bool:
    """Recalcula el riesgo de un solo equipo y sus alertas (RF-19)."""

    async def trabajo() -> None:
        async with sesion_de_empresa(empresa_id) as session:
            await riesgo.recalcular_y_alertar(session, empresa_id, activo_id)

    return await _proteger("tras_lectura", empresa_id, trabajo)


async def tras_cierre(empresa_id: UUID, componente_id: UUID, activo_id: UUID) -> bool:
    """Reajusta el modelo del componente y recalcula el equipo (6.7, paso 9).

    El modelo cambia para todos los equipos con ese componente; aquí solo se recalcula el de la
    orden, que es el que cambió de vida. Los demás los recalcula el job de la madrugada.
    """

    async def trabajo() -> None:
        async with sesion_de_empresa(empresa_id) as session:
            await ajuste.reajustar_componente(session, empresa_id, componente_id)
            await riesgo.recalcular_y_alertar(session, empresa_id, activo_id)

    return await _proteger("tras_cierre", empresa_id, trabajo)


@dataclass
class ResumenEmpresa:
    empresa_id: UUID
    saltada: bool = False
    reajustados: int = 0
    sin_convergencia: int = 0
    calculados: int = 0
    alertas_creadas: int = 0
    alertas_resueltas: int = 0
    duracion_ms: int = 0
    error: str | None = None


@dataclass
class ResumenJob:
    empresas: list[ResumenEmpresa] = field(default_factory=list)

    @property
    def fallidas(self) -> list[ResumenEmpresa]:
        return [e for e in self.empresas if e.error is not None]


async def trabajar_empresa(session: AsyncSession, empresa_id: UUID) -> ResumenEmpresa:
    """La pasada nocturna de una empresa, en una sesión con su tenant ya fijado (9.3).

    `asegurar_config`, reajustar lo que devuelve `a_reajustar`, recálculo de toda la empresa,
    alertas nuevas e histéresis. El candado y el tenant los pone quien llama.
    """
    resumen = ResumenEmpresa(empresa_id)
    inicio = time.perf_counter()
    await configuracion.asegurar(session, empresa_id)
    for pendiente in await ajuste.a_reajustar(session):
        modelo = await ajuste.reajustar(session, empresa_id, pendiente)
        if modelo is not None:
            resumen.reajustados += 1
            resumen.sin_convergencia += 0 if modelo["convergio"] else 1
    totales = await riesgo.recalcular_y_alertar(session, empresa_id)
    resumen.calculados = totales["calculados"]
    resumen.alertas_creadas = totales["alertas_creadas"]
    resumen.alertas_resueltas = totales["alertas_resueltas"]
    resumen.duracion_ms = int((time.perf_counter() - inicio) * 1000)
    return resumen


async def recalcular_empresa(empresa_id: UUID) -> bool:
    """Tras cambiar la configuración: el umbral o el horizonte mueven todos los riesgos."""

    async def trabajo() -> None:
        async with sesion_de_empresa(empresa_id) as session:
            await riesgo.recalcular_y_alertar(session, empresa_id)

    return await _proteger("recalcular_empresa", empresa_id, trabajo)


async def tras_ajuste_de_componente(empresa_id: UUID, componente_id: UUID) -> bool:
    """Tras declarar una edad o cambiar la vida nominal: reajusta y recalcula la empresa."""

    async def trabajo() -> None:
        async with sesion_de_empresa(empresa_id) as session:
            await ajuste.reajustar_componente(session, empresa_id, componente_id)
            await riesgo.recalcular_y_alertar(session, empresa_id)

    return await _proteger("tras_ajuste_de_componente", empresa_id, trabajo)
