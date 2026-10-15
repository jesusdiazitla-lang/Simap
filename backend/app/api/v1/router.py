"""Agrupa todas las rutas de la versión 1 de la API."""

from fastapi import APIRouter

from app.api.v1.routes import (
    activos,
    alertas,
    auth,
    campo,
    componentes,
    health,
    lecturas,
    operador,
    ordenes,
    usuarios,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
# Plano de control. Cuelga del mismo prefijo de API pero con su propia sesión, su propio rol de
# base de datos y sus propias cookies. Ver `app.api.v1.routes.operador`.
api_router.include_router(operador.router)

# Plano de datos de la fase 2: todas pasan por get_db (RLS) y declaran sus roles.
api_router.include_router(usuarios.router)
api_router.include_router(componentes.router)
api_router.include_router(activos.router)
api_router.include_router(lecturas.router)
api_router.include_router(lecturas.revision)
api_router.include_router(alertas.router)
api_router.include_router(campo.router)

# Fase 3: órdenes de trabajo.
api_router.include_router(ordenes.router)
