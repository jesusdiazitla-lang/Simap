"""Offset histórico del horómetro: cada reinicio guarda el offset que dejó.

Revision ID: 0008
Revises: 0007

`docs/contexto/06-fase3-ordenes-de-trabajo.md`, sección 5.1: una falla capturada antes de un
reinicio que llega después por la cola «queda marcada para revisión, porque usar el offset nuevo la
mediría mal». Hasta esta revisión quedaba marcada, pero sus horas acumuladas ya se habían calculado
con el offset de hoy, y confirmar el horómetro no las corregía: la vida del componente entraba en
`v_intervalos_entre_fallas` inflada en todo lo que el equipo acumuló antes del reinicio.

1. `lecturas_horometro.offset_resultante`: el offset que dejó cada reinicio, sea el del
   administrador (`es_reinicio`) o una lectura marcada resuelta como `reinicio`. El offset vigente
   en un instante es el del último reinicio capturado en o antes de ese instante, o 0 si no hubo
   ninguno. Lo calcula `activos.offset_en`.
2. **Relleno**: el último reinicio de cada equipo recibe el offset actual del equipo, que es
   exactamente el que dejó. Va con FORCE RLS levantado: sin empresa fijada no vería ninguna fila.
   Los anteriores, si los hay, quedan en NULL: su offset no se puede reconstruir, y una falla de
   esa época queda marcada en vez de medirse con una cifra inventada.
3. **Las horas acumuladas de la orden cambian solo al confirmar el horómetro**: `app_user` recibe
   UPDATE sobre la columna, y el trigger `ot_horas_solo_al_confirmar` rechaza cualquier cambio que
   no vaya en la misma escritura que quita la marca de revisión. Una cifra ya confirmada sigue sin
   poder reescribirse, como pedía la 0007.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_APP = "app_user"


def upgrade() -> None:
    op.add_column("lecturas_horometro", sa.Column("offset_resultante", sa.Integer(), nullable=True))
    # Nombres cortos: la convención de nombres les antepone `ck_lecturas_horometro_`.
    op.create_check_constraint(
        "offset_resultante_no_negativo",
        "lecturas_horometro",
        "offset_resultante IS NULL OR offset_resultante >= 0",
    )
    op.create_check_constraint(
        "offset_solo_en_reinicio",
        "lecturas_horometro",
        "offset_resultante IS NULL OR es_reinicio OR resolucion = 'reinicio'",
    )
    # Las dos tablas tienen FORCE ROW LEVEL SECURITY, que alcanza también al dueño: sin una empresa
    # fijada, el UPDATE no vería ninguna fila y el relleno no haría nada sin avisar. Se levanta solo
    # durante el relleno; la DDL es transaccional, así que si algo falla vuelve con todo lo demás.
    for tabla in ("lecturas_horometro", "activos"):
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE lecturas_horometro l
           SET offset_resultante = a.horometro_offset
          FROM activos a
         WHERE a.id = l.activo_id
           AND l.id = (SELECT r.id FROM lecturas_horometro r
                        WHERE r.activo_id = l.activo_id
                          AND (r.es_reinicio OR r.resolucion = 'reinicio')
                        ORDER BY r.capturado_en DESC, r.id DESC
                        LIMIT 1)
        """
    )
    for tabla in ("lecturas_horometro", "activos"):
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
    op.execute(f"GRANT UPDATE (offset_resultante) ON lecturas_horometro TO {ROL_APP}")

    op.execute(
        """
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
    )
    op.execute(
        "CREATE TRIGGER ot_horas_solo_al_confirmar BEFORE UPDATE OF horas_acumuladas_en_falla"
        " ON ordenes_trabajo FOR EACH ROW EXECUTE FUNCTION ot_horas_solo_al_confirmar()"
    )
    op.execute(f"GRANT UPDATE (horas_acumuladas_en_falla) ON ordenes_trabajo TO {ROL_APP}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (horas_acumuladas_en_falla) ON ordenes_trabajo FROM {ROL_APP}")
    op.execute("DROP TRIGGER IF EXISTS ot_horas_solo_al_confirmar ON ordenes_trabajo")
    op.execute("DROP FUNCTION IF EXISTS ot_horas_solo_al_confirmar()")
    # Los dos CHECK caen solos con la columna que comprueban.
    op.drop_column("lecturas_horometro", "offset_resultante")
