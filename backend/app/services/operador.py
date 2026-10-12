"""Lógica del plano de control: dar de alta clientes y mantenerlos.

Aquí vive lo que puede hacer quien opera SIMAP. Las rutas solo traducen entre HTTP y estas
funciones, y todas reciben una sesión abierta con el rol `operador_user`, que es lo que impide por
construcción que desde aquí se toquen datos de negocio.

TODA ACCIÓN QUEDA REGISTRADA
----------------------------
Crear una empresa, suspenderla o restablecer la contraseña del administrador de una planta son
acciones con poder sobre el acceso de otras personas. Ninguna ocurre sin dejar un asiento en
`operador_bitacora` con quién, cuándo y sobre qué. El registro es parte de la operación, no un
añadido posterior: se escribe en la misma transacción, así que o quedan las dos cosas o ninguna.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.almacen import AlmacenEfimero
from app.core.security import (
    Rol,
    crear_token_de_acceso_operador,
    crear_token_de_refresco_operador,
    generar_clave_temporal,
    hash_password,
    necesita_rehash,
    verify_password,
)
from app.models.activo import Activo
from app.models.empresa import Empresa
from app.models.operador import AccionOperador, BitacoraOperador, Operador
from app.models.usuario import Usuario
from app.services import componentes, limites

#: Hash de descarte con el que se compara cuando el correo no existe, para que un intento con
#: correo inexistente tarde lo mismo que uno con correo real. Ver `app.services.auth`.
_HASH_SENUELO = hash_password("senuelo-del-plano-de-control")


class ErrorDeAutenticacion(Exception):
    """Credenciales de operador inválidas. Sin detalle: el motivo no sale hacia el cliente."""


class ClaveActualIncorrecta(Exception):
    """Al cambiar su clave, el operador no escribió bien la actual."""


class CorreoYaRegistrado(Exception):
    """El correo ya pertenece a un usuario de alguna empresa."""


class EmpresaNoEncontrada(Exception):
    """La empresa no existe."""


class SinAdministrador(Exception):
    """La empresa existe pero no tiene ningún administrador al que restablecerle la clave."""


@dataclass(frozen=True, slots=True)
class SesionOperador:
    operador: Operador
    token_acceso: str
    token_refresco: str
    expira_en_segundos: int


def _sesion_para(operador: Operador, expira_en_segundos: int) -> SesionOperador:
    return SesionOperador(
        operador=operador,
        token_acceso=crear_token_de_acceso_operador(operador.id),
        token_refresco=crear_token_de_refresco_operador(operador.id),
        expira_en_segundos=expira_en_segundos,
    )


async def _anotar(
    session: AsyncSession,
    *,
    operador_id: UUID,
    accion: str,
    empresa_id: UUID | None = None,
    detalle: str | None = None,
) -> None:
    session.add(
        BitacoraOperador(
            operador_id=operador_id, accion=accion, empresa_id=empresa_id, detalle=detalle
        )
    )


# --- Sesión -------------------------------------------------------------------


def _clave_limite(correo: str, ip: str | None) -> tuple[str, str]:
    """Claves del límite del login de la consola.

    Prefijo propio, no el de `/auth/login`: los fallos en una puerta no deben cerrar la otra. Si
    compartieran contador, bastaría golpear la consola con el correo de un administrador de planta
    para dejarlo fuera de su propia empresa.
    """
    return f"op-login:correo:{correo}", f"op-login:ip:{ip or 'desconocida'}"


async def autenticar(
    session: AsyncSession,
    almacen: AlmacenEfimero,
    *,
    correo: str,
    password: str,
    expira_en_segundos: int,
    ip: str | None = None,
) -> SesionOperador:
    """Valida las credenciales de un operador y abre sesión.

    Con límite de intentos, como el login de las plantas (sección 6.2). Es la cuenta con más poder
    del sistema: si alguna puerta necesita límite, es esta.

    Compara siempre contra algún hash, exista el correo o no: sin eso, un intento con correo
    inexistente respondería en microsegundos y uno real tardaría lo que tarda Argon2, y esa
    diferencia de tiempo revela qué cuentas existen.
    """
    correo = correo.strip().lower()
    clave_correo, clave_ip = _clave_limite(correo, ip)
    await limites.comprobar_login(almacen, clave_correo=clave_correo, clave_ip=clave_ip)

    fila = await session.execute(select(Operador).where(Operador.correo == correo))
    operador: Operador | None = fila.scalar_one_or_none()

    hash_a_comparar = operador.password_hash if operador is not None else _HASH_SENUELO
    coincide = verify_password(password, hash_a_comparar)

    if operador is None or not coincide or not operador.activo:
        raise ErrorDeAutenticacion(correo)

    if necesita_rehash(operador.password_hash):
        operador.password_hash = hash_password(password)

    await limites.olvidar(almacen, [clave_correo])
    return _sesion_para(operador, expira_en_segundos)


async def operador_actual(session: AsyncSession, operador_id: UUID) -> Operador | None:
    fila = await session.execute(
        select(Operador).where(Operador.id == operador_id, Operador.activo.is_(True))
    )
    return fila.scalar_one_or_none()


async def cambiar_password(
    session: AsyncSession,
    almacen: AlmacenEfimero,
    *,
    operador_id: UUID,
    password_actual: str,
    password_nueva: str,
    expira_en_segundos: int,
) -> SesionOperador:
    """El operador cambia su propia contraseña.

    Hasta que existió esto, la credencial más poderosa del sistema era la única que no se podía
    rotar: el operador restablecía las claves de los administradores, pero la suya solo se cambiaba
    borrando la fila y volviendo a sembrarla por consola.

    Exige la actual y comparte el límite de intentos con su login. Queda en la bitácora.

    Las sesiones del operador no se renuevan —no hay ruta de refresco en la consola—, así que no
    hace falta versionar su clave como la de los usuarios: otra sesión abierta muere sola cuando
    caduca su token de acceso, en 30 minutos como mucho.
    """
    claves = [f"cambio-clave:operador:{operador_id}"]
    await limites.comprobar(almacen, claves)

    operador = await operador_actual(session, operador_id)
    if operador is None:
        raise ErrorDeAutenticacion(str(operador_id))
    if not verify_password(password_actual, operador.password_hash):
        raise ClaveActualIncorrecta

    operador.password_hash = hash_password(password_nueva)
    await _anotar(session, operador_id=operador.id, accion=AccionOperador.CAMBIO_CLAVE_PROPIA)
    await session.flush()
    await limites.olvidar(almacen, claves)
    return _sesion_para(operador, expira_en_segundos)


# --- Empresas -----------------------------------------------------------------


async def dar_de_alta_empresa(
    session: AsyncSession,
    *,
    operador_id: UUID,
    empresa: str,
    admin_nombre: str,
    admin_correo: str,
) -> tuple[Empresa, Usuario, str]:
    """Crea una empresa cliente y su primer usuario administrador (RF-01).

    Devuelve además la contraseña temporal **en claro**, que es la única vez que existe fuera de su
    hash. Quien opera SIMAP se la pasa al administrador del cliente y este la cambia; si se pierde,
    se genera otra con `restablecer_clave_administrador`.

    El correo duplicado se detecta por la restricción UNIQUE de la base y no con un SELECT previo:
    es lo correcto frente a dos altas simultáneas con el mismo correo.
    """
    admin_correo = admin_correo.strip().lower()
    password = generar_clave_temporal()

    nueva = Empresa(nombre=empresa.strip())
    session.add(nueva)
    # flush, no commit: empuja el INSERT para obtener el id sin cerrar la transacción, de modo que
    # empresa, administrador y asiento de bitácora se crean juntos o no se crea ninguno.
    await session.flush()

    admin = Usuario(
        empresa_id=nueva.id,
        nombre=admin_nombre.strip(),
        correo=admin_correo,
        password_hash=hash_password(password),
        rol=Rol.ADMINISTRADOR.value,
    )
    session.add(admin)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_usuarios_correo" in str(exc.orig):
            raise CorreoYaRegistrado(admin_correo) from exc
        raise

    # Catálogo inicial de componentes (05-fase2-activos-y-campo.md, sección 2), en la misma
    # transacción: no puede existir una empresa sin catálogo. El rol del operador puede INSERTAR en
    # `componentes` pero no leerlos (revisión 0005).
    session.add_all(componentes.plantilla_para(nueva.id))
    await session.flush()

    await _anotar(
        session,
        operador_id=operador_id,
        accion=AccionOperador.ALTA_EMPRESA,
        empresa_id=nueva.id,
        detalle=f"Empresa «{nueva.nombre}» con administrador {admin_correo}",
    )
    return nueva, admin, password


async def listar_empresas(session: AsyncSession) -> list[tuple[Empresa, Usuario | None]]:
    """Todas las empresas con su administrador de referencia, para la consola.

    Desde que cada empresa gestiona su personal (RF-03) puede tener varios administradores; se
    muestra el activo más antiguo, que suele ser el que se dio de alta con la empresa. Con un JOIN
    simple, una empresa con dos administradores aparecería dos veces en la lista.

    `outerjoin` y no `join`: una empresa sin ningún administrador activo sigue existiendo y tiene
    que aparecer, porque justamente es la que necesita atención.
    """
    referencia = (
        select(Usuario.id)
        .where(
            Usuario.empresa_id == Empresa.id,
            Usuario.rol == Rol.ADMINISTRADOR.value,
            Usuario.activo.is_(True),
        )
        .order_by(Usuario.creado_en)
        .limit(1)
        .correlate(Empresa)
        .scalar_subquery()
    )
    consulta = (
        select(Empresa, Usuario)
        .outerjoin(Usuario, Usuario.id == referencia)
        .order_by(Empresa.nombre)
    )
    filas = await session.execute(consulta)
    return [(e, u) for e, u in filas.all()]


async def contar_equipos(session: AsyncSession) -> dict[UUID, int]:
    """Equipos en servicio por empresa, que es la unidad de cobro.

    Es la única consulta del plano de control sobre una tabla de negocio, y la base la deja pasar
    solo porque toca exactamente dos columnas: `operador_user` tiene permiso de SELECT sobre
    `activos.empresa_id` y `activos.estado`, y sobre ninguna otra (revisión 0005). Pedir aquí el
    nombre de un equipo daría un error de permisos de PostgreSQL, no una fila.

    Los equipos dados de baja no cuentan: no se monitorean y no se facturan. Una empresa sin equipos
    no aparece en el diccionario; quien llama la cuenta como cero.
    """
    filas = await session.execute(
        select(Activo.empresa_id, func.count())
        .where(Activo.estado == "activo")
        .group_by(Activo.empresa_id)
    )
    return {empresa_id: int(total) for empresa_id, total in filas.all()}


async def _empresa_por_id(session: AsyncSession, empresa_id: UUID) -> Empresa:
    fila = await session.execute(select(Empresa).where(Empresa.id == empresa_id))
    empresa: Empresa | None = fila.scalar_one_or_none()
    if empresa is None:
        raise EmpresaNoEncontrada(str(empresa_id))
    return empresa


async def cambiar_estado_empresa(
    session: AsyncSession, *, operador_id: UUID, empresa_id: UUID, activa: bool
) -> Empresa:
    """Suspende o reactiva una empresa.

    Suspender no borra nada: los datos del cliente siguen donde estaban y su gente deja de poder
    entrar. `app.services.auth.autenticar` lo comprueba antes de abrir sesión.
    """
    empresa = await _empresa_por_id(session, empresa_id)
    empresa.activa = activa
    empresa.suspendida_en = None if activa else datetime.now(UTC)
    await _anotar(
        session,
        operador_id=operador_id,
        accion=AccionOperador.REACTIVACION if activa else AccionOperador.SUSPENSION,
        empresa_id=empresa.id,
        detalle=f"Empresa «{empresa.nombre}»",
    )
    return empresa


async def renombrar_empresa(
    session: AsyncSession, *, operador_id: UUID, empresa_id: UUID, nombre: str
) -> Empresa:
    empresa = await _empresa_por_id(session, empresa_id)
    anterior = empresa.nombre
    empresa.nombre = nombre.strip()
    await _anotar(
        session,
        operador_id=operador_id,
        accion=AccionOperador.EDICION_EMPRESA,
        empresa_id=empresa.id,
        detalle=f"Nombre: «{anterior}» → «{empresa.nombre}»",
    )
    return empresa


async def restablecer_clave_administrador(
    session: AsyncSession, *, operador_id: UUID, empresa_id: UUID
) -> tuple[Usuario, str]:
    """Genera una contraseña temporal para el administrador de una empresa.

    Es el caso de soporte más frecuente: el administrador de la planta se queda fuera y no hay
    nadie por encima de él que pueda ayudarlo. Por eso existe, y por eso queda registrado: quien
    ejecuta esto obtiene acceso a la cuenta de un cliente hasta que ese cliente cambie la clave.
    """
    empresa = await _empresa_por_id(session, empresa_id)
    fila = await session.execute(
        select(Usuario)
        .where(
            Usuario.empresa_id == empresa.id,
            Usuario.rol == Rol.ADMINISTRADOR.value,
            # Un administrador dado de baja por su propia empresa no se reactiva por la puerta de
            # atrás restableciéndole la clave.
            Usuario.activo.is_(True),
        )
        .order_by(Usuario.creado_en)
    )
    admin: Usuario | None = fila.scalars().first()
    if admin is None:
        raise SinAdministrador(str(empresa_id))

    password = generar_clave_temporal()
    admin.password_hash = hash_password(password)
    # Cierra las sesiones abiertas con la clave anterior. Restablecer suele pedirse porque alguien
    # perdió el control de la cuenta: si esas sesiones siguieran renovándose siete días, el
    # restablecimiento no echaría a nadie. Ver la revisión 0004.
    admin.version_clave = admin.version_clave + 1
    await _anotar(
        session,
        operador_id=operador_id,
        accion=AccionOperador.RESTABLECER_CLAVE,
        empresa_id=empresa.id,
        detalle=f"Clave temporal para {admin.correo}",
    )
    return admin, password


async def leer_bitacora(
    session: AsyncSession, *, limite: int = 100
) -> list[tuple[BitacoraOperador, str | None]]:
    """Historial de acciones, de la más reciente a la más antigua."""
    consulta = (
        select(BitacoraOperador, Operador.nombre)
        .outerjoin(Operador, Operador.id == BitacoraOperador.operador_id)
        .order_by(BitacoraOperador.creado_en.desc())
        .limit(limite)
    )
    filas = await session.execute(consulta)
    return [(asiento, nombre) for asiento, nombre in filas.all()]
