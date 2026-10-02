"use client";

/**
 * Raíz de la aplicación: decide a dónde va quien llega.
 *
 * No hay página de inicio pública. SIMAP no vende nada desde aquí —el alta de empresas es por
 * invitación— así que la raíz solo resuelve un desvío: al panel si hay sesión, al acceso si no.
 *
 * Tiene que preguntar al servidor para saberlo, porque la sesión vive en una cookie `httpOnly` que
 * este código no puede leer. Ese viaje tarda algo, así que mientras se resuelve se dibuja el mismo
 * marco que van a tener las dos pantallas posibles: así el desvío no parpadea entre dos fondos.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Marco, Panel } from "@/components/marco";
import { usuarioActual } from "@/lib/auth";

export default function InicioPage() {
  const router = useRouter();

  useEffect(() => {
    const control = new AbortController();
    void (async () => {
      try {
        const usuario = await usuarioActual(control.signal);
        router.replace(usuario === null ? "/login" : "/panel");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        // Si el servidor no responde, el acceso es el destino útil: desde allí el mensaje de error
        // explica que no hay conexión, en vez de dejar esta pantalla intermedia colgada.
        router.replace("/login");
      }
    })();
    return () => control.abort();
  }, [router]);

  return (
    <Marco centrado>
      <div className="mx-auto w-full max-w-[26rem]">
        <Panel titulo="Abriendo SIMAP">
          <p aria-live="polite" className="text-[0.9375rem] leading-6 text-texto-suave">
            Comprobando tu sesión…
          </p>
        </Panel>
      </div>
    </Marco>
  );
}
