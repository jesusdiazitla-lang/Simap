"""F3: órdenes de trabajo, su historial, el contador por empresa y el offset del horómetro.

Revision ID: 0007
Revises: 0006

Corresponde a la «migración 0003» de `docs/contexto/06-fase3-ordenes-de-trabajo.md` (sección 7). El
documento la escribe como `ALTER TABLE` sobre una `ordenes_trabajo` vacía; aquí la tabla nunca se
creó, así que esta revisión la **crea** ya con su forma final y la comprobación de «tabla vacía» no
hace falta.

LO QUE IMPONE LA BASE, NO EL CÓDIGO
-----------------------------------
1. **Estados coherentes** (7.3): una orden Reparada sin reparador, una Cerrada sin quien autorizó o
   una Cancelada sin motivo no se pueden guardar. Las CHECK no fijan qué estado sigue a cuál: eso lo
   hace el UPDATE condicionado del servicio.
2. **Referencias compuestas** (7.4) en las siete referencias de la orden: PostgreSQL comprueba las
   llaves foráneas ignorando RLS.
3. **Una sola orden abierta por equipo y componente, y una por alerta** (7.5): índices únicos
   parciales. Al cerrar o cancelar, el cupo queda libre.
4. **Inmutabilidad** (7.7): un trigger rechaza cualquier UPDATE de una orden cerrada o cancelada
   salvo que la transacción haya fijado `app.correccion`, que solo fija la corrección
   administrativa.
5. **Historial de solo adición** (7.8, 7.10): `app_user` no puede modificar ni borrar eventos, y
   tampoco hay política RLS que lo permita. Dos cerrojos para lo mismo.
6. **Vista con `security_invoker`** (7.9): sin la opción, la vista correría con los permisos de su
   dueño y saltaría RLS, devolviendo las fallas de todas las empresas.
7. **UPDATE por columna**: `app_user` solo puede escribir las columnas que mueven las
   transiciones y la edición; el número, la empresa, la fecha de la falla, quién la reportó y las
   horas acumuladas no se pueden reescribir ni con un error en el código.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_APP = "app_user"
TENANT = "(SELECT app_empresa_id())"
ABIERTA = "estado IN ('reportada', 'en_taller', 'reparada')"

#: Columnas de la orden que la aplicación puede modificar después de crearla: las que mueven las
#: transiciones, la edición de una orden abierta y la corrección administrativa.
COLUMNAS_ESCRIBIBLES = (
    "estado",
    "en_taller_en",
    "reparada_en",
    "reparado_por",
    "trabajo_realizado",
    "tipo_intervencion",
    "autorizado_por",
    "fecha_salida_taller",
    "tiempo_fuera_servicio_min",
    "motivo_cancelacion",
    "descripcion",
    "codigo_error",
    "temperatura",
    "componente_id",
    "requiere_revision",
    "motivo_revision",
)


def _uuid() -> sa.TextClause:
    return sa.text("gen_random_uuid()")


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _mismo_tenant(columna: str, tabla: str, nombre: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["empresa_id", columna], [f"{tabla}.empresa_id", f"{tabla}.id"], name=nombre
    )


def upgrade() -> None:
    # --- Claves candidatas que faltaban y deudas de la fase 2 (7.1) ---------
    op.create_unique_constraint("uq_alertas_empresa_id_id", "alertas", ["empresa_id", "id"])
    op.create_unique_constraint(
        "uq_lecturas_horometro_empresa_id_id", "lecturas_horometro", ["empresa_id", "id"]
    )
    op.add_column(
        "activos",
        sa.Column("horometro_offset", sa.Integer(), server_default="0", nullable=False),
    )
    # Rechaza un reinicio absurdo: un dial nuevo mayor que las horas ya acumuladas (5.1).
    op.create_check_constraint("offset_no_negativo", "activos", "horometro_offset >= 0")
    op.add_column(
        "lecturas_horometro",
        sa.Column("es_reinicio", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # --- ordenes_trabajo (7.2 a 7.4) -----------------------------------------
    op.create_table(
        "ordenes_trabajo",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        # Sin valor por defecto, a propósito: los calcula el servicio y la base exige que existan.
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("alerta_origen_id", sa.Uuid(), nullable=True),
        sa.Column("lectura_id", sa.Uuid(), nullable=True),
        sa.Column("reportado_por", sa.Uuid(), nullable=False),
        sa.Column("reparado_por", sa.Uuid(), nullable=True),
        sa.Column("autorizado_por", sa.Uuid(), nullable=True),
        # Valor del dial que vio quien reportó, y horas acumuladas (dial + offset) que usa la F4.
        sa.Column("horometro_en_falla", sa.Integer(), nullable=False),
        sa.Column("horas_acumuladas_en_falla", sa.Integer(), nullable=False),
        sa.Column("temperatura", sa.Numeric(5, 2), nullable=True),
        sa.Column("codigo_error", sa.Text(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="reportada", nullable=False),
        sa.Column("trabajo_realizado", sa.Text(), nullable=True),
        sa.Column("tipo_intervencion", sa.Text(), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column("requiere_revision", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("motivo_revision", sa.Text(), nullable=True),
        # Sin valor por defecto: viene de `capturado_en`. Un now() ocultaría a un cliente que olvidó
        # enviarla y falsearía la fecha de una falla ocurrida horas antes.
        sa.Column("fecha_falla", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reportada_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.Column("en_taller_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reparada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_salida_taller", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tiempo_fuera_servicio_min", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ordenes_trabajo"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_ordenes_trabajo_empresa_id_empresas"
        ),
        _mismo_tenant("activo_id", "activos", "fk_ordenes_trabajo_activo_mismo_tenant"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_ordenes_trabajo_componente_mismo_tenant"
        ),
        _mismo_tenant("alerta_origen_id", "alertas", "fk_ordenes_trabajo_alerta_mismo_tenant"),
        _mismo_tenant(
            "lectura_id", "lecturas_horometro", "fk_ordenes_trabajo_lectura_mismo_tenant"
        ),
        _mismo_tenant("reportado_por", "usuarios", "fk_ordenes_trabajo_reportado_mismo_tenant"),
        _mismo_tenant("reparado_por", "usuarios", "fk_ordenes_trabajo_reparado_mismo_tenant"),
        _mismo_tenant(
            "autorizado_por", "usuarios", "fk_ordenes_trabajo_autorizado_mismo_tenant"
        ),
        sa.UniqueConstraint("empresa_id", "numero", name="uq_ordenes_trabajo_numero"),
        sa.UniqueConstraint("empresa_id", "cliente_id", name="uq_ordenes_trabajo_idempotente"),
        sa.UniqueConstraint("empresa_id", "id", name="uq_ordenes_trabajo_empresa_id_id"),
        # Nombres cortos: la convención de nombres les antepone `ck_ordenes_trabajo_`.
        sa.CheckConstraint(
            "estado IN ('reportada', 'en_taller', 'reparada', 'cerrada', 'cancelada')",
            name="estado_valido",
        ),
        sa.CheckConstraint(
            "tipo_intervencion IN ('reemplazo', 'reparacion', 'ajuste')",
            name="tipo_intervencion_valido",
        ),
        sa.CheckConstraint(
            "char_length(descripcion) BETWEEN 5 AND 1000", name="descripcion_valida"
        ),
        sa.CheckConstraint("temperatura BETWEEN -100 AND 999", name="temperatura_rango"),
        sa.CheckConstraint("char_length(codigo_error) <= 50", name="codigo_error_acotado"),
        sa.CheckConstraint("horometro_en_falla >= 0", name="horometro_no_negativo"),
        sa.CheckConstraint("horas_acumuladas_en_falla >= 0", name="horas_no_negativas"),
        sa.CheckConstraint(
            "tiempo_fuera_servicio_min >= 0", name="tiempo_fuera_no_negativo"
        ),
        # Coherencia entre estado y datos: la base rechaza estados a medias.
        sa.CheckConstraint(
            "estado NOT IN ('reparada', 'cerrada') OR (reparado_por IS NOT NULL"
            " AND trabajo_realizado IS NOT NULL AND tipo_intervencion IS NOT NULL)",
            name="reparada_completa",
        ),
        sa.CheckConstraint(
            "estado <> 'cerrada' OR (autorizado_por IS NOT NULL"
            " AND fecha_salida_taller IS NOT NULL AND tiempo_fuera_servicio_min IS NOT NULL)",
            name="cierre_completo",
        ),
        sa.CheckConstraint(
            "estado <> 'cancelada' OR motivo_cancelacion IS NOT NULL",
            name="cancelada_con_motivo",
        ),
        sa.CheckConstraint(
            "NOT requiere_revision OR motivo_revision IS NOT NULL", name="revision_con_motivo"
        ),
    )
    # Una sola orden abierta por equipo y componente. Sirve también para saber si está en falla.
    op.create_index(
        "ix_ordenes_trabajo_una_abierta_por_componente",
        "ordenes_trabajo",
        ["empresa_id", "activo_id", "componente_id"],
        unique=True,
        postgresql_where=sa.text(ABIERTA),
    )
    # Una alerta origina, como máximo, una orden vigente.
    op.create_index(
        "ix_ordenes_trabajo_una_por_alerta",
        "ordenes_trabajo",
        ["empresa_id", "alerta_origen_id"],
        unique=True,
        postgresql_where=sa.text("alerta_origen_id IS NOT NULL AND estado <> 'cancelada'"),
    )
    op.create_index(
        "ix_ordenes_trabajo_activo_fecha",
        "ordenes_trabajo",
        ["empresa_id", "activo_id", sa.text("fecha_falla DESC")],
    )
    op.create_index(
        "ix_ordenes_trabajo_abiertas",
        "ordenes_trabajo",
        ["empresa_id", sa.text("fecha_falla DESC")],
        postgresql_where=sa.text(ABIERTA),
    )

    # --- Contador y eventos (7.6) ---------------------------------------------
    op.create_table(
        "ordenes_contador",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("ultimo", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("empresa_id", name="pk_ordenes_contador"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_ordenes_contador_empresa_id_empresas"
        ),
    )
    op.create_table(
        "orden_eventos",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("orden_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("estado_anterior", sa.Text(), nullable=True),
        sa.Column("estado_nuevo", sa.Text(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("rol_al_momento", sa.Text(), nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("datos", postgresql.JSONB(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_orden_eventos"),
        sa.ForeignKeyConstraint(
            ["empresa_id"], ["empresas.id"], name="fk_orden_eventos_empresa_id_empresas"
        ),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_orden_eventos_orden_mismo_tenant"),
        _mismo_tenant("usuario_id", "usuarios", "fk_orden_eventos_usuario_mismo_tenant"),
        sa.CheckConstraint(
            "tipo IN ('creada', 'transicion', 'nota', 'correccion')", name="tipo_valido"
        ),
        sa.CheckConstraint("char_length(nota) <= 1000", name="nota_acotada"),
    )
    op.create_index(
        "ix_orden_eventos_orden", "orden_eventos", ["empresa_id", "orden_id", "creado_en"]
    )

    # --- Inmutabilidad (7.7) --------------------------------------------------
    # COALESCE y la comparación con 'on': en una conexión reutilizada `current_setting` devuelve
    # cadena vacía, no NULL. `set_config(…, true)` limita la corrección a su transacción.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ot_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.estado IN ('cerrada', 'cancelada')
               AND COALESCE(current_setting('app.correccion', true), '') <> 'on' THEN
                RAISE EXCEPTION 'La orden % esta % y no se puede modificar',
                    OLD.numero, OLD.estado USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER ot_inmutable BEFORE UPDATE ON ordenes_trabajo"
        " FOR EACH ROW EXECUTE FUNCTION ot_inmutable()"
    )

    # --- Row-Level Security (7.8) ---------------------------------------------
    for tabla in ("ordenes_trabajo", "ordenes_contador", "orden_eventos"):
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
    # Las permisivas se combinan con OR: una política vieja viva ampliaría el acceso. La tabla es
    # nueva, pero se eliminan los dos nombres posibles igual que pide el documento.
    op.execute("DROP POLICY IF EXISTS tenant_isolation_ordenes ON ordenes_trabajo")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_ordenes_trabajo ON ordenes_trabajo")
    op.execute(
        f"CREATE POLICY tenant_isolation_ordenes_trabajo ON ordenes_trabajo"
        f" USING (empresa_id = {TENANT}) WITH CHECK (empresa_id = {TENANT})"
    )
    op.execute(
        f"CREATE POLICY tenant_isolation_ordenes_contador ON ordenes_contador"
        f" USING (empresa_id = {TENANT}) WITH CHECK (empresa_id = {TENANT})"
    )
    # Solo lectura e inserción: sin política de UPDATE ni DELETE, RLS los deniega aunque algún día
    # se concediera el permiso por error.
    op.execute(
        f"CREATE POLICY eventos_lectura ON orden_eventos FOR SELECT"
        f" USING (empresa_id = {TENANT})"
    )
    op.execute(
        f"CREATE POLICY eventos_insercion ON orden_eventos FOR INSERT"
        f" WITH CHECK (empresa_id = {TENANT})"
    )

    # --- Vista para la fase 4 (7.9) -------------------------------------------
    op.execute(
        """
        CREATE VIEW v_intervalos_entre_fallas WITH (security_invoker = true) AS
        SELECT empresa_id, activo_id, componente_id, id AS orden_id, numero,
               fecha_falla, tipo_intervencion, horas_acumuladas_en_falla,
               horas_acumuladas_en_falla
                 - MAX(CASE WHEN tipo_intervencion = 'reemplazo'
                            THEN horas_acumuladas_en_falla END)
                     OVER (PARTITION BY empresa_id, activo_id, componente_id
                           ORDER BY fecha_falla
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
                 AS horas_de_vida
        FROM ordenes_trabajo
        WHERE estado = 'cerrada' AND NOT requiere_revision
        """
    )

    # --- Permisos (7.10) --------------------------------------------------------
    # Explícitos: ALTER DEFAULT PRIVILEGES solo cubre lo que crea el rol que lo ejecutó.
    op.execute(f"GRANT SELECT, INSERT ON ordenes_trabajo TO {ROL_APP}")
    op.execute(f"REVOKE UPDATE, DELETE ON ordenes_trabajo FROM {ROL_APP}")
    op.execute(
        f"GRANT UPDATE ({', '.join(COLUMNAS_ESCRIBIBLES)}) ON ordenes_trabajo TO {ROL_APP}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ordenes_contador TO {ROL_APP}")
    op.execute(f"REVOKE DELETE ON ordenes_contador FROM {ROL_APP}")
    op.execute(f"GRANT SELECT, INSERT ON orden_eventos TO {ROL_APP}")
    op.execute(f"REVOKE UPDATE, DELETE ON orden_eventos FROM {ROL_APP}")
    op.execute(f"GRANT SELECT ON v_intervalos_entre_fallas TO {ROL_APP}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_intervalos_entre_fallas")
    op.drop_index("ix_orden_eventos_orden", table_name="orden_eventos")
    op.drop_table("orden_eventos")
    op.drop_table("ordenes_contador")
    op.execute("DROP TRIGGER IF EXISTS ot_inmutable ON ordenes_trabajo")
    op.execute("DROP FUNCTION IF EXISTS ot_inmutable()")
    op.drop_index("ix_ordenes_trabajo_abiertas", table_name="ordenes_trabajo")
    op.drop_index("ix_ordenes_trabajo_activo_fecha", table_name="ordenes_trabajo")
    op.drop_index("ix_ordenes_trabajo_una_por_alerta", table_name="ordenes_trabajo")
    op.drop_index("ix_ordenes_trabajo_una_abierta_por_componente", table_name="ordenes_trabajo")
    op.drop_table("ordenes_trabajo")
    op.drop_column("lecturas_horometro", "es_reinicio")
    # El CHECK del offset cae solo con la columna que comprueba.
    op.drop_column("activos", "horometro_offset")
    op.drop_constraint(
        "uq_lecturas_horometro_empresa_id_id", "lecturas_horometro", type_="unique"
    )
    op.drop_constraint("uq_alertas_empresa_id_id", "alertas", type_="unique")
