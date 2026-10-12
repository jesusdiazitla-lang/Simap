"""Esquemas de la gestión de usuarios por el administrador de la planta (RF-03).

La contraseña no se acepta en ninguna entrada: la genera el servidor y se entrega una sola vez,
igual que hace la consola del operador con los administradores. Quien da de alta a alguien no elige
su clave, así que no conserva acceso a esa cuenta una vez cambiada.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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

    @field_validator("nombre", "rol", "activo")
    @classmethod
    def _sin_nulos(cls, valor: object) -> object:
        # Omitir un campo lo deja como está; enviarlo como null pedía vaciar una columna que no lo
        # admite, y salía como un 500. El validador solo corre con los campos que vienen.
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


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
