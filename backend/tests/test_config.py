"""El secreto de las sesiones sale del entorno y nunca es el de ejemplo (04-fase1, sección 6.5).

Sin la variable, o con el valor de `.env.example`, la API no arranca: con un valor por defecto, un
despliegue al que le faltara la variable firmaría las sesiones con un secreto público.
"""

import pytest
from pydantic import ValidationError

from app.core.config import SECRETOS_DE_EJEMPLO, Settings


def _settings_sin_env_file() -> Settings:
    # `_env_file=None`: que no lo rellene el `.env` local de quien corre las pruebas.
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_seccion65_sin_jwt_secret_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="jwt_secret"):
        _settings_sin_env_file()


@pytest.mark.parametrize("ejemplo", sorted(SECRETOS_DE_EJEMPLO))
def test_seccion65_el_secreto_de_ejemplo_se_rechaza(
    monkeypatch: pytest.MonkeyPatch, ejemplo: str
) -> None:
    monkeypatch.setenv("JWT_SECRET", ejemplo)
    with pytest.raises(ValidationError, match="valor de ejemplo|at least 32"):
        _settings_sin_env_file()


def test_seccion65_un_secreto_corto_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "corto")
    with pytest.raises(ValidationError):
        _settings_sin_env_file()


def test_un_secreto_propio_se_acepta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    assert _settings_sin_env_file().jwt_secret == "x" * 48
