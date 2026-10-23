"""Punto de entrada de la aplicación FastAPI."""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core import registro
from app.core.config import get_settings
from app.core.cursor import CursorInvalido

#: Cabeceras de seguridad exigidas por 04-fase1-fundamentos.md, sección 6.4.
#: HSTS solo tiene sentido sobre HTTPS, así que se añade únicamente cuando las cookies son `secure`
#: (es decir, fuera de desarrollo local): enviarla por HTTP no hace nada y confunde al depurar.
CABECERAS_SEGURIDAD = {
    # Impide que el navegador adivine el tipo de contenido e interprete como script
    # algo que no lo es.
    "X-Content-Type-Options": "nosniff",
    # La API no devuelve HTML: nada de esto deberia embeberse en un marco.
    "X-Frame-Options": "DENY",
    # No filtrar la URL completa (que puede llevar ids) a sitios de terceros.
    "Referrer-Policy": "no-referrer",
}


#: Métodos que modifican datos. Son los únicos que un sitio ajeno podría querer forzar con la sesión
#: del usuario (CSRF), así que son los únicos en los que se comprueba el origen.
METODOS_QUE_ESCRIBEN = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def origenes_permitidos() -> frozenset[str]:
    s = get_settings()
    return frozenset({*s.cors_origins, s.app_base_url.rstrip("/")})


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    """Programa el job nocturno dentro del proceso si así se configuró (F4, 9.3)."""
    programador = None
    if get_settings().job_diario_en_proceso:
        from app.jobs import programador as job

        programador = job.iniciar()
    try:
        yield
    finally:
        if programador is not None:
            programador.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    registro.configurar()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=ciclo_de_vida,
    )

    app.add_middleware(
        CORSMiddleware,
        # Lista blanca explicita, nunca "*": la sesion viaja en cookie y con "*" el navegador
        # rechazaria las credenciales o, peor, cualquier origen podria pedirlas (seccion 6.4).
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def registrar_peticion(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Una línea por petición con su `request_id`, y el id devuelto en `X-Request-ID`.

        Va registrado el último, así que es el más externo: envuelve también los rechazos de
        `origen_de_confianza`. Ver `app.core.registro`.
        """
        contexto = registro.nuevo_contexto(request.headers.get("x-request-id"))
        inicio = time.perf_counter()
        estado = 500
        try:
            response = await call_next(request)
            estado = response.status_code
        finally:
            ruta = request.scope.get("route")
            registro.evento(
                "http",
                metodo=request.method,
                # La plantilla de la ruta, no la URL: el código de un equipo o un id no acaban en
                # el registro.
                ruta=getattr(ruta, "path", "sin-ruta"),
                estado=estado,
                ms=round((time.perf_counter() - inicio) * 1000, 1),
            )
        response.headers["X-Request-ID"] = contexto.request_id
        return response

    @app.middleware("http")
    async def origen_de_confianza(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Defensa adicional contra CSRF (05-fase2-activos-y-campo.md, sección 8.2).

        `SameSite` ya impide que la cookie viaje en peticiones de otros sitios, pero no todos los
        navegadores lo aplican igual. Si una petición que escribe trae `Origin` y no es el del
        frontend, se rechaza. Sin cabecera `Origin` se deja pasar: los navegadores la mandan
        siempre en estas peticiones, y su ausencia indica un cliente que no es un navegador
        (pruebas, scripts), que no lleva la cookie de nadie más.
        """
        origen = request.headers.get("origin")
        if (
            request.method in METODOS_QUE_ESCRIBEN
            and origen is not None
            and origen.rstrip("/") not in origenes_permitidos()
        ):
            return JSONResponse(status_code=403, content={"detail": "Origen no permitido."})
        return await call_next(request)

    @app.middleware("http")
    async def cabeceras_de_seguridad(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for cabecera, valor in CABECERAS_SEGURIDAD.items():
            response.headers.setdefault(cabecera, valor)
        # Se relee la configuracion en cada peticion en lugar de capturarla al crear la aplicacion:
        # `app` se construye al importar el modulo, asi que un valor capturado ignoraria cualquier
        # cambio posterior del entorno (y haria imposible probar este comportamiento).
        if get_settings().cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception_handler(CursorInvalido)
    async def cursor_invalido(_request: Request, _exc: CursorInvalido) -> JSONResponse:
        # El cursor se descodifica en la ruta, pero su valor solo se interpreta en el servicio,
        # que es quien sabe si es un instante o un nombre. Lo que falle ahí también es un cursor
        # manipulado, y se responde igual que en `comun.leer_cursor`.
        return JSONResponse(status_code=422, content={"detail": "Cursor no válido."})

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
