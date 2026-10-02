"""Configuración central del backend, cargada desde variables de entorno / .env.

Todo valor ajustable vive aquí y sale del entorno: el mismo código corre en desarrollo, pruebas y
producción sin modificaciones (04-fase1-fundamentos.md, sección 7.5).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SIMAP API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # Orígenes permitidos para CORS (el frontend Next.js en desarrollo).
    # Lista blanca explícita: nunca "*", porque la sesión viaja en cookie.
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Base de datos -------------------------------------------------------
    # El usuario de esta URL debe ser app_user (sin BYPASSRLS y sin ser dueño de
    # las tablas), o las políticas RLS quedan inertes. Ver db/rls_policies.sql.
    database_url: str = "postgresql+asyncpg://app_user:changeme@localhost:5432/simap"
    # Las migraciones corren con el dueño de las tablas, no con app_user (que no puede crear
    # objetos) ni con el superusuario (cuyas tablas escaparían a FORCE ROW LEVEL SECURITY).
    database_url_migraciones: str = (
        "postgresql+asyncpg://simap_owner:changeme_owner@localhost:5432/simap"
    )
    # El plano de control (consola del operador de SIMAP) se atiende con un rol PROPIO, no con
    # app_user. Ese rol tiene permisos concedidos tabla por tabla y ninguno sobre las tablas de
    # negocio, así que quien opera SIMAP puede dar de alta clientes sin poder leer sus datos.
    # Cambiar esta URL a la de app_user derriba esa frontera sin un solo error visible.
    database_url_operador: str = (
        "postgresql+asyncpg://operador_user:changeme_operador@localhost:5432/simap"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    # Deja trazas SQL en consola. Solo para depurar en local.
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # --- Autenticación -------------------------------------------------------
    jwt_secret: str = "change_me_in_production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    # Parámetros Argon2id recomendados en 04-fase1-fundamentos.md, sección 4.4.
    # memory_cost va en KiB: 65536 KiB = 64 MiB por hash.
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    # Rate limiting de /auth/login (sección 6.2): intentos por ventana.
    login_max_attempts: int = 5
    login_attempt_window_seconds: int = 60

    # Cookies de sesión. `secure=True` exige HTTPS, así que en desarrollo local hay que ponerlo a
    # false o el navegador descartará la cookie y el login no funcionará. En cualquier otro entorno
    # se deja activado: es lo que impide que la sesión viaje en claro.
    cookie_secure: bool = True
    cookie_samesite: str = "lax"

    # --- Motor de predicción (se usa a partir de F4) -------------------------
    risk_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
