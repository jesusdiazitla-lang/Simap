"use client";

/**
 * Cambio de la contraseña propia de un usuario de empresa.
 *
 * Hace falta sobre todo para el administrador de cada planta: entra la primera vez con una clave
 * que generó SIMAP y que vio quien se la entregó. Hasta que la cambie, esa persona puede entrar en
 * su cuenta.
 *
 * Al terminar no se cierra la sesión de este aparato —el servidor la renueva con la clave nueva—,
 * pero sí las de cualquier otro, y la pantalla lo dice: es justo lo que espera quien la cambia
 * porque sospecha que alguien la vio.
 */

import Link from "next/link";
import { useState } from "react";

import { FormularioClave } from "@/components/formulario-clave";
import { FechaHora, Marco, Panel } from "@/components/marco";
import { cambiarClave } from "@/lib/auth";

const ENLACE =
  "inline-flex h-12 items-center self-start rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.9375rem] font-medium text-texto transition-colors hover:bg-superficie-alterna";

export default function CambiarClavePage() {
  const [hecho, setHecho] = useState(false);

  return (
    <Marco
      barra={
        <div className="flex items-center gap-4">
          <FechaHora />
          <Link
            href="/panel"
            className="flex h-9 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto-suave transition-colors hover:bg-superficie-alterna"
          >
            Volver al panel
          </Link>
        </div>
      }
    >
      <div className="mx-auto w-full max-w-[30rem]">
        {hecho ? (
          <Panel titulo="Contraseña cambiada">
            <div role="status" className="flex flex-col gap-4">
              <p className="max-w-[60ch] text-[0.9375rem] leading-6 text-texto">
                Desde ahora entras con la contraseña nueva. Este aparato sigue con la sesión
                abierta; en cualquier otro donde la tuvieras abierta tendrás que volver a entrar.
              </p>
              <Link href="/panel" className={ENLACE}>
                Volver al panel
              </Link>
            </div>
          </Panel>
        ) : (
          <Panel
            titulo="Cambiar contraseña"
            descripcion="Te pedimos la actual para que nadie pueda cambiarla con una sesión que dejaste abierta."
            pie="Al cambiarla se cierra tu sesión en cualquier otro aparato. Si entraste con una contraseña que te dio otra persona, cámbiala ahora."
          >
            <FormularioClave
              prefijo="clave"
              cambiar={cambiarClave}
              alTerminar={() => setHecho(true)}
            />
          </Panel>
        )}
      </div>
    </Marco>
  );
}
