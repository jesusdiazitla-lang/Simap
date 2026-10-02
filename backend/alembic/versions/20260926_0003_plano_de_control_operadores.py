"""Plano de control: operadores de SIMAP, bitácora y estado de las empresas.

Revision ID: 0003
Revises: 0002

QUÉ AÑADE Y POR QUÉ
-------------------
El dueño de SIMAP necesita dar de alta a las empresas clientes y a su primer administrador. Ese
usuario no pertenece a ninguna empresa, así que rompe la suposición sobre la que descansa todo el
aislamiento: que cada fila tiene un `empresa_id` y el token dice cuál.

La solución **no** es darle permiso para saltarse el Row-Level Security. Eso convertiría una sola
contraseña filtrada en el compromiso de todos los clientes a la vez, y dejaría inservible la
prueba que comprueba que ningún rol que atiende HTTP puede saltarse el aislamiento.

Lo que se hace es separar dos planos:

- **Plano de control** (esta migración): tabla `operadores`, sin `empresa_id`, atendida por el rol
  de base de datos `operador_user`. Da de alta empresas y sus administradores.
- **Plano de datos** (lo que ya existía): `usuarios` dentro de una empresa, atendido por `app_user`.

LA FRONTERA LA IMPONE POSTGRESQL, NO EL CÓDIGO
-----------------------------------------------
A `operador_user` se le conceden permisos **tabla por tabla**, aquí y en cada migración futura que
cree una tabla que deba ver. Nunca recibe un `ALTER DEFAULT PRIVILEGES` como el de `app_user`. Por
tanto las tablas de negocio de F2 en adelante (activos, lecturas, alertas, órdenes, repuestos)
quedan fuera de su alcance **por omisión**: hacerlas visibles exigiría un `GRANT` explícito que se
ve en la revisión del código.

Y dentro de lo que sí ve, las políticas lo estrechan más:

- sobre `empresas`, acceso completo: es su trabajo;
- sobre `usuarios`, **solo las filas con rol `administrador`**. No puede ver ni tocar operarios,
  supervisores, técnicos ni gerentes de ninguna planta.

Nada de esto le da acceso a datos de negocio, que es la frontera que el usuario pidió.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Rol de base de datos que atiende la consola del operador.
ROL_OPERADOR = "operador_user"
#: Rol que corre las migraciones y es dueño de las tablas.
ROL_DUENO = "simap_owner"


def upgrade() -> None:
    # --- Estado de la empresa: suspender sin borrar --------------------------
    # Una empresa que deja de pagar no se elimina: se suspende. Sus datos siguen ahí y nadie de esa
    # empresa puede entrar. `server_default` en true para que las filas existentes queden activas.
    op.add_column(
        "empresas",
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("empresas", sa.Column("suspendida_en", sa.DateTime(timezone=True), nullable=True))

    # --- Operadores de SIMAP -------------------------------------------------
    op.create_table(
        "operadores",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("correo", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        # Un operador que se va se desactiva, no se borra: su rastro en la bitácora tiene que
        # seguir apuntando a alguien con nombre.
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("correo", name="uq_operadores_correo"),
    )

    # --- Bitácora del plano de control ---------------------------------------
    # Crear una empresa, suspenderla o restablecer la contraseña del administrador de una planta
    # son acciones sensibles por definición: quedan registradas con quién, cuándo y sobre qué.
    op.create_table(
        "operador_bitacora",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # ondelete RESTRICT: no se puede borrar un operador que dejó rastro. Es lo que impide que
        # alguien borre su propia cuenta para hacer desaparecer lo que hizo.
        sa.Column(
            "operador_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("operadores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accion", sa.Text(), nullable=False),
        # Sin clave foránea a `empresas` a propósito: si algún día se borra una empresa, el asiento
        # de la bitácora tiene que sobrevivir para decir que existió.
        sa.Column("empresa_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_bitacora_creado_en", "operador_bitacora", ["creado_en"])
    op.create_index("ix_bitacora_empresa_id", "operador_bitacora", ["empresa_id"])

    # --- Permisos del rol del plano de control -------------------------------
    # Tabla por tabla, nunca por defecto. Ver la cabecera de este archivo.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON empresas TO {ROL_OPERADOR}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON usuarios TO {ROL_OPERADOR}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON operadores TO {ROL_OPERADOR}")
    op.execute(f"GRANT SELECT, INSERT ON operador_bitacora TO {ROL_OPERADOR}")
    # app_user no tiene nada que hacer en el plano de control: ni leer quién opera SIMAP ni la
    # bitácora. Se revoca lo que ALTER DEFAULT PRIVILEGES le concedió al crearse las tablas.
    op.execute("REVOKE ALL ON operadores FROM app_user")
    op.execute("REVOKE ALL ON operador_bitacora FROM app_user")

    # --- Row-Level Security de las tablas nuevas -----------------------------
    for tabla in ("operadores", "operador_bitacora"):
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
    # Solo el rol del plano de control las ve. Con RLS activo y sin política aplicable, cualquier
    # otro rol no superusuario obtiene cero filas aunque tuviera el GRANT.
    op.execute(
        f"CREATE POLICY operador_gestiona_operadores ON operadores"
        f" FOR ALL TO {ROL_OPERADOR} USING (true) WITH CHECK (true)"
    )
    op.execute(
        f"CREATE POLICY operador_escribe_bitacora ON operador_bitacora"
        f" FOR ALL TO {ROL_OPERADOR} USING (true) WITH CHECK (true)"
    )
    # El dueño de las tablas necesita poder sembrar el primer operador desde la consola
    # (`python -m app.cli crear-operador`), igual que hace con el alta de empresas.
    op.execute(
        f"CREATE POLICY dueno_siembra_operadores ON operadores"
        f" FOR ALL TO {ROL_DUENO} USING (true) WITH CHECK (true)"
    )

    # --- Políticas del operador sobre las tablas que ya existían -------------
    op.execute(
        f"CREATE POLICY operador_gestiona_empresas ON empresas"
        f" FOR ALL TO {ROL_OPERADOR} USING (true) WITH CHECK (true)"
    )
    # Solo administradores. El operador no tiene nada que ver con el personal de planta: ni
    # operarios, ni supervisores, ni técnicos, ni gerentes.
    op.execute(
        f"CREATE POLICY operador_gestiona_administradores ON usuarios"
        f" FOR ALL TO {ROL_OPERADOR}"
        f" USING (rol = 'administrador') WITH CHECK (rol = 'administrador')"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS operador_gestiona_administradores ON usuarios")
    op.execute("DROP POLICY IF EXISTS operador_gestiona_empresas ON empresas")
    op.execute("DROP POLICY IF EXISTS dueno_siembra_operadores ON operadores")
    op.execute("DROP POLICY IF EXISTS operador_escribe_bitacora ON operador_bitacora")
    op.execute("DROP POLICY IF EXISTS operador_gestiona_operadores ON operadores")
    op.drop_index("ix_bitacora_empresa_id", table_name="operador_bitacora")
    op.drop_index("ix_bitacora_creado_en", table_name="operador_bitacora")
    op.drop_table("operador_bitacora")
    op.drop_table("operadores")
    op.drop_column("empresas", "suspendida_en")
    op.drop_column("empresas", "activa")
