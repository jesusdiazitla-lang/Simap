import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { connection } from "next/server";
import "./globals.css";

import { RegistroServiceWorker } from "@/components/registro-sw";

/**
 * Inter, una sola familia para todo el producto.
 *
 * Es la letra neutra de las herramientas de trabajo: alta legibilidad a tamaños pequeños, cifras
 * tabulares de verdad y ninguna opinión propia. Aquí eso es una virtud, no una carencia: la pantalla
 * tiene que desaparecer detrás de la tarea, y una tipografía con carácter compite con el dato.
 *
 * Sustituye a Libre Franklin, que se había elegido por su parentesco con la imprenta industrial
 * cuando la interfaz imitaba una bitácora de papel. Retirada esa metáfora, el motivo desapareció con
 * ella, y mantenerla habría sido conservar un rasgo expresivo por apego.
 *
 * Una sola familia es lo correcto en una interfaz de trabajo: la jerarquía la llevan el peso y el
 * tamaño, no un segundo tipo de titulares. `display: "swap"` para que el texto nunca quede invisible
 * esperando la descarga, que en una planta con cobertura irregular pasaría a menudo.
 */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: {
    default: "SIMAP",
    template: "%s · SIMAP",
  },
  description:
    "Sistema Inteligente de Mantenimiento Predictivo: predice la falla de equipos industriales a " +
    "partir del horómetro y los reportes del personal de planta, sin necesidad de sensores.",
  applicationName: "SIMAP",
  manifest: "/manifest.webmanifest",
  // La API no es indexable y la aplicación es privada: nada de esto debe aparecer en un buscador.
  robots: { index: false, follow: false },
  appleWebApp: {
    capable: true,
    title: "SIMAP",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // NO se pone maximumScale ni userScalable: false. Impedir el zoom en una pantalla que se usa con
  // guantes, a contraluz y a veces con gafas de seguridad es quitarle la única ayuda que le queda a
  // quien no ve bien el renglón.
  // Los dos valores salen de `--lienzo` en cada tema (globals.css) y tienen que seguirlo: si se
  // quedan atrás, la barra del navegador se pinta de un color que ya no existe en la aplicación.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f1f3f5" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1215" },
  ],
};

/**
 * Todas las páginas se renderizan por petición: la CSP lleva un nonce nuevo en cada una (ver
 * `src/proxy.ts`) y Next solo puede ponérselo a sus scripts al renderizar. Una página estática
 * saldría sin nonce y el navegador bloquearía sus propios scripts (08-fase5, 10.2).
 */
export default async function RootLayout({ children }: LayoutProps<"/">) {
  await connection();
  return (
    <html lang="es" className={`${inter.variable} h-full`}>
      <body className="flex min-h-full flex-col font-sans">
        {children}
        <RegistroServiceWorker />
      </body>
    </html>
  );
}
