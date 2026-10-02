"use client";

/**
 * El operador de SIMAP cambia su propia contraseña.
 *
 * Es la credencial con más poder del sistema y, hasta que existió esta pantalla, la única que no se
 * podía rotar sin tocar la base de datos. El cambio queda en la bitácora de la consola.
 */

import Link from "next/link";
import { useState } from "react";

import { FormularioClave } from "@/components/formulario-clave";
import { EtiquetaConsola, Marco, Panel } from "@/components/marco";
import { cambiarClaveOperador } from "@/lib/operador";

const ENLACE =
  "inline-flex h-12 items-center self-start rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.9375rem] font-medium text-texto transition-colors hover:bg-superficie-alterna";

export default function CambiarClaveOperadorPage() {
  const [hecho, setHecho] = useState(false);

  return (
    <Marco
      barra={
        <div className="flex items-center gap-3">
          <EtiquetaConsola />
          <Link
            href="/operador"
            className="flex h-9 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto-suave transition-colors hover:bg-superficie-alterna"
          >
            Volver a la consola
          </Link>
        </div>
      }
    >
      <div className="mx-auto w-full max-w-[30rem]">
        {hecho ? (
          <Panel titulo="Contraseña cambiada">
            <div role="status" className="flex flex-col gap-4">
              <p className="max-w-[60ch] text-[0.9375rem] leading-6 text-texto">
                Desde ahora entras en la consola con la contraseña nueva. El cambio queda anotado en
                la bitácora.
              </p>
              <Link href="/operador" className={ENLACE}>
                Volver a la consola
              </Link>
            </div>
          </Panel>
        ) : (
          <Panel
            titulo="Cambiar mi contraseña"
            descripcion="La de tu cuenta de operador, no la de ningún cliente."
            pie="Una sesión abierta en otro aparato dura como mucho 30 minutos más: la consola no renueva sesiones."
          >
            <FormularioClave
              prefijo="clave-operador"
              cambiar={cambiarClaveOperador}
              alTerminar={() => setHecho(true)}
            />
          </Panel>
        )}
      </div>
    </Marco>
  );
}
