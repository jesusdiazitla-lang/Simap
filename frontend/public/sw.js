/*
 * Service worker de SIMAP (05-fase2-activos-y-campo.md, sección 7.5).
 *
 * QUÉ HACE
 * --------
 * Que la aplicación **abra sin cobertura**: en una sala de máquinas sin red, el operario escanea la
 * etiqueta y la pantalla del equipo aparece igual, con los datos que guardó la última vez y los
 * formularios funcionando (lo que registre va a la cola del teléfono, `src/lib/offline-queue.ts`).
 *
 * - **Precarga** el cascarón de la pantalla del equipo (`/equipo`, que se sirve en todas las
 *   `/a/{código}`) con su JavaScript y su CSS, y la página «Sin conexión». Así funciona aunque no se
 *   haya escaneado nada con red todavía.
 * - **Recursos estáticos** (`/_next/static/...`): primero la caché. Next les pone en el nombre una
 *   huella de su contenido, así que una versión nueva tiene otro nombre y nunca se sirve una vieja
 *   por error.
 * - **Pantallas**: primero la red; si no hay, la última copia guardada de esa pantalla; si tampoco,
 *   la página «Sin conexión». Se guardan solo pantallas que llegaron bien y sin redirección: una
 *   redirección al acceso guardada como «el panel» dejaría a alguien sin panel offline para siempre.
 *
 * QUÉ NO HACE NUNCA
 * -----------------
 * **No guarda respuestas de la API.** Son datos de una persona y una empresa: en un teléfono
 * compartido entre turnos, una caché del navegador se los serviría a quien venga después. Los datos
 * para consultar sin red los guarda la aplicación, por persona, en IndexedDB, y los borra al cerrar
 * sesión. Las pantallas que sí se guardan son cascarones sin datos: todas piden lo suyo a la API.
 *
 * Al cambiar algo aquí, sube VERSION: el navegador instala la versión nueva y `activate` borra las
 * cachés de la anterior.
 */

const VERSION = "simap-v2";
const ESTATICO = `${VERSION}-estatico`;
const PANTALLAS = `${VERSION}-pantallas`;
const SIN_CONEXION = "/offline.html";
const CASCARON_EQUIPO = "/equipo";

/** Descarga el cascarón y todos los recursos que nombra su HTML. Lo que falle, no tumba la instalación. */
async function precargar() {
  const estatico = await caches.open(ESTATICO);
  await estatico.add(SIN_CONEXION);
  try {
    const respuesta = await fetch(CASCARON_EQUIPO, { credentials: "same-origin" });
    if (!respuesta.ok || respuesta.redirected) return;
    const html = await respuesta.clone().text();
    await (await caches.open(PANTALLAS)).put(CASCARON_EQUIPO, respuesta);
    const recursos = new Set(html.match(/\/_next\/static\/[^"'\s)\\]+/g) ?? []);
    await Promise.all(
      [...recursos].map((url) => estatico.add(url).catch(() => undefined)),
    );
  } catch {
    // Sin red durante la instalación: el cascarón se guardará la primera vez que se abra con red.
  }
}

self.addEventListener("install", (evento) => {
  evento.waitUntil(precargar());
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(claves.filter((c) => !c.startsWith(VERSION)).map((c) => caches.delete(c))),
      )
      .then(() => self.clients.claim()),
  );
});

function esPantallaDeEquipo(url) {
  return /^\/a\/[^/]+$/.test(url.pathname);
}

async function navegar(peticion) {
  const url = new URL(peticion.url);
  try {
    const respuesta = await fetch(peticion);
    const esHtml = (respuesta.headers.get("content-type") ?? "").includes("text/html");
    if (respuesta.ok && !respuesta.redirected && esHtml) {
      const cache = await caches.open(PANTALLAS);
      // Todas las etiquetas comparten cascarón: se guarda una vez, bajo su propio nombre.
      const clave = esPantallaDeEquipo(url) ? CASCARON_EQUIPO : url.pathname;
      await cache.put(clave, respuesta.clone());
    }
    return respuesta;
  } catch {
    const cache = await caches.open(PANTALLAS);
    const guardada =
      (await cache.match(url.pathname)) ??
      (esPantallaDeEquipo(url) ? await cache.match(CASCARON_EQUIPO) : undefined);
    return guardada ?? (await caches.match(SIN_CONEXION)) ?? Response.error();
  }
}

async function estatico(peticion) {
  const cache = await caches.open(ESTATICO);
  const guardado = await cache.match(peticion);
  if (guardado) return guardado;
  const respuesta = await fetch(peticion);
  if (respuesta.ok) await cache.put(peticion, respuesta.clone());
  return respuesta;
}

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;
  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;
  // La API, nunca: ni la caché ni respuestas de respaldo. Sin red, falla y la aplicación lo sabe.
  if (url.pathname.startsWith("/api/")) return;

  if (peticion.mode === "navigate") {
    evento.respondWith(navegar(peticion));
    return;
  }
  if (url.pathname.startsWith("/_next/static/")) {
    evento.respondWith(estatico(peticion));
  }
});
