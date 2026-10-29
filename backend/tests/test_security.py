"""Pruebas de las primitivas de seguridad (RF-02, RNF-07)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    CLAIM_TIPO,
    ErrorDeToken,
    Rol,
    TipoToken,
    crear_token_de_acceso,
    crear_token_de_refresco,
    decodificar_token,
    hash_password,
    verify_password,
)

# Argon2 con memory_cost=64 MiB es lento a proposito; en tests basta con unas
# pocas llamadas, asi que se reutilizan estos valores en vez de generar mas.
PASSWORD = "contrasena-de-prueba-123"


def test_rf02_hash_no_guarda_la_contrasena_en_claro() -> None:
    h = hash_password(PASSWORD)
    assert PASSWORD not in h
    assert h.startswith("$argon2id$"), "debe ser Argon2id, no bcrypt ni SHA"


def test_rf02_verify_acepta_la_contrasena_correcta() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_rf02_verify_rechaza_la_contrasena_incorrecta() -> None:
    assert verify_password("otra-cosa", hash_password(PASSWORD)) is False


def test_rf02_verify_devuelve_false_ante_un_hash_corrupto() -> None:
    # No debe propagar la excepcion de Argon2: quien llama solo quiere un bool.
    assert verify_password(PASSWORD, "esto-no-es-un-hash") is False


def test_rf02_dos_hashes_de_la_misma_contrasena_son_distintos() -> None:
    # Sal aleatoria por hash: dos usuarios con la misma clave no se delatan.
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_rf02_token_de_acceso_conserva_las_reclamaciones() -> None:
    usuario, empresa = uuid4(), uuid4()
    token = crear_token_de_acceso(usuario, empresa, Rol.SUPERVISOR)
    claims = decodificar_token(token)
    assert claims.usuario_id == usuario
    assert claims.empresa_id == empresa
    assert claims.rol is Rol.SUPERVISOR
    assert claims.tipo is TipoToken.ACCESO


def test_rnf07_un_token_de_refresco_no_sirve_como_token_de_acceso() -> None:
    token = crear_token_de_refresco(uuid4(), uuid4(), Rol.OPERARIO)
    with pytest.raises(ErrorDeToken):
        decodificar_token(token, TipoToken.ACCESO)
    # Pero si vale cuando se pide explicitamente uno de refresco.
    assert decodificar_token(token, TipoToken.REFRESCO).rol is Rol.OPERARIO


def test_rnf07_token_con_firma_alterada_es_rechazado() -> None:
    token = crear_token_de_acceso(uuid4(), uuid4(), Rol.GERENTE)
    cuerpo, _, _firma = token.rpartition(".")
    with pytest.raises(ErrorDeToken):
        decodificar_token(f"{cuerpo}.firmafalsa")


def test_rnf07_token_expirado_es_rechazado() -> None:
    s = get_settings()
    pasado = datetime.now(UTC) - timedelta(minutes=1)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "empresa_id": str(uuid4()),
            "rol": Rol.OPERARIO.value,
            CLAIM_TIPO: TipoToken.ACCESO.value,
            "exp": int(pasado.timestamp()),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    with pytest.raises(ErrorDeToken):
        decodificar_token(token)


def test_rnf07_token_sin_empresa_id_es_rechazado() -> None:
    # Un token sin tenant no debe poder abrir una sesion: sin empresa_id no hay
    # nada que fijar en app.empresa_id y el aislamiento quedaria indefinido.
    s = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "rol": Rol.OPERARIO.value,
            CLAIM_TIPO: TipoToken.ACCESO.value,
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    with pytest.raises(ErrorDeToken):
        decodificar_token(token)


def test_rnf07_token_con_rol_desconocido_es_rechazado() -> None:
    s = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "empresa_id": str(uuid4()),
            "rol": "superadmin_inventado",
            CLAIM_TIPO: TipoToken.ACCESO.value,
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    with pytest.raises(ErrorDeToken):
        decodificar_token(token)


def test_los_roles_coinciden_con_los_valores_de_la_base() -> None:
    # El CHECK de usuarios.rol en backend/db/schema.sql acepta exactamente estos.
    assert {r.value for r in Rol} == {
        "operario",
        "supervisor",
        "tecnico_taller",
        "gerente",
        "administrador",
    }
