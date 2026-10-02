"""Punto de entrada de la aplicación FastAPI."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)

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

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
