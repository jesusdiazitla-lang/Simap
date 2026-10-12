"""Sincronización en lote de la cola sin conexión (RF-10; 05-fase2-activos-y-campo.md, sección 5.3).

Cuando un teléfono recupera la red, envía de una vez lo que capturó sin cobertura. Cada ítem se
procesa con su propio savepoint: uno inválido no tumba a los demás, y la respuesta dice qué pasó con
cada uno —creado, duplicado o rechazado con su motivo— para que el teléfono sepa cuáles quitar de su
cola.

Un ítem rechazado tampoco debe quedarse en la cola para siempre: el motivo dice por qué no entrará
nunca (equipo dado de baja, captura demasiado antigua), y el teléfono lo retira avisando a quien lo
capturó. Por eso cada ítem se valida aquí por separado y no en el esquema del lote: un 422 del lote
entero dejaría al teléfono sin saber cuál era el ítem malo.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.schemas.campo import ItemAlerta, ItemLectura, ItemLote, ResultadoItem
from app.services import alertas, lecturas
from app.services.capturas import CapturaInvalida

_VALIDADOR: TypeAdapter[ItemLectura | ItemAlerta] = TypeAdapter(ItemLote)


def _cliente_id(crudo: dict[str, Any]) -> UUID | None:
    """El `cliente_id` del ítem si se puede leer, aunque el resto del ítem no sea válido.

    Es lo que permite al teléfono saber qué ítem de su cola fue rechazado.
    """
    try:
        return UUID(str(crudo.get("cliente_id")))
    except ValueError:
        return None


def _motivo(error: ValidationError) -> str:
    primero = error.errors()[0]
    campo = ".".join(str(parte) for parte in primero["loc"]) or "ítem"
    return f"Dato no válido en «{campo}»: {primero['msg']}"


async def procesar_lote(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    items: list[dict[str, Any]],
) -> list[ResultadoItem]:
    resultados: list[ResultadoItem] = []
    for indice, crudo in enumerate(items):
        cliente_id = _cliente_id(crudo)
        try:
            item = _VALIDADOR.validate_python(crudo)
        except ValidationError as exc:
            resultados.append(
                ResultadoItem(
                    indice=indice, cliente_id=cliente_id, estado="rechazado", motivo=_motivo(exc)
                )
            )
            continue

        try:
            async with session.begin_nested():
                if isinstance(item, ItemLectura):
                    estado, _ = await lecturas.registrar(
                        session,
                        empresa_id=empresa_id,
                        autor_id=autor_id,
                        activo_id=item.activo_id,
                        valor=item.valor,
                        capturado_en=item.capturado_en,
                        cliente_id=item.cliente_id,
                    )
                else:
                    estado, _ = await alertas.reportar(
                        session,
                        empresa_id=empresa_id,
                        autor_id=autor_id,
                        activo_id=item.activo_id,
                        sintoma=item.sintoma,
                        nota=item.nota,
                        capturado_en=item.capturado_en,
                        cliente_id=item.cliente_id,
                    )
        except CapturaInvalida as exc:
            resultados.append(
                ResultadoItem(
                    indice=indice, cliente_id=item.cliente_id, estado="rechazado", motivo=str(exc)
                )
            )
            continue
        except IntegrityError:
            # Una restricción de la base que la validación no previó. El ítem se rechaza sin
            # detalle —el mensaje de PostgreSQL no es para el operario— y los demás siguen.
            resultados.append(
                ResultadoItem(
                    indice=indice,
                    cliente_id=item.cliente_id,
                    estado="rechazado",
                    motivo="El servidor no pudo guardar este dato.",
                )
            )
            continue
        resultados.append(
            ResultadoItem(
                indice=indice,
                cliente_id=item.cliente_id,
                estado="creado" if estado == "creado" else "duplicado",
            )
        )
    # Métrica de sincronización (sección 9.7): un salto en duplicados o rechazados delata un fallo
    # en los teléfonos antes de que nadie lo reporte.
    registro.evento(
        "campo.lote",
        recibidos=len(items),
        creados=sum(r.estado == "creado" for r in resultados),
        duplicados=sum(r.estado == "duplicado" for r in resultados),
        rechazados=sum(r.estado == "rechazado" for r in resultados),
    )
    return resultados
