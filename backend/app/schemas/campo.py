"""Esquemas del registro de campo: lecturas de horómetro, alertas y lotes sin conexión (RF-08..10).

Todo lo que llega de un teléfono es no confiable (05-fase2-activos-y-campo.md, sección 8.3): listas
cerradas, rangos, longitudes máximas y rechazo de campos desconocidos. `empresa_id` y `usuario_id`
no existen en ningún esquema de entrada: salen del token.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Sintoma = Literal["ruido", "vibracion", "calor", "olor", "fuga", "otro"]
EstadoAlerta = Literal["pendiente", "revisada", "descartada", "convertida_en_orden"]
MAX_NOTA = 500


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Captura(_Estricto):
    #: Lo genera el teléfono antes del primer intento y lo repite en cada reintento.
    cliente_id: UUID
    #: Cuándo se tomó el dato, con zona horaria. Sin zona, «las 14:00» no dice de qué día ni de
    #: dónde, y el modelo de la fase 4 necesita ordenar las lecturas sin ambigüedad.
    capturado_en: AwareDatetime


class LecturaCrear(_Captura):
    #: El techo (`HOROMETRO_MAX`) es configurable, así que lo comprueba el servicio con la
    #: configuración vigente; aquí solo se descarta lo que no puede ser un horómetro.
    valor: int = Field(ge=0)


class AlertaCrear(_Captura):
    sintoma: Sintoma
    nota: str | None = Field(default=None, max_length=MAX_NOTA)


class LecturaOut(_Salida):
    id: UUID
    activo_id: UUID
    valor_horometro: int
    capturado_en: datetime
    fecha: datetime
    requiere_revision: bool
    motivo_revision: str | None
    registrado_por: UUID
    #: Si fue marcada: cómo se resolvió (`confirmada`, `descartada`, `reinicio`) o `None` si sigue
    #: pendiente. Ver la revisión 0006.
    resolucion: Literal["confirmada", "descartada", "reinicio"] | None = None
    revisada_por: UUID | None = None
    revisada_en: datetime | None = None


class LecturaPorRevisar(LecturaOut):
    """Una lectura pendiente de revisión, con lo necesario para decidir sin abrir el equipo."""

    activo_nombre: str
    activo_codigo: str
    #: El horómetro vigente del equipo, para comparar con la lectura marcada.
    horometro_vigente: int


class LecturaResolver(_Estricto):
    """`reinicio` solo lo puede registrar el administrador: cambia la serie de horas del equipo."""

    resolucion: Literal["confirmada", "descartada", "reinicio"]


class AlertaOut(_Salida):
    id: UUID
    activo_id: UUID
    sintoma: Sintoma
    nota: str | None
    estado: EstadoAlerta
    capturado_en: datetime
    fecha: datetime
    reportado_por: UUID
    revisada_por: UUID | None
    revisada_en: datetime | None
    #: Solo en la bandeja: el equipo al que se refiere, para no tener que pedirlo aparte por cada
    #: fila. Se obtiene con un JOIN que también pasa por RLS.
    activo_nombre: str | None = None
    activo_codigo: str | None = None


class RegistroOut(BaseModel):
    """Respuesta de un registro individual: qué pasó y la fila resultante.

    `duplicado` no es un error: el teléfono reenvió algo que ya había llegado (o la misma persona
    insistió sobre el mismo síntoma). Se responde con la fila que ya existía para que el cliente la
    dé por entregada y la quite de su cola.
    """

    estado: Literal["creado", "duplicado"]


class LecturaRegistrada(RegistroOut):
    lectura: LecturaOut


class AlertaRegistrada(RegistroOut):
    alerta: AlertaOut


class AlertaRevisar(_Estricto):
    """Solo dos destinos desde `pendiente`. `convertida_en_orden` llega con la fase 3."""

    estado: Literal["revisada", "descartada"]


# --- Lotes sin conexión (sección 5.3) -------------------------------------------


class ItemLectura(LecturaCrear):
    tipo: Literal["lectura"]
    activo_id: UUID


class ItemAlerta(AlertaCrear):
    tipo: Literal["alerta"]
    activo_id: UUID


ItemLote = Annotated[ItemLectura | ItemAlerta, Field(discriminator="tipo")]


class LoteEntrada(_Estricto):
    """Los ítems llegan como objetos sin validar, y se validan **uno a uno** en el servicio.

    Si se validaran aquí, un solo ítem malformado —un síntoma que una versión vieja de la app
    escribía distinto— haría un 422 de todo el lote. El teléfono no sabría cuál quitar de su cola y
    lo reenviaría para siempre. Validados por separado, ese ítem vuelve como `rechazado` con su
    motivo y los demás entran.
    """

    items: list[dict[str, Any]] = Field(min_length=1, max_length=50)


class ResultadoItem(BaseModel):
    #: Posición en el lote: identifica el ítem aunque su `cliente_id` fuera ilegible.
    indice: int
    cliente_id: UUID | None
    estado: Literal["creado", "duplicado", "rechazado"]
    motivo: str | None = None


class LoteSalida(BaseModel):
    resultados: list[ResultadoItem]
