"""Lógica de negocio de autenticación (RF-01, RF-02, CU-06).

Aquí vive todo lo que decide; las rutas solo traducen entre HTTP y estas funciones. Las consultas
usan el ORM de SQLAlchemy (`select(...)`), no cadenas SQL: además de evitar concatenación, es lo que
mantiene el código independiente del motor.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.almacen import AlmacenEfimero
from app.core.config import get_settings
from app.core.security import (
    Claims,
    ErrorDeToken,
    Rol,
    TipoToken,
    crear_token_de_acceso,
    crear_token_de_refresco,
    decodificar_token,
    hash_password,
    necesita_rehash,
    verify_password,
)
from app.db.deps import fijar_tenant, permitir_busqueda_por_correo
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services import componentes, limites

#: Hash de descarte con el que se compara cuando el correo no existe. Sin esto, un login con correo
#: inexistente respondería en microsegundos y uno con correo real tardaría lo que tarda Argon2:
#: la diferencia de tiempo revela qué correos están registrados (04-fase1-fundamentos.md, 6.2).
_HASH_SENUELO = hash_password("señuelo-para-igualar-el-tiempo-de-respuesta")


class ErrorDeAutenticacion(Exception):
    """Credenciales inválidas. Deliberadamente sin detalle: el motivo no sale hacia el cliente."""


class ClaveActualIncorrecta(Exception):
    """Al cambiar la clave, la actual no coincide.

    Distinta de `ErrorDeAutenticacion` porque aquí sí hay sesión: el usuario ya demostró quién es, y
    decirle que la clave actual está mal no revela nada que no sepa. La ruta la traduce a 400, no a
    401, para que el cliente no confunda el error con una sesión caducada.
    """


class CorreoYaRegistrado(Exception):
    """El correo ya pertenece a un usuario. Es el único caso en que sí se informa al cliente."""


class EmpresaSuspendida(Exception):
    """La empresa dejó de estar activa. Sus usuarios no pueden entrar hasta que se reactive."""


class UsuarioDadoDeBaja(Exception):
    """El administrador de la planta dio de baja a esta persona (RF-03)."""


@dataclass(frozen=True, slots=True)
class Sesion:
    """Resultado de un registro o login correcto."""

    usuario: Usuario
    token_acceso: str
    token_refresco: str
    expira_en_segundos: int


def _sesion_para(usuario: Usuario) -> Sesion:
    s = get_settings()
    rol = Rol(usuario.rol)
    # `or 0` porque un objeto recién creado y aún sin flush no tiene el valor por defecto de la
    # columna: SQLAlchemy lo rellena al insertar.
    version = usuario.version_clave or 0
    return Sesion(
        usuario=usuario,
        token_acceso=crear_token_de_acceso(usuario.id, usuario.empresa_id, rol, version),
        token_refresco=crear_token_de_refresco(usuario.id, usuario.empresa_id, rol, version),
        expira_en_segundos=s.jwt_access_expire_minutes * 60,
    )


async def registrar_empresa(
    session: AsyncSession, *, empresa: str, nombre: str, correo: str, password: str
) -> Sesion:
    """Crea una empresa y su primer usuario administrador (RF-01).

    Orden obligado por RLS: primero la empresa (lo permite `empresa_alta_administrativa`, que solo
    alcanza al rol dueño de las tablas), después se
    fija `app.empresa_id` con el id recién generado y solo entonces se puede insertar el usuario,
    que ya pasa `tenant_isolation_usuarios`. Invertir el orden falla.

    El rol es siempre `administrador`: quien crea la empresa la administra. Nunca se acepta del
    cliente.

    El correo duplicado se detecta por la restricción UNIQUE de la base, no con un SELECT previo.
    Un `select(Usuario).where(correo == ...)` aquí **siempre** devolvería vacío: la sesión no tiene
    tenant fijado, así que RLS le oculta los usuarios de todas las empresas. Apoyarse en la
    restricción es además lo correcto frente a dos registros simultáneos con el mismo correo.
    """
    correo = correo.strip().lower()
    nueva = Empresa(nombre=empresa.strip())
    session.add(nueva)
    # flush, no commit: empuja el INSERT para obtener el id sin cerrar la transaccion, de modo que
    # empresa y usuario se crean juntos o no se crea ninguno.
    await session.flush()

    await fijar_tenant(session, nueva.id)

    admin = Usuario(
        empresa_id=nueva.id,
        nombre=nombre.strip(),
        correo=correo,
        password_hash=hash_password(password),
        rol=Rol.ADMINISTRADOR.value,
    )
    session.add(admin)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _es_correo_duplicado(exc):
            raise CorreoYaRegistrado(correo) from exc
        raise
    # Catálogo inicial de componentes, en la misma transacción que la empresa.
    session.add_all(componentes.plantilla_para(nueva.id))
    await session.flush()
    return _sesion_para(admin)


def _es_correo_duplicado(exc: IntegrityError) -> bool:
    """Distingue el choque con `uq_usuarios_correo` de cualquier otra violación de integridad.

    Sin esta comprobación, un fallo distinto (una clave foránea rota, por ejemplo) se le presentaría
    al usuario como «ese correo ya está registrado» y mandaría a todo el mundo a buscar en el sitio
    equivocado.
    """
    return "uq_usuarios_correo" in str(exc.orig)


def _ip_valida(ip: str | None) -> str | None:
    """Devuelve la IP solo si lo es de verdad; None en cualquier otro caso.

    La columna `intentos_login.ip` es de tipo INET y rechaza lo que no sea una dirección.
    `request.client.host` no siempre lo es: detrás de ciertos proxies, o con el cliente de pruebas
    de Starlette, llega un nombre. Sin este filtro, un login fallido reventaría con un 500 en lugar
    de registrarse — el registro de auditoría tumbaría justo el caso que existe para auditar.
    """
    if not ip:
        return None
    try:
        ip_address(ip)
    except ValueError:
        return None
    return ip


def _clave_limite(correo: str, ip: str | None) -> tuple[str, str]:
    """Claves del límite de `/auth/login` (sección 6.2), por correo y por IP.

    Se cuentan por separado: solo por IP dejaría pasar un ataque distribuido contra una cuenta
    concreta, y solo por correo dejaría pasar un barrido de muchas cuentas desde una misma IP.
    """
    return f"login:correo:{correo}", f"login:ip:{ip or 'desconocida'}"


async def registrar_intento(
    session: AsyncSession, *, correo: str, ip: str | None, exitoso: bool
) -> None:
    """Deja constancia del intento en `intentos_login` (sección 2 del documento de F1).

    Se usa SQL crudo y no el ORM porque `intentos_login` no tiene modelo: es una tabla de auditoría
    a la que la aplicación solo escribe, nunca consulta, y darle una entidad invitaría a mapearla y
    consultarla desde los servicios. Los valores van como parámetros enlazados, nunca concatenados.
    """
    await session.execute(
        text(
            "INSERT INTO intentos_login (correo, ip, exitoso)"
            " VALUES (:correo, CAST(:ip AS INET), :exitoso)"
        ),
        {"correo": correo.lower(), "ip": _ip_valida(ip), "exitoso": exitoso},
    )


async def autenticar(
    session: AsyncSession,
    almacen: AlmacenEfimero,
    *,
    correo: str,
    password: str,
    ip: str | None = None,
) -> Sesion:
    """Valida credenciales y devuelve una sesión (RF-02).

    Lanza siempre `ErrorDeAutenticacion` sin distinguir entre «el correo no existe» y «la contraseña
    no coincide»: decir cuál de los dos falló le confirma a un atacante qué correos están
    registrados.
    """
    correo = correo.strip().lower()
    await limites.comprobar(almacen, _clave_limite(correo, ip))

    # Habilita la politica login_lookup para ESTE correo. Sin esto RLS ocultaria la fila y todo
    # login fallaria: para saber la empresa hay que leer al usuario, y para leerlo hay que saber la
    # empresa. Ver app.db.tenant.EstrategiaTenant.permitir_busqueda_por_correo.
    await permitir_busqueda_por_correo(session, correo)
    usuario = await session.scalar(select(Usuario).where(Usuario.correo == correo))

    # Se verifica SIEMPRE un hash, exista el usuario o no, para que ambos caminos tarden lo mismo.
    hash_a_verificar = usuario.password_hash if usuario else _HASH_SENUELO
    coincide = verify_password(password, hash_a_verificar)

    if usuario is None or not coincide:
        await registrar_intento(session, correo=correo, ip=ip, exitoso=False)
        raise ErrorDeAutenticacion

    if necesita_rehash(usuario.password_hash):
        # Los parametros de Argon2 subieron desde que se creo este hash: se rehace ahora que
        # tenemos la contrasena en claro, sin pedirle nada al usuario.
        usuario.password_hash = hash_password(password)

    # Dado de baja por su administrador. Como la empresa suspendida, se comprueba DESPUES de la
    # contrasena: decirlo antes confirmaria a cualquiera que ese correo existe.
    if not usuario.activo:
        await registrar_intento(session, correo=correo, ip=ip, exitoso=False)
        raise UsuarioDadoDeBaja(str(usuario.id))

    # La empresa puede estar suspendida (dejo de pagar). Se comprueba DESPUES de validar la
    # contrasena, no antes: hacerlo antes le diria a cualquiera que probara un correo si esa
    # empresa existe y en que estado esta, sin necesidad de acertar la clave.
    #
    # Hay que fijar el tenant para poder leer la fila: hasta aqui la sesion no tenia ninguno, y
    # `tenant_isolation_empresas` oculta todas las empresas mientras no se fije. Es el mismo
    # tenant que se va a usar en el resto de la sesion, asi que no se adelanta nada indebido.
    await fijar_tenant(session, usuario.empresa_id)
    empresa = await session.scalar(select(Empresa).where(Empresa.id == usuario.empresa_id))
    if empresa is not None and not empresa.activa:
        await registrar_intento(session, correo=correo, ip=ip, exitoso=False)
        raise EmpresaSuspendida(str(usuario.empresa_id))

    await registrar_intento(session, correo=correo, ip=ip, exitoso=True)
    # Acerto: se olvidan los contadores para no penalizar a quien solo se equivoco un par de veces.
    await limites.olvidar(almacen, _clave_limite(correo, ip))
    return _sesion_para(usuario)


def _clave_revocacion(usuario_id: UUID, jti: str) -> str:
    """Clave de revocacion. Se indexa por `jti` (identificador unico del token), no por la cadena
    del token: el jti es corto, estable y distingue de verdad un token de otro."""
    return f"revocado:{usuario_id}:{jti}"


async def revocar_refresco(almacen: AlmacenEfimero, claims: Claims) -> None:
    """Marca un refresh token como revocado hasta que caduque (logout, sección 4.4).

    Un JWT es válido por sí mismo hasta su expiración, así que «cerrar sesión» solo es real si se
    recuerda cuáles se han revocado. La marca caduca a la vez que el token: pasado ese punto ya no
    sirve de nada guardarla.
    """
    s = get_settings()
    await almacen.marcar(
        _clave_revocacion(claims.usuario_id, claims.jti), s.jwt_refresh_expire_days * 86400
    )


async def esta_revocado(almacen: AlmacenEfimero, claims: Claims) -> bool:
    return await almacen.esta_marcada(_clave_revocacion(claims.usuario_id, claims.jti))


async def refrescar(
    session: AsyncSession,
    almacen: AlmacenEfimero,
    *,
    claims: Claims,
) -> Sesion:
    """Emite tokens nuevos a partir de un refresh token vigente (sección 4.4).

    Rota el refresh token: el anterior queda revocado. Así, si alguien roba uno y lo usa, el usuario
    legítimo pierde la sesión y el robo se nota, en vez de convivir en silencio durante siete días.
    """
    if await esta_revocado(almacen, claims):
        raise ErrorDeAutenticacion

    # Aqui SI se conoce la empresa: viene firmada dentro del refresh token. Se fija antes de
    # consultar para que la lectura pase por RLS como cualquier otra.
    await fijar_tenant(session, claims.empresa_id)
    usuario = await session.scalar(select(Usuario).where(Usuario.id == claims.usuario_id))
    if usuario is None:
        raise ErrorDeAutenticacion

    # La clave cambió (o la restableció el operador) después de emitirse este token: pertenece a
    # una sesión que el cambio tenía que cerrar. La lectura del usuario ya se hacía, así que la
    # comprobación no cuesta ninguna consulta más.
    if claims.version_clave != usuario.version_clave:
        raise ErrorDeAutenticacion
    # Dado de baja mientras tenía la sesión abierta: no se le renueva.
    if not usuario.activo:
        raise ErrorDeAutenticacion

    await revocar_refresco(almacen, claims)
    return _sesion_para(usuario)


def _clave_limite_cambio(usuario_id: UUID) -> list[str]:
    """Contador propio del cambio de clave, separado del de login.

    Por usuario y no por IP: aquí ya se sabe quién es, y lo que se protege es su cuenta frente a
    quien tenga su sesión en la mano.
    """
    return [f"cambio-clave:usuario:{usuario_id}"]


async def cambiar_password(
    session: AsyncSession,
    almacen: AlmacenEfimero,
    *,
    claims: Claims,
    password_actual: str,
    password_nueva: str,
) -> Sesion:
    """Cambia la contraseña del usuario de la sesión y cierra sus demás sesiones.

    Exige la clave actual aunque haya sesión, con el mismo límite de intentos que el login: una
    sesión robada no debe servir para adivinarla.

    Devuelve una sesión nueva para ESTE aparato, emitida con la versión de clave nueva. Las demás
    —cualquier refresh token emitido antes— dejan de renovarse en cuanto lo intentan; ver
    `refrescar`. El token de acceso de esos otros aparatos no se puede retirar sin consultar la base
    en cada petición, así que les queda como mucho lo que falte de sus 30 minutos.
    """
    claves = _clave_limite_cambio(claims.usuario_id)
    await limites.comprobar(almacen, claves)

    # La sesión viene con el tenant fijado por `get_db`, así que esta lectura pasa por RLS y no
    # puede devolver un usuario de otra empresa aunque el id estuviera manipulado.
    usuario = await usuario_actual(session, claims.usuario_id)
    if usuario is None:
        raise ErrorDeAutenticacion
    if not verify_password(password_actual, usuario.password_hash):
        raise ClaveActualIncorrecta

    usuario.password_hash = hash_password(password_nueva)
    usuario.version_clave = usuario.version_clave + 1
    await session.flush()
    await limites.olvidar(almacen, claves)
    return _sesion_para(usuario)


def decodificar_refresco(token: str) -> Claims:
    """Verifica un refresh token y devuelve sus reclamaciones.

    Traduce `ErrorDeToken` a `ErrorDeAutenticacion` para que las rutas manejen un solo tipo de error
    de credenciales, sin tener que conocer el módulo de tokens.
    """
    try:
        return decodificar_token(token, TipoToken.REFRESCO)
    except ErrorDeToken as exc:
        raise ErrorDeAutenticacion from exc


async def usuario_actual(session: AsyncSession, usuario_id: UUID) -> Usuario | None:
    """Recupera el usuario de la sesión en curso.

    La sesión ya viene restringida por RLS a la empresa del token, así que esta consulta no puede
    devolver un usuario de otra empresa aunque el id estuviera manipulado.
    """
    resultado: Usuario | None = await session.scalar(
        select(Usuario).where(Usuario.id == usuario_id)
    )
    return resultado
