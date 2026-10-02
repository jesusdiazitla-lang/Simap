"""Pruebas de la selección de estrategia por motor (requisito de portabilidad).

Verifican que cambiar de motor sea cambiar `DATABASE_URL` y nada más, y que un motor sin RLS quede
marcado como tal en lugar de degradar el aislamiento en silencio.
"""

from typing import Any
from uuid import UUID

import pytest

from app.db.tenant import (
    DIALECTO_RECOMENDADO,
    EstrategiaTenant,
    FiltradoEnAplicacion,
    RowLevelSecurityPostgres,
    estrategia_para,
)

EMPRESA = UUID("11111111-1111-1111-1111-111111111111")


class SesionEspia:
    def __init__(self) -> None:
        self.ejecutadas: list[tuple[str, Any]] = []

    async def execute(self, stmt: object, params: Any = None) -> None:
        self.ejecutadas.append((str(stmt), params))


@pytest.mark.parametrize(
    ("dialecto", "esperada"),
    [
        ("postgresql", RowLevelSecurityPostgres),
        ("mysql", FiltradoEnAplicacion),
        ("sqlite", FiltradoEnAplicacion),
        ("mssql", FiltradoEnAplicacion),
    ],
)
def test_cada_dialecto_recibe_su_estrategia(
    dialecto: str, esperada: type[EstrategiaTenant]
) -> None:
    assert isinstance(estrategia_para(dialecto), esperada)


def test_un_motor_desconocido_cae_en_la_estrategia_conservadora() -> None:
    # No debe fingir que hay RLS donde no se sabe si la hay.
    estrategia = estrategia_para("motor_inventado")
    assert isinstance(estrategia, FiltradoEnAplicacion)
    assert estrategia.aplicado_por_la_base is False


def test_solo_postgres_declara_que_la_base_impone_el_aislamiento() -> None:
    # Esta bandera es lo que permite detectar una degradacion del aislamiento
    # al cambiar de motor, en vez de descubrirla con datos de otra empresa en
    # pantalla.
    assert estrategia_para(DIALECTO_RECOMENDADO).aplicado_por_la_base is True
    assert estrategia_para("mysql").aplicado_por_la_base is False


async def _fijar(estrategia: EstrategiaTenant, sesion: SesionEspia) -> None:
    await estrategia.fijar_empresa(sesion, EMPRESA)  # type: ignore[arg-type]


def test_rnf01_postgres_fija_el_tenant_con_parametro_enlazado() -> None:
    import asyncio

    sesion = SesionEspia()
    asyncio.run(_fijar(RowLevelSecurityPostgres(), sesion))

    sql, params = sesion.ejecutadas[0]
    assert "set_config" in sql
    # El id no puede ir concatenado en el texto: seria una inyeccion via token.
    assert str(EMPRESA) not in sql
    assert params["empresa_id"] == str(EMPRESA)
    assert params["variable"] == "app.empresa_id"


def test_un_motor_sin_rls_no_ejecuta_sql_al_fijar_el_tenant() -> None:
    import asyncio

    sesion = SesionEspia()
    asyncio.run(_fijar(FiltradoEnAplicacion(), sesion))
    assert sesion.ejecutadas == []


def test_la_variable_de_sesion_coincide_con_la_de_las_politicas() -> None:
    # db/rls_policies.sql lee current_setting('app.empresa_id'). Si alguien
    # renombra una de las dos y no la otra, el aislamiento deja de aplicarse.
    assert RowLevelSecurityPostgres.VARIABLE == "app.empresa_id"
