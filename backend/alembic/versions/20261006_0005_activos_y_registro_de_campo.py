"""F2: componentes, activos, lecturas de horómetro y alertas, con su Row-Level Security.

Revision ID: 0005
Revises: 0004

Corresponde a la «migración 0002» de `docs/contexto/05-fase2-activos-y-campo.md` (sección 4). El
documento la numera así y la escribe como `ALTER TABLE` porque supone que las tablas de negocio ya
existen; aquí la fase 1 solo creó `empresas` y `usuarios`, así que esta revisión **crea** las cuatro
tablas directamente con su forma final.

LO QUE IMPONE LA BASE, NO EL CÓDIGO
-----------------------------------
1. **RLS con ENABLE y FORCE en la misma revisión que crea cada tabla.** Nunca existe una tabla
   multiempresa sin su política, ni siquiera entre dos commits.
2. **`app_empresa_id()`** centraliza la lectura del tenant con `NULLIF(..., '')` (sección 8.5): una
   conexión del pool que ya fijó el parámetro devuelve cadena vacía, no NULL, y convertirla a uuid
   daría un 500 en vez de cero filas. Las políticas de `empresas` y `usuarios` se recrean con ella.
3. **Referencias compuestas** (sección 4.2): las llaves foráneas incluyen `empresa_id`, porque
   PostgreSQL las comprueba ignorando RLS.
4. **Solo adición** (sección 8.1): `app_user` no puede borrar en ninguna de las cuatro tablas, no
   puede reescribir una lectura salvo sus columnas de revisión, ni una alerta salvo su estado.
5. **El plano de control sigue sin ver datos de negocio.** `operador_user` recibe permiso de columna
   sobre `activos` —solo `empresa_id` y `estado`—: puede contar equipos por empresa para facturar,
   pero leer el nombre, la ubicación o el código de un equipo le da error de permisos. Y puede
   INSERTAR en `componentes` (la plantilla inicial al dar de alta una empresa) sin poder leerlos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_APP = "app_user"
ROL_OPERADOR = "operador_user"

#: Expresión de aislamiento. Envolver la función en un SELECT hace que PostgreSQL la evalúe una vez
#: por consulta y no una vez por fila (sección 4.4).
TENANT = "(SELECT app_empresa_id())"

TABLAS_NUEVAS = ("componentes", "activos", "lecturas_horometro", "alertas")


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _uuid() -> sa.TextClause:
    return sa.text("gen_random_uuid()")


#: Los CHECK se nombran solo con su sufijo (`criticidad_valida`): la convención de nombres de
#: `app.models.base`, que Alembic aplica también aquí, les antepone `ck_<tabla>_`. Escribir el
#: nombre completo lo duplicaba (`ck_activos_ck_activos_...`).


def upgrade() -> None:
    # --- Lectura central del tenant -----------------------------------------
    op.execute(
        "CREATE OR REPLACE FUNCTION app_empresa_id() RETURNS uuid LANGUAGE sql STABLE AS"
        " $$ SELECT NULLIF(current_setting('app.empresa_id', true), '')::uuid $$"
    )

    # --- usuarios: baja lógica y clave candidata compuesta -------------------
    op.add_column(
        "usuarios",
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_unique_constraint("uq_usuarios_empresa_id_id", "usuarios", ["empresa_id", "id"])

    # Las políticas de la fase 1 pasan a la función común y declaran WITH CHECK explícito.
    op.execute("DROP POLICY tenant_isolation_empresas ON empresas")
    op.execute(
        f"CREATE POLICY tenant_isolation_empresas ON empresas"
        f" USING (id = {TENANT}) WITH CHECK (id = {TENANT})"
    )
    op.execute("DROP POLICY tenant_isolation_usuarios ON usuarios")
    op.execute(
        f"CREATE POLICY tenant_isolation_usuarios ON usuarios"
        f" USING (empresa_id = {TENANT}) WITH CHECK (empresa_id = {TENANT})"
    )

    # --- componentes ---------------------------------------------------------
    op.create_table(
        "componentes",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_componentes"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_componentes_empresa_id_empresas"
        ),
        sa.UniqueConstraint("empresa_id", "nombre", name="uq_componentes_empresa_id_nombre"),
        sa.UniqueConstraint("empresa_id", "id", name="uq_componentes_empresa_id_id"),
    )

    # --- activos -------------------------------------------------------------
    op.create_table(
        "activos",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=True),
        sa.Column("ubicacion", sa.Text(), nullable=True),
        sa.Column("criticidad", sa.Text(), nullable=True),
        sa.Column("qr_code", sa.Text(), nullable=False),
        sa.Column("horometro_actual", sa.Integer(), server_default="0", nullable=False),
        sa.Column("horometro_actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_ultima_falla", sa.Date(), nullable=True),
        sa.Column("marca", sa.Text(), nullable=True),
        sa.Column("modelo", sa.Text(), nullable=True),
        sa.Column("numero_serie", sa.Text(), nullable=True),
        sa.Column("fecha_instalacion", sa.Date(), nullable=True),
        sa.Column("estado", sa.Text(), server_default="activo", nullable=False),
        sa.Column("dado_de_baja_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_activos"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_activos_empresa_id_empresas"
        ),
        # Único en todo el sistema: al escanear se resuelve sin saber de qué empresa es.
        sa.UniqueConstraint("qr_code", name="uq_activos_qr_code"),
        sa.UniqueConstraint("empresa_id", "id", name="uq_activos_empresa_id_id"),
        sa.CheckConstraint(
            "criticidad IN ('alta', 'media', 'baja')", name="criticidad_valida"
        ),
        sa.CheckConstraint("estado IN ('activo', 'baja')", name="estado_valido"),
        sa.CheckConstraint("horometro_actual >= 0", name="horometro_no_negativo"),
    )
    op.create_index("ix_activos_empresa_id_estado", "activos", ["empresa_id", "estado"])

    # --- lecturas_horometro --------------------------------------------------
    op.create_table(
        "lecturas_horometro",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=False),
        sa.Column("registrado_por", sa.Uuid(), nullable=False),
        sa.Column("valor_horometro", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column(
            "capturado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.Column("requiere_revision", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("motivo_revision", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_lecturas_horometro"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_lecturas_horometro_empresa_id_empresas"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activos.empresa_id", "activos.id"],
            name="fk_lecturas_horometro_activo_mismo_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id", "registrado_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_lecturas_horometro_autor_mismo_tenant",
        ),
        sa.UniqueConstraint("empresa_id", "cliente_id", name="uq_lecturas_horometro_idempotente"),
        sa.CheckConstraint("valor_horometro >= 0", name="valor_valido"),
    )
    op.create_index(
        "ix_lecturas_horometro_activo_captura",
        "lecturas_horometro",
        ["empresa_id", "activo_id", "capturado_en"],
    )

    # --- alertas -------------------------------------------------------------
    op.create_table(
        "alertas",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=False),
        sa.Column("reportado_por", sa.Uuid(), nullable=False),
        sa.Column("sintoma", sa.Text(), nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("estado", sa.Text(), server_default="pendiente", nullable=False),
        sa.Column("cliente_id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column(
            "capturado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.Column("revisada_por", sa.Uuid(), nullable=True),
        sa.Column("revisada_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_alertas"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_alertas_empresa_id_empresas"
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activos.empresa_id", "activos.id"],
            name="fk_alertas_activo_mismo_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id", "reportado_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_alertas_autor_mismo_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id", "revisada_por"],
            ["usuarios.empresa_id", "usuarios.id"],
            name="fk_alertas_revisor_mismo_tenant",
        ),
        sa.UniqueConstraint("empresa_id", "cliente_id", name="uq_alertas_idempotente"),
        sa.CheckConstraint(
            "sintoma IN ('ruido', 'vibracion', 'calor', 'olor', 'fuga', 'otro')",
            name="sintoma_valido",
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'revisada', 'descartada', 'convertida_en_orden')",
            name="estado_valido",
        ),
        sa.CheckConstraint("char_length(nota) <= 500", name="nota_acotada"),
    )
    op.create_index("ix_alertas_activo_fecha", "alertas", ["empresa_id", "activo_id", "fecha"])
    op.create_index(
        "ix_alertas_pendientes",
        "alertas",
        ["empresa_id", "fecha"],
        postgresql_where=sa.text("estado = 'pendiente'"),
    )

    # --- Row-Level Security --------------------------------------------------
    for tabla in TABLAS_NUEVAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{tabla} ON {tabla}"
            f" USING (empresa_id = {TENANT}) WITH CHECK (empresa_id = {TENANT})"
        )

    # --- Permisos de app_user: solo adición donde corresponde -----------------
    # ALTER DEFAULT PRIVILEGES (db/roles.sql) ya le concedió SELECT, INSERT, UPDATE y DELETE al
    # crearse cada tabla. Aquí se recorta. Nada se borra nunca: los componentes los referencian las
    # órdenes, los equipos se dan de baja, y lecturas y alertas son el historial del modelo.
    for tabla in TABLAS_NUEVAS:
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_APP}")
        op.execute(f"REVOKE DELETE ON {tabla} FROM {ROL_APP}")
    op.execute(f"GRANT UPDATE ON componentes, activos TO {ROL_APP}")
    # Una lectura no se reescribe: solo puede cambiar su marca de revisión.
    op.execute(f"REVOKE UPDATE ON lecturas_horometro FROM {ROL_APP}")
    op.execute(
        f"GRANT UPDATE (requiere_revision, motivo_revision) ON lecturas_horometro TO {ROL_APP}"
    )
    # Una alerta no se reescribe: solo cambia de estado, y queda quién y cuándo.
    op.execute(f"REVOKE UPDATE ON alertas FROM {ROL_APP}")
    op.execute(f"GRANT UPDATE (estado, revisada_por, revisada_en) ON alertas TO {ROL_APP}")

    # --- Plano de control: contar sin leer ----------------------------------
    # Permiso de COLUMNA, no de tabla: el operador puede hacer COUNT(*) agrupado por empresa, que es
    # lo que se factura, pero cualquier consulta que toque otra columna de `activos` falla.
    op.execute(f"GRANT SELECT (empresa_id, estado) ON activos TO {ROL_OPERADOR}")
    op.execute(
        f"CREATE POLICY operador_cuenta_equipos ON activos FOR SELECT TO {ROL_OPERADOR}"
        f" USING (true)"
    )
    # Plantilla inicial de componentes al dar de alta una empresa desde la consola. Solo INSERT:
    # puede sembrar el catálogo de un cliente nuevo, no leer el de ninguno.
    op.execute(f"GRANT INSERT ON componentes TO {ROL_OPERADOR}")
    op.execute(
        f"CREATE POLICY operador_siembra_componentes ON componentes FOR INSERT TO {ROL_OPERADOR}"
        f" WITH CHECK (true)"
    )


def downgrade() -> None:
    op.drop_index("ix_alertas_pendientes", table_name="alertas")
    op.drop_index("ix_alertas_activo_fecha", table_name="alertas")
    op.drop_table("alertas")
    op.drop_index("ix_lecturas_horometro_activo_captura", table_name="lecturas_horometro")
    op.drop_table("lecturas_horometro")
    op.drop_index("ix_activos_empresa_id_estado", table_name="activos")
    op.drop_table("activos")
    op.drop_table("componentes")

    # Vuelven las políticas de la fase 1 tal como eran.
    expresion = "NULLIF(current_setting('app.empresa_id', true), '')::UUID"
    op.execute("DROP POLICY tenant_isolation_usuarios ON usuarios")
    op.execute(
        f"CREATE POLICY tenant_isolation_usuarios ON usuarios USING (empresa_id = {expresion})"
    )
    op.execute("DROP POLICY tenant_isolation_empresas ON empresas")
    op.execute(f"CREATE POLICY tenant_isolation_empresas ON empresas USING (id = {expresion})")

    op.drop_constraint("uq_usuarios_empresa_id_id", "usuarios", type_="unique")
    op.drop_column("usuarios", "activo")
    op.execute("DROP FUNCTION IF EXISTS app_empresa_id()")
