"""Agrupa todas las rutas de la versión 1 de la API."""

from fastapi import APIRouter

from app.api.v1.routes import auth, health, operador

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
# Plano de control. Cuelga del mismo prefijo de API pero con su propia sesión, su propio rol de
# base de datos y sus propias cookies. Ver `app.api.v1.routes.operador`.
api_router.include_router(operador.router)
