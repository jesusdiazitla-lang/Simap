"""Personal de la empresa, gestionado por su administrador (RF-03)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.rbac import requiere_roles
from app.core.security import Claims, Rol
from app.db.deps import SesionDB
from app.schemas.usuario import (
    UsuarioConClave,
    UsuarioCrear,
    UsuarioDeEmpresaOut,
    UsuarioEditar,
)
from app.services import usuarios as servicio

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

Administrador = Annotated[Claims, Depends(requiere_roles(Rol.ADMINISTRADOR))]

NO_ENCONTRADO = "Usuario no encontrado."


@router.get("", response_model=list[UsuarioDeEmpresaOut])
async def listar(_: Administrador, session: SesionDB) -> list[UsuarioDeEmpresaOut]:
    return [UsuarioDeEmpresaOut.model_validate(u) for u in await servicio.listar(session)]


@router.post("", response_model=UsuarioConClave, status_code=status.HTTP_201_CREATED)
async def crear(datos: UsuarioCrear, claims: Administrador, session: SesionDB) -> UsuarioConClave:
    """Alta de una persona con su rol. La contraseña la genera el servidor y se ve una sola vez."""
    try:
        usuario, clave = await servicio.crear(
            session,
            empresa_id=claims.empresa_id,
            nombre=datos.nombre,
            correo=datos.correo,
            rol=datos.rol,
        )
    except servicio.CorreoEnUso as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ese correo ya tiene una cuenta en SIMAP."
        ) from exc
    return UsuarioConClave(
        usuario=UsuarioDeEmpresaOut.model_validate(usuario), password_temporal=clave
    )


@router.patch("/{usuario_id}", response_model=UsuarioDeEmpresaOut)
async def editar(
    usuario_id: UUID, datos: UsuarioEditar, claims: Administrador, session: SesionDB
) -> UsuarioDeEmpresaOut:
    """Nombre, rol o baja. Dar de baja o cambiar el rol cierra las sesiones de esa persona."""
    try:
        usuario = await servicio.editar(
            session,
            actor_id=claims.usuario_id,
            usuario_id=usuario_id,
            **datos.model_dump(exclude_unset=True),
        )
    except servicio.UsuarioNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_ENCONTRADO) from exc
    except servicio.OperacionNoPermitida as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return UsuarioDeEmpresaOut.model_validate(usuario)


@router.post("/{usuario_id}/restablecer-clave", response_model=UsuarioConClave)
async def restablecer_clave(
    usuario_id: UUID, _: Administrador, session: SesionDB
) -> UsuarioConClave:
    try:
        usuario, clave = await servicio.restablecer_clave(session, usuario_id=usuario_id)
    except servicio.UsuarioNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_ENCONTRADO) from exc
    return UsuarioConClave(
        usuario=UsuarioDeEmpresaOut.model_validate(usuario), password_temporal=clave
    )
