"""Esquemas de componentes y activos (RF-04, RF-05, RF-06, RF-07).

Ningún esquema de entrada acepta `empresa_id`, `qr_code` ni `horometro_actual`: la empresa sale del
token, el código lo genera el servidor, y el horómetro vigente solo lo mueven las lecturas.
`extra="forbid"` hace que intentar colarlos sea un 422 y no un campo ignorado en silencio
(05-fase2-activos-y-campo.md, sección 8.3).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.schemas.orden_trabajo import OrdenAbierta

T = TypeVar("T")

Criticidad = Literal["alta", "media", "baja"]
EstadoActivo = Literal["activo", "baja"]

#: Longitudes máximas de los textos libres. Nadie necesita 10.000 caracteres para la ubicación de un
#: compresor, y sin tope un solo campo puede inflar cada listado.
CORTO = 120
LARGO = 500


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagina(BaseModel, Generic[T]):
    """Una página de un listado por cursor (sección 9.1). `next_cursor` es `None` en la última."""

    items: list[T]
    next_cursor: str | None


# --- Componentes ------------------------------------------------------------


class ComponenteCrear(_Estricto):
    nombre: str = Field(min_length=2, max_length=CORTO)
    descripcion: str | None = Field(default=None, max_length=LARGO)


class ComponenteEditar(_Estricto):
    """Renombrar o desactivar. No hay borrado: lo referencian las órdenes de la fase 3."""

    nombre: str | None = Field(default=None, min_length=2, max_length=CORTO)
    descripcion: str | None = Field(default=None, max_length=LARGO)
    activo: bool | None = None
    #: Vida nominal en horas (F4, decisión 6). `null` la borra; omitirla la deja como está.
    vida_nominal_horas: int | None = Field(default=None, ge=10, le=1_000_000)

    @field_validator("nombre", "activo")
    @classmethod
    def _sin_nulos(cls, valor: object) -> object:
        # Omitir un campo lo deja como está; enviarlo como null pedía vaciar una columna que no lo
        # admite, y salía como un 500. El validador solo corre con los campos que vienen.
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


class ComponenteOut(_Salida):
    id: UUID
    nombre: str
    descripcion: str | None
    activo: bool
    vida_nominal_horas: int | None = None


# --- Activos ----------------------------------------------------------------


class _FichaTecnica(_Estricto):
    tipo: str | None = Field(default=None, max_length=CORTO)
    ubicacion: str | None = Field(default=None, max_length=CORTO)
    criticidad: Criticidad | None = None
    marca: str | None = Field(default=None, max_length=CORTO)
    modelo: str | None = Field(default=None, max_length=CORTO)
    numero_serie: str | None = Field(default=None, max_length=CORTO)
    fecha_instalacion: date | None = None


class ActivoCrear(_FichaTecnica):
    nombre: str = Field(min_length=2, max_length=CORTO)
    #: Lo que marca el horómetro el día del alta. Se guarda como la primera lectura del historial,
    #: firmada por quien dio de alta el equipo, para que la siguiente lectura tenga con qué
    #: compararse.
    horometro_inicial: int = Field(default=0, ge=0)

    @field_validator("horometro_inicial")
    @classmethod
    def _dentro_del_rango(cls, valor: int) -> int:
        # El mismo tope que una lectura (sección 5.1). Va en un validador y no en `le=` porque
        # HOROMETRO_MAX es configuración y se lee al validar, no al importar el módulo. Sin tope, un
        # número que no cabe en la columna llegaba a la base y salía como un 500.
        if valor > get_settings().horometro_max:
            raise ValueError("El horómetro inicial está fuera del rango admitido.")
        return valor


class ActivoEditar(_FichaTecnica):
    """Todo opcional: solo cambia lo que se envía. No admite `qr_code` ni `empresa_id`."""

    nombre: str | None = Field(default=None, min_length=2, max_length=CORTO)
    #: Desde cuándo se observa el equipo (`activos.creado_en`; 08-fase5, decisión 8). Solo se puede
    #: adelantar, para cargar la historia de antes de usar SIMAP: posponerla escondería horas de
    #: calendario y subiría la disponibilidad sin que nada mejorara.
    observado_desde: AwareDatetime | None = None

    @field_validator("nombre", "observado_desde")
    @classmethod
    def _sin_nulos(cls, valor: object) -> object:
        # Omitir un campo lo deja como está; enviarlo como null pedía vaciar una columna que no lo
        # admite, y salía como un 500. El validador solo corre con los campos que vienen.
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


class ActivoOut(_Salida):
    id: UUID
    nombre: str
    tipo: str | None
    ubicacion: str | None
    criticidad: Criticidad | None
    marca: str | None
    modelo: str | None
    numero_serie: str | None
    fecha_instalacion: date | None
    estado: EstadoActivo
    dado_de_baja_en: datetime | None
    horometro_actual: int
    horometro_actualizado_en: datetime | None
    #: Horas acumuladas antes del último cambio o reinicio del horómetro (F3, 5.1).
    horometro_offset: int = 0
    #: Desde cuándo se observa el equipo: inicio de sus horas de calendario (F5, decisión 8).
    creado_en: datetime | None = None
    fecha_ultima_falla: date | None
    #: El código tal cual, y presentado en dos grupos para imprimir y dictar (`XK7P-2QH9`).
    codigo: str
    codigo_corto: str
    #: Lo que codifica el QR: la URL de la pantalla del equipo, nada más.
    url_qr: str
    #: Tiene alguna orden de trabajo abierta (F3, 6.2). Derivado, nunca guardado.
    en_falla: bool = False
    #: Solo en la ficha de un equipo: sus órdenes abiertas. Las ve cualquiera, operario incluido,
    #: para no registrar lecturas de rutina sobre una máquina que está en el taller sin saberlo.
    ordenes_abiertas: list[OrdenAbierta] = []
