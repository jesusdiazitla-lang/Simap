"""Equipos de la empresa: alta con código QR, ficha técnica y baja lógica (RF-04 a RF-07).

Todas las consultas pasan por la sesión de `get_db`, con el tenant fijado: ninguna función de este
módulo filtra por `empresa_id` a mano. RLS ya lo hace, y un filtro duplicado solo serviría para
creer que hay dos protecciones donde el código podría desincronizarlas. Lo que sí se escribe aquí es
la empresa de las filas **nuevas**, que sale siempre del token.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import Cursor
from app.models.activo import Activo
from app.models.componente import Componente
from app.models.lectura_horometro import LecturaHorometro
from app.models.orden_trabajo import ABIERTOS, OrdenTrabajo
from app.services import qr

#: Reintentos ante un choque de código (sección 6.1). Con 32⁸ combinaciones, dos seguidos ya serían
#: extraordinarios; cinco convierten en imposible práctico que el alta falle por mala suerte.
INTENTOS_CODIGO = 5


class ActivoNoEncontrado(Exception):
    """No existe, o es de otra empresa: desde fuera son lo mismo (404 en los dos casos)."""


class SinCodigoLibre(Exception):
    """No se encontró un código libre tras varios intentos. No debería ocurrir nunca."""


def _ahora() -> datetime:
    return datetime.now(UTC)


async def _guardar_con_codigo_nuevo(session: AsyncSession, activo: Activo) -> None:
    """Asigna un código aleatorio y guarda, reintentando si ya lo tiene otro equipo.

    El choque se detecta con la restricción UNIQUE global de `qr_code`, dentro de un savepoint para
    no perder la transacción. El error de la base nunca llega al cliente: o hay código, o
    `SinCodigoLibre` (sección 6.1).
    """
    for _ in range(INTENTOS_CODIGO):
        activo.qr_code = qr.generar_codigo()
        try:
            async with session.begin_nested():
                session.add(activo)
                await session.flush()
            return
        except IntegrityError as exc:
            if "uq_activos_qr_code" not in str(exc.orig):
                raise
    raise SinCodigoLibre


async def crear(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    datos: dict[str, Any],
    horometro_inicial: int = 0,
) -> Activo:
    """Da de alta un equipo con su código.

    Si se conoce el horómetro del día del alta, se guarda además como la primera lectura del
    historial, firmada por quien dio de alta el equipo. Sin ella, la primera lectura de campo no
    tendría con qué compararse y no se podría detectar un dígito de más. Con horómetro 0 no se crea:
    un cero que solo significa «no lo sé» haría que la primera lectura real pareciera un salto
    imposible.
    """
    ahora = _ahora()
    activo = Activo(
        empresa_id=empresa_id,
        horometro_actual=horometro_inicial,
        horometro_actualizado_en=ahora if horometro_inicial > 0 else None,
        **datos,
    )
    await _guardar_con_codigo_nuevo(session, activo)
    if horometro_inicial > 0:
        session.add(
            LecturaHorometro(
                empresa_id=empresa_id,
                activo_id=activo.id,
                registrado_por=autor_id,
                valor_horometro=horometro_inicial,
                cliente_id=uuid4(),
                capturado_en=ahora,
            )
        )
        await session.flush()
    return activo


async def obtener(session: AsyncSession, activo_id: UUID) -> Activo:
    activo: Activo | None = await session.scalar(select(Activo).where(Activo.id == activo_id))
    if activo is None:
        raise ActivoNoEncontrado(str(activo_id))
    return activo


async def por_codigo(session: AsyncSession, tecleado: str) -> Activo:
    """Resuelve lo que codifica un QR o lo que alguien tecleó de la etiqueta (sección 6.2).

    Un código mal formado, uno inexistente y uno de otra empresa dan exactamente el mismo resultado.
    Nunca un 403: confirmaría que el código existe y permitiría usar la respuesta para barrer
    códigos ajenos. Un equipo dado de baja sí resuelve, con su estado: quien escanea una etiqueta
    vieja tiene que entender qué pasa.
    """
    codigo = qr.normalizar(tecleado)
    if codigo is None:
        raise ActivoNoEncontrado(tecleado)
    activo: Activo | None = await session.scalar(select(Activo).where(Activo.qr_code == codigo))
    if activo is None:
        raise ActivoNoEncontrado(tecleado)
    return activo


async def listar(
    session: AsyncSession,
    *,
    estado: str | None = None,
    tipo: str | None = None,
    ubicacion: str | None = None,
    texto: str | None = None,
    cursor: Cursor | None = None,
    limite: int,
) -> tuple[list[Activo], Cursor | None]:
    """Listado por nombre, paginado por cursor (sección 9.1).

    Se pide una fila de más para saber si hay página siguiente sin un COUNT aparte.
    """
    consulta = select(Activo)
    if estado is not None:
        consulta = consulta.where(Activo.estado == estado)
    if tipo:
        consulta = consulta.where(Activo.tipo == tipo)
    if ubicacion:
        consulta = consulta.where(Activo.ubicacion == ubicacion)
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(
                Activo.nombre.ilike(patron),
                Activo.ubicacion.ilike(patron),
                Activo.tipo.ilike(patron),
                Activo.qr_code.ilike(patron.replace("-", "")),
            )
        )
    if cursor is not None:
        # «Después de» la última fila entregada, desempatando por id. Se escribe con OR/AND y no
        # con una comparación de tuplas para que valga en cualquier motor.
        consulta = consulta.where(
            or_(
                Activo.nombre > cursor.valor,
                and_(Activo.nombre == cursor.valor, Activo.id > cursor.id),
            )
        )
    consulta = consulta.order_by(Activo.nombre, Activo.id).limit(limite + 1)
    filas = list((await session.scalars(consulta)).all())
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1]
    return filas[:limite], Cursor(ultima.nombre, ultima.id)


class ObservacionInvalida(ValueError):
    """`observado_desde` posterior a la fecha actual de observación o en el futuro."""


async def editar(session: AsyncSession, activo_id: UUID, cambios: dict[str, Any]) -> Activo:
    """Cambia la ficha técnica. `cambios` ya viene validado y sin `qr_code` ni `empresa_id`.

    `observado_desde` (F5, decisión 8) solo puede adelantar `creado_en`, nunca posponerlo ni
    ponerlo en el futuro: lo contrario escondería horas de calendario a la disponibilidad.
    """
    activo = await obtener(session, activo_id)
    if "observado_desde" in cambios:
        desde = cambios.pop("observado_desde")
        if desde > _ahora() or desde > activo.creado_en:
            raise ObservacionInvalida(
                "La fecha desde la que se observa el equipo solo se puede adelantar, y no puede"
                " estar en el futuro."
            )
        activo.creado_en = desde
    for campo, valor in cambios.items():
        setattr(activo, campo, valor)
    await session.flush()
    return activo


async def dar_de_baja(session: AsyncSession, activo_id: UUID) -> Activo:
    """Baja lógica (RF-06): el equipo deja de admitir registros, pero su código sigue resolviendo y
    su historial sigue ahí. Dar de baja dos veces no cambia la fecha de la primera."""
    activo = await obtener(session, activo_id)
    if activo.estado != "baja":
        activo.estado = "baja"
        activo.dado_de_baja_en = _ahora()
        await session.flush()
    return activo


async def regenerar_codigo(session: AsyncSession, activo_id: UUID) -> Activo:
    """Código nuevo para una etiqueta copiada o comprometida (sección 6.3).

    El anterior deja de resolver en ese mismo momento: cualquiera que escanee la etiqueta vieja
    obtiene un 404. Hay que reimprimir.
    """
    activo = await obtener(session, activo_id)
    await _guardar_con_codigo_nuevo(session, activo)
    return activo


# --- Horómetro: cambio o reinicio (06-fase3, sección 5.1) --------------------------


class ReinicioInvalido(Exception):
    """El valor nuevo no puede ser el de un reinicio. El mensaje se muestra tal cual."""


async def reiniciar_horometro(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    autor_id: UUID,
    activo_id: UUID,
    nuevo: int,
    capturado_en: datetime | None = None,
    lectura: LecturaHorometro | None = None,
) -> Activo:
    """Cambio o reinicio del horómetro sin perder las horas acumuladas del equipo.

    El dial vuelve a un número bajo, pero las horas de vida del equipo —lo que mide el modelo— no:
    el offset absorbe la diferencia (`offset nuevo + valor nuevo = offset anterior + último valor`).

    Dos entradas pasan por aquí, para que ninguna deje las horas sin corregir:

    - `POST /activos/{id}/reinicio-horometro`: el administrador escribe el valor nuevo y se registra
      una lectura con `es_reinicio`.
    - La resolución `reinicio` de una lectura marcada (revisión 0006): `lectura` es esa lectura, ya
      guardada, y no se crea otra.

    El UPDATE va condicionado en el tiempo, como el de la fase 2: un reinicio no puede colocarse
    antes de la última lectura vigente. Si el valor nuevo es mayor que las horas ya acumuladas, el
    offset quedaría negativo y el CHECK de la base lo rechaza.

    La lectura del reinicio guarda el offset que deja (`offset_resultante`, revisión 0008): una
    falla capturada antes y recibida después se mide con el offset de su momento (`offset_en`).
    """
    activo = await obtener(session, activo_id)
    momento = capturado_en or _ahora()
    try:
        async with session.begin_nested():
            resultado = await session.execute(
                update(Activo)
                .where(
                    Activo.id == activo_id,
                    or_(
                        Activo.horometro_actualizado_en.is_(None),
                        Activo.horometro_actualizado_en <= momento,
                    ),
                )
                .values(
                    horometro_offset=Activo.horometro_offset + Activo.horometro_actual - nuevo,
                    horometro_actual=nuevo,
                    horometro_actualizado_en=momento,
                )
                .execution_options(synchronize_session=False)
            )
    except IntegrityError as exc:
        if "offset_no_negativo" not in str(exc.orig):
            raise
        raise ReinicioInvalido(
            f"El valor nuevo ({nuevo:,} h) es mayor que las horas que ya acumula el equipo "
            f"({activo.horometro_offset + activo.horometro_actual:,} h): no puede ser un reinicio."
        ) from exc
    if resultado.rowcount == 0:
        raise ReinicioInvalido(
            "Hay una lectura más reciente que este reinicio. Revisa el historial del equipo."
        )
    await session.refresh(activo)
    if lectura is None:
        session.add(
            LecturaHorometro(
                empresa_id=empresa_id,
                activo_id=activo_id,
                registrado_por=autor_id,
                valor_horometro=nuevo,
                cliente_id=uuid4(),
                capturado_en=momento,
                es_reinicio=True,
                offset_resultante=activo.horometro_offset,
            )
        )
    else:
        lectura.offset_resultante = activo.horometro_offset
    await session.flush()
    return activo


async def offset_en(session: AsyncSession, activo_id: UUID, instante: datetime) -> int | None:
    """El offset del horómetro vigente en `instante` (06-fase3, 5.1; revisión 0008).

    Es el que dejó el último reinicio capturado en o antes de ese instante, o 0 si no hubo ninguno:
    el offset solo lo mueve `reiniciar_horometro`. Usar el de hoy mediría mal una falla capturada
    antes de un reinicio y recibida después, y le sumaría a la vida del componente todo lo que el
    equipo acumuló antes del cambio. `None` si ese reinicio es anterior a la 0008 y su offset no se
    pudo reconstruir: quien llama no debe inventar una cifra.
    """
    reinicio = (
        await session.execute(
            select(LecturaHorometro.offset_resultante)
            .where(
                LecturaHorometro.activo_id == activo_id,
                or_(
                    LecturaHorometro.es_reinicio.is_(True),
                    LecturaHorometro.resolucion == "reinicio",
                ),
                LecturaHorometro.capturado_en <= instante,
            )
            .order_by(LecturaHorometro.capturado_en.desc(), LecturaHorometro.id.desc())
            .limit(1)
        )
    ).first()
    if reinicio is None:
        return 0
    offset: int | None = reinicio[0]
    return offset


# --- «En falla»: derivado de las órdenes abiertas, nunca guardado (06-fase3, 6.2) ---


async def ordenes_abiertas(
    session: AsyncSession, activo_id: UUID
) -> list[tuple[OrdenTrabajo, str]]:
    """Las órdenes abiertas del equipo con el nombre de su componente.

    «El equipo está en falla» es tener alguna. No se guarda en una columna del equipo: una columna
    duplicada es una que algún día se desincroniza. La consulta usa el índice único parcial de
    órdenes abiertas, así que es barata.
    """
    filas = await session.execute(
        select(OrdenTrabajo, Componente.nombre)
        .join(Componente, Componente.id == OrdenTrabajo.componente_id)
        .where(OrdenTrabajo.activo_id == activo_id, OrdenTrabajo.estado.in_(ABIERTOS))
        .order_by(OrdenTrabajo.numero)
    )
    return [(orden, nombre) for orden, nombre in filas.all()]


async def en_falla(session: AsyncSession, activo_ids: list[UUID]) -> set[UUID]:
    """Cuáles de estos equipos tienen alguna orden abierta: una consulta para toda la página del
    listado, no una por fila (sección 12.1)."""
    if not activo_ids:
        return set()
    filas = await session.scalars(
        select(OrdenTrabajo.activo_id)
        .where(OrdenTrabajo.activo_id.in_(activo_ids), OrdenTrabajo.estado.in_(ABIERTOS))
        .distinct()
    )
    return set(filas.all())
