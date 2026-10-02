"""Esquemas Pydantic de autenticación (RF-01, RF-02).

Todos usan `extra="forbid"`: un campo inesperado se rechaza con 422 antes de tocar la base de datos,
como exige `docs/contexto/04-fase1-fundamentos.md`, sección 6.5. Sin eso, un cliente podría colar
`rol="administrador"` en el registro y escalar privilegios si algún día el servicio pasara el cuerpo
entero al modelo.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.security import Rol

#: Longitud mínima de contraseña. Argon2id resiste fuerza bruta, pero no resucita una clave de
#: cuatro caracteres presente en cualquier diccionario.
MIN_PASSWORD = 12
MAX_PASSWORD = 128


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegistroRequest(_Estricto):
    """Alta de una empresa nueva junto con su primer usuario administrador.

    El rol no se acepta del cliente: quien se registra es siempre `administrador` de la empresa que
    acaba de crear. Los demás usuarios los da de alta ese administrador más adelante.
    """

    empresa: str = Field(min_length=2, max_length=200)
    nombre: str = Field(min_length=2, max_length=200)
    correo: EmailStr
    password: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)


class LoginRequest(_Estricto):
    correo: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)


class CambioClaveRequest(_Estricto):
    """Cambio de la contraseña propia. Lo usan los dos planos: usuarios de empresa y operadores.

    Pide la actual aunque haya sesión: una sesión abierta en un aparato compartido no debe bastar
    para quedarse con la cuenta.

    Recorta los espacios de los extremos, como todos los esquemas de este módulo. No es un detalle:
    `LoginRequest` los recorta, así que si este no lo hiciera, quien pusiera un espacio al final de
    la clave nueva guardaría un hash que el login nunca podría reproducir, y quedaría fuera de su
    propia cuenta.
    """

    password_actual: str = Field(min_length=1, max_length=MAX_PASSWORD)
    password_nueva: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)

    @model_validator(mode="after")
    def _distinta_de_la_actual(self) -> "CambioClaveRequest":
        # Cambiar una clave por sí misma no cambia nada y, si se hace porque alguien la vio, deja
        # al usuario creyendo que está protegido.
        if self.password_nueva == self.password_actual:
            raise ValueError("La contraseña nueva tiene que ser distinta de la actual.")
        return self


class UsuarioOut(_Estricto):
    """Usuario tal como se devuelve al cliente. Nunca incluye `password_hash`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    empresa_id: UUID
    nombre: str
    correo: str
    rol: Rol
    creado_en: datetime


class SesionResponse(_Estricto):
    """Respuesta de registro y login.

    Los tokens NO viajan aquí: van en cookies httpOnly que el JavaScript de la página no puede leer
    (sección 6.1). El cuerpo solo lleva quién eres y cuándo caduca la sesión, que es lo que la
    interfaz necesita para pintar el menú del rol y avisar antes de expirar.
    """

    usuario: UsuarioOut
    expira_en_segundos: int
