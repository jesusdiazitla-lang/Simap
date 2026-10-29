import type { NextConfig } from "next";

/**
 * Dónde está el backend, visto desde el servidor de Next (no desde el navegador).
 *
 * El navegador nunca habla con el backend directamente: pide `/api/...` al mismo origen del
 * frontend y Next lo reenvía aquí (05-fase2-activos-y-campo.md, sección 8.2). Así la cookie de
 * sesión es siempre del mismo sitio, sin CORS y con `SameSite=Lax`, también en producción, donde
 * frontend y backend viven en dominios distintos y una cookie de otro sitio no viajaría.
 */
const API_ORIGEN = (process.env.API_ORIGEN ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Carpeta de la compilación. Por defecto `.next`; `NEXT_DIST_DIR` permite compilar y servir una
  // segunda copia (para las pruebas e2e) sin pisar la que esté sirviendo `next start`: recompilar
  // encima de un servidor vivo deja la página sin estilos (pasó el 2026-10-07).
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // No anunciar el framework en cada respuesta (OWASP A02).
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:ruta*", destination: `${API_ORIGEN}/api/:ruta*` },
      // Todas las etiquetas QR apuntan a `/a/{código}`, una dirección distinta por equipo. Se sirven
      // todas con la misma página estática, que lee el código de la barra de direcciones. Al ser una
      // sola página sin datos, el service worker la guarda una vez y la pantalla del equipo abre
      // sin cobertura para cualquier código (05-fase2-activos-y-campo.md, 7.5).
      { source: "/a/:codigo", destination: "/equipo" },
    ];
  },
  async redirects() {
    return [
      // El acceso del operador se unificó con el de las plantas en `/login` (ver
      // `src/lib/acceso.ts`). Se conserva la dirección vieja para no romper enlaces guardados.
      { source: "/operador/login", destination: "/login", permanent: false },
    ];
  },
  async headers() {
    return [
      {
        // Lo que no depende de la petición (08-fase5, 10.2). La CSP, con su nonce, la pone
        // `src/proxy.ts` en cada página. La cámara se permite al propio sitio: el escáner de QR.
        source: "/:ruta*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          ...(process.env.NODE_ENV === "production"
            ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
            : []),
        ],
      },
      {
        // El service worker no se cachea nunca: si el navegador guardara una copia, una versión
        // nueva tardaría hasta un día en llegar a los teléfonos. `Service-Worker-Allowed` no hace
        // falta porque se sirve desde la raíz y su alcance es la raíz.
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
        ],
      },
    ];
  },
};

export default nextConfig;
