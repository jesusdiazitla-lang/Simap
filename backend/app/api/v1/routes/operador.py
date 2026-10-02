"""Endpoints del plano de control: la consola de quien opera SIMAP.

Todas cuelgan de `/operador` y **todas** usan `SesionOperador`, que abre la conexión con el rol de
base de datos `operador_user`. Ese rol tiene permisos concedidos tabla por tabla y ninguno sobre las
tablas de negocio, así que desde aquí no se puede leer un activo, una orden ni una lectura aunque
alguien escribiera la consulta. La frontera la impone PostgreSQL, no estas funciones.

La cookie de sesión también es distinta (`simap_op_*`) y está restringida a este prefijo, de modo
que la sesión del operador ni siquiera viaja en las peticiones del plano de datos.
"""

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.almacen import AlmacenEfimero, get_almacen
from app.core.auth import (
    COOKIE_OPERADOR_ACCESO,
    COOKIE_OPERADOR_REFRESCO,
    COOKIE_PISTA_OPERADOR,
    ClaimsOperadorActuales,
)
from app.core.config import get_settings
from app.db.deps import SesionOperador
from app.models.empresa import Empresa
from app.schemas.auth import CambioClaveRequest
from app.schemas.operador import (
    AltaEmpresaRequest,
    AsientoBitacora,
    ClaveTemporalResponse,
    EmpresaEdicionRequest,
    EmpresaResumen,
    LoginOperadorRequest,
    OperadorOut,
    SesionOperadorResponse,
)
from app.services import operador as servicio
from app.services.limites import DemasiadosIntentos

router = APIRouter(prefix="/operador", tags=["operador"])

NO_ENCONTRADA = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada."
)


def _uuid(valor: str) -> UUID:
    """Un identificador malformado es un 404, no un 422.

    Desde fuera son lo mismo —esa empresa no existe— y distinguirlos permitiría averiguar qué
    identificadores tienen forma válida a base de probar.
    """
    try:
        return UUID(valor)
    except ValueError as exc:
        raise NO_ENCONTRADA from exc


def _resumen(empresa: Empresa) -> EmpresaResumen:
    return EmpresaResumen(
        id=empresa.id,
        nombre=empresa.nombre,
        activa=empresa.activa,
        fecha_registro=None,
        suspendida_en=empresa.suspendida_en,
    )


Almacen = Annotated[AlmacenEfimero, Depends(get_almacen)]

#: Mensaje único para credenciales inválidas, igual que en el plano de datos: no distingue entre
#: correo inexistente y contraseña incorrecta.
CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos."


def _ruta_cookies() -> str:
    """Las cookies del operador solo viajan a su propio prefijo."""
    return f"{get_settings().api_v1_prefix}/operador"


#: Ruta de la pista de sesión del operador: las páginas de la consola en el frontend, no la API.
#: Así el proxy puede proteger `/operador` sin que la pista viaje con cada petición del sitio.
RUTA_PISTA_OPERADOR = "/operador"


def _poner_cookies(response: Response, sesion: servicio.SesionOperador) -> None:
    s = get_settings()
    samesite = cast(Literal["lax", "strict", "none"], s.cookie_samesite.lower())
    ruta = _ruta_cookies()
    response.set_cookie(
        COOKIE_OPERADOR_ACCESO,
        sesion.token_acceso,
        max_age=s.jwt_access_expire_minutes * 60,
        # A diferencia de la cookie del plano de datos, que va en `/`, esta se limita a la consola:
        # una petición a `/api/v1/auth/...` no la lleva, así que no hay forma de que una ruta del
        # plano de datos vea nunca el token del operador.
        path=ruta,
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )
    response.set_cookie(
        COOKIE_OPERADOR_REFRESCO,
        sesion.token_refresco,
        max_age=s.jwt_refresh_expire_days * 86400,
        path=ruta,
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )
    # Pista para el proxy del frontend. Dura lo que el token de acceso, no lo que el de refresco:
    # la consola no renueva sesiones, así que pasados 30 minutos no queda nada que conservar.
    # Ver COOKIE_PISTA_SESION en app.core.auth.
    response.set_cookie(
        COOKIE_PISTA_OPERADOR,
        "1",
        max_age=s.jwt_access_expire_minutes * 60,
        path=RUTA_PISTA_OPERADOR,
        httponly=True,
        secure=s.cookie_secure,
        samesite=samesite,
    )


def _borrar_cookies(response: Response) -> None:
    ruta = _ruta_cookies()
    response.delete_cookie(COOKIE_OPERADOR_ACCESO, path=ruta)
    response.delete_cookie(COOKIE_OPERADOR_REFRESCO, path=ruta)
    response.delete_cookie(COOKIE_PISTA_OPERADOR, path=RUTA_PISTA_OPERADOR)


def _demasiados_intentos(exc: DemasiadosIntentos) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiados intentos. Espera un momento antes de volver a probar.",
        headers={"Retry-After": str(exc.espera_segundos)},
    )


# --- Sesión -------------------------------------------------------------------


@router.post("/login", response_model=SesionOperadorResponse)
async def login(
    datos: LoginOperadorRequest,
    session: SesionOperador,
    almacen: Almacen,
    request: Request,
    response: Response,
) -> SesionOperadorResponse:
    s = get_settings()
    try:
        sesion = await servicio.autenticar(
            session,
            almacen,
            correo=datos.correo,
            password=datos.password,
            expira_en_segundos=s.jwt_access_expire_minutes * 60,
            ip=request.client.host if request.client else None,
        )
    except DemasiadosIntentos as exc:
        raise _demasiados_intentos(exc) from exc
    except servicio.ErrorDeAutenticacion as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=CREDENCIALES_INVALIDAS
        ) from exc
    _poner_cookies(response, sesion)
    return SesionOperadorResponse(
        operador=OperadorOut.model_validate(sesion.operador),
        expira_en_segundos=sesion.expira_en_segundos,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    """Cierra la sesión del operador. No exige estar autenticado, igual que el del plano de datos:
    salir con un token caducado debe limpiar las cookies, no dejar a nadie atrapado en un 401."""
    _borrar_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/cambiar-clave", response_model=SesionOperadorResponse)
async def cambiar_clave(
    datos: CambioClaveRequest,
    claims: ClaimsOperadorActuales,
    session: SesionOperador,
    almacen: Almacen,
    response: Response,
) -> SesionOperadorResponse:
    """El operador cambia su propia contraseña. Queda en la bitácora."""
    s = get_settings()
    try:
        sesion = await servicio.cambiar_password(
            session,
            almacen,
            operador_id=claims.operador_id,
            password_actual=datos.password_actual,
            password_nueva=datos.password_nueva,
            expira_en_segundos=s.jwt_access_expire_minutes * 60,
        )
    except DemasiadosIntentos as exc:
        raise _demasiados_intentos(exc) from exc
    except servicio.ClaveActualIncorrecta as exc:
        # 400 y no 401, igual que en el plano de datos: la sesión es válida.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        ) from exc
    except servicio.ErrorDeAutenticacion as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado"
        ) from exc
    _poner_cookies(response, sesion)
    return SesionOperadorResponse(
        operador=OperadorOut.model_validate(sesion.operador),
        expira_en_segundos=sesion.expira_en_segundos,
    )


@router.get("/yo", response_model=OperadorOut)
async def yo(claims: ClaimsOperadorActuales, session: SesionOperador) -> OperadorOut:
    operador = await servicio.operador_actual(session, claims.operador_id)
    if operador is None:
        # Cuenta desactivada o borrada mientras la sesión seguía viva.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return OperadorOut.model_validate(operador)


# --- Empresas -----------------------------------------------------------------


@router.get("/empresas", response_model=list[EmpresaResumen])
async def listar_empresas(
    claims: ClaimsOperadorActuales, session: SesionOperador
) -> list[EmpresaResumen]:
    """Las empresas clientes con su administrador y su conteo de equipos.

    Sin ningún dato de negocio: eso es lo que separa este plano del otro.
    """
    filas = await servicio.listar_empresas(session)
    equipos = await servicio.contar_equipos(session)
    return [
        EmpresaResumen(
            id=empresa.id,
            nombre=empresa.nombre,
            activa=empresa.activa,
            fecha_registro=None,
            suspendida_en=empresa.suspendida_en,
            admin_nombre=admin.nombre if admin else None,
            admin_correo=admin.correo if admin else None,
            equipos=None if equipos is None else equipos.get(empresa.id, 0),
        )
        for empresa, admin in filas
    ]


@router.post("/empresas", response_model=ClaveTemporalResponse, status_code=status.HTTP_201_CREATED)
async def alta_empresa(
    datos: AltaEmpresaRequest, claims: ClaimsOperadorActuales, session: SesionOperador
) -> ClaveTemporalResponse:
    """Da de alta una empresa cliente y su primer administrador (RF-01).

    Devuelve la contraseña temporal **una sola vez**. No se guarda en claro en ningún sitio, así
    que si se pierde hay que generar otra con `/restablecer-clave`.
    """
    try:
        _empresa, admin, password = await servicio.dar_de_alta_empresa(
            session,
            operador_id=claims.operador_id,
            empresa=datos.empresa,
            admin_nombre=datos.admin_nombre,
            admin_correo=datos.admin_correo,
        )
    except servicio.CorreoYaRegistrado as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese correo ya pertenece a un usuario de otra empresa.",
        ) from exc
    return ClaveTemporalResponse(correo=admin.correo, password_temporal=password)


@router.patch("/empresas/{empresa_id}", response_model=EmpresaResumen)
async def editar_empresa(
    empresa_id: str,
    datos: EmpresaEdicionRequest,
    claims: ClaimsOperadorActuales,
    session: SesionOperador,
) -> EmpresaResumen:
    try:
        empresa = await servicio.renombrar_empresa(
            session,
            operador_id=claims.operador_id,
            empresa_id=_uuid(empresa_id),
            nombre=datos.nombre,
        )
    except servicio.EmpresaNoEncontrada as exc:
        raise NO_ENCONTRADA from exc
    return _resumen(empresa)


@router.post("/empresas/{empresa_id}/suspender", response_model=EmpresaResumen)
async def suspender(
    empresa_id: str, claims: ClaimsOperadorActuales, session: SesionOperador
) -> EmpresaResumen:
    """Suspende una empresa: sus datos siguen ahí y su gente deja de poder entrar."""
    try:
        empresa = await servicio.cambiar_estado_empresa(
            session, operador_id=claims.operador_id, empresa_id=_uuid(empresa_id), activa=False
        )
    except servicio.EmpresaNoEncontrada as exc:
        raise NO_ENCONTRADA from exc
    return _resumen(empresa)


@router.post("/empresas/{empresa_id}/reactivar", response_model=EmpresaResumen)
async def reactivar(
    empresa_id: str, claims: ClaimsOperadorActuales, session: SesionOperador
) -> EmpresaResumen:
    try:
        empresa = await servicio.cambiar_estado_empresa(
            session, operador_id=claims.operador_id, empresa_id=_uuid(empresa_id), activa=True
        )
    except servicio.EmpresaNoEncontrada as exc:
        raise NO_ENCONTRADA from exc
    return _resumen(empresa)


@router.post("/empresas/{empresa_id}/restablecer-clave", response_model=ClaveTemporalResponse)
async def restablecer_clave(
    empresa_id: str, claims: ClaimsOperadorActuales, session: SesionOperador
) -> ClaveTemporalResponse:
    """Genera una contraseña temporal para el administrador de una empresa.

    Es el caso de soporte más frecuente y también el más delicado: quien lo ejecuta obtiene acceso
    a la cuenta de un cliente hasta que ese cliente la cambie. Queda registrado en la bitácora.
    """
    try:
        admin, password = await servicio.restablecer_clave_administrador(
            session, operador_id=claims.operador_id, empresa_id=_uuid(empresa_id)
        )
    except servicio.EmpresaNoEncontrada as exc:
        raise NO_ENCONTRADA from exc
    except servicio.SinAdministrador as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esa empresa no tiene ningún administrador activo.",
        ) from exc
    return ClaveTemporalResponse(correo=admin.correo, password_temporal=password)


# --- Bitácora -----------------------------------------------------------------


@router.get("/bitacora", response_model=list[AsientoBitacora])
async def bitacora(
    claims: ClaimsOperadorActuales, session: SesionOperador
) -> list[AsientoBitacora]:
    filas = await servicio.leer_bitacora(session)
    return [
        AsientoBitacora(
            id=asiento.id,
            accion=asiento.accion,
            empresa_id=asiento.empresa_id,
            detalle=asiento.detalle,
            creado_en=asiento.creado_en,
            operador_nombre=nombre,
        )
        for asiento, nombre in filas
    ]
