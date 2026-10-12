"""Lecturas de horómetro de un equipo (RF-08; 05-fase2-activos-y-campo.md, sección 5.1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.v1.comun import CursorDePagina, LimiteCampo, LimiteDePagina, http_de_captura
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import Pagina
from app.schemas.campo import (
    LecturaCrear,
    LecturaOut,
    LecturaPorRevisar,
    LecturaRegistrada,
    LecturaResolver,
)
from app.services import activos, lecturas
from app.services.capturas import CapturaInvalida

router = APIRouter(prefix="/activos/{activo_id}/lecturas", tags=["campo"])

Registra = Annotated[Claims, Depends(requiere_roles(Rol.OPERARIO, Rol.SUPERVISOR))]
Consulta = Annotated[
    Claims, Depends(requiere_roles(Rol.SUPERVISOR, Rol.ADMINISTRADOR, Rol.GERENTE))
]


@router.post("", response_model=LecturaRegistrada)
async def registrar(
    activo_id: UUID,
    datos: LecturaCrear,
    claims: Registra,
    __: LimiteCampo,
    session: SesionDB,
    response: Response,
) -> LecturaRegistrada:
    """Registra una lectura. Idempotente por `cliente_id`.

    201 si se creó, 200 si ya existía: un reintento recibe la misma lectura que entró la primera
    vez, y el teléfono la da por entregada. Una lectura que no cuadra también es un 201 —se guarda—,
    pero vuelve con `requiere_revision` y su motivo para que la pantalla lo diga.
    """
    try:
        estado, lectura = await lecturas.registrar(
            session,
            empresa_id=claims.empresa_id,
            autor_id=claims.usuario_id,
            activo_id=activo_id,
            valor=datos.valor,
            capturado_en=datos.capturado_en,
            cliente_id=datos.cliente_id,
        )
    except CapturaInvalida as exc:
        raise http_de_captura(exc) from exc
    response.status_code = status.HTTP_201_CREATED if estado == "creado" else status.HTTP_200_OK
    return LecturaRegistrada(estado=estado, lectura=LecturaOut.model_validate(lectura))


@router.get("", response_model=Pagina[LecturaOut])
async def listar(
    activo_id: UUID,
    _: Consulta,
    session: SesionDB,
    cursor: CursorDePagina,
    limite: LimiteDePagina,
) -> Pagina[LecturaOut]:
    """Historial del equipo, de la más reciente a la más antigua según cuándo se capturó."""
    try:
        await activos.obtener(session, activo_id)
    except activos.ActivoNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipo no encontrado.") from exc
    filas, siguiente = await lecturas.listar(
        session, activo_id=activo_id, cursor=cursor, limite=limite
    )
    return Pagina[LecturaOut](
        items=[LecturaOut.model_validate(f) for f in filas],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


# --- Revisión de lecturas marcadas (revisión 0006) ------------------------------

revision = APIRouter(prefix="/lecturas", tags=["campo"])

Revisa = Annotated[Claims, Depends(requiere_roles(Rol.SUPERVISOR, Rol.ADMINISTRADOR))]


@revision.get("/por-revisar", response_model=Pagina[LecturaPorRevisar])
async def por_revisar(
    _: Revisa, session: SesionDB, cursor: CursorDePagina, limite: LimiteDePagina
) -> Pagina[LecturaPorRevisar]:
    """Lecturas que no cuadraban y nadie ha resuelto. Mientras lo estén, no mueven el horómetro."""
    filas, siguiente = await lecturas.por_revisar(session, cursor=cursor, limite=limite)
    return Pagina[LecturaPorRevisar](
        items=[
            LecturaPorRevisar.model_validate(
                {
                    **LecturaOut.model_validate(lectura).model_dump(),
                    "activo_nombre": nombre,
                    "activo_codigo": codigo,
                    "horometro_vigente": vigente,
                }
            )
            for lectura, nombre, codigo, vigente in filas
        ],
        next_cursor=siguiente.codificar() if siguiente else None,
    )


@revision.patch("/{lectura_id}", response_model=LecturaOut)
async def resolver(
    lectura_id: UUID, datos: LecturaResolver, claims: Revisa, session: SesionDB
) -> LecturaOut:
    """Confirmar o descartar: supervisor o administrador. Reinicio de horómetro: solo administrador,
    porque cambia la serie de horas sobre la que la fase 4 calcula el riesgo (sección 5.1)."""
    if datos.resolucion == "reinicio" and claims.rol is not Rol.ADMINISTRADOR:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo el administrador puede registrar un reinicio del horómetro.",
        )
    try:
        lectura = await lecturas.resolver(
            session,
            revisor_id=claims.usuario_id,
            lectura_id=lectura_id,
            resolucion=datos.resolucion,
        )
    except lecturas.LecturaNoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lectura no encontrada.") from exc
    except lecturas.YaResuelta as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esa lectura ya no está pendiente de revisión; quizá otra persona la resolvió.",
        ) from exc
    return LecturaOut.model_validate(lectura)
