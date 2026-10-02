/*
 * Service worker mínimo de SIMAP (04-fase1-fundamentos.md, sección 4.7: «manifest, ícono, service
 * worker mínimo»).
 *
 * Hace UNA cosa: si una pantalla no se puede cargar porque no hay red, enseña /offline.html en vez
 * del dinosaurio del navegador. Nada más, y es deliberado:
 *
 * - No guarda en caché ninguna respuesta de la API. Servir datos de mantenimiento viejos como si
 *   fueran actuales es peor que no servir nada: alguien decidiría sobre un equipo con una lectura
 *   de ayer creyendo que es de hoy.
 * - No guarda en caché el JavaScript ni el CSS de la aplicación. Next les pone nombres con huella
 *   y ya viajan con caché del navegador; cachearlos aquí además obliga a gestionar versiones, y un
 *   error en eso deja a la gente con una aplicación vieja que no se actualiza.
 * - Solo intercepta navegaciones. Las peticiones a la API pasan sin tocar.
 *
 * El trabajo sin conexión de verdad —la cola de reportes que se envía sola al volver la red— es de
 * la fase 2 (`src/lib/offline-queue.ts`) y se construirá sobre este archivo.
 *
 * Al cambiar algo aquí, sube VERSION: así el navegador instala la nueva y `activate` borra la caché
 * de la anterior.
 */

const VERSION = "simap-v1";
const SIN_CONEXION = "/offline.html";

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSION).then((cache) => cache.add(SIN_CONEXION)));
  // Sin esperar a que se cierren las pestañas abiertas: este worker no cambia ninguna respuesta
  // que funcione, así que no hay nada que pueda romper a mitad de una sesión.
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(claves.filter((c) => c !== VERSION).map((c) => caches.delete(c))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  if (evento.request.mode !== "navigate") return;
  evento.respondWith(
    fetch(evento.request).catch(async () => {
      const pagina = await caches.match(SIN_CONEXION);
      return pagina ?? Response.error();
    }),
  );
});
