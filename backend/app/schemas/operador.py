"""Esquemas del plano de control (consola del operador de SIMAP).

Como los del plano de datos, todos con `extra="forbid"`: un campo inesperado se rechaza con 422
antes de tocar la base. Aquí importa todavía más, porque estas rutas dan de alta clientes y
restablecen contraseñas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.auth import MAX_PASSWORD


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginOperadorRequest(_Estricto):
    correo: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)


class OperadorOut(_Estricto):
    """El operador de la sesión. Nunca incluye `password_hash`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    nombre: str
    correo: str
    creado_en: datetime


class SesionOperadorResponse(_Estricto):
    operador: OperadorOut
    expira_en_segundos: int


class AltaEmpresaRequest(_Estricto):
    """Alta de una empresa cliente con su primer administrador.

    La contraseña **no** se acepta aquí: la genera el servidor y se muestra una sola vez. Dejar que
    quien opera SIMAP elija la contraseña de su cliente le da acceso permanente a la cuenta de ese
    cliente, que es justo la frontera que este plano existe para no cruzar.
    """

    empresa: str = Field(min_length=2, max_length=200)
    admin_nombre: str = Field(min_length=2, max_length=200)
    admin_correo: EmailStr


class EmpresaEdicionRequest(_Estricto):
    nombre: str = Field(min_length=2, max_length=200)


class EmpresaResumen(_Estricto):
    """Una empresa vista desde el plano de control.

    Lleva lo necesario para facturar y dar soporte —quién es el administrador y cuántos equipos
    tiene monitoreados— y **nada de sus datos de negocio**.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    nombre: str
    activa: bool
    fecha_registro: datetime | None = None
    suspendida_en: datetime | None = None
    admin_nombre: str | None = None
    admin_correo: str | None = None
    #: Equipos monitoreados, que es la unidad de cobro. `None` mientras la tabla `activos` no
    #: exista (llega en F2): mejor decir «todavía no se puede contar» que insinuar que son cero.
    equipos: int | None = None


class ClaveTemporalResponse(_Estricto):
    """Resultado de restablecer la contraseña de un administrador.

    La contraseña viaja en claro en esta única respuesta y no se guarda en ningún sitio más que
    como hash. Si quien opera SIMAP la pierde, no hay forma de recuperarla: hay que generar otra.
    """

    correo: str
    password_temporal: str


class AsientoBitacora(_Estricto):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    accion: str
    empresa_id: UUID | None
    detalle: str | None
    creado_en: datetime
    operador_nombre: str | None = None
