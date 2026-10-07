"""Catálogo de componentes de la empresa (05-fase2-activos-y-campo.md, sección 5)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.comun import TODOS
from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.activo import ComponenteCrear, ComponenteEditar, ComponenteOut
from app.services import componentes as servicio

router = APIRouter(prefix="/componentes", tags=["componentes"])

Cualquiera = Annotated[Claims, Depends(requiere_roles(*TODOS))]
Administrador = Annotated[Claims, Depends(requiere_roles(Rol.ADMINISTRADOR))]

NOMBRE_REPETIDO = "Ya hay un componente con ese nombre en tu empresa."


@router.get("", response_model=list[ComponenteOut])
async def listar(
    claims: Cualquiera, session: SesionDB, incluir_inactivos: bool = False
) -> list[ComponenteOut]:
    """Solo activos. El administrador puede pedir también los desactivados, para reactivarlos."""
    ver_inactivos = incluir_inactivos and claims.rol is Rol.ADMINISTRADOR
    filas = await servicio.listar(session, incluir_inactivos=ver_inactivos)
    return [ComponenteOut.model_validate(c) for c in filas]


@router.post("", response_model=ComponenteOut, status_code=status.HTTP_201_CREATED)
async def crear(datos: ComponenteCrear, claims: Administrador, session: SesionDB) -> ComponenteOut:
    try:
        componente = await servicio.crear(
            session,
            empresa_id=claims.empresa_id,
            nombre=datos.nombre,
            descripcion=datos.descripcion,
        )
    except servicio.NombreRepetido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, NOMBRE_REPETIDO) from exc
    return ComponenteOut.model_validate(componente)


@router.post("/plantilla", response_model=list[ComponenteOut])
async def cargar_plantilla(claims: Administrador, session: SesionDB) -> list[ComponenteOut]:
    """Añade los componentes del catálogo inicial que falten. Devuelve los añadidos."""
    nuevos = await servicio.cargar_plantilla(session, empresa_id=claims.empresa_id)
    return [ComponenteOut.model_validate(c) for c in nuevos]


@router.patch("/{componente_id}", response_model=ComponenteOut)
async def editar(
    componente_id: UUID, datos: ComponenteEditar, _: Administrador, session: SesionDB
) -> ComponenteOut:
    """Renombrar o desactivar. No existe DELETE: lo referencian las órdenes de la fase 3."""
    try:
        componente = await servicio.editar(
            session, componente_id, **datos.model_dump(exclude_unset=True)
        )
    except servicio.ComponenteNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Componente no encontrado.") from exc
    except servicio.NombreRepetido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, NOMBRE_REPETIDO) from exc
    return ComponenteOut.model_validate(componente)
