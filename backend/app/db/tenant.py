"""Estrategias de aislamiento multi-tenant, una por motor de base de datos.

POR QUÉ EXISTE ESTE MÓDULO
--------------------------
SIMAP debe poder cambiar de motor sin reescribir la aplicación. SQLAlchemy ya abstrae el dialecto
para el ORM, así que las consultas son portables casi gratis; lo que **no** es portable es cómo se
impone el aislamiento entre empresas:

* PostgreSQL lo hace en la propia base con Row-Level Security: la sesión fija `app.empresa_id` y las
  políticas de `db/rls_policies.sql` filtran cada consulta. Ni un error de programación en un
  servicio puede devolver filas de otra empresa.
* MySQL no tiene RLS. SQLite tampoco. SQL Server tiene un mecanismo parecido pero incompatible.

Si el SQL de PostgreSQL estuviera esparcido por los servicios, cambiar de motor rompería la
aplicación en veinte sitios. Y si simplemente se omitiera, el cambio de motor dejaría la aplicación
funcionando pero **sin aislamiento**, que es mucho peor que romperse.

Por eso todo lo específico del motor vive aquí detrás de `EstrategiaTenant`, y se elige por dialecto
en un único punto (`estrategia_para`). Cambiar de motor es cambiar `DATABASE_URL`; la estrategia
correcta se selecciona sola.

CÓMO AÑADIR UN MOTOR
--------------------
Escribir una subclase de `EstrategiaTenant` y registrarla en `_ESTRATEGIAS` con el nombre de
dialecto que usa SQLAlchemy (`engine.dialect.name`). Nada más en toda la aplicación.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EstrategiaTenant(ABC):
    """Cómo se restringe una sesión a una sola empresa en un motor concreto."""

    #: True si el motor impone el aislamiento por sí mismo. Cuando es False, la garantía depende de
    #: que los servicios filtren, y eso hay que decirlo en voz alta, no darlo por hecho.
    aplicado_por_la_base: bool = False

    @abstractmethod
    async def fijar_empresa(self, session: AsyncSession, empresa_id: UUID) -> None:
        """Deja la sesión restringida a `empresa_id` durante la transacción en curso."""

    @abstractmethod
    async def limpiar_empresa(self, session: AsyncSession) -> None:
        """Deshace el fijado, para sesiones que no terminan con la transacción."""

    @abstractmethod
    async def permitir_busqueda_por_correo(self, session: AsyncSession, correo: str) -> None:
        """Habilita leer el usuario de un correo concreto sin conocer aún su empresa.

        Lo necesita el login, que tiene un problema de huevo y gallina: para saber a qué empresa
        pertenece alguien hay que leer su fila, pero para leer cualquier fila hay que haber fijado
        ya la empresa. Cada motor lo resuelve a su manera; en los que no aplican aislamiento en la
        base no hace falta nada.
        """


class RowLevelSecurityPostgres(EstrategiaTenant):
    """PostgreSQL: el aislamiento lo aplica la base con RLS.

    `set_config(..., is_local => true)` equivale a `SET LOCAL`: el valor vive solo hasta que termina
    la transacción, así que una conexión devuelta al pool nunca arrastra el tenant del request
    anterior. Se usa la función y no la sentencia `SET LOCAL` porque `SET` no admite parámetros
    enlazados, y construir la sentencia por concatenación abriría una inyección SQL con el contenido
    del token.
    """

    aplicado_por_la_base = True

    #: Variable de sesión que leen las políticas de db/rls_policies.sql.
    VARIABLE = "app.empresa_id"
    #: Variable que habilita la política `login_lookup` para un único correo.
    VARIABLE_CORREO = "app.login_correo"

    async def fijar_empresa(self, session: AsyncSession, empresa_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config(:variable, :empresa_id, true)"),
            {"variable": self.VARIABLE, "empresa_id": str(empresa_id)},
        )

    async def limpiar_empresa(self, session: AsyncSession) -> None:
        await session.execute(
            text("SELECT set_config(:variable, '', true)"),
            {"variable": self.VARIABLE},
        )

    async def permitir_busqueda_por_correo(self, session: AsyncSession, correo: str) -> None:
        """Activa la política `login_lookup` para este correo y solo para él.

        La política compara `usuarios.correo` con esta variable, así que la consulta puede devolver
        como mucho UNA fila: justo la del correo que la persona acaba de escribir en el formulario.
        No permite listar, ni buscar por patrón, ni enumerar correos, y caduca con la transacción.
        Es el mínimo imprescindible para poder verificar una contraseña.
        """
        await session.execute(
            text("SELECT set_config(:variable, :correo, true)"),
            {"variable": self.VARIABLE_CORREO, "correo": correo},
        )


class FiltradoEnAplicacion(EstrategiaTenant):
    """Motores sin RLS: no hay nada que fijar en la conexión.

    El aislamiento pasa a depender de que cada consulta filtre por `empresa_id`. Es una garantía
    estrictamente más débil que la de PostgreSQL: un `select` que olvide el filtro devuelve datos de
    todas las empresas, y nada en la base lo impide.

    `aplicado_por_la_base = False` existe para que eso sea comprobable desde un test y visible en
    arranque, en lugar de ser una degradación silenciosa.
    """

    async def fijar_empresa(self, session: AsyncSession, empresa_id: UUID) -> None:
        return None

    async def limpiar_empresa(self, session: AsyncSession) -> None:
        return None

    async def permitir_busqueda_por_correo(self, session: AsyncSession, correo: str) -> None:
        # Sin RLS no hay nada que habilitar: la consulta ya puede leer la tabla entera.
        return None


#: Dialecto de SQLAlchemy -> estrategia. Añadir un motor es añadir una fila aquí.
_ESTRATEGIAS: dict[str, type[EstrategiaTenant]] = {
    "postgresql": RowLevelSecurityPostgres,
    "mysql": FiltradoEnAplicacion,
    "sqlite": FiltradoEnAplicacion,
    "mssql": FiltradoEnAplicacion,
}

#: Motor recomendado. El proyecto está diseñado sobre RLS; los demás pierden esa garantía.
DIALECTO_RECOMENDADO = "postgresql"


def estrategia_para(dialecto: str) -> EstrategiaTenant:
    """Devuelve la estrategia del dialecto, o la más conservadora si no se conoce.

    Un motor desconocido cae en `FiltradoEnAplicacion` en vez de fallar: puede que funcione. Lo que
    no hace es fingir que hay RLS donde no la hay.
    """
    return _ESTRATEGIAS.get(dialecto, FiltradoEnAplicacion)()
