"""Modelos de dominio / ORM (espejo de backend/db/schema.sql).

Importar aquí cada entidad nueva: Alembic lee `Base.metadata` desde este paquete, y una entidad que
no esté importada es invisible para `--autogenerate` (generaría una migración que borra la tabla).
"""

from app.models.base import Base
from app.models.empresa import Empresa
from app.models.operador import AccionOperador, BitacoraOperador, Operador
from app.models.usuario import Usuario

__all__ = ["AccionOperador", "Base", "BitacoraOperador", "Empresa", "Operador", "Usuario"]
