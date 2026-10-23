"""F4: la conversión en falla registra su lectura de horómetro, como un reporte de falla.

Revision ID: 0010
Revises: 0009

`POST /ordenes/{id}/convertir-en-falla` escribía el horómetro de la falla directamente en la orden,
sin las reglas de lectura de la fase 2: un dígito de menos o de más entraba al modelo sin marca de
revisión y deformaba la curva del componente para toda la empresa (07-fase4, 12.2: las órdenes con
horómetro dudoso quedan fuera hasta confirmarse). Ahora la conversión registra la lectura igual que
`reportar_falla` y la enlaza a la orden, que hereda su marca.

Lo que cambia en la base:

- `app_user` puede actualizar `ordenes_trabajo.lectura_id`.
- El trigger `ot_datos_de_falla` solo deja fijar ese enlace **en la misma escritura que convierte**
  la orden (`es_predictiva` pasa a falso) y **si estaba vacío**. Una orden reportada como falla nace
  con su lectura; una predictiva no tiene ninguna hasta convertirse. Nada más puede reenlazarla.
"""

from __future__ import annotations

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

ROL_APP = "app_user"

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
    IF NEW.lectura_id IS DISTINCT FROM OLD.lectura_id
       AND NOT (convierte AND OLD.lectura_id IS NULL) THEN
        RAISE EXCEPTION 'La lectura de la orden % solo se fija al convertirla en falla',
            OLD.numero USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$
"""

DATOS_DE_FALLA_0009 = """
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


COLUMNAS_0009 = "horas_acumuladas_en_falla, horometro_en_falla, fecha_falla"


def _enganchar(columnas: str) -> None:
    # La 0009 lo enganchó solo a sus tres columnas: un UPDATE de lectura_id no lo dispararía.
    op.execute("DROP TRIGGER ot_datos_de_falla ON ordenes_trabajo")
    op.execute(
        f"CREATE TRIGGER ot_datos_de_falla BEFORE UPDATE OF {columnas} ON ordenes_trabajo"
        " FOR EACH ROW EXECUTE FUNCTION ot_datos_de_falla()"
    )


def upgrade() -> None:
    op.execute(DATOS_DE_FALLA)
    _enganchar(f"{COLUMNAS_0009}, lectura_id")
    op.execute(f"GRANT UPDATE (lectura_id) ON ordenes_trabajo TO {ROL_APP}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (lectura_id) ON ordenes_trabajo FROM {ROL_APP}")
    _enganchar(COLUMNAS_0009)
    op.execute(DATOS_DE_FALLA_0009)
