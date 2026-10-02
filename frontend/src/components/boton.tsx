"use client";

/**
 * Botón. Dos variantes y ninguna más: una acción primaria por pantalla, el resto en secundario.
 *
 * OCUPADO NO ES LO MISMO QUE DESHABILITADO
 * ----------------------------------------
 * Un control **deshabilitado** pierde el azul por completo: en este sistema ese color significa
 * «aquí se puede hacer algo» y ahí no se puede. Pero mientras la petición está en vuelo el botón no
 * está deshabilitado, está *trabajando*: conserva el color y solo cambia el texto. El texto cambia
 * siempre, así que el estado nunca depende únicamente del color.
 *
 * No hay animación de entrada ni de pulsación. Quien abre esta pantalla viene a trabajar, no a ver
 * cómo aparecen los controles.
 */

import type { ReactNode } from "react";

interface BotonProps {
  readonly children: ReactNode;
  /** Texto mientras la acción está en curso. Sustituye al normal, no lo acompaña. */
  readonly textoEnCurso?: string;
  readonly enCurso?: boolean;
  readonly deshabilitado?: boolean;
  readonly variante?: "primario" | "secundario";
  readonly tipo?: "submit" | "button";
  /**
   * Id del `<form>` que envía este botón cuando no está anidado dentro de él. Es HTML estándar y
   * evita el apaño de un `onClick` que llame al envío a mano: con el atributo `form`, la tecla
   * Intro y la validación nativa siguen funcionando igual que si estuviera dentro.
   */
  readonly form?: string;
  readonly anchoCompleto?: boolean;
  readonly onClick?: () => void;
}

export function Boton({
  children,
  textoEnCurso = "Un momento…",
  enCurso = false,
  deshabilitado = false,
  variante = "primario",
  tipo = "submit",
  form,
  anchoCompleto = false,
  onClick,
}: BotonProps) {
  const inactivo = enCurso || deshabilitado;

  const porVariante =
    variante === "primario"
      ? deshabilitado
        ? "border-borde-fuerte bg-superficie-alterna text-texto-tenue"
        : "border-accion-relleno bg-accion-relleno text-accion-texto hover:border-accion-viva hover:bg-accion-viva"
      : deshabilitado
        ? "border-borde-fuerte bg-superficie text-texto-tenue"
        : "border-borde-fuerte bg-superficie text-texto hover:border-accion hover:text-accion";

  return (
    <button
      type={tipo}
      form={form}
      onClick={onClick}
      disabled={inactivo}
      aria-busy={enCurso}
      className={[
        // 48 px de alto: se pulsa con guantes.
        "inline-flex h-12 items-center justify-center rounded-[var(--radius-control)] border px-5",
        "text-[0.9375rem] font-semibold transition-colors",
        anchoCompleto ? "w-full" : "",
        porVariante,
        deshabilitado ? "cursor-not-allowed" : enCurso ? "cursor-progress" : "cursor-pointer",
      ].join(" ")}
    >
      {enCurso ? textoEnCurso : children}
    </button>
  );
}
