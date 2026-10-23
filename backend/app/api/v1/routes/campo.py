"""Sincronización de la cola sin conexión (RF-10; 05-fase2-activos-y-campo.md, sección 5.3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.v1.comun import LimiteCampo
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.campo import LoteEntrada, LoteSalida
from app.services import campo
from app.services.prediccion import tareas

router = APIRouter(prefix="/campo", tags=["campo"])

Captura = Annotated[Claims, Depends(requiere_roles(Rol.OPERARIO, Rol.SUPERVISOR))]


@router.post("/lotes", response_model=LoteSalida)
async def lote(
    datos: LoteEntrada,
    claims: Captura,
    __: LimiteCampo,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
) -> LoteSalida:
    """Hasta 50 ítems. Siempre 200 con el resultado de cada uno: creado, duplicado o rechazado.

    Un lote nunca falla entero por un ítem malo; si lo hiciera, el teléfono no sabría cuál quitar
    de su cola y reenviaría el lote para siempre.
    """
    resultados = await campo.procesar_lote(
        session,
        empresa_id=claims.empresa_id,
        autor_id=claims.usuario_id,
        rol=claims.rol.value,
        items=datos.items,
    )
    # Un recálculo por equipo tocado, después del commit (F4, 9.2).
    # Los ítems llegan sin validar: un `activo_id` ilegible ya volvió como rechazado.
    tocados: dict[UUID, None] = {}
    for crudo in datos.items:
        try:
            tocados[UUID(str(crudo.get("activo_id")))] = None
        except ValueError:
            continue
    for activo_id in tocados:
        tareas_fondo.add_task(tareas.tras_lectura, claims.empresa_id, activo_id)
    return LoteSalida(resultados=resultados)
