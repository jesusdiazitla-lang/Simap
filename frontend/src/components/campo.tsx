"use client";

/**
 * Campo de formulario con caja visible, como en cualquier herramienta de trabajo.
 *
 * Cuatro decisiones que no son de gusto y que sobreviven de la versión anterior de esta interfaz,
 * porque eran funcionales y no decorativas:
 *
 * 1. **48 px de alto.** Por encima del mínimo táctil de 44: esto se usa de pie, con guantes y a
 *    menudo con una sola mano.
 * 2. **La ranura del error está reservada siempre.** Un mensaje que aparece y empuja el botón hacia
 *    abajo hace que quien iba a pulsar «Entrar» pulse otra cosa. Se paga una línea de alto vacía a
 *    cambio de que la geometría no se mueva nunca.
 * 3. **El error se conecta al campo con `aria-describedby` y se marca con `aria-invalid`.** Un borde
 *    rojo no es un mensaje de error para quien usa un lector de pantalla.
 * 4. **Se puede pegar.** Bloquear el pegado obliga a transcribir a mano una contraseña de un gestor,
 *    que es lo que WCAG 2.2 llama fallo de autenticación accesible.
 */

import { useId, useState } from "react";

interface CampoProps {
  readonly etiqueta: string;
  readonly nombre: string;
  /**
   * Identificador del input. Se puede fijar desde fuera porque el resumen de errores necesita
   * enlazar a cada campo inválido con `href="#id"`, y un id generado aquí dentro no sería visible
   * para quien construye ese resumen.
   */
  readonly id?: string;
  readonly tipo?: "text" | "email" | "password" | "date" | "search";
  /**
   * Teclado que abre el móvil. Para el horómetro, `numeric` con `tipo="text"` y no
   * `type="number"`: este último acepta «e» y signos, cambia el valor con la rueda del ratón y en
   * algunos navegadores borra lo tecleado si no le parece un número.
   */
  readonly modoTeclado?: "numeric" | "text";
  /** Texto de ayuda permanente bajo la etiqueta, enlazado al campo con `aria-describedby`. */
  readonly ayuda?: string;
  readonly maxLength?: number;
  /** Cifra grande y gruesa: para el dato que se viene a escribir (el horómetro). */
  readonly grande?: boolean;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
  readonly error?: string;
  readonly autoComplete?: string;
  readonly autoFocus?: boolean;
  readonly requerido?: boolean;
  readonly deshabilitado?: boolean;
}

export function Campo({
  etiqueta,
  nombre,
  id: idFijado,
  tipo = "text",
  valor,
  onCambio,
  error,
  autoComplete,
  autoFocus = false,
  requerido = false,
  deshabilitado = false,
  modoTeclado,
  ayuda,
  maxLength,
  grande = false,
}: CampoProps) {
  const idBase = useId();
  const id = idFijado ?? `${idBase}-${nombre}`;
  const idError = `${id}-error`;
  const idAyuda = `${id}-ayuda`;
  const descritoPor =
    [ayuda !== undefined ? idAyuda : null, error !== undefined ? idError : null]
      .filter((x) => x !== null)
      .join(" ") || undefined;
  const [visible, setVisible] = useState(false);
  const esClave = tipo === "password";

  return (
    <div>
      <label
        htmlFor={id}
        className="flex items-baseline gap-2 pb-1.5 text-[0.8125rem] font-medium leading-5 text-texto"
      >
        {etiqueta}
        {requerido ? (
          <span className="text-[0.75rem] font-normal text-texto-tenue">obligatorio</span>
        ) : null}
      </label>
      {ayuda !== undefined ? (
        <p id={idAyuda} className="-mt-0.5 pb-1.5 text-[0.8125rem] leading-5 text-texto-suave">
          {ayuda}
        </p>
      ) : null}

      <div className="relative">
        <input
          id={id}
          name={nombre}
          type={esClave && visible ? "text" : tipo}
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          required={requerido}
          disabled={deshabilitado}
          aria-invalid={error !== undefined}
          aria-describedby={descritoPor}
          inputMode={modoTeclado}
          maxLength={maxLength}
          spellCheck={false}
          // 16 px exactos: por debajo, iOS hace zoom al enfocar y descoloca la pantalla.
          className={[
            "w-full rounded-[var(--radius-control)] border bg-superficie px-3 text-texto",
            grande ? "h-14 text-[1.5rem] font-semibold tracking-wide" : "h-12 text-[1rem]",
            esClave ? "pr-20" : "",
            "transition-colors placeholder:text-texto-tenue",
            "focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]",
            "disabled:cursor-not-allowed disabled:bg-superficie-alterna disabled:text-texto-tenue",
            error !== undefined ? "border-error" : "border-borde-fuerte",
          ].join(" ")}
        />

        {esClave ? (
          <button
            type="button"
            // aria-pressed en vez de cambiar el nombre accesible: el lector de pantalla anuncia el
            // estado y el texto visible sigue diciendo qué va a pasar al pulsarlo.
            aria-pressed={visible}
            onClick={() => setVisible((v) => !v)}
            disabled={deshabilitado}
            className="absolute right-0 top-0 flex h-12 cursor-pointer items-center px-3 text-[0.8125rem] font-medium text-accion transition-colors hover:text-accion-viva disabled:cursor-not-allowed disabled:text-texto-tenue"
          >
            {visible ? "Ocultar" : "Ver"}
          </button>
        ) : null}
      </div>

      {/* Ranura del error, siempre presente. aria-live para que se anuncie al aparecer sin que el
          foco salte de sitio mientras se escribe. */}
      <p
        id={idError}
        aria-live="polite"
        className="min-h-6 pt-1 text-[0.8125rem] leading-5 text-error"
      >
        {error ?? ""}
      </p>
    </div>
  );
}
