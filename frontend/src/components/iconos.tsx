/**
 * Iconos de la aplicación: trazo de 1,75 px, esquinas redondeadas, 20 × 20, color heredado.
 *
 * Dibujados aquí en lugar de traer una biblioteca entera para unos pocos iconos. Todos con el mismo trazo
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

// --- Menú lateral ------------------------------------------------------------

export function IconoInicio({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M4 10.5L12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />
    </Base>
  );
}

export function IconoEquipos({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M3 20h18V9l-6 4V9l-6 4V5H5a2 2 0 0 0-2 2z" />
      <path d="M7 16.5h2M13 16.5h2" />
    </Base>
  );
}

export function IconoRevision({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M8.5 4.5H6a1 1 0 0 0-1 1V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5.5a1 1 0 0 0-1-1h-2.5" />
      <path d="M8.5 3h7v3h-7z" />
      <path d="M9 13.5l2 2 4-4.5" />
    </Base>
  );
}

export function IconoPersonal({ className }: Props) {
  return (
    <Base className={className}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8" />
    </Base>
  );
}

export function IconoCuenta({ className }: Props) {
  return (
    <Base className={className}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
    </Base>
  );
}

export function IconoDesplegar({ className }: Props) {
  return (
    <Base className={className}>
      <path d="M6 9l6 6 6-6" />
    </Base>
  );
}
