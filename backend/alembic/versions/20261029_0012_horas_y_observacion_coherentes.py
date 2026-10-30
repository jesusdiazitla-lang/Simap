"""F5: las horas acumuladas siguen a los reinicios y la observación nunca empieza tarde.

Revision ID: 0012
Revises: 0011

Corrige dos huecos de la 0011 que encontró la revisión del 2026-10-29:

1. **Un reinicio resuelto después no recalculaba las lecturas posteriores.** Un equipo en 100 h se
   reinicia; llegan 5 h y 20 h, las dos marcadas. Si se confirma primero la de 20 h, el trigger le
   da 0 + 20 (todavía no hay reinicio); cuando luego la de 5 h se registra como reinicio (offset
   95), la de 20 h se quedaba en 20 para siempre en vez de 115. El mes perdía horas y el siguiente
   ganaba unas 95 de más (horas operadas, utilización, MTBF). Ahora:

   - `lectura_horas_acumuladas` recalcula en todo UPDATE de sus columnas (la 0011 se saltaba los de
     una lectura ya válida con el mismo offset). El cálculo es una búsqueda por índice, idempotente.
   - `lectura_reinicio_propaga` (AFTER): cuando una lectura pasa a ser reinicio, deja de serlo o
     cambia su offset, vuelve a calcular las lecturas válidas del equipo capturadas desde ese
     instante hasta el reinicio siguiente. Lo hace tocando `offset_resultante` (que en esas filas es
     NULL y sigue NULL): así dispara el trigger anterior con los permisos que `app_user` ya tiene y
     sin SECURITY DEFINER (control C7). Las filas tocadas no son reinicio y no vuelven a propagar.

2. **`activos.creado_en` podía quedar después de los primeros datos del equipo.** La API acepta
   lecturas y fallas capturadas hasta 14 días atrás en un equipo recién dado de alta, y la 0011 solo
   rellenó lo que ya existía. Las horas operadas caían fuera de las de calendario (utilización por
   encima del 100 %) y la parada de una falla se recortaba (disponibilidad inflada). Ahora un
   trigger baja `creado_en` al `capturado_en` de una lectura o a la `fecha_falla` de una orden
   anteriores (decisión 8: la observación empieza con el primer dato conocido). En la base, para
   que lo cumpla todo camino: campo, sin conexión, reporte de falla y conversión en falla.

Los dos rellenos corren con FORCE RLS desactivado, como en la 0011.
"""

from __future__ import annotations

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None

VALIDA = (
    "(NOT {t}.requiere_revision OR COALESCE({t}.resolucion IN ('confirmada', 'reinicio'), false))"
)
REINICIO = "({t}.es_reinicio OR COALESCE({t}.resolucion = 'reinicio', false))"


def _horas_acumuladas(con_atajo: bool) -> str:
    """La función de la 0011; `con_atajo` es la versión vieja (solo para el downgrade)."""
    atajo = (
        f"""
    IF TG_OP = 'UPDATE' AND {VALIDA.format(t="OLD")}
       AND NEW.offset_resultante IS NOT DISTINCT FROM OLD.offset_resultante THEN
        RETURN NEW;
    END IF;"""
        if con_atajo
        else ""
    )
    return f"""
CREATE OR REPLACE FUNCTION lectura_horas_acumuladas() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_offset integer;
BEGIN
    -- Una lectura dudosa (pendiente o descartada) no suma horas a ningún indicador.
    IF NOT {VALIDA.format(t="NEW")} THEN
        NEW.horas_acumuladas := NULL;
        RETURN NEW;
    END IF;{atajo}
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


PROPAGA = f"""
CREATE FUNCTION lectura_reinicio_propaga() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_hasta timestamptz;
BEGIN
    IF NOT ({REINICIO.format(t="NEW")}
            OR (TG_OP = 'UPDATE' AND {REINICIO.format(t="OLD")})) THEN
        RETURN NULL;
    END IF;
    -- Hasta el reinicio siguiente: desde ahí manda su offset, no el de esta lectura.
    SELECT min(r.capturado_en) INTO v_hasta
      FROM lecturas_horometro r
     WHERE r.empresa_id = NEW.empresa_id AND r.activo_id = NEW.activo_id
       AND {REINICIO.format(t="r")} AND r.capturado_en > NEW.capturado_en AND r.id <> NEW.id;
    UPDATE lecturas_horometro l
       SET offset_resultante = l.offset_resultante
     WHERE l.empresa_id = NEW.empresa_id AND l.activo_id = NEW.activo_id
       AND l.id <> NEW.id
       AND l.capturado_en >= NEW.capturado_en
       AND (v_hasta IS NULL OR l.capturado_en < v_hasta)
       AND {VALIDA.format(t="l")} AND NOT {REINICIO.format(t="l")};
    RETURN NULL;
END
$$
"""

OBSERVACION = """
CREATE FUNCTION activo_observado_desde() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_instante timestamptz;
BEGIN
    -- La columna llega como argumento del trigger: un CASE con NEW.capturado_en y NEW.fecha_falla
    -- fallaría, porque PL/pgSQL resuelve los dos campos aunque la tabla solo tenga uno.
    v_instante := (to_jsonb(NEW) ->> TG_ARGV[0])::timestamptz;
    IF v_instante IS NOT NULL THEN
        UPDATE activos SET creado_en = v_instante
         WHERE empresa_id = NEW.empresa_id AND id = NEW.activo_id AND creado_en > v_instante;
    END IF;
    RETURN NULL;
END
$$
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

#: Vuelve a pasar cada lectura válida por el trigger ya corregido.
RELLENO_HORAS = (
    f"UPDATE lecturas_horometro l SET offset_resultante = l.offset_resultante"
    f" WHERE {VALIDA.format(t='l')}"
)


def _sin_force(tablas: tuple[str, ...], sentencias: tuple[str, ...]) -> None:
    for t in tablas:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
    for s in sentencias:
        op.execute(s)
    for t in tablas:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute(_horas_acumuladas(con_atajo=False))
    op.execute(PROPAGA)
    op.execute(
        "CREATE TRIGGER lectura_reinicio_propaga"
        " AFTER INSERT OR UPDATE OF requiere_revision, resolucion, offset_resultante"
        " ON lecturas_horometro FOR EACH ROW EXECUTE FUNCTION lectura_reinicio_propaga()"
    )
    op.execute(OBSERVACION)
    op.execute(
        "CREATE TRIGGER lectura_observado_desde AFTER INSERT ON lecturas_horometro"
        " FOR EACH ROW EXECUTE FUNCTION activo_observado_desde('capturado_en')"
    )
    op.execute(
        "CREATE TRIGGER orden_observado_desde AFTER INSERT OR UPDATE OF fecha_falla"
        " ON ordenes_trabajo FOR EACH ROW EXECUTE FUNCTION activo_observado_desde('fecha_falla')"
    )
    _sin_force(
        ("activos", "lecturas_horometro", "ordenes_trabajo"),
        (RELLENO_CREADO_EN, RELLENO_HORAS),
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER orden_observado_desde ON ordenes_trabajo")
    op.execute("DROP TRIGGER lectura_observado_desde ON lecturas_horometro")
    op.execute("DROP FUNCTION activo_observado_desde()")
    op.execute("DROP TRIGGER lectura_reinicio_propaga ON lecturas_horometro")
    op.execute("DROP FUNCTION lectura_reinicio_propaga()")
    op.execute(_horas_acumuladas(con_atajo=True))
