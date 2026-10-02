"""Pruebas del modelo Usuario (RF-02, RNF-01). Inspeccionan metadatos, sin base de datos."""

from uuid import UUID, uuid4

from app.core.security import Rol
from app.models.usuario import ROLES_VALIDOS, Usuario


def _crear() -> Usuario:
    return Usuario(
        empresa_id=uuid4(),
        nombre="Ana",
        correo="ana@acme.test",
        password_hash="$argon2id$...",
        rol=Rol.SUPERVISOR.value,
    )


def test_la_tabla_se_llama_como_en_el_esquema() -> None:
    assert Usuario.__tablename__ == "usuarios"


def test_rnf01_lleva_empresa_id_obligatorio_con_clave_foranea() -> None:
    col = Usuario.__table__.columns["empresa_id"]
    assert col.nullable is False
    destinos = {fk.target_fullname for fk in col.foreign_keys}
    assert destinos == {"empresas.id"}


def test_rnf01_empresa_id_esta_indexado() -> None:
    # Seccion 7.2: el indice va desde el primer commit, no despues.
    indexados = {tuple(c.name for c in idx.columns) for idx in Usuario.__table__.indexes}
    assert ("empresa_id",) in indexados


def test_rf02_el_correo_es_unico_en_todo_el_sistema() -> None:
    # Es la credencial de login, y al escribirla el usuario todavia no ha
    # declarado su empresa: no puede ser unico solo dentro del tenant.
    assert Usuario.__table__.columns["correo"].unique is True


def test_rf02_se_guarda_el_hash_y_no_la_contrasena() -> None:
    columnas = set(Usuario.__table__.columns.keys())
    assert "password_hash" in columnas
    assert "password" not in columnas
    assert "contrasena" not in columnas


def test_los_roles_validos_se_derivan_del_enum() -> None:
    # Si divergieran, la base aceptaria un rol que el codigo no reconoce, o al reves.
    assert set(ROLES_VALIDOS) == {r.value for r in Rol}


def test_la_restriccion_de_rol_nombra_los_cinco_roles() -> None:
    restricciones = {
        c.name: str(c.sqltext) for c in Usuario.__table__.constraints if hasattr(c, "sqltext")
    }
    texto = restricciones["ck_usuarios_rol_valido"]
    for rol in ROLES_VALIDOS:
        assert f"'{rol}'" in texto


def test_el_id_se_genera_en_python_no_en_el_servidor() -> None:
    # Portabilidad: el default lo produce Python, no gen_random_uuid(). Se
    # comprueba la definicion porque SQLAlchemy lo aplica al insertar.
    default = Usuario.__table__.columns["id"].default
    assert default is not None and default.is_callable
    assert isinstance(default.arg(None), UUID)


def test_la_fecha_de_creacion_lleva_zona_horaria() -> None:
    # TIMESTAMPTZ, no TIMESTAMP: la planta y el servidor pueden estar en husos
    # distintos y las horas alimentan el modelo de Weibull.
    assert Usuario.__table__.columns["creado_en"].type.timezone is True
    default = Usuario.__table__.columns["creado_en"].default
    assert default is not None and default.is_callable
    assert default.arg(None).tzinfo is not None
