"""Cabeceras de seguridad en TODAS las respuestas de la API (08-fase5, 8.7; OWASP A02).

La API solo devuelve JSON, así que su política de contenido es la más estricta posible: nada que
ejecutar ni que incrustar. Ninguna respuesta se guarda en una caché compartida (`no-store`), salvo
que la ruta haya fijado su propia política (las listas con `ETag` usan `private, no-cache`).

POR QUÉ ASGI PURO Y ENVOLVIENDO LA PILA ENTERA
----------------------------------------------
- `BaseHTTPMiddleware` (`@app.middleware("http")`) rompe las respuestas en streaming.
- Las respuestas 500 de excepciones no controladas las genera `ServerErrorMiddleware`, que Starlette
  coloca por fuera de todo lo registrado con `add_middleware`: un middleware registrado así nunca
  ve esos 500 y salen sin cabeceras. Por eso `SimapAPI.build_middleware_stack` envuelve la pila
  completa con este middleware. La prueba
  `test_un_500_no_controlado_tambien_lleva_las_cabeceras` lo comprueba.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CABECERAS_API: Mapping[str, str] = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
}

#: Las páginas de documentación interactiva son HTML con scripts: con la CSP de la API no cargarían.
#: En producción se apagan (`EXPONER_DOCS=false`); en desarrollo se sirven sin esa CSP.
RUTAS_DOCUMENTACION = ("/docs", "/redoc", "/openapi.json")

HSTS = ("strict-transport-security", "max-age=63072000; includeSubDomains")


class CabecerasSeguridad:
    """Agrega las cabeceras que la respuesta no traiga ya. Ruta y configuración se leen en cada
    petición: `app` se construye al importar el módulo y un valor capturado ignoraría el entorno."""

    def __init__(self, app: ASGIApp, *, con_hsts: Callable[[], bool]) -> None:
        self.app = app
        self.con_hsts = con_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        es_documentacion = str(scope.get("path", "")).startswith(RUTAS_DOCUMENTACION)
        hsts = self.con_hsts()

        async def enviar(mensaje: Message) -> None:
            if mensaje["type"] == "http.response.start":
                existentes = {k.lower() for k, _ in mensaje.get("headers", [])}
                agregadas: list[tuple[bytes, bytes]] = []
                for nombre, valor in CABECERAS_API.items():
                    if es_documentacion and nombre == "content-security-policy":
                        continue
                    if nombre.encode() not in existentes:
                        agregadas.append((nombre.encode(), valor.encode()))
                if hsts and HSTS[0].encode() not in existentes:
                    agregadas.append((HSTS[0].encode(), HSTS[1].encode()))
                mensaje = {**mensaje, "headers": [*mensaje.get("headers", []), *agregadas]}
            await send(mensaje)

        await self.app(scope, receive, enviar)


__all__ = ["CABECERAS_API", "CabecerasSeguridad"]
