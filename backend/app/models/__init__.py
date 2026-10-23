"""Modelos de dominio / ORM (espejo de backend/db/schema.sql).

Importar aquí cada entidad nueva: Alembic lee `Base.metadata` desde este paquete, y una entidad que
no esté importada es invisible para `--autogenerate` (generaría una migración que borra la tabla).
"""

from app.models.activo import Activo
from app.models.alerta import Alerta
from app.models.base import Base
from app.models.componente import Componente
from app.models.empresa import Empresa
from app.models.lectura_horometro import LecturaHorometro
from app.models.operador import AccionOperador, BitacoraOperador, Operador
from app.models.orden_trabajo import OrdenContador, OrdenEvento, OrdenTrabajo
from app.models.prediccion import (
    ActivoComponente,
    AlertaSistema,
    ConfiguracionEmpresa,
    ModeloComponente,
    ModeloHistorial,
    ReajustePendiente,
    Riesgo,
)
from app.models.repuesto import OrdenRepuesto, Repuesto, StockMovimiento
from app.models.usuario import Usuario

__all__ = [
    "AccionOperador",
    "Activo",
    "ActivoComponente",
    "Alerta",
    "AlertaSistema",
    "Base",
    "BitacoraOperador",
    "Componente",
    "ConfiguracionEmpresa",
    "Empresa",
    "LecturaHorometro",
    "ModeloComponente",
    "ModeloHistorial",
    "Operador",
    "OrdenContador",
    "OrdenEvento",
    "OrdenRepuesto",
    "OrdenTrabajo",
    "ReajustePendiente",
    "Repuesto",
    "Riesgo",
    "StockMovimiento",
    "Usuario",
]
