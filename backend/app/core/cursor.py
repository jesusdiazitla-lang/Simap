"""Cursor de paginación opaco (05-fase2-activos-y-campo.md, sección 9.1).

POR QUÉ CURSOR Y NO OFFSET
--------------------------
`OFFSET 500` obliga a la base a recorrer y descartar 500 filas en cada página, y con inserciones
concurrentes salta o repite filas: si entra una lectura nueva mientras alguien pagina, la página
siguiente empieza una fila más tarde de lo que debería. Un cursor dice «dame lo que viene después
de esta fila» y sale directo del índice.

El cursor es la pareja (valor de ordenación, id) de la última fila entregada: la marca de tiempo en
las lecturas y alertas, el nombre en la lista de equipos. El `id` desempata filas con el mismo
valor, que en una ronda de campo sincronizada en lote son habituales.

Va codificado en base64 para que el cliente lo trate como una caja negra: si pudiera leerlo,
acabaría construyéndolo, y entonces cambiar el orden de un listado rompería a todos los clientes.
No es un mecanismo de seguridad —un cursor manipulado solo cambia desde dónde se pagina, y RLS sigue
filtrando—, así que no hace falta firmarlo.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class CursorInvalido(ValueError):
    """El cursor no se puede leer. La ruta lo traduce a 422."""


@dataclass(frozen=True, slots=True)
class Cursor:
    #: Valor de la columna por la que se ordena, como texto.
    valor: str
    id: UUID

    @classmethod
    def de_instante(cls, instante: datetime, id_: UUID) -> Cursor:
        return cls(instante.isoformat(), id_)

    def instante(self) -> datetime:
        try:
            instante = datetime.fromisoformat(self.valor)
        except ValueError as exc:
            raise CursorInvalido("cursor ilegible") from exc
        # Las columnas son `timestamptz`: un instante sin zona no se puede comparar con ellas y la
        # base lo rechaza con un error que sale como 500.
        if instante.tzinfo is None:
            raise CursorInvalido("cursor sin zona horaria")
        return instante

    def codificar(self) -> str:
        crudo = json.dumps({"v": self.valor, "i": str(self.id)})
        return base64.urlsafe_b64encode(crudo.encode()).decode().rstrip("=")

    @classmethod
    def decodificar(cls, valor: str) -> Cursor:
        try:
            relleno = "=" * (-len(valor) % 4)
            datos = json.loads(base64.urlsafe_b64decode(valor + relleno))
            cursor = cls(valor=str(datos["v"]), id=UUID(datos["i"]))
        except (binascii.Error, ValueError, KeyError, TypeError) as exc:
            raise CursorInvalido("cursor ilegible") from exc
        # PostgreSQL no admite el carácter nulo en un texto: compararlo con un nombre daría un 500.
        if "\x00" in cursor.valor:
            raise CursorInvalido("cursor ilegible")
        return cursor
