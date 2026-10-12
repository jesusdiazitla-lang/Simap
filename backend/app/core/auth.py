"""Dependencias de FastAPI que extraen y verifican el token del request.

Vive en `core` y no en `db` porque no toca la base de datos: solo lee una cookie o una cabecera y
valida una firma. Tenerlo aquí es lo que permite que `app.core.rbac` lo use sin romper el contrato
de capas (`core` es la capa más baja y no puede importar de `db`).

`app.db.deps.get_db` construye encima: toma estas reclamaciones y fija el tenant en la transacción.
"""

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status

from app.core import registro
from app.core.security import (
    Claims,
    ClaimsOperador,
    ErrorDeToken,
    TipoToken,
    decodificar_token,
    decodificar_token_operador,
)

#: Cookies httpOnly donde viajan los tokens. El JavaScript de la página no puede leerlas, así que un
#: XSS no puede robar la sesión (04-fase1-fundamentos.md, sección 6.1).
COOKIE_ACCESO = "simap_access"
COOKIE_REFRESCO = "simap_refresh"

#: Cookies del plano de control. Nombres distintos a propósito: así una sesión de operador y una de
#: usuario de empresa pueden convivir en el mismo navegador sin pisarse, y sobre todo, una no puede
#: presentarse como la otra por accidente. La del operador se restringe además a `/api/v1/operador`,
#: de modo que ni siquiera viaja en las peticiones del plano de datos.
COOKIE_OPERADOR_ACCESO = "simap_op_access"
COOKIE_OPERADOR_REFRESCO = "simap_op_refresh"

#: Pistas de sesión para el `proxy.ts` del frontend. NO SON CREDENCIALES: valen siempre "1", ninguna
#: ruta de la API las lee, y con ellas solas no se entra en ningún sitio.
#:
#: Existen porque el proxy necesita saber, antes de pintar nada, si mandar a alguien a `/login`, y
#: ninguna de las cookies de verdad le sirve para eso:
#:
#: - la de acceso caduca a los 30 minutos, pero la sesión sigue viva siete días gracias al refresh
#:   token. Si el proxy mirara la de acceso, echaría a quien todavía puede renovar en silencio;
#: - la de refresco está restringida a `/api/v1/auth` y el navegador no la manda a las páginas.
#:
#: Así que la pista dura lo que el refresh token, se pone y se quita junto con él, y viaja a las
#: páginas. Si alguien la falsifica, el proxy le deja pasar a una página que, al pedir sus datos a
#: la API, recibe un 401 y le devuelve al acceso. Lo único que se gana falsificándola es nada.
#:
#: Los nombres se repiten en `frontend/src/proxy.ts`; si cambian aquí, hay que cambiarlos allí.
COOKIE_PISTA_SESION = "simap_sesion"
COOKIE_PISTA_OPERADOR = "simap_op_sesion"

NO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


def token_desde_cabecera(authorization: str | None) -> str | None:
    """Extrae el token de `Authorization: Bearer <token>`, o None si no encaja."""
    if not authorization:
        return None
    esquema, _, valor = authorization.partition(" ")
    if esquema.lower() != "bearer" or not valor:
        return None
    return valor


async def get_claims(
    simap_access: Annotated[str | None, Cookie(alias=COOKIE_ACCESO)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Claims:
    """Extrae y verifica el token de acceso del request.

    La cookie httpOnly es la vía principal, porque es la que usa el frontend y la que no puede leer
    un XSS. Se acepta además `Authorization: Bearer` para clientes que no son navegador (tests,
    scripts, integraciones); si vienen las dos, manda la cookie.
    """
    token = simap_access or token_desde_cabecera(authorization)
    if not token:
        raise NO_AUTENTICADO
    try:
        claims = decodificar_token(token, TipoToken.ACCESO)
    except ErrorDeToken as exc:
        raise NO_AUTENTICADO from exc
    # Desde aquí cada línea del registro de esta petición dice de qué empresa y de quién es.
    registro.anotar_usuario(claims.empresa_id, claims.usuario_id)
    return claims


async def get_claims_refresco(
    simap_refresh: Annotated[str | None, Cookie(alias=COOKIE_REFRESCO)] = None,
) -> Claims:
    """Igual que `get_claims`, pero para el token de refresco y solo desde su cookie.

    No se acepta por cabecera: el refresh token dura siete días y solo debe existir en la cookie
    httpOnly, nunca en un encabezado que pueda acabar en un log o en el historial de un proxy.
    """
    if not simap_refresh:
        raise NO_AUTENTICADO
    try:
        return decodificar_token(simap_refresh, TipoToken.REFRESCO)
    except ErrorDeToken as exc:
        raise NO_AUTENTICADO from exc


# =============================================================================
# Plano de control.
# =============================================================================


async def get_claims_operador(
    simap_op_access: Annotated[str | None, Cookie(alias=COOKIE_OPERADOR_ACCESO)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ClaimsOperador:
    """Extrae y verifica el token de acceso de un operador de SIMAP.

    `decodificar_token_operador` rechaza cualquier token que no se declare del plano de control, de
    modo que la sesión de un usuario de empresa no abre la consola aunque llegue por esta vía.
    """
    token = simap_op_access or token_desde_cabecera(authorization)
    if not token:
        raise NO_AUTENTICADO
    try:
        claims = decodificar_token_operador(token, TipoToken.ACCESO)
    except ErrorDeToken as exc:
        raise NO_AUTENTICADO from exc
    registro.anotar_operador(claims.operador_id)
    return claims


async def get_claims_operador_refresco(
    simap_op_refresh: Annotated[str | None, Cookie(alias=COOKIE_OPERADOR_REFRESCO)] = None,
) -> ClaimsOperador:
    """Igual que la anterior, pero para el refresco y solo desde su cookie."""
    if not simap_op_refresh:
        raise NO_AUTENTICADO
    try:
        return decodificar_token_operador(simap_op_refresh, TipoToken.REFRESCO)
    except ErrorDeToken as exc:
        raise NO_AUTENTICADO from exc


ClaimsActuales = Annotated[Claims, Depends(get_claims)]
ClaimsDeRefresco = Annotated[Claims, Depends(get_claims_refresco)]
ClaimsOperadorActuales = Annotated[ClaimsOperador, Depends(get_claims_operador)]
ClaimsOperadorDeRefresco = Annotated[ClaimsOperador, Depends(get_claims_operador_refresco)]
