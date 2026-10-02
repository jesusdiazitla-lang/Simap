"""Control de acceso por rol (RBAC), verificado en la API y no solo en la interfaz.

`docs/contexto/04-fase1-fundamentos.md`, sección 4.5: ningún endpoint asume un rol por defecto. Si
no se declara qué roles pueden usarlo, se rechaza el acceso. Por eso `requiere_roles()` sin
argumentos es un error de programación y no un «cualquiera puede pasar».

RBAC y RLS resuelven cosas distintas y hacen falta las dos: RLS decide **qué filas** ve un usuario
(las de su empresa); RBAC decide **qué operaciones** puede pedir (un operario reporta una alerta,
pero no cierra una orden de trabajo).
"""

from collections.abc import Callable

from fastapi import HTTPException, status

from app.core.auth import ClaimsActuales
from app.core.security import Claims, Rol


class RolNoDeclarado(RuntimeError):
    """Se intentó proteger un endpoint sin decir qué roles lo pueden usar."""


def requiere_roles(*roles: Rol) -> Callable[..., Claims]:
    """Dependencia que exige que el usuario tenga uno de `roles`.

    Se usa así en una ruta::

        @router.post("/ordenes")
        async def crear(claims: Annotated[Claims, Depends(requiere_roles(Rol.SUPERVISOR))]) -> ...:

    Devuelve 403 (no 401) cuando el usuario está autenticado pero su rol no basta: 401 significa
    «no sé quién eres» e invitaría al cliente a reintentar el login, que no arreglaría nada.
    """
    if not roles:
        raise RolNoDeclarado(
            "requiere_roles() necesita al menos un rol. Un endpoint sin roles declarados "
            "se rechaza siempre (04-fase1-fundamentos.md, seccion 4.5)."
        )

    permitidos = frozenset(roles)

    def dependencia(claims: ClaimsActuales) -> Claims:
        if claims.rol not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene permiso para esta operación",
            )
        return claims

    return dependencia
