/**
 * Desvío previo a cualquier página: sin sesión, al acceso (04-fase1-fundamentos.md, sección 4.7).
 *
 * El documento lo llama `middleware.ts`; desde Next.js 16 la convención se llama `proxy.ts`. Es la
 * misma pieza.
 *
 * ESTO NO ES CONTROL DE ACCESO
 * ----------------------------
 * Es una comprobación optimista, como recomienda la guía de autenticación de Next: evita que
 * alguien sin sesión vea durante un instante el esqueleto de una pantalla que no puede usar. El
 * permiso de verdad lo decide la API en cada petición —JWT, rol y Row-Level Security—, y una
 * página a la que el proxy deja pasar sin derecho recibe un 401 al pedir sus datos y devuelve al
 * usuario al acceso.
 *
 * QUÉ MIRA Y POR QUÉ NO MIRA EL TOKEN
 * -----------------------------------
 * Mira una cookie-pista (`simap_sesion`, o `simap_op_sesion` en la consola) que la API pone y quita
 * junto con la sesión y que no vale para nada más. No mira el token de acceso porque caduca a los
 * 30 minutos mientras la sesión sigue viva siete días: hacerlo echaría a quien todavía puede
 * renovar en silencio. Ver `COOKIE_PISTA_SESION` en `backend/app/core/auth.py`.
 *
 * TRES REGLAS QUE EVITAN BUCLES Y SORPRESAS
 * -----------------------------------------
 * 1. **Nunca se desvía una pantalla de acceso.** Si el proxy mandara a `/panel` a quien llega a
 *    `/login` con pista, una pista caducada produciría un bucle infinito entre las dos.
 * 2. **Solo actúa si puede ver la pista.** Las cookies son del host que las pone. Si la API vive en
 *    otro host, el navegador no manda su pista a estas páginas y su ausencia no significa nada; el
 *    proxy entonces se aparta y cada página comprueba la sesión por su cuenta, como hacía antes.
 * 3. **Se protege todo por defecto.** Lo público se enumera; una pantalla nueva nace protegida, igual
 *    que en el backend un endpoint sin roles declarados se rechaza.
 */

import { NextResponse, type NextRequest } from "next/server";

/** Nombres repetidos de `backend/app/core/auth.py`. Si cambian allí, hay que cambiarlos aquí. */
const PISTA_SESION = "simap_sesion";
const PISTA_OPERADOR = "simap_op_sesion";

/**
 * Pantallas que se ven sin sesión. Ninguna se desvía nunca (regla 1).
 *
 * `/equipo` es el cascarón vacío que se sirve en `/a/{código}` (ver `next.config.ts`): no contiene
 * ningún dato —los pide a la API, que sí exige sesión—, y tiene que poder descargarse sin sesión
 * para que el service worker lo guarde y la pantalla del equipo abra sin cobertura. `/a/...` sí
 * está protegida: es la dirección que se escanea.
 */
const PUBLICAS = new Set(["/login", "/equipo"]);

function esConsola(ruta: string): boolean {
  return ruta === "/operador" || ruta.startsWith("/operador/");
}

/**
 * True si las cookies que pone la API llegan a esta página (regla 2).
 *
 * Con la API reenviada por Next (lo normal, ver `next.config.ts`) la URL es relativa y la pista
 * siempre se ve. Si alguien apunta `NEXT_PUBLIC_API_URL` a un backend directo, cuenta el nombre de
 * host: las cookies no distinguen puertos, así que `localhost:3000` sí ve las de `localhost:8000`.
 */
function pistaVisible(request: NextRequest): boolean {
  const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
  try {
    return new URL(api, request.url).hostname === request.nextUrl.hostname;
  } catch {
    return false;
  }
}

/**
 * Política de seguridad de contenido con un nonce nuevo en cada petición (08-fase5, 10.2).
 *
 * Ningún script ni estilo en línea se ejecuta si no lleva el nonce: un XSS que logre meter un
 * `<script>` en el marcado no lo ve ejecutarse. Next lee el nonce de esta cabecera al renderizar y
 * se lo pone a sus propios scripts; por eso todas las páginas se renderizan por petición
 * (`connection()` en el layout raíz). `'strict-dynamic'` deja que los scripts de confianza carguen
 * los suyos y hace que el navegador ignore `'self'` en `script-src`; el service worker se registra
 * por `worker-src`, que por eso se declara aparte: sin él, el modo sin conexión dejaría de instalarse.
 * En desarrollo React necesita `'unsafe-eval'` para reconstruir pilas de llamadas; en producción no.
 */
function politicaDeContenido(nonce: string, https: boolean): string {
  const desarrollo = process.env.NODE_ENV !== "production";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${desarrollo ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    // Solo por HTTPS: en la red de la planta, por http://192.168.x.x, subiría a https cada recurso y
    // la página no cargaría desde el teléfono.
    ...(https ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}

/** Sigue a la página con el nonce en la petición (para que Next lo lea) y la CSP en la respuesta. */
function seguir(request: NextRequest, nonce: string, csp: string): NextResponse {
  const cabeceras = new Headers(request.headers);
  cabeceras.set("x-nonce", nonce);
  cabeceras.set("content-security-policy", csp);
  const respuesta = NextResponse.next({ request: { headers: cabeceras } });
  respuesta.headers.set("content-security-policy", csp);
  return respuesta;
}

function hacia(request: NextRequest, ruta: string): NextResponse {
  return NextResponse.redirect(new URL(ruta, request.url));
}

/**
 * Al acceso, recordando a dónde iba (05-fase2-activos-y-campo.md, 7.2): quien escanea una etiqueta
 * sin sesión vuelve a ese equipo después de entrar, no a su panel. El login valida el destino antes
 * de usarlo (`destinoSeguro` en `src/lib/qr.ts`).
 */
function alAcceso(request: NextRequest): NextResponse {
  const destino = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const url = new URL("/login", request.url);
  url.searchParams.set("next", destino);
  return NextResponse.redirect(url);
}

export function proxy(request: NextRequest): NextResponse {
  const ruta = request.nextUrl.pathname;
  const nonce = btoa(crypto.randomUUID());
  const csp = politicaDeContenido(nonce, request.nextUrl.protocol === "https:");
  const pasar = () => seguir(request, nonce, csp);

  if (PUBLICAS.has(ruta) || !pistaVisible(request)) return pasar();

  if (esConsola(ruta)) {
    // Sin `next`: el acceso es el mismo para todos y el operador va siempre a su consola.
    return request.cookies.has(PISTA_OPERADOR) ? pasar() : hacia(request, "/login");
  }

  const conSesion = request.cookies.has(PISTA_SESION);
  // La raíz no tiene contenido propio: solo decide a dónde ir. Hacerlo aquí evita la pantalla
  // intermedia «Comprobando tu sesión…» en el caso normal.
  if (ruta === "/") return hacia(request, conSesion ? "/panel" : "/login");
  return conSesion ? pasar() : alAcceso(request);
}

export const config = {
  // Fuera: la API (si algún día se sirve desde aquí), los recursos de Next y cualquier archivo con
  // extensión de `public/` —manifiesto, iconos, service worker, página sin conexión—. Sin esta
  // exclusión, el desvío bloquearía también el CSS de la propia pantalla de acceso.
  matcher: ["/((?!api/|_next/|.*\\.[a-zA-Z0-9]+$).*)"],
};
