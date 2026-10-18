"""Órdenes de trabajo: reporte de falla, numeración, consulta, edición y corrección (RF-11..16).

`docs/contexto/06-fase3-ordenes-de-trabajo.md`. Las transiciones de estado viven en
`app.services.ordenes_estados`; aquí está todo lo demás que toca una orden.

Como el resto del plano de datos, ninguna consulta filtra por `empresa_id` a mano: RLS ya lo hace y
la empresa de las filas nuevas sale del token. Y como en la fase 2, el SQL lo escribe el ORM: lo que
el documento escribe con `ON CONFLICT` aquí es un savepoint y la traducción de la restricción por su
**nombre**, que da el mismo resultado sin atarse a un motor. Lo único propio de PostgreSQL (el
trigger de inmutabilidad, la vista de la fase 4) vive en la migración, y el parámetro que abre la
corrección, en `app.db.tenant`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import registro
from app.core.cursor import Cursor
from app.db.session import get_estrategia_tenant
from app.models.activo import Activo
from app.models.alerta import Alerta
from app.models.componente import Componente
from app.models.lectura_horometro import LecturaHorometro
from app.models.orden_trabajo import ABIERTOS, OrdenContador, OrdenEvento, OrdenTrabajo
from app.models.usuario import Usuario
from app.services import activos, lecturas
from app.services.capturas import activo_en_servicio, validar_instante

#: Espacio de nombres del `cliente_id` de la lectura que registra cada falla. Se deriva del de la
#: falla con uuid5 (sección 6.2): un reenvío de la falla reenvía la misma lectura, y no crea dos.
ESPACIO_LECTURA_DE_FALLA = UUID("5f1e8d6c-4a0b-4c3e-9d2a-7b1f0e6c3a94")

#: Cómo se leen los estados en los mensajes. La interfaz tiene los suyos; estos son para el
#: `detail` de un 409, que la pantalla muestra tal cual.
ETIQUETA_ESTADO = {
    "reportada": "Reportada",
    "en_taller": "En taller",
    "reparada": "Reparada",
    "cerrada": "Cerrada",
    "cancelada": "Cancelada",
}


def formato(numero: int) -> str:
    """OT-0001. La base guarda el entero; el formato es solo de presentación."""
    return f"OT-{numero:04d}"


# --- Errores -----------------------------------------------------------------------


class OrdenNoEncontrada(Exception):
    """No existe o es de otra empresa: desde fuera son lo mismo (404)."""


class ReferenciaInvalida(Exception):
    """Un componente o una alerta que no existen o no corresponden (422).

    Dice «no corresponde», nunca «es de otra empresa»: eso confirmaría que el identificador existe.
    """


class Conflicto(Exception):
    """409 con un código estable (sección 8.1) y, si aplica, la orden que lo causó."""

    def __init__(
        self,
        codigo: str,
        mensaje: str,
        *,
        orden_id: UUID | None = None,
        numero: int | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.orden_id = orden_id
        self.numero = numero


class UsuarioInactivo(Exception):
    """Dado de baja con un token que aún no ha caducado (sección 5.2): no puede actuar."""


class SinPermiso(Exception):
    """El rol no basta para esta acción sobre esta orden concreta (403)."""


# --- Quién actúa -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Actor:
    """Quien hace la acción, sacado del token: nunca del cuerpo de la petición."""

    empresa_id: UUID
    usuario_id: UUID
    rol: str


async def exigir_activo(session: AsyncSession, actor: Actor) -> None:
    """Corta a un usuario dado de baja cuyo token de acceso aún no ha caducado (sección 5.2).

    El login y la renovación ya lo rechazan, pero un token emitido antes de la baja vale hasta 30
    minutos. En lo que deja huella en una orden, eso se comprueba contra la base.
    """
    activo = await session.scalar(select(Usuario.activo).where(Usuario.id == actor.usuario_id))
    if not activo:
        raise UsuarioInactivo(str(actor.usuario_id))


# --- Piezas comunes -----------------------------------------------------------------


def _json(valor: Any) -> Any:
    """Valores de una columna a algo que JSON pueda guardar en `orden_eventos.datos`.

    Recursivo: el rechazo de cierre guarda el trabajo rechazado como un objeto anidado.
    """
    if isinstance(valor, dict):
        return {k: _json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_json(v) for v in valor]
    if isinstance(valor, UUID | datetime | date):
        return str(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


async def registrar_evento(
    session: AsyncSession,
    actor: Actor,
    orden: OrdenTrabajo,
    *,
    tipo: str,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
    nota: str | None = None,
    datos: dict[str, Any] | None = None,
) -> OrdenEvento:
    """Un paso del historial (RNF-06). Siempre en la misma transacción que lo que cuenta."""
    evento = OrdenEvento(
        empresa_id=actor.empresa_id,
        orden_id=orden.id,
        tipo=tipo,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        usuario_id=actor.usuario_id,
        rol_al_momento=actor.rol,
        nota=nota,
        datos={k: _json(v) for k, v in datos.items()} if datos else None,
    )
    session.add(evento)
    await session.flush()
    return evento


async def obtener(
    session: AsyncSession, orden_id: UUID, *, refrescar: bool = False
) -> OrdenTrabajo:
    consulta = select(OrdenTrabajo).where(OrdenTrabajo.id == orden_id)
    if refrescar:
        # Tras un UPDATE escrito con el ORM sin sincronizar la sesión: leer lo que hay en la base.
        consulta = consulta.execution_options(populate_existing=True)
    orden: OrdenTrabajo | None = await session.scalar(consulta)
    if orden is None:
        raise OrdenNoEncontrada(str(orden_id))
    return orden


async def explicar_cambio(session: AsyncSession, orden_id: UUID) -> Conflicto:
    """Por qué una transición no encontró la orden en el estado esperado (sección 9.3).

    La pantalla recarga la orden y muestra esto en vez de un error genérico: quién la movió y a
    dónde. Si la orden no existe para esta empresa, 404 y nada más.
    """
    orden = await obtener(session, orden_id, refrescar=True)
    ultimo = await session.execute(
        select(Usuario.nombre, OrdenEvento.estado_nuevo)
        .join(Usuario, Usuario.id == OrdenEvento.usuario_id)
        .where(OrdenEvento.orden_id == orden_id, OrdenEvento.estado_nuevo.is_not(None))
        .order_by(OrdenEvento.creado_en.desc())
        .limit(1)
    )
    fila = ultimo.first()
    estado = ETIQUETA_ESTADO[orden.estado]
    if fila is not None:
        mensaje = f"La orden cambió mientras tanto: {fila[0]} la dejó en «{estado}». Recárgala."
    else:
        mensaje = f"La orden cambió mientras tanto: ahora está en «{estado}». Recárgala."
    registro.evento("ordenes.conflicto", codigo="estado_cambiado")
    return Conflicto("estado_cambiado", mensaje, orden_id=orden.id, numero=orden.numero)


async def _abierta_de(
    session: AsyncSession, activo_id: UUID, componente_id: UUID
) -> OrdenTrabajo | None:
    resultado: OrdenTrabajo | None = await session.scalar(
        select(OrdenTrabajo).where(
            OrdenTrabajo.activo_id == activo_id,
            OrdenTrabajo.componente_id == componente_id,
            OrdenTrabajo.estado.in_(ABIERTOS),
        )
    )
    return resultado


async def _conflicto_abierta(
    session: AsyncSession, activo_id: UUID, componente_id: UUID
) -> Conflicto:
    existente = await _abierta_de(session, activo_id, componente_id)
    registro.evento("ordenes.conflicto", codigo="orden_abierta_existente")
    if existente is None:  # se cerró en el instante intermedio: que lo intente otra vez
        return Conflicto(
            "orden_abierta_existente",
            "Ese componente acaba de cambiar de orden. Vuelve a intentarlo.",
        )
    return Conflicto(
        "orden_abierta_existente",
        "Ya hay una orden abierta para ese componente de este equipo: "
        f"{formato(existente.numero)}.",
        orden_id=existente.id,
        numero=existente.numero,
    )


async def _componente_valido(session: AsyncSession, componente_id: UUID) -> Componente:
    componente: Componente | None = await session.scalar(
        select(Componente).where(Componente.id == componente_id)
    )
    if componente is None or not componente.activo:
        raise ReferenciaInvalida("Ese componente no está en el catálogo de la empresa.")
    return componente


async def _siguiente_numero(session: AsyncSession, empresa_id: UUID) -> int:
    """El siguiente número de orden de la empresa (sección 6.3).

    Un UPDATE que suma uno bloquea la fila del contador hasta el commit: dos fallas de la misma
    empresa se numeran una tras otra y nunca repiten número. Si la transacción se revierte, el
    número vuelve al contador, así que no quedan huecos. La primera orden de la empresa crea la
    fila; si dos la crean a la vez, la que pierde vuelve a intentar el UPDATE.
    """
    for _ in range(3):
        resultado = await session.execute(
            update(OrdenContador)
            .where(OrdenContador.empresa_id == empresa_id)
            .values(ultimo=OrdenContador.ultimo + 1)
            .execution_options(synchronize_session=False)
        )
        if resultado.rowcount:
            numero = await session.scalar(
                select(OrdenContador.ultimo).where(OrdenContador.empresa_id == empresa_id)
            )
            assert numero is not None
            return int(numero)
        try:
            async with session.begin_nested():
                session.add(OrdenContador(empresa_id=empresa_id, ultimo=1))
                await session.flush()
            return 1
        except IntegrityError:
            continue
    raise RuntimeError("No se pudo obtener el número de la orden.")


# --- Reporte de falla (sección 6.2) ----------------------------------------------------


async def _por_cliente_id(session: AsyncSession, cliente_id: UUID) -> OrdenTrabajo | None:
    resultado: OrdenTrabajo | None = await session.scalar(
        select(OrdenTrabajo).where(OrdenTrabajo.cliente_id == cliente_id)
    )
    return resultado


#: Motivo de revisión cuando no se sabe qué offset tenía el horómetro en la fecha de la falla.
OFFSET_DESCONOCIDO = (
    "No se sabe qué offset tenía el horómetro en la fecha de la falla (reinicio anterior a la "
    "revisión 0008): revisa las horas acumuladas antes de confirmar."
)


async def _horas_acumuladas(
    session: AsyncSession, activo: Activo, instante: datetime, dial: int
) -> int | None:
    """Lo que mide la fase 4: el dial más el offset **vigente en `instante`** (06-fase3, 5.1).

    Con el offset de hoy, una falla capturada antes de un reinicio y recibida después contaría dos
    veces todo lo que el equipo acumuló antes del cambio. Sin reinicios posteriores es el offset
    actual, que se usa sin consultar. `None` si ese offset no se conoce.
    """
    if activo.horometro_actualizado_en is None or activo.horometro_actualizado_en <= instante:
        # Ningún reinicio puede ser posterior a la última actualización del horómetro.
        return activo.horometro_offset + dial
    offset = await activos.offset_en(session, activo.id, instante)
    return None if offset is None else offset + dial


async def reportar_falla(
    session: AsyncSession,
    actor: Actor,
    *,
    activo_id: UUID,
    componente_id: UUID,
    horometro: int,
    descripcion: str,
    capturado_en: datetime,
    cliente_id: UUID,
    temperatura: Decimal | None = None,
    codigo_error: str | None = None,
    alerta_id: UUID | None = None,
    ahora: datetime | None = None,
) -> tuple[str, OrdenTrabajo]:
    """Crea la orden de una falla. Devuelve `("creado" | "duplicado", orden)`.

    Sigue la secuencia del documento, en una sola transacción; cualquier excepción la revierte
    entera, también la lectura y el número:

    1. Reenvío del mismo `cliente_id`: la orden que ya existe, antes de cualquier validación.
    2. Equipo en servicio bajo RLS (404 si no es de la empresa), componente del catálogo y alerta
       del mismo equipo, pendiente o revisada (422 o 409).
    3. La lectura de horómetro de la falla, con las reglas de la fase 2. Si queda marcada, la orden
       hereda la marca y la fase 4 la excluye hasta que alguien confirme el horómetro. Las horas
       acumuladas usan el offset vigente en el momento de la falla, no el de hoy (5.1).
    4. Número del contador e INSERT, en un savepoint: si choca, el número vuelve al contador.
    5. La alerta pasa a `convertida_en_orden` con un UPDATE condicionado.
    6. El evento «creada».
    """
    existente = await _por_cliente_id(session, cliente_id)
    if existente is not None:
        return "duplicado", existente

    await exigir_activo(session, actor)
    validar_instante(capturado_en, ahora)
    activo = await activo_en_servicio(session, activo_id)
    await _componente_valido(session, componente_id)
    if alerta_id is not None:
        alerta: Alerta | None = await session.scalar(select(Alerta).where(Alerta.id == alerta_id))
        if alerta is None or alerta.activo_id != activo_id:
            raise ReferenciaInvalida("Esa alerta no corresponde a este equipo.")
        if alerta.estado not in ("pendiente", "revisada"):
            raise Conflicto(
                "alerta_no_disponible",
                "Esa alerta ya no se puede convertir: se descartó o ya originó una orden.",
            )
    # El caso común se responde antes de tocar nada; el índice único sigue siendo quien decide.
    if await _abierta_de(session, activo_id, componente_id) is not None:
        raise await _conflicto_abierta(session, activo_id, componente_id)

    _, lectura = await lecturas.registrar(
        session,
        empresa_id=actor.empresa_id,
        autor_id=actor.usuario_id,
        activo_id=activo_id,
        valor=horometro,
        capturado_en=capturado_en,
        cliente_id=uuid5(ESPACIO_LECTURA_DE_FALLA, str(cliente_id)),
        ahora=ahora,
    )
    marcada = lectura.requiere_revision and lectura.resolucion is None
    motivo = lectura.motivo_revision if marcada else None
    horas = await _horas_acumuladas(session, activo, capturado_en, horometro)
    if horas is None:
        # Un reinicio anterior a la revisión 0008 cuyo offset no se pudo reconstruir: mejor una
        # orden marcada que una vida de componente con una cifra inventada.
        horas, marcada = activo.horometro_offset + horometro, True
        motivo = motivo or OFFSET_DESCONOCIDO
    orden = OrdenTrabajo(
        empresa_id=actor.empresa_id,
        cliente_id=cliente_id,
        activo_id=activo_id,
        componente_id=componente_id,
        alerta_origen_id=alerta_id,
        lectura_id=lectura.id,
        reportado_por=actor.usuario_id,
        horometro_en_falla=horometro,
        horas_acumuladas_en_falla=horas,
        temperatura=temperatura,
        codigo_error=codigo_error,
        descripcion=descripcion,
        fecha_falla=capturado_en,
        requiere_revision=marcada,
        motivo_revision=motivo,
    )
    try:
        async with session.begin_nested():
            orden.numero = await _siguiente_numero(session, actor.empresa_id)
            session.add(orden)
            await session.flush()
    except IntegrityError as exc:
        # Lo primero, en cualquier choque: ¿es un reenvío del mismo envío que ganó la carrera? Dos
        # reenvíos simultáneos violan a la vez la idempotencia y la única abierta por componente, y
        # la base puede quejarse de cualquiera de las dos. El savepoint ya devolvió el número.
        ganadora = await _por_cliente_id(session, cliente_id)
        if ganadora is not None:
            return "duplicado", ganadora
        texto = str(exc.orig)
        if "ix_ordenes_trabajo_una_abierta_por_componente" in texto:
            raise await _conflicto_abierta(session, activo_id, componente_id) from exc
        if "ix_ordenes_trabajo_una_por_alerta" in texto:
            raise Conflicto(
                "alerta_no_disponible", "Esa alerta acaba de originar otra orden."
            ) from exc
        if "mismo_tenant" in texto:
            raise ReferenciaInvalida("Alguna referencia de la orden no es válida.") from exc
        raise

    if alerta_id is not None:
        convertida = await session.execute(
            update(Alerta)
            .where(Alerta.id == alerta_id, Alerta.estado.in_(("pendiente", "revisada")))
            .values(estado="convertida_en_orden")
            .execution_options(synchronize_session=False)
        )
        if convertida.rowcount == 0:
            # Cambió en este instante. La excepción revierte la orden, la lectura y el número.
            raise Conflicto(
                "alerta_no_disponible", "Esa alerta cambió de estado mientras se reportaba."
            )

    await registrar_evento(
        session,
        actor,
        orden,
        tipo="creada",
        estado_nuevo="reportada",
        datos={
            "numero": orden.numero,
            "componente_id": componente_id,
            "horometro": horometro,
            "alerta_id": alerta_id,
            "requiere_revision": marcada,
        },
    )
    registro.evento("ordenes.creada", requiere_revision=marcada, desde_alerta=alerta_id is not None)
    return "creado", orden


# --- Consulta ------------------------------------------------------------------------


GRUPOS = {
    "abiertas": ABIERTOS,
    "cerradas": ("cerrada",),
    "canceladas": ("cancelada",),
}


async def listar(
    session: AsyncSession,
    *,
    filtro: str | None,
    activo_id: UUID | None = None,
    componente_id: UUID | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    cursor: Cursor | None,
    limite: int,
) -> tuple[list[tuple[OrdenTrabajo, str, str, str]], Cursor | None]:
    """Bandeja de órdenes de la más reciente a la más antigua por `fecha_falla` (sección 12.1).

    Cada fila trae el nombre y el código del equipo y el nombre del componente, en la misma
    consulta: nada de una consulta más por fila. Cursor sobre `(fecha_falla, id)`.
    """
    consulta = (
        select(OrdenTrabajo, Activo.nombre, Activo.qr_code, Componente.nombre)
        .join(Activo, Activo.id == OrdenTrabajo.activo_id)
        .join(Componente, Componente.id == OrdenTrabajo.componente_id)
    )
    if filtro is not None:
        consulta = consulta.where(OrdenTrabajo.estado.in_(GRUPOS.get(filtro, (filtro,))))
    if activo_id is not None:
        consulta = consulta.where(OrdenTrabajo.activo_id == activo_id)
    if componente_id is not None:
        consulta = consulta.where(OrdenTrabajo.componente_id == componente_id)
    if desde is not None:
        consulta = consulta.where(OrdenTrabajo.fecha_falla >= desde)
    if hasta is not None:
        consulta = consulta.where(OrdenTrabajo.fecha_falla < hasta)
    if cursor is not None:
        instante = cursor.instante()
        consulta = consulta.where(
            or_(
                OrdenTrabajo.fecha_falla < instante,
                and_(OrdenTrabajo.fecha_falla == instante, OrdenTrabajo.id < cursor.id),
            )
        )
    consulta = consulta.order_by(OrdenTrabajo.fecha_falla.desc(), OrdenTrabajo.id.desc()).limit(
        limite + 1
    )
    filas = [(o, n, c, comp) for o, n, c, comp in (await session.execute(consulta)).all()]
    if len(filas) <= limite:
        return filas, None
    ultima = filas[limite - 1][0]
    return filas[:limite], Cursor.de_instante(ultima.fecha_falla, ultima.id)


@dataclass(frozen=True, slots=True)
class Detalle:
    orden: OrdenTrabajo
    activo_nombre: str
    activo_codigo: str
    componente_nombre: str
    eventos: list[OrdenEvento]
    #: id -> (nombre, activo) de cada persona que aparece en la orden o en su historial.
    personas: dict[UUID, tuple[str, bool]]


async def detalle(session: AsyncSession, orden_id: UUID) -> Detalle:
    """La orden con su historial y el nombre de cada responsable (RF-14).

    Los nombres salen de `usuarios`, que nunca se borran: alguien dado de baja sigue apareciendo
    con su nombre (sección 5.2).
    """
    fila = (
        await session.execute(
            select(OrdenTrabajo, Activo.nombre, Activo.qr_code, Componente.nombre)
            .join(Activo, Activo.id == OrdenTrabajo.activo_id)
            .join(Componente, Componente.id == OrdenTrabajo.componente_id)
            .where(OrdenTrabajo.id == orden_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if fila is None:
        raise OrdenNoEncontrada(str(orden_id))
    orden, activo_nombre, activo_codigo, componente_nombre = fila
    eventos = list(
        (
            await session.scalars(
                select(OrdenEvento)
                .where(OrdenEvento.orden_id == orden_id)
                .order_by(OrdenEvento.creado_en, OrdenEvento.id)
            )
        ).all()
    )
    ids = {orden.reportado_por, *(e.usuario_id for e in eventos)}
    ids |= {i for i in (orden.reparado_por, orden.autorizado_por) if i is not None}
    personas = {
        uid: (nombre, activo)
        for uid, nombre, activo in (
            await session.execute(
                select(Usuario.id, Usuario.nombre, Usuario.activo).where(Usuario.id.in_(ids))
            )
        ).all()
    }
    return Detalle(orden, activo_nombre, activo_codigo, componente_nombre, eventos, personas)


# --- Edición de una orden abierta (sección 8) --------------------------------------------


async def editar(
    session: AsyncSession, actor: Actor, orden_id: UUID, cambios: dict[str, Any]
) -> OrdenTrabajo:
    """Descripción, código de error, temperatura o componente, solo con la orden abierta.

    El caso típico: se reportó con «Otro (por identificar)» y en el taller se supo qué era. Deja
    evento con los valores anteriores. Una orden cerrada no se edita: se corrige (`corregir`).
    """
    await exigir_activo(session, actor)
    orden = await obtener(session, orden_id)
    if orden.estado not in ABIERTOS:
        raise Conflicto(
            "orden_cerrada",
            "La orden ya no está abierta. Una orden cerrada solo la corrige el administrador.",
            orden_id=orden.id,
            numero=orden.numero,
        )
    if "componente_id" in cambios:
        await _componente_valido(session, cambios["componente_id"])
    diferencias = {
        campo: {"antes": _json(getattr(orden, campo)), "despues": _json(valor)}
        for campo, valor in cambios.items()
        if getattr(orden, campo) != valor
    }
    if not diferencias:
        return orden
    try:
        async with session.begin_nested():
            resultado = await session.execute(
                update(OrdenTrabajo)
                .where(OrdenTrabajo.id == orden_id, OrdenTrabajo.estado.in_(ABIERTOS))
                .values(**{c: cambios[c] for c in diferencias})
                .execution_options(synchronize_session=False)
            )
    except IntegrityError as exc:
        if "ix_ordenes_trabajo_una_abierta_por_componente" in str(exc.orig):
            raise await _conflicto_abierta(
                session, orden.activo_id, cambios["componente_id"]
            ) from exc
        raise
    if resultado.rowcount == 0:
        raise await explicar_cambio(session, orden_id)
    orden = await obtener(session, orden_id, refrescar=True)
    await registrar_evento(
        session,
        actor,
        orden,
        tipo="nota",
        nota="Datos de la orden editados.",
        datos={"cambios": diferencias},
    )
    return orden


async def agregar_nota(
    session: AsyncSession, actor: Actor, orden_id: UUID, nota: str
) -> OrdenEvento:
    """Nota libre en el historial. También sobre una orden cerrada: es un evento, no un cambio."""
    await exigir_activo(session, actor)
    orden = await obtener(session, orden_id)
    return await registrar_evento(session, actor, orden, tipo="nota", nota=nota)


# --- Horómetro dudoso y corrección administrativa (secciones 6.2 y 6.5) -----------------


async def confirmar_horometro(session: AsyncSession, actor: Actor, orden_id: UUID) -> OrdenTrabajo:
    """Quita la marca de revisión de la orden y confirma su lectura (sección 6.2).

    Con la orden abierta, supervisor o administrador. Cerrada, es una corrección administrativa:
    solo el administrador, y deja un evento `correccion`. La lectura enlazada se confirma en la
    misma transacción, porque es la misma decisión.

    Recalcula las horas acumuladas con el offset vigente en la fecha de la falla (5.1): un reinicio
    resuelto después del reporte puede haberlo cambiado. Es el único momento en que esa columna
    cambia, y lo impone el trigger `ot_horas_solo_al_confirmar` (revisión 0008).
    """
    await exigir_activo(session, actor)
    orden = await obtener(session, orden_id)
    if not orden.requiere_revision:
        raise Conflicto(
            "sin_revision",
            "El horómetro de esta orden no está pendiente de revisión.",
            orden_id=orden.id,
            numero=orden.numero,
        )
    abierta = orden.estado in ABIERTOS
    if not abierta:
        if actor.rol != "administrador":
            raise SinPermiso("Con la orden cerrada, solo el administrador puede confirmarlo.")
        await get_estrategia_tenant().permitir_correccion(session)
    activo: Activo = await session.get_one(Activo, orden.activo_id, populate_existing=True)
    horas_antes = orden.horas_acumuladas_en_falla
    horas = await _horas_acumuladas(session, activo, orden.fecha_falla, orden.horometro_en_falla)
    if horas is None:
        horas = horas_antes
    condiciones = [OrdenTrabajo.id == orden_id, OrdenTrabajo.requiere_revision.is_(True)]
    if abierta:
        condiciones.append(OrdenTrabajo.estado.in_(ABIERTOS))
    resultado = await session.execute(
        update(OrdenTrabajo)
        .where(*condiciones)
        .values(requiere_revision=False, horas_acumuladas_en_falla=horas)
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount == 0:
        raise await explicar_cambio(session, orden_id)
    if orden.lectura_id is not None:
        pendiente = await session.scalar(
            select(LecturaHorometro.id).where(
                LecturaHorometro.id == orden.lectura_id,
                LecturaHorometro.requiere_revision.is_(True),
                LecturaHorometro.resolucion.is_(None),
            )
        )
        if pendiente is not None:
            await lecturas.resolver(
                session,
                revisor_id=actor.usuario_id,
                lectura_id=orden.lectura_id,
                resolucion="confirmada",
                desde_orden=True,
            )
    orden = await obtener(session, orden_id, refrescar=True)
    await registrar_evento(
        session,
        actor,
        orden,
        tipo="nota" if abierta else "correccion",
        nota="Horómetro de la falla confirmado.",
        datos={
            "requiere_revision": {"antes": True, "despues": False},
            **(
                {"horas_acumuladas_en_falla": {"antes": horas_antes, "despues": horas}}
                if horas != horas_antes
                else {}
            ),
        },
    )
    return orden


#: Lo único que la corrección administrativa puede tocar (sección 6.5). Nunca estado, número,
#: fechas ni responsables.
CAMPOS_CORREGIBLES = (
    "descripcion",
    "trabajo_realizado",
    "codigo_error",
    "temperatura",
    "tipo_intervencion",
    "requiere_revision",
)


async def corregir(
    session: AsyncSession, actor: Actor, orden_id: UUID, cambios: dict[str, Any], nota: str
) -> OrdenTrabajo:
    """Corrección administrativa de una orden cerrada (sección 6.5): el único camino para cambiarla.

    Solo el administrador (lo exige la ruta), con nota, sobre una lista cerrada de campos, y siempre
    con un evento `correccion` que guarda los valores anteriores y los nuevos. Como cambiar el tipo
    de intervención o la marca de revisión altera los intervalos de la fase 4, ese evento sirve
    también para saber cuándo reajustar el modelo.
    """
    await exigir_activo(session, actor)
    orden = await obtener(session, orden_id)
    if orden.estado != "cerrada":
        raise Conflicto(
            "no_corregible",
            "Solo se corrige una orden cerrada. Una abierta se edita; una cancelada no cambia.",
            orden_id=orden.id,
            numero=orden.numero,
        )
    cambios = {c: v for c, v in cambios.items() if c in CAMPOS_CORREGIBLES}
    diferencias = {
        campo: {"antes": _json(getattr(orden, campo)), "despues": _json(valor)}
        for campo, valor in cambios.items()
        if getattr(orden, campo) != valor
    }
    if not diferencias:
        raise ReferenciaInvalida("La corrección no cambia nada de la orden.")
    valores = {c: cambios[c] for c in diferencias}
    if valores.get("requiere_revision") is True and orden.motivo_revision is None:
        # La base exige un motivo para toda orden marcada: el de la corrección es su nota.
        valores["motivo_revision"] = f"Marcada en una corrección: {nota}"
    await get_estrategia_tenant().permitir_correccion(session)
    await session.execute(
        update(OrdenTrabajo)
        .where(OrdenTrabajo.id == orden_id, OrdenTrabajo.estado == "cerrada")
        .values(**valores)
        .execution_options(synchronize_session=False)
    )
    orden = await obtener(session, orden_id, refrescar=True)
    await registrar_evento(
        session, actor, orden, tipo="correccion", nota=nota, datos={"cambios": diferencias}
    )
    registro.evento("ordenes.correccion", campos=",".join(sorted(diferencias)))
    return orden


def ahora() -> datetime:
    return datetime.now(UTC)
