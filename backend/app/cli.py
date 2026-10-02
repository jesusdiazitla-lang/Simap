"""Herramientas de administración de SIMAP que se ejecutan desde la consola del servidor.

POR QUÉ ESTO NO ES UN ENDPOINT
------------------------------
SIMAP se cobra por equipo monitoreado, así que dar de alta una empresa no puede ser autoservicio:
una empresa que se registra sola usaría el sistema completo sin haber pagado. El alta es por
invitación, y esa invitación la concede quien opera SIMAP.

Podría haberse dejado `POST /auth/register` publicado y simplemente no enlazarlo desde la interfaz,
pero eso no es seguridad: FastAPI publica el esquema OpenAPI en `/docs`, así que cualquiera
encontraría la ruta en menos de un minuto. La única forma de cerrarla de verdad es que no exista. La
lógica de alta no se duplica aquí: es la misma `app.services.auth.registrar_empresa` que estaba
probada, invocada desde un sitio al que no se llega por HTTP.

Se conecta con `DATABASE_URL_MIGRACIONES` (el rol `simap_owner`), no con la del backend: desde la
revisión 0002 de Alembic, `app_user` no tiene ninguna política RLS que le permita insertar en
`empresas`. Es decir, aunque alguien reintrodujera la ruta por descuido, la base la rechazaría.

Uso:

    python -m app.cli crear-empresa --empresa "Planta Norte" \\
        --admin-nombre "Ana Reyes" --admin-correo ana@plantanorte.com

La contraseña se pide por teclado y no se hace eco. No se acepta como argumento porque los
argumentos quedan en el historial del intérprete de comandos y son visibles para cualquier otro
proceso de la máquina mientras el comando corre.

NO HAY COMANDO PARA LISTAR EMPRESAS, Y ES DELIBERADO
----------------------------------------------------
`FORCE ROW LEVEL SECURITY` oculta las filas incluso al dueño de las tablas cuando no hay tenant
fijado, así que un `listar-empresas` habría devuelto siempre vacío. La salida correcta no era
debilitar la política para que el listado funcionara: eso convertiría a `simap_owner` en un rol
capaz de leer datos de todas las empresas, y hay una prueba en `test_aislamiento_tenant.py` que
existe justo para impedirlo. Quien opera SIMAP y necesite inventariar los tenants lo hace con `psql`
como superusuario, el único rol al que PostgreSQL permite saltarse RLS y el único que se administra
a mano.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.operador import Operador
from app.schemas.auth import MAX_PASSWORD, MIN_PASSWORD, RegistroRequest
from app.services import auth as servicio

#: Código de salida para un fallo previsible (correo duplicado, contraseña corta). Se distingue de 1
#: para que un script que envuelva este comando pueda reaccionar sin analizar el texto del error.
SALIDA_ERROR_DE_USO = 2


def _conexion() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Motor y sesiones con el rol dueño de las tablas, el único que puede dar de alta una empresa.

    No reutiliza `app.db.session.get_sessionmaker` a propósito: aquella está cacheada y apunta a
    `DATABASE_URL` (app_user), que es justamente el rol al que la revisión 0002 le quitó el permiso.
    Devuelve también el motor porque quien lo crea es quien tiene que cerrarlo.
    """
    motor = create_async_engine(get_settings().database_url_migraciones)
    return motor, async_sessionmaker(motor, expire_on_commit=False)


async def _crear_empresa(datos: RegistroRequest) -> None:
    motor, fabrica = _conexion()
    try:
        async with fabrica() as session:
            async with session.begin():
                sesion = await servicio.registrar_empresa(
                    session,
                    empresa=datos.empresa,
                    nombre=datos.nombre,
                    correo=datos.correo,
                    password=datos.password,
                )
                # Los tokens que devuelve el servicio se descartan: aquí no se abre ninguna sesión
                # de usuario, solo se crean las filas. El administrador entrará por la pantalla de
                # acceso como cualquier otra persona.
                empresa_id = sesion.usuario.empresa_id
                usuario_id = sesion.usuario.id
        print(f"Empresa creada:   {datos.empresa}")
        print(f"  empresa_id:     {empresa_id}")
        print(f"  administrador:  {datos.correo}")
        print(f"  usuario_id:     {usuario_id}")
        print("\nYa puede iniciar sesion en la pantalla de acceso.")
    finally:
        await motor.dispose()


def _pedir_password() -> str:
    password = getpass.getpass("Contrasena del administrador: ")
    if password != getpass.getpass("Repetir contrasena: "):
        raise SystemExit("Las contrasenas no coinciden.")
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise SystemExit(
            f"La contrasena debe tener entre {MIN_PASSWORD} y {MAX_PASSWORD} caracteres."
        )
    return password


async def _crear_operador(nombre: str, correo: str, password: str) -> None:
    """Siembra un operador de SIMAP (plano de control).

    Es el único comando que sigue haciendo falta después del primer arranque, y solo la primera
    vez: en cuanto exista un operador, los siguientes se crean desde la consola web. El huevo y la
    gallina no se pueden romper de otra forma.

    Corre con el rol dueño de las tablas, que tiene una política propia sobre `operadores`
    justamente para esto (revisión 0003 de Alembic).
    """
    motor, fabrica = _conexion()
    try:
        async with fabrica() as session:
            async with session.begin():
                operador = Operador(
                    nombre=nombre.strip(),
                    correo=correo.strip().lower(),
                    password_hash=hash_password(password),
                )
                session.add(operador)
                await session.flush()
                operador_id = operador.id
        print(f"Operador creado:  {nombre}")
        print(f"  operador_id:    {operador_id}")
        print(f"  correo:         {correo}")
        print("")
        print("Ya puede entrar en la consola del operador: /operador")
    finally:
        await motor.dispose()


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Administracion de SIMAP. El alta de empresas es por invitacion.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    crear = sub.add_parser("crear-empresa", help="Da de alta una empresa y su administrador.")
    crear.add_argument("--empresa", required=True, help="Nombre de la empresa cliente.")
    crear.add_argument("--admin-nombre", required=True, help="Nombre de la persona administradora.")
    crear.add_argument("--admin-correo", required=True, help="Correo con el que iniciara sesion.")
    crear.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la contrasena de la entrada estandar en lugar de pedirla por teclado."
        " Solo para automatizacion.",
    )

    operador = sub.add_parser(
        "crear-operador",
        help="Siembra un operador de SIMAP (plano de control). Solo hace falta la primera vez.",
    )
    operador.add_argument("--nombre", required=True, help="Nombre de la persona que opera SIMAP.")
    operador.add_argument("--correo", required=True, help="Correo con el que entrara a la consola.")
    operador.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la contrasena de la entrada estandar en lugar de pedirla por teclado.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else _pedir_password()

    if args.comando == "crear-operador":
        if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
            print(
                f"La contrasena debe tener entre {MIN_PASSWORD} y {MAX_PASSWORD} caracteres.",
                file=sys.stderr,
            )
            return SALIDA_ERROR_DE_USO
        try:
            asyncio.run(_crear_operador(args.nombre, args.correo, password))
        except IntegrityError as exc:
            if "uq_operadores_correo" in str(exc.orig):
                print(f"Ya existe un operador con ese correo: {args.correo}", file=sys.stderr)
                return SALIDA_ERROR_DE_USO
            raise
        return 0

    # Se valida con el MISMO esquema que validaba la ruta HTTP que se retiro. Si el CLI tuviera sus
    # propias reglas, el alta por consola aceptaria correos malformados o contrasenas debiles que la
    # ruta rechazaba, y la regla real del sistema seria la mas laxa de las dos.
    try:
        datos = RegistroRequest(
            empresa=args.empresa,
            nombre=args.admin_nombre,
            correo=args.admin_correo,
            password=password,
        )
    except ValidationError as exc:
        for error in exc.errors():
            campo = ".".join(str(parte) for parte in error["loc"]) or "(cuerpo)"
            print(f"{campo}: {error['msg']}", file=sys.stderr)
        return SALIDA_ERROR_DE_USO

    try:
        asyncio.run(_crear_empresa(datos))
    except servicio.CorreoYaRegistrado:
        print(f"Ese correo ya pertenece a un usuario: {datos.correo}", file=sys.stderr)
        return SALIDA_ERROR_DE_USO
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
