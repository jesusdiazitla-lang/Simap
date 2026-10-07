"""Revisión de lecturas marcadas y reinicio de horómetro.

Revision ID: 0006
Revises: 0005

`docs/contexto/05-fase2-activos-y-campo.md`, sección 5.1: una lectura que no cuadra se guarda
marcada y «no mueve el valor vigente hasta que un supervisor la confirme». Hasta esta revisión no
había forma de confirmarla, así que quedaba marcada para siempre. Y el cambio o reinicio del
horómetro «debe
resolverse antes de la Fase 4»: sin él, las horas desde la última falla se calculan mal.

Tres resoluciones posibles de una lectura marcada:

- `confirmada`: la lectura era buena (un salto real, una lectura que llegó tarde). Pasa a contar
  como lectura válida y, si es la más reciente, mueve el horómetro vigente.
- `descartada`: era un error de tecleo. Se conserva —el dato del operario nunca se borra— pero no
  cuenta para nada.
- `reinicio`: el horómetro se cambió o se puso a cero. La lectura marca el comienzo de una serie
  nueva: las siguientes se comparan con ella y no con las de antes. La fase 4 suma las horas de cada
  serie para no perder las anteriores al reinicio.

`requiere_revision` no cambia: dice que la lectura **fue** marcada, que es historia. Lo pendiente es
`requiere_revision AND resolucion IS NULL`.

Permisos: `app_user` recibe UPDATE solo sobre las tres columnas nuevas. La lectura en sí sigue sin
poder reescribirse.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _renombrar_check_usuarios(de: str, a: str) -> None:
    """Idempotente: solo renombra si existe con el nombre de origen, para que una base a medio
    camino (o una creada antes de este arreglo) no haga fallar la migración en ningún sentido."""
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{de}')"
        f" THEN ALTER TABLE usuarios RENAME CONSTRAINT {de} TO {a}; END IF; END $$"
    )


def upgrade() -> None:
    op.add_column("lecturas_horometro", sa.Column("resolucion", sa.Text(), nullable=True))
    op.add_column("lecturas_horometro", sa.Column("revisada_por", sa.Uuid(), nullable=True))
    op.add_column(
        "lecturas_horometro",
        sa.Column("revisada_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "resolucion_valida",
        "lecturas_horometro",
        "resolucion IN ('confirmada', 'descartada', 'reinicio')",
    )
    # Solo se resuelve lo que estaba marcado.
    op.create_check_constraint(
        # Nombre corto: la convención de nombres le antepone `ck_lecturas_horometro_`.
        "resolucion_solo_si_marcada",
        "lecturas_horometro",
        "resolucion IS NULL OR requiere_revision",
    )
    op.create_foreign_key(
        "fk_lecturas_horometro_revisor_mismo_tenant",
        "lecturas_horometro",
        "usuarios",
        ["empresa_id", "revisada_por"],
        ["empresa_id", "id"],
    )
    # Bandeja de lecturas por revisar: barata aunque la tabla acumule años.
    op.create_index(
        "ix_lecturas_horometro_por_revisar",
        "lecturas_horometro",
        ["empresa_id", "capturado_en"],
        postgresql_where=sa.text("requiere_revision AND resolucion IS NULL"),
    )
    op.execute(
        "GRANT UPDATE (resolucion, revisada_por, revisada_en) ON lecturas_horometro TO app_user"
    )
    # Arreglo de paso: la 0001 escribió el CHECK de `usuarios` con su nombre completo y la
    # convención de nombres le añadió el prefijo otra vez. Se renombra para que todos sigan el
    # mismo patrón;
    # tests/test_migraciones.py comprueba que no vuelva a ocurrir.
    _renombrar_check_usuarios("ck_usuarios_ck_usuarios_rol_valido", "ck_usuarios_rol_valido")


def downgrade() -> None:
    _renombrar_check_usuarios("ck_usuarios_rol_valido", "ck_usuarios_ck_usuarios_rol_valido")
    op.drop_index("ix_lecturas_horometro_por_revisar", table_name="lecturas_horometro")
    op.drop_constraint(
        "fk_lecturas_horometro_revisor_mismo_tenant", "lecturas_horometro", type_="foreignkey"
    )
    # Los dos CHECK caen solos con la columna `resolucion`, que es la que comprueban.
    op.drop_column("lecturas_horometro", "revisada_en")
    op.drop_column("lecturas_horometro", "revisada_por")
    op.drop_column("lecturas_horometro", "resolucion")
