"""F4: predicción de fallas e inventario de repuestos.

Revision ID: 0009
Revises: 0008

Corresponde a la «migración 0004» de `docs/contexto/07-fase4-prediccion-e-inventario.md`
(sección 7). El contenido de cada tabla, vista, índice y trigger es el del documento; los nombres
siguen la convención del proyecto (`uq_…`, `fk_…_mismo_tenant`, `ck_<tabla>_…`, `ix_…`).

LO QUE IMPONE LA BASE, NO EL CÓDIGO
-----------------------------------
1. **Diez tablas con RLS forzada** y referencias compuestas `(empresa_id, x)`: el modelo, el riesgo,
   el inventario y el libro de una empresa no son visibles ni referenciables desde otra.
2. **Solo agregar**: `stock_movimientos` y `modelos_historial` no tienen políticas ni permisos de
   UPDATE o DELETE. El libro es la auditoría del inventario y el historial, la curva de aprendizaje.
3. **El libro refuerza el negocio**: el signo del movimiento depende de su tipo, un consumo siempre
   tiene orden y costo, un ajuste siempre lleva nota, y una orden no descuenta dos veces el mismo
   repuesto (`ix_stock_movimientos_consumo_unico`). `stock_actual` nunca es negativo.
4. **Una alerta vigente** por componente de un equipo y una por repuesto (índices únicos parciales):
   dos cálculos simultáneos nunca crean dos alertas.
5. **Las líneas de repuestos de una orden cerrada no se tocan** (trigger `orden_repuesto_inmutable`,
   con FOR SHARE para esperar a un cierre en curso).
6. **`v_vidas`** reemplaza a `v_intervalos_entre_fallas` (decisión 10): ve también las piezas que
   siguen funcionando, que son la mayor parte de los datos (censura por la derecha).
7. **Datos de la falla**: el trigger de la 0008 se amplía. Horas, dial y fecha de la falla cambian
   solo al confirmar el horómetro (las horas) o al convertir una orden predictiva en falla (6.4).

DOS ADAPTACIONES A ESTE REPOSITORIO
-----------------------------------
- `empresas` tiene FORCE ROW LEVEL SECURITY, que alcanza también a su dueño: `empresas_activas()`,
  SECURITY DEFINER propiedad de `simap_owner`, vería cero filas (el documento lo advierte en 7.10).
  Se le da a `simap_owner` una política de solo lectura sobre `empresas`. No amplía su poder: como
  dueño de las tablas ya podía desactivar RLS.
- `simap_owner` no puede crear roles. `job_user` y su pertenencia a `app_user` viven en
  `backend/db/roles.sql`; aquí solo se le concede EXECUTE sobre la función, si el rol existe.

Los rellenos leen tablas con FORCE ROW LEVEL SECURITY: se levanta mientras duran, en la misma
transacción, como en la 0008. Sin eso insertarían cero filas sin ningún error.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_APP = "app_user"
ROL_JOB = "job_user"
ROL_DUENO = "simap_owner"
TENANT = "(SELECT app_empresa_id())"
COMPONENTE_POR_IDENTIFICAR = "Otro (por identificar)"

#: Tablas con la política habitual de aislamiento.
ORDINARIAS = (
    "configuracion_empresa",
    "repuestos",
    "orden_repuesto",
    "activo_componentes",
    "alertas_sistema",
    "modelos_componente",
    "reajustes_pendientes",
    "riesgos",
)
#: Tablas que solo se agregan: políticas de SELECT e INSERT, ninguna de UPDATE ni DELETE.
SOLO_AGREGAR = ("stock_movimientos", "modelos_historial")


def _uuid() -> sa.TextClause:
    return sa.text("gen_random_uuid()")


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _empresa(tabla: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["empresa_id"], ["empresas.id"], name=f"fk_{tabla}_empresa_id_empresas"
    )


def _mismo_tenant(columna: str, tabla: str, nombre: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["empresa_id", columna], [f"{tabla}.empresa_id", f"{tabla}.id"], name=nombre
    )


V_VIDAS = """
CREATE VIEW v_vidas WITH (security_invoker = true) AS
WITH ev AS NOT MATERIALIZED (
    SELECT o.empresa_id, o.activo_id, o.componente_id,
           o.horas_acumuladas_en_falla::double precision AS horas,
           (o.tipo_intervencion = 'reemplazo') AS renueva,
           o.es_predictiva,
           count(*) FILTER (WHERE o.tipo_intervencion = 'reemplazo') OVER w AS vida,
           (max(o.horas_acumuladas_en_falla)
               FILTER (WHERE o.tipo_intervencion = 'reemplazo') OVER w)::double precision
               AS reemplazo_previo
    FROM ordenes_trabajo o
    WHERE o.estado = 'cerrada' AND NOT o.requiere_revision
    WINDOW w AS (PARTITION BY o.empresa_id, o.activo_id, o.componente_id
                 ORDER BY o.fecha_falla, o.numero
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
), ev2 AS NOT MATERIALIZED (
    SELECT ev.*, COALESCE(ev.reemplazo_previo,
                          ac.horas_instalacion_inicial::double precision) AS inicio
    FROM ev
    LEFT JOIN activo_componentes ac
           ON ac.empresa_id = ev.empresa_id AND ac.activo_id = ev.activo_id
          AND ac.componente_id = ev.componente_id
), cerradas AS (
    SELECT empresa_id, activo_id, componente_id, vida::int AS vida,
           false AS abierta, inicio,
           (count(*) FILTER (WHERE NOT es_predictiva))::int AS n_eventos,
           CASE WHEN inicio IS NULL THEN NULL
                ELSE COALESCE(sum(ln(greatest(horas - inicio, 0.5)))
                              FILTER (WHERE NOT es_predictiva), 0) END AS suma_ln_edades,
           max(horas) FILTER (WHERE renueva) - inicio AS exposicion
    FROM ev2
    GROUP BY empresa_id, activo_id, componente_id, vida, inicio
    HAVING bool_or(renueva)
), abiertas AS (
    SELECT ac.empresa_id, ac.activo_id, ac.componente_id,
           COALESCE(r.n_reemplazos, 0)::int AS vida,
           true AS abierta, i.inicio,
           COALESCE(e.n_eventos, 0)::int AS n_eventos,
           CASE WHEN i.inicio IS NULL THEN NULL ELSE COALESCE(e.suma, 0) END AS suma_ln_edades,
           CASE WHEN i.inicio IS NULL THEN NULL
                ELSE greatest((a.horometro_offset + a.horometro_actual)::double precision
                              - i.inicio, COALESCE(e.edad_max, 0), 0) END AS exposicion
    FROM activo_componentes ac
    JOIN activos a ON a.empresa_id = ac.empresa_id AND a.id = ac.activo_id
    LEFT JOIN LATERAL (
        SELECT count(*) AS n_reemplazos, max(ev.horas) AS ultimo
        FROM ev
        WHERE ev.empresa_id = ac.empresa_id AND ev.activo_id = ac.activo_id
          AND ev.componente_id = ac.componente_id AND ev.renueva) r ON true
    CROSS JOIN LATERAL (
        SELECT COALESCE(r.ultimo, ac.horas_instalacion_inicial::double precision) AS inicio) i
    LEFT JOIN LATERAL (
        SELECT (count(*) FILTER (WHERE NOT ev2.es_predictiva)) AS n_eventos,
               sum(ln(greatest(ev2.horas - i.inicio, 0.5)))
                   FILTER (WHERE NOT ev2.es_predictiva) AS suma,
               max(ev2.horas - i.inicio) AS edad_max
        FROM ev2
        WHERE ev2.empresa_id = ac.empresa_id AND ev2.activo_id = ac.activo_id
          AND ev2.componente_id = ac.componente_id
          AND ev2.vida = COALESCE(r.n_reemplazos, 0)) e ON true
)
SELECT * FROM cerradas
UNION ALL
SELECT * FROM abiertas
"""

V_RIESGO_ACTIVO = """
CREATE VIEW v_riesgo_activo WITH (security_invoker = true) AS
SELECT DISTINCT ON (empresa_id, activo_id)
       empresa_id, activo_id, componente_id AS componente_critico,
       riesgo, confianza, fuente, calculado_en
FROM riesgos
WHERE estado_calculo = 'ok'
ORDER BY empresa_id, activo_id, riesgo DESC, componente_id
"""

V_INTERVALOS_ENTRE_FALLAS = """
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

DATOS_DE_FALLA = """
CREATE OR REPLACE FUNCTION ot_datos_de_falla() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    confirma boolean := OLD.requiere_revision AND NOT NEW.requiere_revision;
    convierte boolean := OLD.es_predictiva AND NOT NEW.es_predictiva;
BEGIN
    IF NEW.horas_acumuladas_en_falla IS DISTINCT FROM OLD.horas_acumuladas_en_falla
       AND NOT (confirma OR convierte) THEN
        RAISE EXCEPTION 'Las horas de la orden % solo cambian al confirmar su horometro'
            ' o al convertirla en falla', OLD.numero USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.horometro_en_falla IS DISTINCT FROM OLD.horometro_en_falla
        OR NEW.fecha_falla IS DISTINCT FROM OLD.fecha_falla) AND NOT convierte THEN
        RAISE EXCEPTION 'El horometro y la fecha de la orden % solo cambian al convertirla'
            ' en falla', OLD.numero USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$
"""

HORAS_SOLO_AL_CONFIRMAR = """
CREATE OR REPLACE FUNCTION ot_horas_solo_al_confirmar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.horas_acumuladas_en_falla IS DISTINCT FROM OLD.horas_acumuladas_en_falla
       AND NOT (OLD.requiere_revision AND NOT NEW.requiere_revision) THEN
        RAISE EXCEPTION 'Las horas de la orden % solo cambian al confirmar su horometro',
            OLD.numero USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$
"""

ORDEN_REPUESTO_INMUTABLE = """
CREATE OR REPLACE FUNCTION orden_repuesto_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_estado TEXT;
    v_orden UUID;
    v_emp UUID;
BEGIN
    v_orden := CASE WHEN TG_OP = 'DELETE' THEN OLD.orden_id ELSE NEW.orden_id END;
    v_emp := CASE WHEN TG_OP = 'DELETE' THEN OLD.empresa_id ELSE NEW.empresa_id END;
    SELECT estado INTO v_estado FROM ordenes_trabajo
     WHERE empresa_id = v_emp AND id = v_orden FOR SHARE;
    IF v_estado IN ('cerrada', 'cancelada')
       AND COALESCE(current_setting('app.correccion', true), '') <> 'on' THEN
        RAISE EXCEPTION 'La orden esta % y sus repuestos no se pueden modificar', v_estado
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END
$$
"""


def _crear_tablas() -> None:
    # --- 7.1 Configuración por empresa y vida nominal ---------------------------
    op.add_column("componentes", sa.Column("vida_nominal_horas", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "vida_nominal_rango", "componentes", "vida_nominal_horas BETWEEN 10 AND 1000000"
    )
    op.create_table(
        "configuracion_empresa",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("umbral_riesgo", sa.Numeric(4, 3), server_default="0.250", nullable=False),
        sa.Column("horizonte_horas", sa.Integer(), server_default="50", nullable=False),
        sa.Column("alertas_minimas", sa.Integer(), server_default="2", nullable=False),
        sa.Column("ventana_alertas_dias", sa.Integer(), server_default="15", nullable=False),
        sa.Column("multiplicador_alertas", sa.Numeric(3, 2), server_default="1.30", nullable=False),
        sa.Column("descarte_silencio_dias", sa.Integer(), server_default="7", nullable=False),
        sa.PrimaryKeyConstraint("empresa_id", name="pk_configuracion_empresa"),
        _empresa("configuracion_empresa"),
        sa.CheckConstraint("umbral_riesgo BETWEEN 0.05 AND 0.95", name="umbral_rango"),
        sa.CheckConstraint("horizonte_horas BETWEEN 1 AND 2000", name="horizonte_rango"),
        sa.CheckConstraint("alertas_minimas BETWEEN 1 AND 20", name="alertas_minimas_rango"),
        sa.CheckConstraint("ventana_alertas_dias BETWEEN 1 AND 90", name="ventana_rango"),
        sa.CheckConstraint(
            "multiplicador_alertas BETWEEN 1.00 AND 2.00", name="multiplicador_rango"
        ),
        sa.CheckConstraint("descarte_silencio_dias BETWEEN 1 AND 90", name="silencio_rango"),
    )

    # --- 7.2 Inventario ------------------------------------------------------------
    op.create_table(
        "repuestos",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("stock_actual", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stock_minimo", sa.Integer(), server_default="0", nullable=False),
        sa.Column("costo_unitario", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_repuestos"),
        _empresa("repuestos"),
        sa.UniqueConstraint("empresa_id", "codigo", name="uq_repuestos_codigo"),
        sa.UniqueConstraint("empresa_id", "id", name="uq_repuestos_empresa_id_id"),
        sa.CheckConstraint("char_length(nombre) BETWEEN 2 AND 120", name="nombre_valido"),
        sa.CheckConstraint("char_length(codigo) BETWEEN 1 AND 60", name="codigo_valido"),
        sa.CheckConstraint("stock_actual >= 0", name="stock_no_negativo"),
        sa.CheckConstraint("stock_minimo >= 0", name="minimo_no_negativo"),
        sa.CheckConstraint("costo_unitario >= 0", name="costo_no_negativo"),
    )
    op.create_table(
        "stock_movimientos",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("repuesto_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("stock_resultante", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(12, 2), nullable=True),
        sa.Column("orden_id", sa.Uuid(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movimientos"),
        _empresa("stock_movimientos"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_stock_movimientos_repuesto_mismo_tenant"),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_stock_movimientos_orden_mismo_tenant"),
        _mismo_tenant("usuario_id", "usuarios", "fk_stock_movimientos_usuario_mismo_tenant"),
        sa.CheckConstraint(
            "tipo IN ('inicial', 'ingreso', 'consumo', 'ajuste')", name="tipo_valido"
        ),
        sa.CheckConstraint(
            "delta <> 0 AND delta BETWEEN -1000000 AND 1000000", name="delta_valido"
        ),
        sa.CheckConstraint("stock_resultante >= 0", name="resultante_no_negativo"),
        sa.CheckConstraint("costo_unitario >= 0", name="costo_no_negativo"),
        sa.CheckConstraint("char_length(nota) <= 500", name="nota_acotada"),
        sa.CheckConstraint(
            "(tipo IN ('inicial', 'ingreso') AND delta > 0) OR (tipo = 'consumo' AND delta < 0)"
            " OR tipo = 'ajuste'",
            name="signo",
        ),
        sa.CheckConstraint("(tipo = 'consumo') = (orden_id IS NOT NULL)", name="consumo_con_orden"),
        sa.CheckConstraint(
            "tipo <> 'consumo' OR costo_unitario IS NOT NULL", name="consumo_con_costo"
        ),
        sa.CheckConstraint("tipo <> 'ajuste' OR nota IS NOT NULL", name="ajuste_con_nota"),
    )
    # Una orden descuenta cada repuesto una sola vez, aunque el código se ejecute dos veces.
    op.create_index(
        "ix_stock_movimientos_consumo_unico",
        "stock_movimientos",
        ["empresa_id", "orden_id", "repuesto_id"],
        unique=True,
        postgresql_where=sa.text("tipo = 'consumo'"),
    )
    op.create_index(
        "ix_stock_movimientos_repuesto",
        "stock_movimientos",
        ["empresa_id", "repuesto_id", sa.text("creado_en DESC")],
    )
    op.create_table(
        "orden_repuesto",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("orden_id", sa.Uuid(), nullable=False),
        sa.Column("repuesto_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("registrado_por", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("empresa_id", "orden_id", "repuesto_id", name="pk_orden_repuesto"),
        _empresa("orden_repuesto"),
        _mismo_tenant("orden_id", "ordenes_trabajo", "fk_orden_repuesto_orden_mismo_tenant"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_orden_repuesto_repuesto_mismo_tenant"),
        _mismo_tenant("registrado_por", "usuarios", "fk_orden_repuesto_usuario_mismo_tenant"),
        sa.CheckConstraint("cantidad BETWEEN 1 AND 10000", name="cantidad_valida"),
    )
    op.create_index("ix_orden_repuesto_repuesto", "orden_repuesto", ["empresa_id", "repuesto_id"])

    # --- 7.3 Componentes de cada equipo -----------------------------------------------
    op.create_table(
        "activo_componentes",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        # NULL = edad desconocida: sin riesgo hasta el primer reemplazo (decisión 7).
        sa.Column("horas_instalacion_inicial", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint(
            "empresa_id", "activo_id", "componente_id", name="pk_activo_componentes"
        ),
        _empresa("activo_componentes"),
        _mismo_tenant("activo_id", "activos", "fk_activo_componentes_activo_mismo_tenant"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_activo_componentes_componente_mismo_tenant"
        ),
        sa.CheckConstraint("horas_instalacion_inicial >= 0", name="horas_instalacion_validas"),
    )

    # --- 7.4 Alertas del sistema ---------------------------------------------------------
    op.create_table(
        "alertas_sistema",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=True),
        sa.Column("componente_id", sa.Uuid(), nullable=True),
        sa.Column("repuesto_id", sa.Uuid(), nullable=True),
        sa.Column("riesgo", sa.Numeric(6, 5), nullable=True),
        sa.Column("umbral", sa.Numeric(4, 3), nullable=True),
        sa.Column("confianza", sa.Text(), nullable=True),
        sa.Column("fuente", sa.Text(), nullable=True),
        sa.Column("stock_al_alertar", sa.Integer(), nullable=True),
        sa.Column("stock_minimo_al_alertar", sa.Integer(), nullable=True),
        sa.Column("estado", sa.Text(), server_default="activa", nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False),
        sa.Column("gestionada_por", sa.Uuid(), nullable=True),
        sa.Column("gestionada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_alertas_sistema"),
        _empresa("alertas_sistema"),
        sa.UniqueConstraint("empresa_id", "id", name="uq_alertas_sistema_empresa_id_id"),
        _mismo_tenant("activo_id", "activos", "fk_alertas_sistema_activo_mismo_tenant"),
        _mismo_tenant("componente_id", "componentes", "fk_alertas_sistema_componente_mismo_tenant"),
        _mismo_tenant("repuesto_id", "repuestos", "fk_alertas_sistema_repuesto_mismo_tenant"),
        _mismo_tenant("gestionada_por", "usuarios", "fk_alertas_sistema_gestor_mismo_tenant"),
        sa.CheckConstraint("tipo IN ('riesgo', 'reorden')", name="tipo_valido"),
        sa.CheckConstraint("confianza IN ('baja', 'media', 'alta')", name="confianza_valida"),
        sa.CheckConstraint("fuente IN ('previo', 'mixto', 'empresa')", name="fuente_valida"),
        sa.CheckConstraint(
            "estado IN ('activa', 'reconocida', 'atendida', 'resuelta', 'descartada')",
            name="estado_valido",
        ),
        sa.CheckConstraint("char_length(nota) <= 500", name="nota_acotada"),
        sa.CheckConstraint(
            "(tipo = 'riesgo' AND activo_id IS NOT NULL AND componente_id IS NOT NULL"
            " AND repuesto_id IS NULL AND riesgo IS NOT NULL AND umbral IS NOT NULL)"
            " OR (tipo = 'reorden' AND repuesto_id IS NOT NULL AND activo_id IS NULL"
            " AND componente_id IS NULL AND stock_al_alertar IS NOT NULL)",
            name="forma_por_tipo",
        ),
        sa.CheckConstraint(
            "estado <> 'descartada' OR nota IS NOT NULL", name="descartada_con_nota"
        ),
    )
    op.create_index(
        "ix_alertas_sistema_riesgo_vigente",
        "alertas_sistema",
        ["empresa_id", "activo_id", "componente_id"],
        unique=True,
        postgresql_where=sa.text(
            "tipo = 'riesgo' AND estado IN ('activa', 'reconocida', 'atendida')"
        ),
    )
    op.create_index(
        "ix_alertas_sistema_reorden_vigente",
        "alertas_sistema",
        ["empresa_id", "repuesto_id"],
        unique=True,
        postgresql_where=sa.text("tipo = 'reorden' AND estado IN ('activa', 'reconocida')"),
    )
    op.create_index(
        "ix_alertas_sistema_bandeja",
        "alertas_sistema",
        ["empresa_id", sa.text("creada_en DESC")],
        postgresql_where=sa.text("estado IN ('activa', 'reconocida', 'atendida')"),
    )

    # --- 7.5 Órdenes predictivas -------------------------------------------------------
    op.add_column(
        "ordenes_trabajo",
        sa.Column("es_predictiva", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("ordenes_trabajo", sa.Column("alerta_sistema_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_ordenes_trabajo_alerta_sistema_mismo_tenant",
        "ordenes_trabajo",
        "alertas_sistema",
        ["empresa_id", "alerta_sistema_id"],
        ["empresa_id", "id"],
    )
    op.create_index(
        "ix_ordenes_trabajo_una_por_alerta_sistema",
        "ordenes_trabajo",
        ["empresa_id", "alerta_sistema_id"],
        unique=True,
        postgresql_where=sa.text("alerta_sistema_id IS NOT NULL AND estado <> 'cancelada'"),
    )
    # Apoya la ventana de v_vidas: misma partición y orden, solo órdenes cerradas y confirmadas.
    op.create_index(
        "ix_ordenes_trabajo_cerradas_vida",
        "ordenes_trabajo",
        ["empresa_id", "activo_id", "componente_id", "fecha_falla", "numero"],
        postgresql_where=sa.text("estado = 'cerrada' AND NOT requiere_revision"),
    )

    # --- 7.6 Modelo, historial, marcas y riesgos ---------------------------------------
    op.create_table(
        "modelos_componente",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("beta", sa.Double(), nullable=False),
        sa.Column("eta", sa.Double(), nullable=False),
        sa.Column("n_eventos", sa.Integer(), nullable=False),
        sa.Column("n_vidas", sa.Integer(), nullable=False),
        sa.Column("exposicion_horas", sa.Double(), nullable=False),
        sa.Column("fuente", sa.Text(), nullable=False),
        sa.Column("confianza", sa.Text(), nullable=False),
        sa.Column("convergio", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "ajustado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.PrimaryKeyConstraint("empresa_id", "componente_id", name="pk_modelos_componente"),
        _empresa("modelos_componente"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_modelos_componente_componente_mismo_tenant"
        ),
        sa.CheckConstraint("beta BETWEEN 0.3 AND 10", name="beta_rango"),
        sa.CheckConstraint("eta > 0", name="eta_positiva"),
        sa.CheckConstraint("n_eventos >= 0", name="eventos_no_negativos"),
        sa.CheckConstraint("n_vidas >= 0", name="vidas_no_negativas"),
        sa.CheckConstraint("exposicion_horas >= 0", name="exposicion_no_negativa"),
        sa.CheckConstraint("fuente IN ('previo', 'mixto', 'empresa')", name="fuente_valida"),
        sa.CheckConstraint("confianza IN ('baja', 'media', 'alta')", name="confianza_valida"),
    )
    op.create_table(
        "modelos_historial",
        sa.Column("id", sa.Uuid(), server_default=_uuid(), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("beta", sa.Double(), nullable=False),
        sa.Column("eta", sa.Double(), nullable=False),
        sa.Column("n_eventos", sa.Integer(), nullable=False),
        sa.Column("fuente", sa.Text(), nullable=False),
        sa.Column("confianza", sa.Text(), nullable=False),
        sa.Column(
            "ajustado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_modelos_historial"),
        _empresa("modelos_historial"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_modelos_historial_componente_mismo_tenant"
        ),
    )
    op.create_index(
        "ix_modelos_historial_componente",
        "modelos_historial",
        ["empresa_id", "componente_id", "ajustado_en"],
    )
    op.create_table(
        "reajustes_pendientes",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("generacion", sa.BigInteger(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("empresa_id", "componente_id", name="pk_reajustes_pendientes"),
        _empresa("reajustes_pendientes"),
        _mismo_tenant(
            "componente_id", "componentes", "fk_reajustes_pendientes_componente_mismo_tenant"
        ),
    )
    op.create_table(
        "riesgos",
        sa.Column("empresa_id", sa.Uuid(), nullable=False),
        sa.Column("activo_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("estado_calculo", sa.Text(), nullable=False),
        sa.Column("edad_horas", sa.Double(), nullable=True),
        sa.Column("horizonte_horas", sa.Integer(), nullable=True),
        sa.Column("beta", sa.Double(), nullable=True),
        sa.Column("eta", sa.Double(), nullable=True),
        sa.Column("riesgo_base", sa.Numeric(6, 5), nullable=True),
        sa.Column("multiplicador", sa.Numeric(3, 2), nullable=True),
        sa.Column("riesgo", sa.Numeric(6, 5), nullable=True),
        sa.Column("n_eventos", sa.Integer(), nullable=True),
        sa.Column("fuente", sa.Text(), nullable=True),
        sa.Column("confianza", sa.Text(), nullable=True),
        sa.Column(
            "calculado_en", sa.DateTime(timezone=True), server_default=_ahora(), nullable=False
        ),
        sa.PrimaryKeyConstraint("empresa_id", "activo_id", "componente_id", name="pk_riesgos"),
        _empresa("riesgos"),
        sa.ForeignKeyConstraint(
            ["empresa_id", "activo_id", "componente_id"],
            [
                "activo_componentes.empresa_id",
                "activo_componentes.activo_id",
                "activo_componentes.componente_id",
            ],
            name="fk_riesgos_par_registrado",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "estado_calculo IN ('ok', 'sin_edad', 'sin_modelo')", name="estado_calculo_valido"
        ),
        sa.CheckConstraint(
            "estado_calculo <> 'ok' OR (riesgo IS NOT NULL AND riesgo_base IS NOT NULL"
            " AND edad_horas IS NOT NULL AND beta IS NOT NULL AND eta IS NOT NULL"
            " AND horizonte_horas IS NOT NULL)",
            name="ok_completo",
        ),
    )
    op.create_index(
        "ix_riesgos_altos",
        "riesgos",
        ["empresa_id", sa.text("riesgo DESC")],
        postgresql_where=sa.text("estado_calculo = 'ok'"),
    )


def _rellenar() -> None:
    """Rellenos de 7.1, 7.3 y 7.6. Leen tablas con FORCE RLS: se levanta mientras duran."""
    leidas = ("empresas", "ordenes_trabajo", "componentes")
    for tabla in leidas:
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
    op.execute("INSERT INTO configuracion_empresa (empresa_id) SELECT id FROM empresas")
    # Los pares que ya tienen órdenes quedan registrados, con edad desconocida. El componente
    # comodín no se registra: la fase 4 no ajusta modelo con él (F3, 6.2).
    op.execute(
        f"""
        INSERT INTO activo_componentes (empresa_id, activo_id, componente_id)
        SELECT DISTINCT o.empresa_id, o.activo_id, o.componente_id
        FROM ordenes_trabajo o
        JOIN componentes c ON c.empresa_id = o.empresa_id AND c.id = o.componente_id
        WHERE c.nombre <> '{COMPONENTE_POR_IDENTIFICAR}'
        """
    )
    op.execute(
        f"""
        INSERT INTO reajustes_pendientes (empresa_id, componente_id)
        SELECT DISTINCT o.empresa_id, o.componente_id
        FROM ordenes_trabajo o
        JOIN componentes c ON c.empresa_id = o.empresa_id AND c.id = o.componente_id
        WHERE o.estado = 'cerrada' AND c.nombre <> '{COMPONENTE_POR_IDENTIFICAR}'
        """
    )
    for tabla in leidas:
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")


def _seguridad() -> None:
    # --- 7.9 Row-Level Security ----------------------------------------------------
    for tabla in ORDINARIAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{tabla} ON {tabla}"
            f" USING (empresa_id = {TENANT}) WITH CHECK (empresa_id = {TENANT})"
        )
    for tabla in SOLO_AGREGAR:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tabla}_lectura ON {tabla} FOR SELECT USING (empresa_id = {TENANT})"
        )
        op.execute(
            f"CREATE POLICY {tabla}_insercion ON {tabla} FOR INSERT"
            f" WITH CHECK (empresa_id = {TENANT})"
        )

    # --- 7.10 Función del job nocturno -----------------------------------------------
    # Ver la nota del docstring: sin esta política el dueño ve cero empresas por FORCE RLS.
    op.execute(
        f"CREATE POLICY empresas_lista_para_el_job ON empresas FOR SELECT TO {ROL_DUENO}"
        " USING (true)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION empresas_activas() RETURNS SETOF uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$ SELECT id FROM empresas ORDER BY id $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION empresas_activas() FROM PUBLIC")
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_JOB}') THEN
                GRANT EXECUTE ON FUNCTION empresas_activas() TO {ROL_JOB};
            END IF;
        END $$
        """
    )

    # --- Permisos explícitos (7.10) -------------------------------------------------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON modelos_componente TO {ROL_APP}")
    op.execute(f"REVOKE DELETE ON modelos_componente FROM {ROL_APP}")
    op.execute(f"GRANT SELECT, INSERT ON modelos_historial TO {ROL_APP}")
    op.execute(f"GRANT SELECT, INSERT ON stock_movimientos TO {ROL_APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON reajustes_pendientes TO {ROL_APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON riesgos TO {ROL_APP}")
    op.execute(f"GRANT SELECT ON v_vidas, v_riesgo_activo TO {ROL_APP}")
    op.execute(f"REVOKE DELETE ON repuestos FROM {ROL_APP}")
    op.execute(f"REVOKE DELETE ON alertas_sistema FROM {ROL_APP}")
    op.execute(f"REVOKE DELETE ON configuracion_empresa FROM {ROL_APP}")
    op.execute(f"REVOKE UPDATE, DELETE ON stock_movimientos FROM {ROL_APP}")
    op.execute(f"REVOKE UPDATE, DELETE ON modelos_historial FROM {ROL_APP}")
    # La conversión en falla (6.4) reescribe estas columnas; el trigger ot_datos_de_falla decide
    # cuándo. alerta_sistema_id no se modifica nunca después de crear la orden.
    op.execute(
        f"GRANT UPDATE (es_predictiva, horometro_en_falla, fecha_falla) ON ordenes_trabajo"
        f" TO {ROL_APP}"
    )


def upgrade() -> None:
    _crear_tablas()
    _rellenar()

    # La vista de la fase 3 queda reemplazada por v_vidas (decisión 10).
    op.execute("DROP VIEW v_intervalos_entre_fallas")
    op.execute(V_VIDAS)
    op.execute(V_RIESGO_ACTIVO)

    # Datos de la falla: amplía el trigger de la 0008 a la conversión en falla.
    op.execute("DROP TRIGGER ot_horas_solo_al_confirmar ON ordenes_trabajo")
    op.execute("DROP FUNCTION ot_horas_solo_al_confirmar()")
    op.execute(DATOS_DE_FALLA)
    op.execute(
        "CREATE TRIGGER ot_datos_de_falla BEFORE UPDATE OF horas_acumuladas_en_falla,"
        " horometro_en_falla, fecha_falla ON ordenes_trabajo"
        " FOR EACH ROW EXECUTE FUNCTION ot_datos_de_falla()"
    )

    # 7.8: las líneas de una orden cerrada o cancelada no se tocan.
    op.execute(ORDEN_REPUESTO_INMUTABLE)
    op.execute(
        "CREATE TRIGGER orden_repuesto_inmutable BEFORE INSERT OR UPDATE OR DELETE"
        " ON orden_repuesto FOR EACH ROW EXECUTE FUNCTION orden_repuesto_inmutable()"
    )

    _seguridad()


def downgrade() -> None:
    op.execute(
        f"REVOKE UPDATE (es_predictiva, horometro_en_falla, fecha_falla) ON ordenes_trabajo"
        f" FROM {ROL_APP}"
    )
    op.execute("DROP FUNCTION IF EXISTS empresas_activas()")
    op.execute("DROP POLICY IF EXISTS empresas_lista_para_el_job ON empresas")
    op.execute("DROP VIEW IF EXISTS v_riesgo_activo")
    op.execute("DROP VIEW IF EXISTS v_vidas")
    op.execute(V_INTERVALOS_ENTRE_FALLAS)
    op.execute(f"GRANT SELECT ON v_intervalos_entre_fallas TO {ROL_APP}")

    op.execute("DROP TRIGGER IF EXISTS ot_datos_de_falla ON ordenes_trabajo")
    op.execute("DROP FUNCTION IF EXISTS ot_datos_de_falla()")
    op.execute(HORAS_SOLO_AL_CONFIRMAR)
    op.execute(
        "CREATE TRIGGER ot_horas_solo_al_confirmar BEFORE UPDATE OF horas_acumuladas_en_falla"
        " ON ordenes_trabajo FOR EACH ROW EXECUTE FUNCTION ot_horas_solo_al_confirmar()"
    )

    op.drop_table("riesgos")
    op.drop_table("reajustes_pendientes")
    op.drop_table("modelos_historial")
    op.drop_table("modelos_componente")
    op.drop_index("ix_ordenes_trabajo_cerradas_vida", table_name="ordenes_trabajo")
    op.drop_index("ix_ordenes_trabajo_una_por_alerta_sistema", table_name="ordenes_trabajo")
    op.drop_constraint(
        "fk_ordenes_trabajo_alerta_sistema_mismo_tenant", "ordenes_trabajo", type_="foreignkey"
    )
    op.drop_column("ordenes_trabajo", "alerta_sistema_id")
    op.drop_column("ordenes_trabajo", "es_predictiva")
    op.drop_table("alertas_sistema")
    op.drop_table("activo_componentes")
    op.execute("DROP TRIGGER IF EXISTS orden_repuesto_inmutable ON orden_repuesto")
    op.execute("DROP FUNCTION IF EXISTS orden_repuesto_inmutable()")
    op.drop_table("orden_repuesto")
    op.drop_table("stock_movimientos")
    op.drop_table("repuestos")
    op.drop_table("configuracion_empresa")
    # El CHECK de la vida nominal cae solo con la columna.
    op.drop_column("componentes", "vida_nominal_horas")
