/**
 * Iconos de la aplicación: trazo de 1,75 px, esquinas redondeadas, 20 × 20, color heredado.
 *
 * Dibujados aquí en lugar de traer una biblioteca entera para siete iconos. Todos con el mismo trazo
 * y la misma caja, para que se lean como un solo sistema. Siempre acompañan a un texto: son
 * decorativos para el lector de pantalla (`aria-hidden`), y el significado lo lleva la palabra.
 */

import type { ReactNode } from "react";

function Base({ children, className }: { readonly children: ReactNode; readonly className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={["shrink-0", className ?? ""].join(" ")}
    >
      {children}
    </svg>
  );
}

type Props = { readonly className?: string };

export function IconoSinRed({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M2 8.8a15 15 0 0 1 4.2-2.6M9.8 5.2A15 15 0 0 1 22 8.8M5 12.5a10 10 0 0 1 3.8-2.1M15.4 10.6a10 10 0 0 1 3.6 1.9M8.5 16a5 5 0 0 1 7 0" />
      <path d="M12 20h.01M3 3l18 18" />
    </Base>
  );
}

export function IconoPendiente({ className }: Props) {
  return (
    <Base className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Base>
  );
}

export function IconoHecho({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M4 12.5l5 5L20 6.5" />
    </Base>
  );
}

export function IconoAviso({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M12 3.5L2.5 20h19L12 3.5z" />
      <path d="M12 10v4.5M12 17.5h.01" />
    </Base>
  );
}

export function IconoEscanear({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" />
      <path d="M8 12h8" />
    </Base>
  );
}

export function IconoBaja({ className }: Props) {
  return (
    <Base className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M5.6 5.6l12.8 12.8" />
    </Base>
  );
}

export function IconoImprimir({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M7 9V3h10v6M7 17H4v-7a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v7h-3" />
      <path d="M7 14h10v7H7z" />
    </Base>
  );
}
