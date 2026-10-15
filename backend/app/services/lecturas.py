"""Lecturas de horómetro: idempotentes, con marca de revisión, sin retroceder nunca (RF-08).

Es el dato del que depende todo el modelo predictivo, así que aquí pesa tanto la integridad como que
la captura funcione (05-fase2-activos-y-campo.md, sección 5.1).

TRES GARANTÍAS
--------------
1. **Idempotencia.** El teléfono genera `cliente_id` antes del primer intento y lo repite en cada
   reintento. La restricción UNIQUE `(empresa_id, cliente_id)` hace que el mismo envío entre una
   sola vez aunque la red lo duplique; el segundo intento recibe la lectura que ya existía.
2. **El dato del operario nunca se pierde, pero tampoco ensucia.** Una lectura que no cuadra con las
   demás se guarda marcada (`requiere_revision`, con su motivo) y no mueve el horómetro vigente.
3. **El horómetro vigente nunca retrocede.** Se actualiza con un UPDATE condicionado y atómico, sin
   leer antes ni bloquear: una lectura vieja que llega tarde no hace retroceder el valor, y dos
   teléfonos reportando a la vez no se pisan (sección 9.4).

SIN `ON CONFLICT`
-----------------
El documento escribe el INSERT con `ON CONFLICT ... DO NOTHING`, que es sintaxis de PostgreSQL. Aquí
se usa el ORM dentro de un savepoint y se traduce el choque con la restricción: el resultado es el
mismo —la restricción de la base es quien decide— y el código no se ata a un motor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.core.config import get_settings
from app.core.cursor import Cursor
from app.models.activo import Activo
from app.models.lectura_horometro import LecturaHorometro as Lectura
from app.models.orden_trabajo import OrdenTrabajo
from app.services import activos
from app.services.capturas import CapturaInvalida, activo_en_servicio, validar_instante


async def _por_cliente_id(session: AsyncSession, cliente_id: UUID) -> Lectura | None:
    resultado: Lectura | None = await session.scalar(
        select(Lectura).where(Lectura.cliente_id == cliente_id)
    )
    return resultado


def _cuenta_como_valida() -> ColumnElement[bool]:
    """Lecturas que sirven de referencia: las no marcadas, y las marcadas que un supervisor confirmó
    o registró como reinicio del horómetro. Las pendientes y las descartadas no cuentan."""
    return or_(
        Lectura.requiere_revision.is_(False),
        Lectura.resolucion.in_(("confirmada", "reinicio")),
    )


# Los motivos se escriben con separador de miles con coma y punto decimal (`f"{n:,}"`), que es la
# convención de es-DO y la misma que usa la interfaz: «48,000 h» y «43,200 h» en la misma fila.


async def motivo_de_revision(
    session: AsyncSession, *, activo_id: UUID, valor: int, capturado_en: datetime
) -> str | None:
    """Por qué esta lectura no cuadra con las demás, o `None` si cuadra (sección 5.1).

    Se compara solo contra lecturas **válidas** (ver `_cuenta_como_valida`): una lectura con un
    dígito de más no puede convertirse en la referencia que hace parecer erróneas a todas las
    correctas que vengan detrás. Tras un reinicio confirmado, la lectura del reinicio es la nueva
    referencia, así que las siguientes ya no parecen «menores que la anterior».
    Las vecinas se buscan por `capturado_en`, no por orden de llegada: con la cola sin conexión, una
    lectura de esta mañana puede llegar después de una de esta tarde.
    """
    validas = (Lectura.activo_id == activo_id, _cuenta_como_valida())
    anterior: Lectura | None = await session.scalar(
        select(Lectura)
        .where(*validas, Lectura.capturado_en <= capturado_en)
        .order_by(Lectura.capturado_en.desc(), Lectura.id.desc())
        .limit(1)
    )
    posterior: Lectura | None = await session.scalar(
        select(Lectura)
        .where(*validas, Lectura.capturado_en > capturado_en)
        .order_by(Lectura.capturado_en.asc(), Lectura.id.asc())
        .limit(1)
    )
    if anterior is not None and valor < anterior.valor_horometro:
        return (
            f"Menor que la lectura anterior ({anterior.valor_horometro:,} h). "
            "¿Cambio o reinicio del horómetro, o un error al teclear?"
        )
    if posterior is not None and valor > posterior.valor_horometro:
        return (
            f"Mayor que una lectura posterior ya registrada ({posterior.valor_horometro:,} h). "
            "Llegó tarde y no cuadra con el historial."
        )
    if anterior is not None:
        horas_reloj = (capturado_en - anterior.capturado_en).total_seconds() / 3600
        incremento = valor - anterior.valor_horometro
        if incremento > horas_reloj + get_settings().horometro_tolerancia_horas:
            return (
                f"Sube {incremento:,} h en {horas_reloj:,.1f} h de reloj: una máquina no puede "
                "sumar más horas de operación que las que han pasado. ¿Un dígito de más?"
            )
    return None


async def registrar(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    activo_id: UUID,
    valor: int,
    capturado_en: datetime,
    cliente_id: UUID,
    ahora: datetime | None = None,
) -> tuple[str, Lectura]:
    """Registra una lectura. Devuelve `("creado" | "duplicado", lectura)`.

    El duplicado se comprueba antes que cualquier validación: un reintento de algo que ya entró
    tiene que responder «ya lo tengo» aunque, por ejemplo, el equipo se haya dado de baja después.
    Si no, el teléfono recibiría un rechazo por un dato que sí se guardó y avisaría de un fallo que
    no existe.
    """
    existente = await _por_cliente_id(session, cliente_id)
    if existente is not None:
        return "duplicado", existente

    validar_instante(capturado_en, ahora)
    if valor > get_settings().horometro_max:
        raise CapturaInvalida("Ese valor de horómetro está fuera del rango admitido.")
    await activo_en_servicio(session, activo_id)

    motivo = await motivo_de_revision(
        session, activo_id=activo_id, valor=valor, capturado_en=capturado_en
    )
    lectura = Lectura(
        empresa_id=empresa_id,
        activo_id=activo_id,
        registrado_por=autor_id,
        valor_horometro=valor,
        capturado_en=capturado_en,
        cliente_id=cliente_id,
        requiere_revision=motivo is not None,
        motivo_revision=motivo,
    )
    try:
        async with session.begin_nested():
            session.add(lectura)
            await session.flush()
    except IntegrityError as exc:
        # Dos reintentos del mismo envío llegaron a la vez y el otro ganó la carrera.
        if "uq_lecturas_horometro_idempotente" not in str(exc.orig):
            raise
        ganadora = await _por_cliente_id(session, cliente_id)
        if ganadora is None:
            raise
        return "duplicado", ganadora

    if motivo is None:
        await _avanzar_vigente(session, activo_id=activo_id, valor=valor, capturado_en=capturado_en)
    else:
        registro.evento("campo.lectura_marcada", activo_id=str(activo_id))
    return "creado", lectura


async def _avanzar_vigente(
    session: AsyncSession,
    *,
    activo_id: UUID,
    valor: int,
    capturado_en: datetime,
    aunque_baje: bool = False,
) -> None:
    """UPDATE condicionado (sección 5.1): el vigente solo avanza, en valor y en tiempo.

    Sin SELECT previo ni bloqueo explícito; la condición la evalúa la base en el mismo instante en
    que escribe. `aunque_baje` es para el reinicio del horómetro, el único caso en que el valor
    vigente puede bajar: sigue sin poder retroceder en el tiempo.
    """
    condiciones = [
        Activo.id == activo_id,
        or_(
            Activo.horometro_actualizado_en.is_(None),
            Activo.horometro_actualizado_en <= capturado_en,
        ),
    ]
    if not aunque_baje:
        condiciones.append(Activo.horometro_actual <= valor)
    await session.execute(
        update(Activo)
        .where(*condiciones)
        .values(horometro_actual=valor, horometro_actualizado_en=capturado_en)
        .execution_options(synchronize_session="fetch")
    )


class LecturaNoEncontrada(Exception):
    pass


class YaResuelta(Exception):
    """La lectura no está pendiente: no se marcó, o alguien ya la resolvió."""


class LecturaDeOrden(Exception):
    """La lectura la registró un reporte de falla: se confirma desde su orden."""

    def __init__(self, numero: int) -> None:
        super().__init__(f"OT-{numero:04d}")
        self.numero = numero


async def por_revisar(
    session: AsyncSession, *, cursor: Cursor | None, limite: int
) -> tuple[list[tuple[Lectura, str, str, int]], Cursor | None]:
    """Lecturas marcadas que nadie ha resuelto, con el nombre, código y horómetro de su equipo.

    De la más antigua a la más reciente: la que lleva más tiempo esperando es la que más estorba,
    porque mientras esté pendiente el horómetro del equipo no se mueve con ella.
    """
    consulta = (
        select(Lectura, Activo.nombre, Activo.qr_code, Activo.horometro_actual)
        .join(Activo, Activo.id == Lectura.activo_id)
        .where(Lectura.requiere_revision.is_(True), Lectura.resolucion.is_(None))
    )
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(
                Lectura.capturado_en > instante,
                and_(Lectura.capturado_en == instante, Lectura.id > cursor.id),
            )
        )
    consulta = consulta.order_by(Lectura.capturado_en, Lectura.id).limit(limite + 1)
    filas = [(lec, n, c, h) for lec, n, c, h in (await session.execute(consulta)).all()]
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1][0]
    return filas[:limite], Cursor.de_instante(ultima.capturado_en, ultima.id)


async def resolver(
    session: AsyncSession,
    *,
    revisor_id: UUID,
    lectura_id: UUID,
    resolucion: str,
    desde_orden: bool = False,
) -> Lectura:
    """Resuelve una lectura marcada (revisión 0006). Deja constancia de quién y cuándo.

    - `confirmada`: pasa a contar y, si es la más reciente, mueve el horómetro vigente hacia arriba.
    - `descartada`: se conserva, no cuenta.
    - `reinicio`: el horómetro se cambió o se puso a cero. Pasa por
      `activos.reiniciar_horometro`, que ajusta el offset para que las horas acumuladas del equipo
      no se pierdan (06-fase3, 5.1); las lecturas siguientes se comparan con esta.

    Una lectura que registró un reporte de falla se resuelve desde su orden (06-fase3, 5.3): la
    marca de la orden y la de la lectura son la misma decisión, y resolver una sin la otra dejaría
    la orden fuera de la fase 4 para siempre. `desde_orden` lo usa solo el servicio de órdenes.
    """
    if not desde_orden:
        orden = await session.scalar(
            select(OrdenTrabajo.numero).where(OrdenTrabajo.lectura_id == lectura_id)
        )
        if orden is not None:
            raise LecturaDeOrden(orden)
    # Escritura condicionada, como en `alertas.revisar`: si dos supervisores resuelven a la vez,
    # solo el primero cambia la fila; el segundo recibe «ya resuelta» en vez de pisar la decisión.
    resultado = await session.execute(
        update(Lectura)
        .where(
            Lectura.id == lectura_id,
            Lectura.requiere_revision.is_(True),
            Lectura.resolucion.is_(None),
        )
        .values(resolucion=resolucion, revisada_por=revisor_id, revisada_en=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    lectura: Lectura | None = await session.scalar(
        select(Lectura).where(Lectura.id == lectura_id).execution_options(populate_existing=True)
    )
    if lectura is None:
        raise LecturaNoEncontrada(str(lectura_id))
    if resultado.rowcount == 0:
        raise YaResuelta(str(lectura_id))
    registro.evento("campo.lectura_resuelta", resolucion=resolucion)
    if resolucion == "confirmada":
        await _avanzar_vigente(
            session,
            activo_id=lectura.activo_id,
            valor=lectura.valor_horometro,
            capturado_en=lectura.capturado_en,
        )
    elif resolucion == "reinicio":
        await activos.reiniciar_horometro(
            session,
            empresa_id=lectura.empresa_id,
            autor_id=revisor_id,
            activo_id=lectura.activo_id,
            nuevo=lectura.valor_horometro,
            capturado_en=lectura.capturado_en,
            lectura=lectura,
        )
    return lectura


async def listar(
    session: AsyncSession, *, activo_id: UUID, cursor: Cursor | None, limite: int
) -> tuple[list[Lectura], Cursor | None]:
    """Historial de un equipo, de la más reciente a la más antigua según `capturado_en`."""
    consulta = select(Lectura).where(Lectura.activo_id == activo_id)
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(
                Lectura.capturado_en < instante,
                and_(Lectura.capturado_en == instante, Lectura.id < cursor.id),
            )
        )
    consulta = consulta.order_by(Lectura.capturado_en.desc(), Lectura.id.desc()).limit(limite + 1)
    filas = list((await session.scalars(consulta)).all())
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], Cursor.de_instante(ultima.capturado_en, ultima.id)
