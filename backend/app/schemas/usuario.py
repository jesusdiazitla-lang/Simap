"""Esquemas de la gestión de usuarios por el administrador de la planta (RF-03).

La contraseña no se acepta en ninguna entrada: la genera el servidor y se entrega una sola vez,
igual que hace la consola del operador con los administradores. Quien da de alta a alguien no elige
su clave, así que no conserva acceso a esa cuenta una vez cambiada.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.security import Rol


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UsuarioCrear(_Estricto):
    nombre: str = Field(min_length=2, max_length=200)
    correo: EmailStr
    rol: Rol


class UsuarioEditar(_Estricto):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    rol: Rol | None = None
    activo: bool | None = None


class UsuarioDeEmpresaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    correo: str
    rol: Rol
    activo: bool
    creado_en: datetime


class UsuarioConClave(BaseModel):
    """Respuesta del alta y del restablecimiento: la única vez que la clave existe en claro."""

    usuario: UsuarioDeEmpresaOut
    password_temporal: str
