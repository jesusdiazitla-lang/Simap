"""Primitivas de seguridad: hash de contraseñas (Argon2id) y tokens JWT.

Esta capa es la más baja del contrato de arquitectura, así que no importa de ninguna otra: solo
convierte credenciales en hashes y reclamaciones en tokens. Quién puede hacer qué se decide en
`app.core.rbac`; de dónde salen los datos, en `app.db`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from jose import JWTError, jwt

from app.core.config import get_settings


class Rol(StrEnum):
    """Roles del sistema. El valor es exactamente el que guarda la columna `usuarios.rol`."""

    OPERARIO = "operario"
    SUPERVISOR = "supervisor"
    TECNICO_TALLER = "tecnico_taller"
    GERENTE = "gerente"
    ADMINISTRADOR = "administrador"


class TipoToken(StrEnum):
    ACCESO = "access"
    REFRESCO = "refresh"


#: Nombre de la reclamación que distingue un token de acceso de uno de refresco.
#: Sin ella, un refresh token (7 días) valdría como token de acceso.
CLAIM_TIPO: Final = "typ"

#: Versión de la contraseña con la que se emitió el token (`usuarios.version_clave`).
#:
#: Es lo que permite que cambiar la clave eche a los demás aparatos. Un JWT es válido por sí mismo
#: hasta que caduca, así que sin esto un refresh token emitido con la clave vieja seguiría
#: renovando la sesión siete días. Al refrescar se compara con la versión actual del usuario, que
#: sube en cada cambio o restablecimiento.
#:
#: Es un contador y no una fecha a propósito: `iat` tiene resolución de un segundo, y un token
#: emitido en el mismo segundo que el cambio quedaría a un lado u otro de la frontera por azar.
CLAIM_VERSION_CLAVE: Final = "ver"


class ErrorDeToken(Exception):
    """El token no es válido: firma incorrecta, expirado, malformado o de tipo equivocado."""


@dataclass(frozen=True, slots=True)
class Claims:
    """Contenido verificado de un token. `empresa_id` es lo que fija el tenant en cada request."""

    usuario_id: UUID
    empresa_id: UUID
    rol: Rol
    tipo: TipoToken
    #: Identificador unico de ESTE token (JWT ID). Ver `_crear_token` para saber por que hace falta.
    jti: str
    #: Ver `CLAIM_VERSION_CLAVE`. Cero para los tokens emitidos antes de que existiera: coincide
    #: con el valor por defecto de la columna, así que esas sesiones no se cortan al desplegar.
    version_clave: int = 0


def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de una contraseña en claro."""
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Comprueba una contraseña contra su hash.

    Devuelve False ante cualquier fallo de Argon2 (hash corrupto, algoritmo distinto, no coincide)
    en lugar de propagar la excepción: quien llama solo necesita saber si la credencial sirve, y
    distinguir los motivos hacia fuera filtraría información al atacante.

    `InvalidHashError` se captura aparte porque hereda de `ValueError`, no de `Argon2Error`: sin
    ella, una fila con el hash dañado devolvería un 500 en vez de un login rechazado.
    """
    try:
        return _hasher().verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def necesita_rehash(password_hash: str) -> bool:
    """True si el hash se generó con parámetros más débiles que los actuales.

    Permite reforzar el coste de Argon2 sin invalidar contraseñas: al siguiente login correcto se
    regraba el hash con los parámetros nuevos. Un hash ilegible se trata como "hay que rehacerlo".
    """
    try:
        return _hasher().check_needs_rehash(password_hash)
    except (Argon2Error, InvalidHashError):
        return True


#: Bytes de entropía de una contraseña temporal. 12 bytes en base64 seguro para URL dan 16
#: caracteres imposibles de adivinar y cómodos de dictar por teléfono, que es como llegará a su
#: destinatario la mitad de las veces.
_BYTES_CLAVE_TEMPORAL = 12


def generar_clave_temporal() -> str:
    """Contraseña de un solo uso, generada por el servidor.

    La usan los dos planos: el operador al dar de alta una empresa o restablecer a su
    administrador, y el administrador de una planta al dar de alta o restablecer a su personal.
    Quien la entrega no la elige, así que no conserva acceso a la cuenta una vez cambiada.

    `secrets` y no `random`: el segundo es predecible a partir de valores anteriores.
    """
    return secrets.token_urlsafe(_BYTES_CLAVE_TEMPORAL)


def _crear_token(claims: Claims, expira_en: timedelta) -> str:
    ahora = datetime.now(UTC)
    # jti unico por token. Sin el, dos tokens emitidos para el mismo usuario dentro del mismo
    # segundo tendrian un payload identico y por tanto serian la MISMA cadena: la rotacion del
    # refresh token no rotaria nada y, al revocar el anterior, quedaria revocado tambien el nuevo.
    payload: dict[str, Any] = {
        "sub": str(claims.usuario_id),
        "empresa_id": str(claims.empresa_id),
        "rol": claims.rol.value,
        CLAIM_TIPO: claims.tipo.value,
        "jti": claims.jti,
        CLAIM_VERSION_CLAVE: claims.version_clave,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + expira_en).timestamp()),
    }
    s = get_settings()
    # python-jose no trae stubs, asi que mypy ve Any: se acota aqui en lugar de propagarlo.
    return str(jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm))


def crear_token_de_acceso(
    usuario_id: UUID, empresa_id: UUID, rol: Rol, version_clave: int = 0
) -> str:
    s = get_settings()
    claims = Claims(usuario_id, empresa_id, rol, TipoToken.ACCESO, uuid4().hex, version_clave)
    return _crear_token(claims, timedelta(minutes=s.jwt_access_expire_minutes))


def crear_token_de_refresco(
    usuario_id: UUID, empresa_id: UUID, rol: Rol, version_clave: int = 0
) -> str:
    s = get_settings()
    claims = Claims(usuario_id, empresa_id, rol, TipoToken.REFRESCO, uuid4().hex, version_clave)
    return _crear_token(claims, timedelta(days=s.jwt_refresh_expire_days))


def decodificar_token(token: str, tipo_esperado: TipoToken = TipoToken.ACCESO) -> Claims:
    """Verifica firma y expiración y devuelve las reclamaciones.

    Lanza `ErrorDeToken` ante cualquier problema, incluido que el tipo no sea el esperado: así un
    refresh token no puede colarse donde se pide uno de acceso.
    """
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ErrorDeToken("token inválido o expirado") from exc

    # Un token del plano de control no vale aquí. Hoy tampoco pasaría, porque no lleva
    # `empresa_id` y el constructor de abajo fallaría; pero rechazarlo por lo que el token DICE
    # ser, y no por lo que le falta, es lo que sigue funcionando el día que alguien añada un
    # `empresa_id` opcional sin acordarse de esta frontera.
    if payload.get(CLAIM_SUJETO, Sujeto.USUARIO.value) != Sujeto.USUARIO.value:
        raise ErrorDeToken("este token pertenece al plano de control, no al de datos")

    try:
        tipo = TipoToken(payload[CLAIM_TIPO])
        claims = Claims(
            usuario_id=UUID(payload["sub"]),
            empresa_id=UUID(payload["empresa_id"]),
            rol=Rol(payload["rol"]),
            tipo=tipo,
            jti=str(payload["jti"]),
            version_clave=int(payload.get(CLAIM_VERSION_CLAVE, 0)),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ErrorDeToken("reclamaciones ausentes o malformadas") from exc

    if claims.tipo is not tipo_esperado:
        raise ErrorDeToken(f"se esperaba un token de tipo {tipo_esperado.value}")
    return claims


# =============================================================================
# Plano de control: tokens del operador de SIMAP.
#
# Un operador no pertenece a ninguna empresa, así que sus reclamaciones NO llevan `empresa_id`.
# Eso, por sí solo, ya impide que su token sirva para entrar en el plano de datos:
# `decodificar_token` exige `empresa_id` y falla sin él.
#
# Aun así se marca explícitamente con `CLAIM_SUJETO`, y la comprobación se hace en las dos
# direcciones. Depender de que falte un campo es depender de un accidente afortunado; depender de
# un campo que afirma qué es el token es una decisión, y es la que sobrevive a que alguien añada
# mañana un `empresa_id` opcional sin pensar en esto.
# =============================================================================

#: Reclamación que dice a qué plano pertenece el token.
CLAIM_SUJETO: Final = "suj"


class Sujeto(StrEnum):
    USUARIO = "usuario"
    OPERADOR = "operador"


@dataclass(frozen=True, slots=True)
class ClaimsOperador:
    """Contenido verificado del token de un operador de SIMAP."""

    operador_id: UUID
    tipo: TipoToken
    jti: str


def _crear_token_operador(claims: ClaimsOperador, duracion: timedelta) -> str:
    s = get_settings()
    ahora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(claims.operador_id),
        CLAIM_SUJETO: Sujeto.OPERADOR.value,
        CLAIM_TIPO: claims.tipo.value,
        "jti": claims.jti,
        "iat": ahora,
        "exp": ahora + duracion,
    }
    return str(jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm))


def crear_token_de_acceso_operador(operador_id: UUID) -> str:
    s = get_settings()
    claims = ClaimsOperador(operador_id, TipoToken.ACCESO, uuid4().hex)
    return _crear_token_operador(claims, timedelta(minutes=s.jwt_access_expire_minutes))


def crear_token_de_refresco_operador(operador_id: UUID) -> str:
    s = get_settings()
    claims = ClaimsOperador(operador_id, TipoToken.REFRESCO, uuid4().hex)
    return _crear_token_operador(claims, timedelta(days=s.jwt_refresh_expire_days))


def decodificar_token_operador(
    token: str, tipo_esperado: TipoToken = TipoToken.ACCESO
) -> ClaimsOperador:
    """Verifica un token del plano de control.

    Rechaza cualquier token que no se declare del operador, de modo que una sesión de usuario de
    empresa no sirva jamás para entrar en la consola.
    """
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ErrorDeToken("token inválido o expirado") from exc

    if payload.get(CLAIM_SUJETO) != Sujeto.OPERADOR.value:
        raise ErrorDeToken("este token no pertenece al plano de control")

    try:
        claims = ClaimsOperador(
            operador_id=UUID(payload["sub"]),
            tipo=TipoToken(payload[CLAIM_TIPO]),
            jti=str(payload["jti"]),
        )
    except (KeyError, ValueError) as exc:
        raise ErrorDeToken("reclamaciones ausentes o malformadas") from exc

    if claims.tipo is not tipo_esperado:
        raise ErrorDeToken(f"se esperaba un token de tipo {tipo_esperado.value}")
    return claims
