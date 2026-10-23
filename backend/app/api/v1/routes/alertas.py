"""Alertas de campo: reporte, bandeja y revisión (RF-09; 05-fase2-activos-y-campo.md, 5.2)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from app.api.v1.comun import CursorDePagina, LimiteCampo, LimiteDePagina, http_de_captura
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import Pagina
from app.schemas.campo import AlertaCrear, AlertaOut, AlertaRegistrada, AlertaRevisar
from app.services import alertas
from app.services.capturas import CapturaInvalida
from app.services.prediccion import tareas

router = APIRouter(tags=["campo"])

Reporta = Annotated[Claims, Depends(requiere_roles(Rol.OPERARIO, Rol.SUPERVISOR))]
#: El técnico de taller no está: trabaja sobre órdenes (fase 3), no sobre la bandeja de alertas.
VeBandeja = Annotated[
    Claims,
    Depends(requiere_roles(Rol.OPERARIO, Rol.SUPERVISOR, Rol.ADMINISTRADOR, Rol.GERENTE)),
]
Revisa = Annotated[Claims, Depends(requiere_roles(Rol.SUPERVISOR, Rol.ADMINISTRADOR))]


@router.post("/activos/{activo_id}/alertas", response_model=AlertaRegistrada)
async def reportar(
    activo_id: UUID,
    datos: AlertaCrear,
    claims: Reporta,
    __: LimiteCampo,
    session: SesionDB,
    response: Response,
    tareas_fondo: BackgroundTasks,
) -> AlertaRegistrada:
    """201 si se creó; 200 si ya existía (un reintento, o la misma persona insistiendo)."""
    try:
        estado, alerta = await alertas.reportar(
            session,
            empresa_id=claims.empresa_id,
            autor_id=claims.usuario_id,
            activo_id=activo_id,
            sintoma=datos.sintoma,
            nota=datos.nota,
            capturado_en=datos.capturado_en,
            cliente_id=datos.cliente_id,
        )
    except CapturaInvalida as exc:
        raise http_de_captura(exc) from exc
    response.status_code = status.HTTP_201_CREATED if estado == "creado" else status.HTTP_200_OK
    # RF-20: las alertas de campo mueven el multiplicador del riesgo del equipo.
    tareas_fondo.add_task(tareas.tras_lectura, claims.empresa_id, activo_id)
    return AlertaRegistrada(estado=estado, alerta=AlertaOut.model_validate(alerta))


@router.get("/alertas", response_model=Pagina[AlertaOut])
async def listar(
    claims: VeBandeja,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
    estado: Literal["pendiente", "revisada", "descartada", "convertida_en_orden"] | None = None,
    activo_id: UUID | None = None,
) -> Pagina[AlertaOut]:
    """Un operario solo ve las alertas que reportó él (sección 5.2); los demás, las de la planta."""
    filas, siguiente = await alertas.listar(
        session,
        solo_de=claims.usuario_id if claims.rol is Rol.OPERARIO else None,
        estado=estado,
        activo_id=activo_id,
        cursor=cursor,
        limite=limite,
    )
    return Pagina[AlertaOut](
        items=[
            AlertaOut.model_validate(alerta).model_copy(
                update={"activo_nombre": nombre, "activo_codigo": codigo}
            )
            for alerta, nombre, codigo in filas
        ],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@router.patch("/alertas/{alerta_id}", response_model=AlertaOut)
async def revisar(
    alerta_id: UUID,
    datos: AlertaRevisar,
    claims: Revisa,
    session: SesionDB,
    tareas_fondo: BackgroundTasks,
) -> AlertaOut:
    try:
        alerta = await alertas.revisar(
            session, revisor_id=claims.usuario_id, alerta_id=alerta_id, estado=datos.estado
        )
    except alertas.AlertaNoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada.") from exc
    except alertas.TransicionNoPermitida as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esa alerta ya no está pendiente: otra persona la atendió."
        ) from exc
    tareas_fondo.add_task(tareas.tras_lectura, claims.empresa_id, alerta.activo_id)
    return AlertaOut.model_validate(alerta)
