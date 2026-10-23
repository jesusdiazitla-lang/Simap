"""Programa el job nocturno dentro del backend con APScheduler (opción local, sin cron externo).

Se activa con `JOB_DIARIO_EN_PROCESO=true`. Corre a la hora configurada en la zona de Santo
Domingo. El día que se despliegue, se apaga aquí y lo sustituye un cron que ejecuta
`python -m app.jobs.diario`: el trabajo es el mismo código.

Con varios procesos del backend, cada uno programaría su propia corrida; el candado por empresa
hace que dos corridas a la vez no trabajen la misma empresa, y el trabajo es idempotente.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core import registro
from app.core.config import get_settings
from app.jobs.recalculo_riesgo import correr


async def _corrida() -> None:
    try:
        await correr()
    except Exception as exc:  # noqa: BLE001 — el programador no debe morir por una corrida.
        registro.evento("job.corrida_fallida", error=type(exc).__name__)


def iniciar() -> AsyncIOScheduler:
    s = get_settings()
    programador = AsyncIOScheduler(timezone=s.job_zona_horaria)
    programador.add_job(
        _corrida,
        CronTrigger(hour=s.job_diario_hora, minute=0, timezone=s.job_zona_horaria),
        id="recalculo_diario",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    programador.start()
    registro.evento("job.programado", hora=s.job_diario_hora, zona=s.job_zona_horaria)
    return programador
