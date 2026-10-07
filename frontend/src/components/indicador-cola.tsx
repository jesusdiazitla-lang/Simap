"use client";

/**
 * Estado de la red y de la cola sin conexión, siempre a la vista (05-fase2-activos-y-campo.md, 7.5).
 *
 * Quien captura tiene que saber qué llegó y qué no. Tres estados, cada uno con palabra e icono —nunca
 * solo un color—:
 *
 * - **Sin conexión**: lo que se registre ahora se guarda en el teléfono.
 * - **N pendientes**: hay capturas guardadas que aún no llegaron.
 * - **Enviado**: lo pendiente acaba de llegar. Se ve unos segundos y desaparece.
 *
 * Si no hay nada que decir, no ocupa sitio. Es una región de estado única y atómica: el lector de
 * pantalla anuncia «3 pendientes por enviar», no un número suelto.
 */

import { useEffect, useState, useSyncExternalStore } from "react";

import { IconoHecho, IconoPendiente, IconoSinRed } from "@/components/iconos";
import { estadoCola, estadoColaServidor, suscribirCola } from "@/lib/offline-queue";

const SEGUNDOS_ENVIADO = 5;

export function IndicadorCola() {
  const cola = useSyncExternalStore(suscribirCola, estadoCola, estadoColaServidor);
  // «Enviado» se muestra mientras el último envío no se haya dado por visto. Se deriva del estado en
  // vez de encenderse con un setState dentro del efecto, que forzaría un render de más; el efecto
  // solo programa cuándo apagarlo.
  const [visto, setVisto] = useState<number | null>(null);
  const mostrarEnviado = cola.ultimoEnvio !== null && visto !== cola.ultimoEnvio;

  useEffect(() => {
    const envio = cola.ultimoEnvio;
    if (envio === null) return;
    const t = setTimeout(() => setVisto(envio), SEGUNDOS_ENVIADO * 1000);
    return () => clearTimeout(t);
  }, [cola.ultimoEnvio]);

  let contenido: React.ReactNode = null;
  if (!cola.enLinea) {
    contenido = (
      <>
        <IconoSinRed className="h-4 w-4" />
        Sin conexión{cola.pendientes > 0 ? ` · ${cola.pendientes} por enviar` : ""}
      </>
    );
  } else if (cola.pendientes > 0) {
    contenido = (
      <>
        <IconoPendiente className="h-4 w-4" />
        {cola.sincronizando
          ? "Enviando…"
          : `${cola.pendientes} ${cola.pendientes === 1 ? "pendiente" : "pendientes"} por enviar`}
      </>
    );
  } else if (mostrarEnviado) {
    contenido = (
      <>
        <IconoHecho className="h-4 w-4" />
        Enviado
      </>
    );
  }

  const tono = !cola.enLinea
    ? "border-estado-aviso text-estado-aviso"
    : cola.pendientes > 0
      ? "border-borde-fuerte text-texto-suave"
      : "border-estado-ok text-estado-ok";

  return (
    <span role="status" aria-atomic="true" className="empty:hidden">
      {contenido !== null ? (
        <span
          className={[
            "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-[var(--radius-control)] border bg-superficie px-2.5",
            "text-[0.8125rem] font-semibold",
            tono,
          ].join(" ")}
        >
          {contenido}
        </span>
      ) : null}
    </span>
  );
}
