"""Esquemas del inventario de repuestos (RF-23 a RF-26; 07-fase4, secciones 8 y 12.2).

El stock **no aparece en ningún esquema de entrada** salvo como stock inicial del alta, que entra al
libro como movimiento `inicial`: después solo lo mueven ingresos, consumos y ajustes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

TipoMovimiento = Literal["inicial", "ingreso", "consumo", "ajuste"]
Dinero = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RepuestoCrear(_Estricto):
    nombre: str = Field(min_length=2, max_length=120)
    codigo: str = Field(min_length=1, max_length=60)
    stock_inicial: int = Field(default=0, ge=0, le=1_000_000)
    stock_minimo: int = Field(default=0, ge=0, le=1_000_000)
    costo_unitario: Decimal = Field(
        default=Decimal("0"), ge=Decimal("0"), max_digits=12, decimal_places=2
    )


class RepuestoEditar(_Estricto):
    """Nombre, mínimo, costo y activo. Nunca el stock."""

    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    stock_minimo: int | None = Field(default=None, ge=0, le=1_000_000)
    costo_unitario: Decimal | None = Field(
        default=None, ge=Decimal("0"), max_digits=12, decimal_places=2
    )
    activo: bool | None = None

    @field_validator("nombre", "stock_minimo", "costo_unitario", "activo")
    @classmethod
    def _sin_nulos(cls, valor: object) -> object:
        if valor is None:
            raise ValueError("Este campo no se puede dejar vacío; omítelo para no cambiarlo.")
        return valor


class RepuestoOut(_Salida):
    id: UUID
    nombre: str
    codigo: str
    stock_actual: int
    stock_minimo: int
    costo_unitario: Decimal
    activo: bool
    bajo_minimo: bool = False


class RepuestoTecnico(BaseModel):
    """Lo que ve el técnico: existencias, sin costo (decisión 2: consulta, no el libro)."""

    id: UUID
    nombre: str
    codigo: str
    stock_actual: int
    stock_minimo: int
    bajo_minimo: bool


class Ingreso(_Estricto):
    cantidad: int = Field(ge=1, le=1_000_000)
    nota: str | None = Field(default=None, max_length=500)


class Ajuste(_Estricto):
    """Conteo físico: el stock contado, no la diferencia. Nota obligatoria."""

    conteo: int = Field(ge=0, le=1_000_000)
    nota: str = Field(min_length=3, max_length=500)


class MovimientoOut(_Salida):
    id: UUID
    tipo: TipoMovimiento
    delta: int
    stock_resultante: int
    costo_unitario: Decimal | None
    orden_id: UUID | None
    usuario_id: UUID
    nota: str | None
    creado_en: datetime


class Descuadre(BaseModel):
    repuesto_id: UUID
    codigo: str
    stock_actual: int
    suma_libro: int


class LineaGuardar(_Estricto):
    cantidad: int = Field(ge=1, le=10_000)


class LineaOut(BaseModel):
    repuesto_id: UUID
    codigo: str
    nombre: str
    cantidad: int
    stock_actual: int
    #: Solo para quien puede ver costos (no el técnico).
    costo_unitario: Decimal | None
