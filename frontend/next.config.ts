import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
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
