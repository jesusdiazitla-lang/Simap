"""Sincronización de la cola sin conexión (RF-10; 05-fase2-activos-y-campo.md, sección 5.3)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.comun import LimiteCampo
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.campo import LoteEntrada, LoteSalida
from app.services import campo

router = APIRouter(prefix="/campo", tags=["campo"])

Captura = Annotated[Claims, Depends(requiere_roles(Rol.OPERARIO, Rol.SUPERVISOR))]


@router.post("/lotes", response_model=LoteSalida)
async def lote(
    datos: LoteEntrada, claims: Captura, __: LimiteCampo, session: SesionDB
) -> LoteSalida:
    """Hasta 50 ítems. Siempre 200 con el resultado de cada uno: creado, duplicado o rechazado.

    Un lote nunca falla entero por un ítem malo; si lo hiciera, el teléfono no sabría cuál quitar
    de su cola y reenviaría el lote para siempre.
    """
    resultados = await campo.procesar_lote(
        session, empresa_id=claims.empresa_id, autor_id=claims.usuario_id, items=datos.items
    )
    return LoteSalida(resultados=resultados)
