"""Pruebas del modelo Empresa (RF-01). No necesitan base de datos: inspeccionan los metadatos."""

from datetime import UTC, datetime
from uuid import UUID

from app.models.empresa import Empresa


def test_la_tabla_se_llama_como_en_el_esquema() -> None:
    # backend/db/schema.sql define 'empresas'. Si diverge, la migracion crearia
    # una tabla que el ORM no encuentra.
    assert Empresa.__tablename__ == "empresas"


def test_rnf01_empresa_no_tiene_columna_empresa_id() -> None:
    # La fila ES la empresa: su politica RLS filtra por id, no por empresa_id.
    assert "empresa_id" not in Empresa.__table__.columns


def test_la_clave_primaria_es_uuid() -> None:
    # Seccion 7.2: UUID, no entero autoincremental.
    pk = list(Empresa.__table__.primary_key.columns)
    assert len(pk) == 1
    assert pk[0].name == "id"
    assert pk[0].type.python_type is UUID


def test_el_id_se_genera_en_python_no_en_el_servidor() -> None:
    # Requisito de portabilidad: el valor por defecto lo produce Python, no
    # gen_random_uuid(), que solo existe en PostgreSQL. SQLAlchemy lo aplica al
    # insertar, no al construir el objeto, asi que se comprueba la definicion.
    default = Empresa.__table__.columns["id"].default
    assert default is not None and default.is_callable
    assert isinstance(default.arg(None), UUID)


def test_la_fecha_de_registro_se_rellena_sola_en_utc() -> None:
    # UTC, no la fecha local del servidor: SIMAP es multiempresa y los clientes
    # pueden estar en husos distintos. Comparar contra date.today() haria que el
    # test fallara segun la hora del dia en maquinas fuera de UTC.
    default = Empresa.__table__.columns["fecha_registro"].default
    assert default is not None and default.is_callable
    assert default.arg(None) == datetime.now(UTC).date()


def test_el_nombre_es_obligatorio() -> None:
    assert Empresa.__table__.columns["nombre"].nullable is False
