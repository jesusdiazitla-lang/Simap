"""Cierra el alta de empresas al rol de aplicación: solo el dueño de las tablas puede crearlas.

Revision ID: 0002
Revises: 0001

POR QUÉ EXISTE ESTA MIGRACIÓN
-----------------------------
La revisión 0001 creó la política `empresa_signup`:

    CREATE POLICY empresa_signup ON empresas FOR INSERT WITH CHECK (true)

Existía para que `POST /auth/register` pudiera insertar una empresa antes de que hubiera ningún
tenant que fijar: el registro público era un camino abierto por diseño.

El modelo de negocio de SIMAP cobra **por equipo monitoreado**, así que el alta de una empresa no
puede ser autoservicio: quien se registra solo usaría el sistema completo sin haber pagado nada.
El registro pasa a ser **por invitación**, es decir, una operación administrativa que ejecuta quien
opera SIMAP desde la consola (`python -m app.cli crear-empresa`), no una ruta HTTP.

Esconder el endpoint no habría servido de nada: FastAPI publica el esquema OpenAPI en `/docs`, así
que cualquiera lo encontraría. Por eso la ruta pública se elimina *y* la política se estrecha; lo
segundo es lo que hace que la primera no se pueda saltar.

QUÉ CAMBIA EXACTAMENTE
----------------------
La política deja de aplicar a `PUBLIC` y pasa a aplicar solo a `simap_owner`. El efecto es que
`app_user` —el rol con el que el backend atiende cada petición HTTP— **ya no tiene ninguna política
que le permita insertar en `empresas`**. Con RLS activo, una operación sin política aplicable se
deniega, así que el `GRANT INSERT` que app_user conserva queda inerte para esta tabla.

Resultado: ningún rol que atienda tráfico web puede crear un tenant. Es estrictamente más estrecho
que antes y no depende de que nadie recuerde no llamar a una función.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Rol que corre las migraciones y, desde ahora, también el alta administrativa de empresas.
#: No es superusuario, así que sigue sujeto a FORCE ROW LEVEL SECURITY en todo lo demás.
ROL_ADMINISTRATIVO = "simap_owner"


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS empresa_signup ON empresas")
    # El nombre cambia porque el propósito cambió: ya no es el registro de nadie, es un alta
    # administrativa. Una política que se llama "signup" pero que solo puede usar el operador del
    # sistema es una trampa para quien la lea dentro de seis meses.
    op.execute(
        "CREATE POLICY empresa_alta_administrativa ON empresas"
        f" FOR INSERT TO {ROL_ADMINISTRATIVO} WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS empresa_alta_administrativa ON empresas")
    op.execute("CREATE POLICY empresa_signup ON empresas FOR INSERT WITH CHECK (true)")
