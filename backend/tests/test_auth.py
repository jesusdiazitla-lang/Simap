"""Pruebas de login, refresco y cierre de sesión (RF-02, CU-06).

Son de integración: recorren HTTP → ruta → servicio → PostgreSQL real, porque el login depende de
que la política `login_lookup` permita leer la fila de un correo concreto sin tenant fijado. Con una
base falsa ese acoplamiento quedaría sin probar, que es donde estaría el fallo.

**No hay pruebas de un endpoint de registro porque no hay endpoint de registro.** El alta de una
empresa es por invitación y se hace con `python -m app.cli crear-empresa` (ver `app/cli.py` y
`tests/test_cli.py`). Las pruebas que necesitan una empresa existente la crean con el ayudante
`dar_de_alta` del conftest, que ejecuta ese mismo comando.

El almacén efímero sí se sustituye por el de memoria: el rate limiting debe ser determinista y no
arrastrar contadores de una ejecución anterior.
"""

from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.almacen import AlmacenMemoria, get_almacen
from app.core.auth import COOKIE_ACCESO, COOKIE_PISTA_SESION, COOKIE_REFRESCO
from app.core.config import get_settings
from app.db.session import get_engine, get_estrategia_tenant, get_sessionmaker
from app.main import app
from tests.conftest import dar_de_alta, requiere_base

PASSWORD = "contrasena-larga-de-prueba"


pytestmark = requiere_base


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Sin HTTPS el navegador (y httpx) descartan una cookie `secure`, asi que en pruebas se apaga.
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()

    # El motor se cachea por proceso, pero TestClient abre un bucle de eventos nuevo en cada test.
    # Reutilizar conexiones de asyncpg entre bucles distintos revienta en Windows con
    # "'NoneType' object has no attribute 'send'". Vaciar la cache da a cada test su propio motor.
    _limpiar_motor()

    almacen = AlmacenMemoria()
    app.dependency_overrides[get_almacen] = lambda: almacen
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpiar_motor()
    get_settings.cache_clear()


def _limpiar_motor() -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_estrategia_tenant.cache_clear()


def _alta(monkeypatch: pytest.MonkeyPatch) -> str:
    """Crea una empresa con su administrador y devuelve el correo con el que iniciará sesión."""
    correo = f"{uuid4().hex}@example.com"
    assert dar_de_alta(monkeypatch, correo=correo, password=PASSWORD) == 0
    return correo


def _entrar(client: TestClient, correo: str) -> httpx.Response:
    return client.post("/api/v1/auth/login", json={"correo": correo, "password": PASSWORD})


# --- El registro público ya no existe ----------------------------------------


def test_no_existe_ruta_publica_de_registro(client: TestClient) -> None:
    """RF-01 se cumple por consola, no por HTTP.

    Esta prueba es la que impide que la ruta vuelva por descuido. Comprueba las dos caras: que la
    ruta responde 404 y que **tampoco aparece en el esquema OpenAPI**. La segunda importa más de lo
    que parece: esconder un endpoint de la interfaz no lo cierra, porque `/docs` lo anuncia.
    """
    assert client.post("/api/v1/auth/register", json={}).status_code == 404
    rutas = client.get("/openapi.json").json()["paths"]
    assert not [r for r in rutas if "register" in r], rutas.keys()


# --- Login -------------------------------------------------------------------


def test_rf02_login_correcto_abre_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    resp = client.post("/api/v1/auth/login", json={"correo": correo, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["usuario"]["correo"] == correo
    # Quien da de alta la empresa es su administrador: el rol no se acepta de nadie.
    assert cuerpo["usuario"]["rol"] == "administrador"
    assert cuerpo["expira_en_segundos"] == 30 * 60


def test_el_login_devuelve_las_cookies_de_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    resp = client.post("/api/v1/auth/login", json={"correo": correo, "password": PASSWORD})
    assert COOKIE_ACCESO in resp.cookies
    assert COOKIE_REFRESCO in resp.cookies


def test_seccion61_las_cookies_son_httponly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Si el JavaScript de la pagina pudiera leerlas, un XSS robaria la sesion.
    correo = _alta(monkeypatch)
    resp = client.post("/api/v1/auth/login", json={"correo": correo, "password": PASSWORD})
    cabeceras = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
    crudas = "\n".join(cabeceras)
    assert crudas.lower().count("httponly") >= 2


def test_rf02_la_respuesta_nunca_incluye_el_hash_de_la_contrasena(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    resp = client.post("/api/v1/auth/login", json={"correo": correo, "password": PASSWORD})
    # Se comprueba primero que la respuesta es la buena: contra un 404 las dos aserciones de abajo
    # pasarian sin haber mirado ningun cuerpo de sesion.
    assert resp.status_code == 200, resp.text
    assert "password" not in resp.text
    assert "argon2" not in resp.text.lower()


def test_seccion65_el_login_rechaza_un_campo_inesperado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # extra="forbid": sin esto, colar rol="administrador" en un endpoint podria escalar privilegios
    # si el servicio pasara el cuerpo entero al modelo.
    correo = _alta(monkeypatch)
    cuerpo = {"correo": correo, "password": PASSWORD, "rol": "administrador"}
    assert client.post("/api/v1/auth/login", json=cuerpo).status_code == 422


def test_seccion62_el_mensaje_de_error_no_distingue_correo_de_contrasena(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Distinguirlos revelaria que correos estan registrados.
    correo = _alta(monkeypatch)

    inexistente = client.post(
        "/api/v1/auth/login", json={"correo": "nadie@example.com", "password": PASSWORD}
    )
    mala_clave = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": "otra-cosa-larga"}
    )
    assert inexistente.status_code == mala_clave.status_code == 401
    assert inexistente.json()["detail"] == mala_clave.json()["detail"]


def test_seccion62_el_rate_limiting_corta_tras_cinco_intentos(client: TestClient) -> None:
    correo = f"{uuid4().hex}@example.com"
    cuerpo = {"correo": correo, "password": "clave-equivocada-larga"}
    for _ in range(get_settings().login_max_attempts):
        assert client.post("/api/v1/auth/login", json=cuerpo).status_code == 401

    bloqueado = client.post("/api/v1/auth/login", json=cuerpo)
    assert bloqueado.status_code == 429
    assert "Retry-After" in bloqueado.headers


def test_acertar_la_contrasena_limpia_el_contador(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Quien se equivoca dos veces y luego acierta no debe quedar penalizado.
    correo = _alta(monkeypatch)
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"correo": correo, "password": "mal-mal-mal-mal"})
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo, "password": PASSWORD}
        ).status_code
        == 200
    )
    # Y el contador quedo a cero: caben de nuevo los intentos completos.
    for _ in range(get_settings().login_max_attempts):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"correo": correo, "password": "mal-mal-mal-mal"},
            ).status_code
            == 401
        )


# --- Sesión, refresco y cierre -----------------------------------------------


def test_yo_devuelve_el_usuario_de_la_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    assert _entrar(client, correo).status_code == 200
    resp = client.get("/api/v1/auth/yo")
    assert resp.status_code == 200, resp.text
    assert resp.json()["correo"] == correo


def test_yo_sin_sesion_da_401(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/v1/auth/yo").status_code == 401


def test_seccion44_refrescar_emite_tokens_nuevos(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    anterior = client.cookies.get(COOKIE_REFRESCO)

    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert client.cookies.get(COOKIE_REFRESCO) != anterior, "el refresh token debe rotar"


def test_seccion44_un_refresh_token_ya_usado_queda_revocado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La rotacion es lo que delata un robo: si alguien reutiliza el token viejo,
    # se le rechaza en vez de convivir en silencio durante siete dias.
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    viejo = client.cookies.get(COOKIE_REFRESCO)
    assert client.post("/api/v1/auth/refresh").status_code == 200

    client.cookies.set(COOKIE_REFRESCO, viejo)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_un_token_de_acceso_no_sirve_para_refrescar(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    client.cookies.set(COOKIE_REFRESCO, client.cookies.get(COOKIE_ACCESO))
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_seccion44_logout_borra_las_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert not client.cookies.get(COOKIE_ACCESO)
    assert client.get("/api/v1/auth/yo").status_code == 401


def test_logout_sin_sesion_no_falla(client: TestClient) -> None:
    # Cerrar sesion con un token caducado debe limpiar igualmente, no dejar al
    # usuario atrapado con un 401 en la pantalla de salida.
    client.cookies.clear()
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_el_login_deja_la_pista_de_sesion_y_el_logout_la_borra(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La pista es lo unico que mira el proxy del frontend para decidir si manda a alguien a /login.
    # Tiene que durar lo que el refresh token, no lo que el de acceso: si durara 30 minutos, el
    # proxy echaria a quien todavia puede renovar su sesion en silencio.
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    assert client.cookies.get(COOKIE_PISTA_SESION) == "1"

    client.post("/api/v1/auth/logout")
    assert not client.cookies.get(COOKIE_PISTA_SESION)


def test_la_pista_de_sesion_no_abre_nada(client: TestClient) -> None:
    # Es una pista para redirigir, no una credencial: con ella sola la API no reconoce a nadie.
    client.cookies.clear()
    client.cookies.set(COOKIE_PISTA_SESION, "1")
    assert client.get("/api/v1/auth/yo").status_code == 401


# --- Cambio de la contraseña propia ------------------------------------------

NUEVA = "otra-contrasena-larga-de-prueba"


def _cambiar(client: TestClient, actual: str, nueva: str) -> httpx.Response:
    return client.post(
        "/api/v1/auth/cambiar-clave",
        json={"password_actual": actual, "password_nueva": nueva},
    )


def test_cambiar_la_clave_propia(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    correo = _alta(monkeypatch)
    _entrar(client, correo)

    resp = _cambiar(client, PASSWORD, NUEVA)
    assert resp.status_code == 200, resp.text
    assert client.get("/api/v1/auth/yo").status_code == 200, "este aparato sigue dentro"

    client.cookies.clear()
    assert _entrar(client, correo).status_code == 401, "la clave anterior ya no sirve"
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo, "password": NUEVA}
        ).status_code
        == 200
    )


def test_cambiar_la_clave_exige_la_actual(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin esto, quien encontrara una sesion abierta en un aparato compartido podria quedarse con
    # la cuenta cambiando la clave.
    correo = _alta(monkeypatch)
    _entrar(client, correo)

    resp = _cambiar(client, "no-es-la-contrasena", NUEVA)
    # 400 y no 401: la sesion es valida. Un 401 haria que el cliente intentara renovarla y
    # escondiera el error real detras de un reintento.
    assert resp.status_code == 400, resp.text
    assert client.get("/api/v1/auth/yo").status_code == 200
    client.cookies.clear()
    assert _entrar(client, correo).status_code == 200, "la clave no debe haber cambiado"


def test_cambiar_la_clave_cierra_las_demas_sesiones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Quien cambia la clave porque sospecha que se la han visto espera que el intruso quede fuera.
    # El refresh token emitido antes del cambio representa a cualquier otro aparato.
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    de_otro_aparato = client.cookies.get(COOKIE_REFRESCO)

    assert _cambiar(client, PASSWORD, NUEVA).status_code == 200
    # El de este aparato, emitido con la clave nueva, sigue renovando.
    assert client.post("/api/v1/auth/refresh").status_code == 200

    client.cookies.set(COOKIE_REFRESCO, de_otro_aparato)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_cambiar_la_clave_tiene_limite_de_intentos(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Una sesion robada no debe servir para adivinar la clave a base de reintentos.
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    for _ in range(get_settings().login_max_attempts):
        assert _cambiar(client, "mal-mal-mal-mal", NUEVA).status_code == 400

    bloqueado = _cambiar(client, PASSWORD, NUEVA)
    assert bloqueado.status_code == 429
    assert "Retry-After" in bloqueado.headers


@pytest.mark.parametrize(
    ("nueva", "motivo"),
    [
        ("corta", "por debajo del minimo"),
        (PASSWORD, "igual a la actual"),
    ],
)
def test_la_clave_nueva_se_valida(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, nueva: str, motivo: str
) -> None:
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    assert _cambiar(client, PASSWORD, nueva).status_code == 422, motivo


def test_la_clave_nueva_se_guarda_como_la_leera_el_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El login recorta los espacios de los extremos. Si el cambio no lo hiciera tambien, quien
    # pusiera un espacio al final guardaria un hash que el login nunca podria reproducir.
    correo = _alta(monkeypatch)
    _entrar(client, correo)
    assert _cambiar(client, PASSWORD, f"{NUEVA} ").status_code == 200
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/login", json={"correo": correo, "password": NUEVA}
        ).status_code
        == 200
    )


def test_cambiar_la_clave_exige_sesion(client: TestClient) -> None:
    client.cookies.clear()
    assert _cambiar(client, PASSWORD, NUEVA).status_code == 401


# --- Cabeceras de seguridad ---------------------------------------------------


def test_seccion64_la_api_envia_las_cabeceras_de_seguridad(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"


def test_hsts_solo_cuando_las_cookies_son_secure(client: TestClient) -> None:
    # En desarrollo (sin HTTPS) enviar HSTS no hace nada y confunde al depurar.
    assert "Strict-Transport-Security" not in client.get("/api/v1/health").headers


# --- Defensa adicional contra CSRF (05-fase2-activos-y-campo.md, 8.2) ---------


def test_una_peticion_que_escribe_desde_otro_origen_se_rechaza(client: TestClient) -> None:
    ajeno = client.post("/api/v1/auth/logout", headers={"Origin": "https://malicioso.example"})
    assert ajeno.status_code == 403
    propio = client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"})
    assert propio.status_code == 204


def test_las_lecturas_no_miran_el_origen(client: TestClient) -> None:
    resp = client.get("/api/v1/health", headers={"Origin": "https://malicioso.example"})
    assert resp.status_code == 200
