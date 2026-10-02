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

/** Pantallas que se ven sin sesión. Ninguna se desvía nunca (regla 1). */
const PUBLICAS = new Set(["/login", "/operador/login"]);

function esConsola(ruta: string): boolean {
  return ruta === "/operador" || ruta.startsWith("/operador/");
}

/**
 * True si las cookies que pone la API llegan a esta página (regla 2).
 *
 * Las cookies no distinguen puertos, así que `localhost:3000` ve las de `localhost:8000`. Lo que
 * importa es el nombre de host. Una URL relativa (API servida desde el mismo dominio) también vale.
 */
function pistaVisible(request: NextRequest): boolean {
  const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  try {
    return new URL(api, request.url).hostname === request.nextUrl.hostname;
  } catch {
    return false;
  }
}

function hacia(request: NextRequest, ruta: string): NextResponse {
  return NextResponse.redirect(new URL(ruta, request.url));
}

export function proxy(request: NextRequest): NextResponse {
  const ruta = request.nextUrl.pathname;

  if (PUBLICAS.has(ruta) || !pistaVisible(request)) return NextResponse.next();

  if (esConsola(ruta)) {
    return request.cookies.has(PISTA_OPERADOR) ? NextResponse.next() : hacia(request, "/operador/login");
  }

  const conSesion = request.cookies.has(PISTA_SESION);
  // La raíz no tiene contenido propio: solo decide a dónde ir. Hacerlo aquí evita la pantalla
  // intermedia «Comprobando tu sesión…» en el caso normal.
  if (ruta === "/") return hacia(request, conSesion ? "/panel" : "/login");
  return conSesion ? NextResponse.next() : hacia(request, "/login");
}

export const config = {
  // Fuera: la API (si algún día se sirve desde aquí), los recursos de Next y cualquier archivo con
  // extensión de `public/` —manifiesto, iconos, service worker, página sin conexión—. Sin esta
  // exclusión, el desvío bloquearía también el CSS de la propia pantalla de acceso.
  matcher: ["/((?!api/|_next/|.*\\.[a-zA-Z0-9]+$).*)"],
};
