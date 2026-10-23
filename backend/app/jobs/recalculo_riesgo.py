"""Job nocturno de la fase 4: reajusta modelos y recalcula el riesgo de todas las empresas.

`docs/contexto/07-fase4-prediccion-e-inventario.md`, sección 9.3 (RF-21, RF-22).

- Se conecta como `job_user`: miembro de `app_user`, sujeto a RLS. Sin tenant no ve ninguna fila.
- Pide los ids con `empresas_activas()`, la única función que puede ejecutar y que no devuelve
  ningún otro dato.
- Cada empresa va en **su propia transacción**, con su tenant fijado y un candado consultivo: si
  otro proceso ya la está trabajando, la salta. Por eso el job escala lanzando varios procesos sin
  coordinarlos.
- Un fallo en una empresa se registra con su id y no detiene a las demás. `statement_timeout`
  impide que una consulta atascada se lleve la noche.
- El registro lleva ids, duraciones y contadores; nunca notas ni descripciones.
"""

from __future__ import annotations

import time

from app.core import registro
from app.core.config import get_settings
from app.db.deps import fijar_tenant, sesion_del_job
from app.db.session import get_estrategia_tenant, get_sessionmaker_job
from app.services.prediccion.tareas import ResumenEmpresa, ResumenJob, trabajar_empresa


async def correr() -> ResumenJob:
    """Una pasada completa. Devuelve el resumen; las empresas fallidas llevan su error."""
    estrategia = get_estrategia_tenant()
    timeout = get_settings().job_statement_timeout_ms
    inicio = time.perf_counter()
    async with sesion_del_job() as session:
        empresas = await estrategia.empresas_activas(session)
    resumen = ResumenJob()
    for empresa_id in empresas:
        try:
            async with get_sessionmaker_job()() as session, session.begin():
                await fijar_tenant(session, empresa_id)
                if not await estrategia.tomar_candado_empresa(session, empresa_id):
                    resumen.empresas.append(ResumenEmpresa(empresa_id, saltada=True))
                    continue
                await estrategia.limitar_duracion(session, timeout)
                parcial = await trabajar_empresa(session, empresa_id)
            resumen.empresas.append(parcial)
            registro.evento(
                "job.empresa",
                empresa_id=str(empresa_id),
                duracion_ms=parcial.duracion_ms,
                reajustados=parcial.reajustados,
                sin_convergencia=parcial.sin_convergencia,
                calculados=parcial.calculados,
                alertas_creadas=parcial.alertas_creadas,
                alertas_resueltas=parcial.alertas_resueltas,
            )
        except Exception as exc:  # noqa: BLE001 — una empresa rota no detiene a las demás.
            resumen.empresas.append(ResumenEmpresa(empresa_id, error=type(exc).__name__))
            registro.evento(
                "job.empresa_fallida", empresa_id=str(empresa_id), error=type(exc).__name__
            )
    registro.evento(
        "job.fin",
        empresas=len(resumen.empresas),
        fallidas=len(resumen.fallidas),
        duracion_ms=int((time.perf_counter() - inicio) * 1000),
    )
    return resumen
