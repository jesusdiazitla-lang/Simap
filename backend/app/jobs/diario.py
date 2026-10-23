"""Punto de entrada del job nocturno: `python -m app.jobs.diario` (07-fase4, 9.3).

En producción lo ejecuta un cron (Railway, a las 06:00 UTC = 02:00 en Santo Domingo, que no tiene
horario de verano). Termina con código distinto de cero si alguna empresa falló, para que el panel
del cron lo muestre como fallido. En local lo programa `app.jobs.programador` dentro del backend.
"""

from __future__ import annotations

import asyncio
import sys

from app.core import registro
from app.db.session import dispose_engine
from app.jobs.recalculo_riesgo import correr


async def _principal() -> int:
    try:
        resumen = await correr()
    finally:
        await dispose_engine()
    for empresa in resumen.empresas:
        estado = "saltada" if empresa.saltada else (empresa.error or "ok")
        print(
            f"{empresa.empresa_id}  {estado:<12} reajustados={empresa.reajustados} "
            f"riesgos={empresa.calculados} alertas+={empresa.alertas_creadas} "
            f"resueltas={empresa.alertas_resueltas} {empresa.duracion_ms} ms"
        )
    return 1 if resumen.fallidas else 0


def main() -> int:
    registro.configurar()
    return asyncio.run(_principal())


if __name__ == "__main__":
    sys.exit(main())
