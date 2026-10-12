"""Registro estructurado y métricas mínimas (05-fase2-activos-y-campo.md, sección 9.7).

QUÉ SE REGISTRA
---------------
Una línea JSON por petición —método, ruta, estado, duración— y eventos de negocio con nombre
(`campo.lote`, `campo.lectura_marcada`…). Todas llevan `request_id`, `empresa_id` y `usuario_id`
(u `operador_id` en la consola) cuando se conocen, para poder seguir lo que le pasó a una persona o
a una empresa sin buscar a ciegas.

Las métricas que pide el documento —lotes recibidos, ítems creados, duplicados y rechazados,
lecturas marcadas— salen de esos eventos. Un salto en duplicados o rechazados suele delatar un
fallo de sincronización en los teléfonos antes de que alguien lo reporte. Se emiten como
registros y no con una librería de métricas para no atar el backend a un proveedor: cualquier
recolector de logs (Railway, Loki, CloudWatch) las agrega.

QUÉ NO SE REGISTRA NUNCA
------------------------
Contraseñas, tokens, cookies, cuerpos de petición ni el texto de las notas de las alertas. Este
módulo solo escribe los campos que se le pasan explícitamente, y la ruta se registra con su
plantilla (`/activos/{activo_id}`), no con los valores: así tampoco acaba en el log el código de
un equipo.

CÓMO VIAJA EL CONTEXTO
----------------------
El middleware crea un `Contexto` por petición y lo publica en una `ContextVar`. La dependencia que
verifica el token lo **rellena** (empresa, usuario) en lugar de publicar uno nuevo: FastAPI ejecuta
el endpoint en otra tarea y los cambios de una `ContextVar` no vuelven al middleware, pero las
mutaciones de un objeto compartido sí.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

NOMBRE = "simap"

#: Un `X-Request-ID` que venga de fuera solo se acepta si tiene esta forma. Si no, se genera uno:
#: una cabecera arbitraria acabaría tal cual en cada línea del log.
_PATRON_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


@dataclass
class Contexto:
    request_id: str
    empresa_id: UUID | None = None
    usuario_id: UUID | None = None
    operador_id: UUID | None = None


_contexto: ContextVar[Contexto | None] = ContextVar("simap_contexto", default=None)


def nuevo_contexto(id_entrante: str | None) -> Contexto:
    """Contexto de una petición, con el id que trajo si es válido o uno nuevo."""
    rid = id_entrante if id_entrante and _PATRON_ID.fullmatch(id_entrante) else uuid4().hex
    contexto = Contexto(request_id=rid)
    _contexto.set(contexto)
    return contexto


def contexto_actual() -> Contexto | None:
    return _contexto.get()


def anotar_usuario(empresa_id: UUID, usuario_id: UUID) -> None:
    """Lo llama la verificación del token: desde ese momento las líneas llevan quién es."""
    contexto = _contexto.get()
    if contexto is not None:
        contexto.empresa_id = empresa_id
        contexto.usuario_id = usuario_id


def anotar_operador(operador_id: UUID) -> None:
    contexto = _contexto.get()
    if contexto is not None:
        contexto.operador_id = operador_id


class FormatoJSON(logging.Formatter):
    """Una línea JSON por registro, con el contexto de la petición en curso."""

    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "nivel": record.levelname.lower(),
            "evento": record.getMessage(),
        }
        contexto = _contexto.get()
        if contexto is not None:
            datos["request_id"] = contexto.request_id
            for campo in ("empresa_id", "usuario_id", "operador_id"):
                valor = getattr(contexto, campo)
                if valor is not None:
                    datos[campo] = str(valor)
        extra = getattr(record, "datos", None)
        if isinstance(extra, dict):
            datos.update(extra)
        if record.exc_info:
            datos["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


def configurar() -> None:
    """Instala el formato JSON en el registro de SIMAP. Idempotente."""
    registro = logging.getLogger(NOMBRE)
    if any(isinstance(h.formatter, FormatoJSON) for h in registro.handlers):
        return
    salida = logging.StreamHandler(sys.stdout)
    salida.setFormatter(FormatoJSON())
    registro.addHandler(salida)
    registro.setLevel(logging.INFO)
    # Sin propagar: el registro raíz de uvicorn volvería a escribir cada línea en su propio formato.
    registro.propagate = False


def evento(nombre: str, **datos: Any) -> None:
    """Registra un evento de negocio con nombre. Solo con datos que se puedan leer sin riesgo."""
    logging.getLogger(NOMBRE).info(nombre, extra={"datos": datos})
