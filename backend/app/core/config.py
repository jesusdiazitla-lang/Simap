"""Configuración central del backend, cargada desde variables de entorno / .env.

Todo valor ajustable vive aquí y sale del entorno: el mismo código corre en desarrollo, pruebas y
producción sin modificaciones (04-fase1-fundamentos.md, sección 7.5).
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Valores de plantilla que nunca pueden firmar sesiones de verdad.
SECRETOS_DE_EJEMPLO = frozenset({"change_me_in_production", "cambia-esto-por-un-secreto-propio"})


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
    # El job nocturno de la fase 4 (07-fase4, 9.3) se conecta con job_user: miembro de app_user y
    # sujeto a RLS, con el único privilegio extra de listar los ids de las empresas.
    database_url_job: str = "postgresql+asyncpg://job_user:changeme_job@localhost:5432/simap"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    # Deja trazas SQL en consola. Solo para depurar en local.
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # --- Autenticación -------------------------------------------------------
    # Sin valor por defecto, a propósito (04-fase1, sección 6.5): con uno, un despliegue al que le
    # faltara la variable arrancaría firmando las sesiones con un secreto que está en el
    # repositorio, y cualquiera podría fabricarse un token de administrador. Así, sin la variable
    # no arranca.
    jwt_secret: str = Field(min_length=32)
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
    # Por IP el tope es mayor y un acierto no lo reinicia. Mayor, porque una planta entera sale a
    # internet por la misma IP y al empezar el turno entran todos a la vez. Sin reinicio, porque si
    # acertar lo pusiera a cero, quien tenga una cuenta válida podría intercalar su propio login
    # entre intentos contra cuentas ajenas y barrerlas sin tocar nunca el límite.
    login_max_intentos_por_ip: int = 30

    # Cookies de sesión. `secure=True` exige HTTPS, así que en desarrollo local hay que ponerlo a
    # false o el navegador descartará la cookie y el login no funcionará. En cualquier otro entorno
    # se deja activado: es lo que impide que la sesión viaje en claro.
    cookie_secure: bool = True
    cookie_samesite: str = "lax"

    # --- Registro de campo (F2) -----------------------------------------------
    # Dirección pública del frontend. El QR de cada equipo codifica `{app_base_url}/a/{codigo}` y
    # nada más: ni datos del equipo ni de la empresa (05-fase2-activos-y-campo.md, sección 6.1).
    app_base_url: str = "http://localhost:3000"
    # Horómetro (sección 5.1): techo de valor admitido, y holgura en horas al comprobar que una
    # máquina no acumula más horas de operación que las que han pasado en el reloj.
    horometro_max: int = 1_000_000
    horometro_tolerancia_horas: int = 2
    # Ventana de `capturado_en` admitida: un teléfono con el reloj adelantado, o un ítem olvidado
    # semanas en una cola sin conexión, no deben escribir en la historia del equipo.
    captura_tolerancia_futuro_minutos: int = 5
    captura_antiguedad_max_dias: int = 14
    # Deduplicación de alertas (sección 5.2): misma persona, mismo equipo y mismo síntoma dentro de
    # esta ventana cuentan como una sola. Un botón atascado no debe inflar el riesgo en la fase 4.
    alerta_dedup_minutos: int = 10
    # Límites por usuario (secciones 6.2 y 8.4). La resolución de códigos lleva el suyo, más
    # estricto, porque es la que permitiría barrer códigos ajenos.
    campo_max_peticiones_por_minuto: int = 60
    codigo_max_peticiones_por_minuto: int = 30
    pagina_max: int = 100

    # --- Órdenes de trabajo (06-fase3, sección 11.4) -------------------------
    # Por usuario y minuto: un bucle en el cliente no debe poder llenar la tabla de eventos, que no
    # se puede borrar.
    falla_max_por_minuto: int = 20
    transicion_max_por_minuto: int = 60

    # --- Motor de predicción e inventario (F4) ----------------------------------
    # El umbral, el horizonte y el multiplicador son de cada empresa (configuracion_empresa,
    # decisión 5); aquí solo lo que es del proceso.
    # Programa el job diario dentro del propio backend (APScheduler) a las 02:00 de Santo Domingo.
    # En producción lo sustituye un cron que ejecuta `python -m app.jobs.diario`.
    job_diario_en_proceso: bool = False
    job_diario_hora: int = Field(default=2, ge=0, le=23)
    job_zona_horaria: str = "America/Santo_Domingo"
    # Una consulta atascada no debe detener a las demás empresas (9.3).
    job_statement_timeout_ms: int = Field(default=60_000, ge=1_000)
    linea_repuesto_max_por_minuto: int = 30
    ingreso_max_por_minuto: int = 20

    @field_validator("jwt_secret")
    @classmethod
    def _secreto_propio(cls, valor: str) -> str:
        # El valor de ejemplo de `.env.example` es público. Copiar la plantilla sin cambiarlo es el
        # descuido más probable, y el más caro.
        if valor in SECRETOS_DE_EJEMPLO:
            raise ValueError(
                "JWT_SECRET tiene el valor de ejemplo. Genera uno propio con: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return valor


@lru_cache
def get_settings() -> Settings:
    return Settings()
