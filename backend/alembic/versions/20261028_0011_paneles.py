"""F5: paneles e indicadores (desde cuándo se observa cada equipo, horas por lectura, paradas).

Revision ID: 0011
Revises: 0010

Corresponde a la «migración 0005» de `docs/contexto/08-fase5-dashboard-y-cierre.md` (sección 6). No
crea tablas: agrega una columna con su trigger, rellena dos, crea seis índices y una vista, y quita
permisos de escritura a las vistas.

LO QUE CAMBIA RESPECTO DEL PDF
------------------------------
1. **`activos.creado_en` ya existía** (fase 2, con `now()` por defecto). Solo se rellena: el primer
   dato conocido de cada equipo (lectura u orden) si es anterior (decisión 8).
2. **Qué lectura es válida.** En el PDF, `NOT requiere_revision`. Aquí una lectura marcada que un
   supervisor confirmó o registró como reinicio conserva la marca y lleva `resolucion`
   (`_cuenta_como_valida` en `app.services.lecturas`): esas también aportan horas.
3. **El offset de su momento.** El PDF deja sin horas una lectura confirmada después de un reinicio
   posterior a su captura, porque no puede ubicarla. Aquí cada reinicio guarda el offset que deja
   (`offset_resultante`, revisión 0008), así que la lectura se ubica con el offset vigente en su
   `capturado_en`, igual que `activos.offset_en`. Solo un reinicio anterior a la 0008 sin offset
   reconstruible deja la lectura sin horas.
4. **JIT.** `ALTER ROLE ... SET jit = off` exige ser superusuario o tener CREATEROLE, y la migración
   corre como `simap_owner`, que no lo es. Se aplica en `backend/db/roles.sql`; aquí se intenta y,
   si no hay permiso, solo se avisa. La prueba de la migración comprueba `pg_roles.rolconfig`.
5. Los rellenos desactivan `FORCE ROW LEVEL SECURITY` mientras corren (como la 0008 y la 0009): el
   dueño también está sujeto a RLS forzada y sin empresa fijada no vería ninguna fila.
"""

from __future__ import annotations

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None

ROL_APP = "app_user"

#: Válida = no marcada, o marcada y resuelta como confirmada o reinicio (`_cuenta_como_valida`).
#: Los COALESCE no son adorno: con `resolucion` nula, `resolucion IN (...)` es NULL, `NOT valida`
#: también, y un `IF NOT NULL` no entra: una lectura marcada recibía horas (lo encontró la prueba
#: `test_horas_acumuladas_las_mantiene_el_trigger`).
VALIDA = (
    "(NOT {t}.requiere_revision OR COALESCE({t}.resolucion IN ('confirmada', 'reinicio'), false))"
)
REINICIO = "({t}.es_reinicio OR COALESCE({t}.resolucion = 'reinicio', false))"

HORAS_ACUMULADAS = f"""
CREATE OR REPLACE FUNCTION lectura_horas_acumuladas() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_offset integer;
BEGIN
    -- Una lectura dudosa (pendiente o descartada) no suma horas a ningún indicador.
    IF NOT {VALIDA.format(t="NEW")} THEN
        NEW.horas_acumuladas := NULL;
        RETURN NEW;
    END IF;
    -- Un UPDATE que no la vuelve válida ni cambia el offset de un reinicio no recalcula nada.
    IF TG_OP = 'UPDATE' AND {VALIDA.format(t="OLD")}
       AND NEW.offset_resultante IS NOT DISTINCT FROM OLD.offset_resultante THEN
        RETURN NEW;
    END IF;
    IF {REINICIO.format(t="NEW")} THEN
        -- La lectura del reinicio ya está en la escala nueva: su propio offset.
        v_offset := NEW.offset_resultante;
    ELSE
        -- El offset vigente en su captura: el del último reinicio anterior, o 0 si no hubo.
        SELECT r.offset_resultante INTO v_offset
          FROM lecturas_horometro r
         WHERE r.empresa_id = NEW.empresa_id AND r.activo_id = NEW.activo_id
           AND {REINICIO.format(t="r")} AND r.capturado_en <= NEW.capturado_en
           AND r.id <> NEW.id
         ORDER BY r.capturado_en DESC, r.id DESC
         LIMIT 1;
        IF NOT FOUND THEN
            v_offset := 0;
        END IF;
    END IF;
    -- Un reinicio anterior a la 0008 sin offset reconstruible: mejor sin horas que inventadas.
    NEW.horas_acumuladas := CASE WHEN v_offset IS NULL THEN NULL
                                ELSE v_offset + NEW.valor_horometro END;
    RETURN NEW;
END
$$
"""

RELLENO_HORAS = f"""
UPDATE lecturas_horometro l
   SET horas_acumuladas = CASE
         WHEN {REINICIO.format(t="l")} THEN l.offset_resultante + l.valor_horometro
         ELSE COALESCE(
                (SELECT r.offset_resultante FROM lecturas_horometro r
                  WHERE r.empresa_id = l.empresa_id AND r.activo_id = l.activo_id
                    AND {REINICIO.format(t="r")} AND r.capturado_en <= l.capturado_en
                    AND r.id <> l.id
                  ORDER BY r.capturado_en DESC, r.id DESC LIMIT 1),
                CASE WHEN EXISTS (
                    SELECT 1 FROM lecturas_horometro r
                     WHERE r.empresa_id = l.empresa_id AND r.activo_id = l.activo_id
                       AND {REINICIO.format(t="r")} AND r.capturado_en <= l.capturado_en
                       AND r.id <> l.id) THEN NULL ELSE 0 END
              ) + l.valor_horometro
       END
 WHERE {VALIDA.format(t="l")}
"""

RELLENO_CREADO_EN = """
UPDATE activos a
   SET creado_en = LEAST(
         a.creado_en,
         COALESCE((SELECT min(l.capturado_en) FROM lecturas_horometro l
                    WHERE l.empresa_id = a.empresa_id AND l.activo_id = a.id), 'infinity'),
         COALESCE((SELECT min(o.fecha_falla) FROM ordenes_trabajo o
                    WHERE o.empresa_id = a.empresa_id AND o.activo_id = a.id), 'infinity'))
"""

V_PARADAS = """
CREATE VIEW v_paradas WITH (security_invoker = true) AS
SELECT o.empresa_id, o.id AS orden_id, o.numero, o.activo_id, o.componente_id,
       o.es_predictiva AS planificada,
       CASE WHEN o.es_predictiva THEN o.en_taller_en ELSE o.fecha_falla END AS inicio,
       CASE WHEN o.estado = 'cerrada' THEN o.fecha_salida_taller END AS fin,
       o.estado, o.requiere_revision
  FROM ordenes_trabajo o
 WHERE o.estado <> 'cancelada'
   AND (NOT o.es_predictiva OR o.en_taller_en IS NOT NULL)
"""

INDICES = (
    # «Última lectura válida antes de t» (y la primera de todas) por equipo.
    (
        "ix_lecturas_horometro_acumuladas",
        "lecturas_horometro (empresa_id, activo_id, capturado_en DESC)"
        " WHERE horas_acumuladas IS NOT NULL",
    ),
    # Órdenes que se cerraron en un periodo, y fallas reales por fecha.
    (
        "ix_ordenes_trabajo_cierre",
        "ordenes_trabajo (empresa_id, fecha_salida_taller) WHERE estado = 'cerrada'",
    ),
    (
        "ix_ordenes_trabajo_falla_real",
        "ordenes_trabajo (empresa_id, fecha_falla) WHERE estado <> 'cancelada' AND NOT"
        " es_predictiva",
    ),
    # Costos: consumos de un periodo.
    (
        "ix_stock_movimientos_consumo_fecha",
        "stock_movimientos (empresa_id, creado_en) WHERE tipo = 'consumo'",
    ),
    # Panel del operario: sus propios reportes.
    (
        "ix_lecturas_horometro_usuario",
        "lecturas_horometro (empresa_id, registrado_por, capturado_en DESC)",
    ),
    ("ix_alertas_usuario", "alertas (empresa_id, reportado_por, capturado_en DESC)"),
)

VISTAS = ("v_paradas", "v_vidas", "v_riesgo_activo")

JIT = f"""
DO $$
BEGIN
    ALTER ROLE {ROL_APP} SET jit = off;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'job_user') THEN
        ALTER ROLE job_user SET jit = off;
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Sin permiso para ALTER ROLE: el JIT se apaga en backend/db/roles.sql';
END
$$
"""


def _sin_force(tablas: tuple[str, ...], sentencias: tuple[str, ...]) -> None:
    for t in tablas:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
    for s in sentencias:
        op.execute(s)
    for t in tablas:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE lecturas_horometro ADD COLUMN horas_acumuladas INTEGER"
        " CONSTRAINT ck_lecturas_horometro_horas_acumuladas CHECK (horas_acumuladas >= 0)"
    )
    _sin_force(
        ("activos", "lecturas_horometro", "ordenes_trabajo"),
        (RELLENO_CREADO_EN, RELLENO_HORAS),
    )
    op.execute(HORAS_ACUMULADAS)
    op.execute(
        "CREATE TRIGGER lectura_horas_acumuladas"
        " BEFORE INSERT OR UPDATE OF requiere_revision, resolucion, offset_resultante"
        " ON lecturas_horometro FOR EACH ROW EXECUTE FUNCTION lectura_horas_acumuladas()"
    )
    for nombre, definicion in INDICES:
        op.execute(f"CREATE INDEX {nombre} ON {definicion}")
    op.execute(V_PARADAS)
    # ALTER DEFAULT PRIVILEGES (fase 1) concede INSERT, UPDATE y DELETE también sobre las vistas
    # nuevas. Una vista de solo lectura no debe tenerlos (decisión 14; v_vidas y v_riesgo_activo
    # vienen de la 0009 con el mismo defecto).
    op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {', '.join(VISTAS)} FROM {ROL_APP}")
    op.execute(f"GRANT SELECT ON v_paradas TO {ROL_APP}")
    op.execute(JIT)


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN ALTER ROLE app_user RESET jit;"
        " IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'job_user') THEN"
        " ALTER ROLE job_user RESET jit; END IF;"
        " EXCEPTION WHEN insufficient_privilege THEN NULL; END $$"
    )
    op.execute("DROP VIEW v_paradas")
    for nombre, _ in reversed(INDICES):
        op.execute(f"DROP INDEX {nombre}")
    op.execute("DROP TRIGGER lectura_horas_acumuladas ON lecturas_horometro")
    op.execute("DROP FUNCTION lectura_horas_acumuladas()")
    op.execute("ALTER TABLE lecturas_horometro DROP COLUMN horas_acumuladas")
