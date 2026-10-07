"""Personal de la empresa: alta, rol y baja, por el administrador de la planta (RF-03).

Sin esto una empresa tendría un único usuario —el administrador que crea la consola del operador— y
no podría existir ningún operario, que es justo quien alimenta de datos al sistema.

DOS REGLAS QUE NO SON DE GUSTO
------------------------------
- **Nadie se quita a sí mismo el rol de administrador ni se da de baja.** Un clic equivocado dejaría
  a esa persona fuera de su propia consola sin nadie que la vuelva a poner.
- **La empresa nunca se queda sin administrador activo.** Si ocurriera, nadie de la planta podría
  dar de alta a nadie más, y la única salida sería pedírselo a quien opera SIMAP.

Dar de baja o cambiar el rol de alguien sube su `version_clave`: sus sesiones abiertas dejan de
renovarse, así que el cambio surte efecto en como mucho 30 minutos, lo que dure su token de acceso.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Rol, generar_clave_temporal, hash_password
from app.models.usuario import Usuario


class UsuarioNoEncontrado(Exception):
    pass


class CorreoEnUso(Exception):
    """El correo ya pertenece a alguien. Es único en todo SIMAP: es la credencial de acceso."""


class OperacionNoPermitida(Exception):
    """Dejaría a alguien fuera o a la empresa sin administrador. El mensaje lo explica."""


async def listar(session: AsyncSession) -> list[Usuario]:
    return list((await session.scalars(select(Usuario).order_by(Usuario.nombre))).all())


async def _obtener(session: AsyncSession, usuario_id: UUID) -> Usuario:
    usuario: Usuario | None = await session.scalar(select(Usuario).where(Usuario.id == usuario_id))
    if usuario is None:
        raise UsuarioNoEncontrado(str(usuario_id))
    return usuario


async def crear(
    session: AsyncSession, *, empresa_id: UUID, nombre: str, correo: str, rol: Rol
) -> tuple[Usuario, str]:
    """Da de alta a una persona. Devuelve también su contraseña temporal, en claro, una sola vez."""
    password = generar_clave_temporal()
    usuario = Usuario(
        empresa_id=empresa_id,
        nombre=nombre,
        correo=correo.strip().lower(),
        password_hash=hash_password(password),
        rol=rol.value,
    )
    try:
        async with session.begin_nested():
            session.add(usuario)
            await session.flush()
    except IntegrityError as exc:
        if "uq_usuarios_correo" in str(exc.orig):
            raise CorreoEnUso(usuario.correo) from exc
        raise
    return usuario, password


async def _administradores_activos_sin(session: AsyncSession, excluido: UUID) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(Usuario)
        .where(
            Usuario.rol == Rol.ADMINISTRADOR.value,
            Usuario.activo.is_(True),
            Usuario.id != excluido,
        )
    )
    return int(total or 0)


async def editar(
    session: AsyncSession,
    *,
    actor_id: UUID,
    usuario_id: UUID,
    nombre: str | None = None,
    rol: Rol | None = None,
    activo: bool | None = None,
) -> Usuario:
    usuario = await _obtener(session, usuario_id)
    deja_de_ser_admin = (
        usuario.rol == Rol.ADMINISTRADOR.value and rol is not None and rol is not Rol.ADMINISTRADOR
    )
    se_da_de_baja = usuario.activo and activo is False

    if usuario_id == actor_id and (deja_de_ser_admin or se_da_de_baja):
        raise OperacionNoPermitida(
            "No puedes quitarte a ti mismo el rol de administrador ni darte de baja. "
            "Pídeselo a otro administrador de tu empresa."
        )
    if (
        usuario.rol == Rol.ADMINISTRADOR.value
        and usuario.activo
        and (deja_de_ser_admin or se_da_de_baja)
        and await _administradores_activos_sin(session, usuario_id) == 0
    ):
        raise OperacionNoPermitida(
            "Es el único administrador activo de la empresa. Da de alta a otro antes."
        )

    cambia_acceso = (rol is not None and rol.value != usuario.rol) or se_da_de_baja
    if nombre is not None:
        usuario.nombre = nombre
    if rol is not None:
        usuario.rol = rol.value
    if activo is not None:
        usuario.activo = activo
    if cambia_acceso:
        usuario.version_clave = usuario.version_clave + 1
    await session.flush()
    return usuario


async def restablecer_clave(session: AsyncSession, *, usuario_id: UUID) -> tuple[Usuario, str]:
    """Contraseña temporal nueva para alguien de la planta que se quedó fuera.

    Cierra además sus sesiones abiertas: restablecer suele pedirse cuando alguien perdió el control
    de su cuenta.
    """
    usuario = await _obtener(session, usuario_id)
    password = generar_clave_temporal()
    usuario.password_hash = hash_password(password)
    usuario.version_clave = usuario.version_clave + 1
    await session.flush()
    return usuario, password
