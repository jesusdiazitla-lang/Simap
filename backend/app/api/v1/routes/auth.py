"""Endpoints de autenticación: login, refresco, cierre de sesión y cambio de clave (RF-02, CU-06).

No hay endpoint de registro. El alta de una empresa es una operación administrativa que se ejecuta
con `python -m app.cli crear-empresa`, porque SIMAP se cobra por equipo y una empresa no puede
darse de alta a sí misma (RF-01). Dejar la ruta publicada y no enlazarla desde la interfaz no habría
servido: el esquema OpenAPI la habría anunciado en `/docs`.

Estas rutas no deciden nada: traducen entre HTTP y `app.services.auth`. Lo único que resuelven aquí
es cómo viajan los tokens, que es una cuestión de transporte: en cookies `httpOnly`, `Secure` y
`SameSite`, nunca en el cuerpo de la respuesta ni en `localStorage`, donde un XSS podría leerlos
(04-fase1-fundamentos.md, sección 6.1).
"""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.almacen import AlmacenEfimero, get_almacen
from app.core.auth import (
    COOKIE_ACCESO,
    COOKIE_PISTA_SESION,
    COOKIE_REFRESCO,
    ClaimsActuales,
    ClaimsDeRefresco,
)
from app.core.config import get_settings
from app.db.deps import SesionDB, SesionSinTenant
from app.schemas.auth import CambioClaveRequest, LoginRequest, SesionResponse, UsuarioOut
from app.services import auth as servicio
from app.services.limites import DemasiadosIntentos

router = APIRouter(prefix="/auth", tags=["auth"])

Almacen = Annotated[AlmacenEfimero, Depends(get_almacen)]

#: Mensaje único para credenciales inválidas. No distingue entre correo inexistente y contraseña
#: incorrecta: lo segundo revelaría qué correos están registrados (sección 6.2). Menciona los dos
#: campos justamente para no señalar ninguno, y está redactado para que se pueda enseñar tal cual:
#: la interfaz muestra lo que responde la API en vez de traducirlo por su cuenta, porque dos textos
#: distintos para el mismo fallo acaban divergiendo, y gana el de la pantalla sin que nadie lo vea.
CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos."


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _poner_cookies(response: Response, sesion: servicio.Sesion) -> None:
    s = get_settings()
    # `secure` se apaga solo en desarrollo: sin HTTPS el navegador descartaria la cookie y no habria
    # forma de probar el login en local. En cualquier otro entorno viaja siempre sobre TLS.
    # `samesite` se estrecha a su Literal porque Settings lo expone como str libre (viene del
    # entorno) y set_cookie solo acepta uno de estos tres valores.
    samesite = cast(Literal["lax", "strict", "none"], s.cookie_samesite.lower())
    response.set_cookie(
        COOKIE_ACCESO,
        sesion.token_acceso,
        max_age=s.jwt_access_expire_minutes * 60,
        path="/",
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )
    response.set_cookie(
        COOKIE_REFRESCO,
        sesion.token_refresco,
        max_age=s.jwt_refresh_expire_days * 86400,
        # El refresh token solo se envia al endpoint que lo necesita, no en cada peticion.
        path=f"{s.api_v1_prefix}/auth",
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )
    # Pista para el proxy del frontend: dura lo que el refresh token. Ver COOKIE_PISTA_SESION.
    response.set_cookie(
        COOKIE_PISTA_SESION,
        "1",
        max_age=s.jwt_refresh_expire_days * 86400,
        path="/",
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )


def _borrar_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(COOKIE_ACCESO, path="/")
    response.delete_cookie(COOKIE_REFRESCO, path=f"{s.api_v1_prefix}/auth")
    response.delete_cookie(COOKIE_PISTA_SESION, path="/")


def _demasiados_intentos(exc: DemasiadosIntentos) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiados intentos. Espera un momento antes de volver a probar.",
        headers={"Retry-After": str(exc.espera_segundos)},
    )


def _respuesta(sesion: servicio.Sesion) -> SesionResponse:
    return SesionResponse(
        usuario=UsuarioOut.model_validate(sesion.usuario),
        expira_en_segundos=sesion.expira_en_segundos,
    )


@router.post("/login", response_model=SesionResponse)
async def login(
    datos: LoginRequest,
    session: SesionSinTenant,
    almacen: Almacen,
    request: Request,
    response: Response,
) -> SesionResponse:
    """Valida credenciales y abre sesión (RF-02, CU-06)."""
    try:
        sesion = await servicio.autenticar(
            session,
            almacen,
            correo=datos.correo,
            password=datos.password,
            ip=_ip(request),
        )
    except DemasiadosIntentos as exc:
        raise _demasiados_intentos(exc) from exc
    except servicio.EmpresaSuspendida as exc:
        # 403 y no 401: las credenciales eran correctas. Decirlo no filtra nada —quien llega aquí
        # ya demostró conocer la contraseña— y evita que alguien pierda una tarde pensando que
        # escribió mal la clave cuando lo que pasa es que su empresa está suspendida.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de tu empresa está suspendida. Contacta con quien administra SIMAP.",
        ) from exc
    except servicio.ErrorDeAutenticacion as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=CREDENCIALES_INVALIDAS
        ) from exc
    _poner_cookies(response, sesion)
    return _respuesta(sesion)


@router.post("/refresh", response_model=SesionResponse)
async def refrescar(
    claims: ClaimsDeRefresco,
    session: SesionSinTenant,
    almacen: Almacen,
    response: Response,
) -> SesionResponse:
    """Emite tokens nuevos a partir del refresh token de la cookie (sección 4.4).

    Rota el token: el anterior queda revocado en el mismo paso.
    """
    try:
        sesion = await servicio.refrescar(session, almacen, claims=claims)
    except servicio.ErrorDeAutenticacion as exc:
        _borrar_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=CREDENCIALES_INVALIDAS
        ) from exc
    _poner_cookies(response, sesion)
    return _respuesta(sesion)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(almacen: Almacen, request: Request, response: Response) -> Response:
    """Cierra la sesión: borra las cookies y revoca el refresh token (sección 4.4).

    No exige estar autenticado. Cerrar sesión con un token ya caducado debe limpiar las cookies
    igualmente, en vez de dejar al usuario atrapado con un 401 en la pantalla de salida.
    """
    token = request.cookies.get(COOKIE_REFRESCO)
    if token:
        try:
            claims = servicio.decodificar_refresco(token)
        except servicio.ErrorDeAutenticacion:
            claims = None
        if claims is not None:
            await servicio.revocar_refresco(almacen, claims)
    _borrar_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/cambiar-clave", response_model=SesionResponse)
async def cambiar_clave(
    datos: CambioClaveRequest,
    claims: ClaimsActuales,
    session: SesionDB,
    almacen: Almacen,
    response: Response,
) -> SesionResponse:
    """Cambia la contraseña de quien tiene la sesión y cierra sus demás sesiones.

    Responde con cookies nuevas: este aparato sigue dentro con tokens emitidos ya con la clave
    nueva, y los demás dejan de poder renovar. Cuelga de `/auth` a propósito, para que el navegador
    adjunte también el refresh token y las cookies de la respuesta reemplacen a las de la petición.
    """
    try:
        sesion = await servicio.cambiar_password(
            session,
            almacen,
            claims=claims,
            password_actual=datos.password_actual,
            password_nueva=datos.password_nueva,
        )
    except DemasiadosIntentos as exc:
        raise _demasiados_intentos(exc) from exc
    except servicio.ClaveActualIncorrecta as exc:
        # 400 y no 401: la sesión es válida. Un 401 haría que el cliente intentara renovarla y
        # tapara el error real con un reintento.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        ) from exc
    except servicio.ErrorDeAutenticacion as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado"
        ) from exc
    _poner_cookies(response, sesion)
    return _respuesta(sesion)


@router.get("/yo", response_model=UsuarioOut)
async def yo(claims: ClaimsActuales, session: SesionDB) -> UsuarioOut:
    """Devuelve el usuario de la sesión actual.

    La interfaz lo usa al cargar para saber a qué panel llevar al usuario. Va con `get_db` (y no con
    la sesión sin tenant) a propósito: así la consulta pasa por RLS y sirve además de comprobación
    de que el aislamiento está activo en cada petición autenticada.
    """
    usuario = await servicio.usuario_actual(session, claims.usuario_id)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return UsuarioOut.model_validate(usuario)
