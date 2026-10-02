"""F1: empresas, usuarios, registro de intentos de login y su Row-Level Security.

Revision ID: 0001
Revises:
Create Date: 2026-09-25

Cubre RF-01, RF-02, RF-03 y RNF-01. Corresponde a la primera migración que pide
`docs/contexto/04-fase1-fundamentos.md`, sección 4.3: extensión pgcrypto, tabla empresas y tabla
usuarios. Se añaden en la misma revisión las políticas de aislamiento, porque una tabla multiempresa
sin su política es una tabla insegura: separarlas dejaría una ventana en la que existen los datos
pero no la protección.

Las ocho tablas restantes del modelo (activos, alertas, órdenes, repuestos…) llegan en F2-F4, cada
una con su política en su propia migración. `backend/db/schema.sql` y `backend/db/rls_policies.sql`
son la referencia del modelo completo.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tablas multiempresa creadas aquí y la columna por la que filtra su política.
#: `empresas` filtra por `id` porque la fila **es** la empresa.
TABLAS_CON_TENANT = {"empresas": "id", "usuarios": "empresa_id"}


def upgrade() -> None:
    # Idempotente: en el entorno de desarrollo la instala ya db/roles.sql como superusuario,
    # porque crear extensiones puede exigir privilegios que simap_owner no tiene.
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "empresas",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column(
            "fecha_registro",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_empresas"),
    )

    op.create_table(
        "usuarios",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("correo", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_usuarios_empresa_id_empresas"
        ),
        sa.UniqueConstraint("correo", name="uq_usuarios_correo"),
        sa.CheckConstraint(
            "rol IN ('operario', 'supervisor', 'tecnico_taller', 'gerente', 'administrador')",
            name="ck_usuarios_rol_valido",
        ),
    )
    # Indice en empresa_id desde el primer commit (seccion 7.2): gratis ahora, caro despues.
    op.create_index("ix_usuarios_empresa_id", "usuarios", ["empresa_id"])

    # Registro de intentos de login (seccion 2: entra ya en F1). SIN RLS por empresa: un intento
    # fallido puede venir de un correo que no existe en ninguna empresa, asi que no hay tenant al
    # que atribuirlo.
    op.create_table(
        "intentos_login",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("correo", sa.Text(), nullable=False),
        sa.Column("ip", sa.dialects.postgresql.INET(), nullable=True),
        sa.Column("exitoso", sa.Boolean(), nullable=False),
        sa.Column(
            "fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_intentos_login"),
    )
    op.create_index(
        "ix_intentos_login_correo_fecha",
        "intentos_login",
        ["correo", sa.text("fecha DESC")],
    )

    _activar_rls()


def _activar_rls() -> None:
    """ENABLE + FORCE y la política de aislamiento de cada tabla multiempresa.

    ENABLE activa las políticas; FORCE las aplica también al dueño de la tabla. Ambas hacen falta:
    sin FORCE, cualquier conexión con `simap_owner` vería todas las empresas.

    `current_setting('app.empresa_id', true)` devuelve NULL en vez de lanzar error cuando nadie lo
    fijó, y una comparación contra NULL es falsa: una transacción que olvide el `set_config` no ve
    ninguna fila. Falla cerrado.
    """
    for tabla, columna in TABLAS_CON_TENANT.items():
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{tabla} ON {tabla}"
            f" USING ({columna} = NULLIF(current_setting('app.empresa_id', true), '')::UUID)"
        )

    # Alta de empresa (registro). Cuando una politica declara USING y omite WITH CHECK, PostgreSQL
    # usa la misma expresion para validar los INSERT, lo que haria imposible registrarse: al crear
    # una empresa todavia no existe el id que habria que fijar. Las politicas permisivas se combinan
    # con OR, asi que esto habilita el INSERT sin abrir la lectura.
    op.execute("CREATE POLICY empresa_signup ON empresas FOR INSERT WITH CHECK (true)")

    # Busqueda de credenciales en el login. Problema de huevo y gallina: para saber a que empresa
    # pertenece alguien hay que leer su fila, pero tenant_isolation_usuarios exige conocer ya la
    # empresa. Sin esta politica, NINGUN login puede funcionar.
    #
    # El alcance es deliberadamente minimo: la politica compara contra app.login_correo, de modo
    # que solo deja ver la fila cuyo correo coincide EXACTAMENTE con el que la persona acaba de
    # escribir. No permite listar, ni buscar por patron, ni enumerar correos; y la variable caduca
    # con la transaccion, igual que app.empresa_id.
    op.execute(
        "CREATE POLICY login_lookup ON usuarios FOR SELECT"
        " USING (correo = NULLIF(current_setting('app.login_correo', true), ''))"
    )

    # Las tablas nacen propiedad de simap_owner (quien corre la migracion), y ALTER DEFAULT
    # PRIVILEGES de db/roles.sql ya concede el acceso a app_user. Este GRANT explicito cubre el caso
    # de que la migracion corra con otro rol en otro entorno.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON empresas, usuarios TO app_user")
    op.execute("GRANT SELECT, INSERT ON intentos_login TO app_user")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS empresa_signup ON empresas")
    op.execute("DROP POLICY IF EXISTS login_lookup ON usuarios")
    for tabla in TABLAS_CON_TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tabla} ON {tabla}")
    op.drop_index("ix_intentos_login_correo_fecha", table_name="intentos_login")
    op.drop_table("intentos_login")
    op.drop_index("ix_usuarios_empresa_id", table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_table("empresas")
    # pgcrypto no se elimina: puede estar en uso por otros objetos de la base.
