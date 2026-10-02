"use client";

/**
 * Registra el service worker (`public/sw.js`).
 *
 * Solo en la compilación de producción: en `next dev` el worker interceptaría las navegaciones de
 * la recarga en caliente y, si algo fallara, enseñaría la página sin conexión en lugar del error
 * real de desarrollo.
 *
 * Se registra después de `load` para no competir con la hidratación por la red en el primer
 * arranque, que en una planta con cobertura irregular es justo cuando más cuesta.
 */

import { useEffect } from "react";

export function RegistroServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    const registrar = (): void => {
      // Un fallo aquí no debe molestar a nadie: sin worker, la aplicación funciona igual con red.
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
    };
    if (document.readyState === "complete") {
      registrar();
      return;
    }
    window.addEventListener("load", registrar, { once: true });
    return () => window.removeEventListener("load", registrar);
  }, []);

  return null;
}
