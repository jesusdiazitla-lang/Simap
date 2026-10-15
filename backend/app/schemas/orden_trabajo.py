"""Esquemas de las órdenes de trabajo (RF-11 a RF-16; 06-fase3-ordenes-de-trabajo.md).

Ningún esquema de entrada acepta `empresa_id`, el número, el estado, los responsables ni las marcas
de tiempo de las transiciones: los fija el servidor (sección 11.2). `extra="forbid"` hace que un
cliente que envíe `estado` o `autorizado_por` reciba 422, no una orden alterada.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

EstadoOrden = Literal["reportada", "en_taller", "reparada", "cerrada", "cancelada"]
TipoIntervencion = Literal["reemplazo", "reparacion", "ajuste"]
TipoEvento = Literal["creada", "transicion", "nota", "correccion"]
#: Agrupaciones de la bandeja (sección 9.1), además de cada estado suelto.
FiltroEstado = Literal["abiertas", "cerradas", "canceladas", "reportada", "en_taller", "reparada"]

#: Rangos de la sección 6.2 y de la tabla de transiciones (6.1).
Descripcion = Field(min_length=5, max_length=1000)
Temperatura = Field(default=None, ge=-100, le=999, max_digits=5, decimal_places=2)
CodigoError = Field(default=None, max_length=50)


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _sin_vacios(valor: str | None) -> str | None:
    """Un código de error en blanco no es un código: se guarda como ausente."""
    return valor or None


class FallaCrear(_Estricto):
    """Reporte de falla (sección 6.2). La empresa y quien reporta salen del token."""

    #: Lo genera el dispositivo antes del primer intento y lo repite en cada reintento.
    cliente_id: UUID
    #: Cuándo ocurrió la falla según el dispositivo: es la `fecha_falla` de la orden.
    capturado_en: AwareDatetime
    componente_id: UUID
    #: Valor del dial. El techo (`HOROMETRO_MAX`) lo comprueba el servicio con la configuración.
    horometro: int = Field(ge=0)
    temperatura: Decimal | None = Temperatura
    codigo_error: str | None = CodigoError
    descripcion: str = Descripcion
    #: Alerta que origina la orden (RF-16). Del mismo equipo, pendiente o revisada.
    alerta_id: UUID | None = None

    _codigo = field_validator("codigo_error")(_sin_vacios)


class OrdenEditar(_Estricto):
    """Solo con la orden abierta (sección 8). Omitir un campo lo deja como está."""

    descripcion: str | None = Field(default=None, min_length=5, max_length=1000)
    codigo_error: str | None = CodigoError
    temperatura: Decimal | None = Temperatura
    componente_id: UUID | None = None

    @field_validator("descripcion", "componente_id")
    @classmethod
    def _no_nulos(cls, valor: object) -> object:
        # Descripción y componente son obligatorios en la orden: enviarlos como null pedía vaciar
        # una columna que no lo admite.
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


class Reparada(_Estricto):
    """En taller a Reparada (sección 6.1): lo que se hizo y qué tipo de intervención fue."""

    trabajo_realizado: str = Field(min_length=10, max_length=2000)
    tipo_intervencion: TipoIntervencion


class NotaOpcional(_Estricto):
    nota: str | None = Field(default=None, max_length=1000)


class NotaObligatoria(_Estricto):
    """Rechazo de cierre y nota libre: lo que se escribe queda para siempre en el historial."""

    nota: str = Field(min_length=10, max_length=1000)


class NotaLibre(_Estricto):
    nota: str = Field(min_length=1, max_length=1000)


class Cancelar(_Estricto):
    motivo: str = Field(min_length=10, max_length=1000)


class Correccion(_Estricto):
    """Corrección administrativa de una orden cerrada (sección 6.5). Lista cerrada de campos.

    Nunca estado, número, fechas ni responsables: el esquema no los tiene, así que intentarlo es un
    422. La nota es obligatoria y queda en el evento junto con los valores anteriores.
    """

    nota: str = Field(min_length=10, max_length=1000)
    descripcion: str | None = Field(default=None, min_length=5, max_length=1000)
    trabajo_realizado: str | None = Field(default=None, min_length=10, max_length=2000)
    codigo_error: str | None = CodigoError
    temperatura: Decimal | None = Temperatura
    tipo_intervencion: TipoIntervencion | None = None
    requiere_revision: bool | None = None

    @field_validator("descripcion", "trabajo_realizado", "tipo_intervencion", "requiere_revision")
    @classmethod
    def _no_nulos(cls, valor: object) -> object:
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


class ReinicioHorometro(_Estricto):
    """Valor nuevo del dial tras cambiar o poner a cero el horómetro (sección 5.1)."""

    nuevo: int = Field(ge=0)


# --- Salidas ----------------------------------------------------------------------


class Persona(BaseModel):
    """Quién hizo algo. El nombre aparece aunque hoy esté dado de baja (sección 5.2)."""

    id: UUID
    nombre: str
    activo: bool


class OrdenResumen(_Salida):
    id: UUID
    numero: int
    estado: EstadoOrden
    activo_id: UUID
    activo_nombre: str
    activo_codigo: str
    componente_id: UUID
    componente_nombre: str
    horometro_en_falla: int
    fecha_falla: datetime
    reportada_en: datetime
    requiere_revision: bool
    tipo_intervencion: TipoIntervencion | None = None
    tiempo_fuera_servicio_min: int | None = None


class Evento(BaseModel):
    id: UUID
    tipo: TipoEvento
    estado_anterior: EstadoOrden | None
    estado_nuevo: EstadoOrden | None
    usuario: Persona
    rol_al_momento: str
    nota: str | None
    datos: dict[str, Any] | None
    creado_en: datetime


class OrdenDetalle(OrdenResumen):
    cliente_id: UUID
    alerta_origen_id: UUID | None
    lectura_id: UUID | None
    horas_acumuladas_en_falla: int
    temperatura: Decimal | None
    codigo_error: str | None
    descripcion: str
    trabajo_realizado: str | None
    motivo_cancelacion: str | None
    motivo_revision: str | None
    en_taller_en: datetime | None
    reparada_en: datetime | None
    fecha_salida_taller: datetime | None
    reportado_por: Persona
    reparado_por: Persona | None
    autorizado_por: Persona | None
    eventos: list[Evento]


class OrdenCreada(BaseModel):
    """Respuesta del reporte: 201 si nació, 200 si era un reenvío del mismo `cliente_id`."""

    estado: Literal["creado", "duplicado"]
    orden: OrdenDetalle


class OrdenAbierta(BaseModel):
    """Lo que ve cualquiera en la pantalla del equipo, operario incluido (sección 8)."""

    id: UUID
    numero: int
    estado: EstadoOrden
    componente_id: UUID
    componente_nombre: str
