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

from pydantic import BaseModel, ConfigDict, Field

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


class ComponenteOut(_Salida):
    id: UUID
    nombre: str
    descripcion: str | None
    activo: bool


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


class ActivoEditar(_FichaTecnica):
    """Todo opcional: solo cambia lo que se envía. No admite `qr_code` ni `empresa_id`."""

    nombre: str | None = Field(default=None, min_length=2, max_length=CORTO)


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
    fecha_ultima_falla: date | None
    #: El código tal cual, y presentado en dos grupos para imprimir y dictar (`XK7P-2QH9`).
    codigo: str
    codigo_corto: str
    #: Lo que codifica el QR: la URL de la pantalla del equipo, nada más.
    url_qr: str
