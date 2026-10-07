/**
 * Cliente HTTP de la API de SIMAP.
 *
 * NO HAY NINGÚN TOKEN EN ESTE ARCHIVO, Y ES LO IMPORTANTE
 * -------------------------------------------------------
 * La sesión viaja en cookies `httpOnly`, así que el JavaScript de la página no puede leerla ni
 * escribirla: no hay nada que guardar en `localStorage` ni cabecera `Authorization` que construir.
 * Lo único que hace falta es `credentials: "include"` en cada petición, para que el navegador
 * adjunte esas cookies aunque la API esté en otro puerto. Esa es toda la gestión de tokens del
 * frontend, y es deliberadamente aburrida: un XSS en esta página no puede robar la sesión porque no
 * tiene forma de leerla.
 *
 * El backend solo acepta el origen del frontend en su lista blanca de CORS (`cors_origins`), nunca
 * `*`, porque con `*` el navegador se niega a enviar credenciales.
 */

/**
 * Base de la API: **el mismo origen del frontend**. Next reenvía `/api/*` al backend (ver
 * `next.config.ts`), así que el navegador nunca habla con otro sitio y la cookie de sesión viaja
 * como cookie propia, también en producción (05-fase2-activos-y-campo.md, sección 8.2). Se puede
 * sobrescribir para apuntar a un backend directamente, pero entonces vuelve el problema de las
 * cookies de otro sitio.
 */
export const BASE_API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "/api/v1";

/** Errores de validación agrupados por nombre de campo, tal como los pinta el formulario. */
export type ErroresDeCampo = Readonly<Record<string, string>>;

/**
 * Fallo de una llamada a la API con el detalle que la interfaz necesita para reaccionar.
 *
 * Se distingue del `Error` genérico porque la pantalla tiene que tratar de forma distinta un 401
 * (credenciales), un 422 (campos concretos), un 429 (esperar) y una caída de red.
 */
export class ErrorApi extends Error {
  constructor(
    /** Código HTTP, o 0 cuando la petición no llegó a salir (red caída, servidor apagado). */
    readonly estado: number,
    mensaje: string,
    /** Errores por campo de un 422, vacío en cualquier otro caso. */
    readonly campos: ErroresDeCampo = {},
    /** Segundos que pide esperar un 429, si el servidor los indicó. */
    readonly esperaSegundos?: number,
  ) {
    super(mensaje);
    this.name = "ErrorApi";
  }

  /** La API no respondió: no hay red, o el backend no está levantado. */
  get esFalloDeRed(): boolean {
    return this.estado === 0;
  }
}

/** Forma de un error de validación de FastAPI (Pydantic v2). */
interface DetallePydantic {
  readonly loc: readonly (string | number)[];
  readonly msg: string;
}

function esListaDePydantic(valor: unknown): valor is readonly DetallePydantic[] {
  return (
    Array.isArray(valor) &&
    valor.every(
      (e) => typeof e === "object" && e !== null && "loc" in e && "msg" in e,
    )
  );
}

/**
 * Traduce el `detail` de FastAPI a algo que se pueda pintar junto al campo culpable.
 *
 * Un 422 llega como lista de errores con la ruta del campo en `loc`, que empieza por `"body"`. Se
 * descarta ese primer tramo porque al usuario no le dice nada de dónde está el problema.
 */
function camposDesdeDetalle(detalle: unknown): ErroresDeCampo {
  if (!esListaDePydantic(detalle)) return {};
  const campos: Record<string, string> = {};
  for (const error of detalle) {
    const ruta = error.loc.filter((parte) => parte !== "body");
    const campo = ruta.length > 0 ? String(ruta[ruta.length - 1]) : "_";
    // Se conserva el primer error de cada campo: mostrar tres mensajes sobre el mismo input
    // convierte una corrección en una lista de deberes.
    campos[campo] ??= error.msg;
  }
  return campos;
}

function mensajeDesdeDetalle(detalle: unknown, porDefecto: string): string {
  if (typeof detalle === "string" && detalle.trim() !== "") return detalle;
  return porDefecto;
}

const MENSAJES_POR_ESTADO: Readonly<Record<number, string>> = {
  401: "Correo o contraseña incorrectos.",
  403: "Tu rol no tiene permiso para esta acción.",
  404: "No encontrado.",
  422: "Revisa los datos marcados.",
  429: "Demasiados intentos. Espera un momento antes de volver a probar.",
  500: "El servidor tuvo un problema. Vuelve a intentarlo en un momento.",
};

/**
 * Promesa de refresco en curso, compartida por todas las llamadas.
 *
 * Sin esto, si tres peticiones simultáneas reciben 401 se dispararían tres refrescos. Como el
 * backend **rota** el refresh token y revoca el anterior en el mismo paso, el segundo refresco
 * llegaría con un token ya revocado y cerraría la sesión de un usuario que no hizo nada mal.
 */
let refrescoEnCurso: Promise<boolean> | null = null;

async function refrescarSesion(): Promise<boolean> {
  refrescoEnCurso ??= (async () => {
    try {
      const resp = await fetch(`${BASE_API}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      // Se libera en el `finally` del IIFE y no del `try`, para que un fallo no deje el cerrojo
      // puesto y bloquee todos los refrescos posteriores de la sesión.
      refrescoEnCurso = null;
    }
  })();
  return refrescoEnCurso;
}

interface Opciones {
  readonly method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  readonly cuerpo?: unknown;
  /** Desactiva el reintento tras refrescar. Lo usan las rutas de sesión para no entrar en bucle. */
  readonly sinRefrescar?: boolean;
  readonly signal?: AbortSignal;
}

async function lanzarSiFalla(resp: Response): Promise<void> {
  if (resp.ok) return;
  let detalle: unknown;
  try {
    detalle = ((await resp.json()) as { detail?: unknown }).detail;
  } catch {
    detalle = undefined;
  }
  const porDefecto = MENSAJES_POR_ESTADO[resp.status] ?? `Error ${resp.status}.`;
  const reintentar = resp.headers.get("Retry-After");
  throw new ErrorApi(
    resp.status,
    mensajeDesdeDetalle(detalle, porDefecto),
    camposDesdeDetalle(detalle),
    reintentar !== null ? Number(reintentar) : undefined,
  );
}

/**
 * Llama a la API y devuelve el cuerpo ya interpretado.
 *
 * Ante un 401 intenta refrescar la sesión una sola vez y reintenta. Eso es lo que hace que el token
 * de acceso pueda caducar a los 30 minutos sin que a media jornada le salte un formulario de acceso
 * a alguien que está en mitad de un reporte.
 */
export async function llamar<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const { method = "GET", cuerpo, sinRefrescar = false, signal } = opciones;

  const enviar = (): Promise<Response> =>
    fetch(`${BASE_API}${ruta}`, {
      method,
      // Sin esto no se envían las cookies de sesión y todo responde 401. Es la única línea del
      // cliente de la que depende la autenticación entera.
      credentials: "include",
      headers: cuerpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      signal,
    });

  let resp: Response;
  try {
    resp = await enviar();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ErrorApi(0, "No se pudo conectar con el servidor de SIMAP.");
  }

  if (resp.status === 401 && !sinRefrescar) {
    if (await refrescarSesion()) {
      try {
        resp = await enviar();
      } catch {
        throw new ErrorApi(0, "No se pudo conectar con el servidor de SIMAP.");
      }
    }
  }

  await lanzarSiFalla(resp);
  // 204 no tiene cuerpo; intentar interpretarlo como JSON revienta.
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
