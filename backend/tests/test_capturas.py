"""Ventana admitida de `capturado_en` (sección 5.1). Lógica pura, sin base de datos."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.capturas import CapturaInvalida, validar_instante

AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "desfase", [timedelta(0), timedelta(minutes=4), -timedelta(days=13, hours=23)]
)
def test_dentro_de_la_ventana_se_acepta(desfase: timedelta) -> None:
    validar_instante(AHORA + desfase, AHORA)


def test_mas_de_cinco_minutos_en_el_futuro_se_rechaza() -> None:
    with pytest.raises(CapturaInvalida, match="futuro"):
        validar_instante(AHORA + timedelta(minutes=6), AHORA)


def test_mas_de_catorce_dias_se_rechaza() -> None:
    with pytest.raises(CapturaInvalida, match="14 días"):
        validar_instante(AHORA - timedelta(days=14, minutes=1), AHORA)
