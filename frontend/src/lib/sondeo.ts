/**
 * Volver a pedir los datos cada cierto tiempo mientras la pestaña está a la vista (06-fase3, 9.4).
 *
 * Sin canal en tiempo real: la bandeja y el detalle de una orden consultan cada 30 segundos. Con la
 * pestaña oculta no se pide nada —es batería y datos de un teléfono que nadie mira—, y al volver a
 * ella se pide en el acto. El servidor responde con ETag, así que si nada cambió la respuesta es un
 * 304 que el navegador resuelve con la copia que ya tenía.
 */

import { useEffect, useRef } from "react";

export const INTERVALO_SONDEO_MS = 30_000;

export function useSondeo(recargar: () => void, intervalo = INTERVALO_SONDEO_MS): void {
  // La función más reciente, sin reiniciar el temporizador cada vez que cambia.
  const ultima = useRef(recargar);
  useEffect(() => {
    ultima.current = recargar;
  }, [recargar]);

  useEffect(() => {
    let temporizador: ReturnType<typeof setInterval> | null = null;
    const arrancar = () => {
      if (temporizador === null) temporizador = setInterval(() => ultima.current(), intervalo);
    };
    const parar = () => {
      if (temporizador !== null) clearInterval(temporizador);
      temporizador = null;
    };
    const alCambiarVisibilidad = () => {
      if (document.visibilityState === "visible") {
        ultima.current();
        arrancar();
      } else {
        parar();
      }
    };
    if (document.visibilityState === "visible") arrancar();
    document.addEventListener("visibilitychange", alCambiarVisibilidad);
    return () => {
      parar();
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
    };
  }, [intervalo]);
}
