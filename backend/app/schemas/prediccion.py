"""Esquemas de la predicción de fallas (RF-17 a RF-22; 07-fase4, secciones 8 y 10.2).

Ningún esquema de entrada acepta `empresa_id`, el riesgo, el modelo, los estados de una alerta ni
quién la gestionó: los fija el servidor. La orden predictiva toma equipo y componente de la alerta,
nunca del cuerpo (12.2).

«Sin edad» y «sin modelo» salen como `estado_calculo`, **nunca como un 0 %** (10.2): `riesgo` es
`None` en esos casos y la pantalla muestra el aviso con su acción.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

EstadoCalculo = Literal["ok", "sin_edad", "sin_modelo"]
Fuente = Literal["previo", "mixto", "empresa"]
Confianza = Literal["baja", "media", "alta"]
TipoAlerta = Literal["riesgo", "reorden"]
EstadoAlerta = Literal["activa", "reconocida", "atendida", "resuelta", "descartada"]
#: Agrupaciones de la bandeja: vigentes (por defecto) y el historial.
FiltroAlerta = Literal[
    "vigentes", "historial", "activa", "reconocida", "atendida", "resuelta", "descartada"
]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RiesgoComponente(BaseModel):
    """Riesgo de un componente de un equipo, con su respaldo (10.2)."""

    componente_id: UUID
    componente: str
    estado_calculo: EstadoCalculo
    edad_horas: float | None
    horizonte_horas: int | None
    beta: float | None
    eta: float | None
    riesgo_base: Decimal | None
    multiplicador: Decimal | None
    riesgo: Decimal | None
    n_eventos: int | None
    fuente: Fuente | None
    confianza: Confianza | None
    calculado_en: datetime | None


class RiesgoEquipo(BaseModel):
    """`GET /activos/{id}/riesgo`: cada componente y el umbral con que se lee."""

    activo_id: UUID
    umbral: Decimal
    horizonte_horas: int
    #: Horas diarias recientes del equipo, para el equivalente informativo en días (decisión 4).
    horas_por_dia: float | None
    alertas_de_campo: int
    alertas_minimas: int
    componentes: list[RiesgoComponente]


class RiesgoActivo(BaseModel):
    """Una fila de `GET /riesgos`: el equipo por su componente más riesgoso (v_riesgo_activo)."""

    activo_id: UUID
    activo: str
    codigo: str
    componente_critico_id: UUID
    componente_critico: str
    riesgo: Decimal
    confianza: Confianza | None
    fuente: Fuente | None
    n_eventos: int | None
    edad_horas: float | None
    calculado_en: datetime


class ComponenteEquipoOut(BaseModel):
    componente_id: UUID
    nombre: str
    horas_instalacion_inicial: int | None
    estado_calculo: EstadoCalculo | None
    riesgo: float | None
    edad_horas: float | None


class ComponentesEquipo(BaseModel):
    activo_id: UUID
    horas_acumuladas: int
    componentes: list[ComponenteEquipoOut]


class DeclararEdad(_Estricto):
    """`PUT /activos/{id}/componentes/{cid}`: 0 si el equipo era nuevo, `null` si no se sabe."""

    horas_instalacion_inicial: int | None = Field(ge=0)


class HistorialModelo(_Salida):
    version: int
    beta: float
    eta: float
    n_eventos: int
    fuente: Fuente
    confianza: Confianza
    ajustado_en: datetime


class ModeloOut(BaseModel):
    """`GET /componentes/{id}/modelo`: el vigente y la curva de aprendizaje."""

    componente_id: UUID
    componente: str
    vida_nominal_horas: int | None
    beta: float | None
    eta: float | None
    n_eventos: int | None
    n_vidas: int | None
    exposicion_horas: float | None
    fuente: Fuente | None
    confianza: Confianza | None
    convergio: bool | None
    version: int | None
    ajustado_en: datetime | None
    historial: list[HistorialModelo]


class ConfiguracionOut(_Salida):
    umbral_riesgo: Decimal
    horizonte_horas: int
    alertas_minimas: int
    ventana_alertas_dias: int
    multiplicador_alertas: Decimal
    descarte_silencio_dias: int


class ConfiguracionEditar(_Estricto):
    """Todo opcional; los límites son los de las CHECK de la base (7.1)."""

    umbral_riesgo: Decimal | None = Field(default=None, ge=Decimal("0.05"), le=Decimal("0.95"))
    horizonte_horas: int | None = Field(default=None, ge=1, le=2000)
    alertas_minimas: int | None = Field(default=None, ge=1, le=20)
    ventana_alertas_dias: int | None = Field(default=None, ge=1, le=90)
    multiplicador_alertas: Decimal | None = Field(
        default=None, ge=Decimal("1.00"), le=Decimal("2.00")
    )
    descarte_silencio_dias: int | None = Field(default=None, ge=1, le=90)


class AlertaSistemaOut(BaseModel):
    id: UUID
    tipo: TipoAlerta
    estado: EstadoAlerta
    activo_id: UUID | None
    activo: str | None
    componente_id: UUID | None
    componente: str | None
    repuesto_id: UUID | None
    repuesto: str | None
    repuesto_codigo: str | None
    riesgo: Decimal | None
    umbral: Decimal | None
    confianza: Confianza | None
    fuente: Fuente | None
    stock_al_alertar: int | None
    stock_minimo_al_alertar: int | None
    creada_en: datetime
    gestionada_en: datetime | None
    nota: str | None
    orden_id: UUID | None
    orden_numero: int | None


class Descartar(_Estricto):
    #: No se borra: no escribas datos personales (12.4).
    nota: str = Field(min_length=3, max_length=500)


class CrearOrdenPredictiva(_Estricto):
    descripcion: str | None = Field(default=None, min_length=5, max_length=1000)


class ConvertirEnFalla(_Estricto):
    """`POST /ordenes/{id}/convertir-en-falla`: el horómetro y la fecha reales de la falla."""

    horometro: int = Field(ge=0)
    fecha_falla: AwareDatetime
