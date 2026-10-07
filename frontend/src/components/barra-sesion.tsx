"use client";

/**
 * Barra superior de toda pantalla con sesión: navegación del rol, quién está dentro, estado de la
 * cola y «Cerrar sesión», siempre a la vista.
 *
 * En pantalla ancha la navegación va en la propia barra. En el móvil no cabe sin desbordar, y
 * esconderla detrás de un icono de tres rayas la vuelve invisible para quien no lo conoce; va en un
 * desplegable con la palabra «Menú», hecho con `<details>`, que funciona con teclado y lector de
 * pantalla sin una línea de JavaScript propia.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { IndicadorCola } from "@/components/indicador-cola";
import { etiquetaDeRol, NAVEGACION_POR_ROL, type Usuario } from "@/lib/auth";
import { cerrarSesion } from "@/lib/sesion";

function Enlaces({ usuario, vertical }: { readonly usuario: Usuario; readonly vertical: boolean }) {
  const ruta = usePathname();
  const destinos = [{ nombre: "Inicio", ruta: "/panel" }, ...NAVEGACION_POR_ROL[usuario.rol]];
  return (
    <ul className={vertical ? "flex flex-col" : "flex items-center gap-1"}>
      {destinos.map((d) => {
        const actual = d.ruta === "/panel" ? ruta === "/panel" : ruta.startsWith(d.ruta);
        return (
          <li key={d.ruta}>
            <Link
              href={d.ruta}
              aria-current={actual ? "page" : undefined}
              className={[
                "flex items-center whitespace-nowrap rounded-[var(--radius-control)] text-[0.875rem] font-medium transition-colors",
                vertical ? "h-12 px-3" : "h-9 px-3",
                actual
                  ? "bg-superficie-alterna text-texto"
                  : "text-texto-suave hover:bg-superficie-alterna hover:text-texto",
              ].join(" ")}
            >
              {d.nombre}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function BarraSesion({ usuario }: { readonly usuario: Usuario }) {
  const router = useRouter();
  const [saliendo, setSaliendo] = useState(false);

  async function salir(): Promise<void> {
    setSaliendo(true);
    try {
      await cerrarSesion();
    } finally {
      // Se va al acceso aunque el cierre falle: dejar a alguien con la sesión a medio cerrar en
      // un aparato compartido es peor que volver a pedirle la contraseña.
      router.replace("/login");
    }
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      <nav aria-label="Principal" className="hidden lg:block">
        <Enlaces usuario={usuario} vertical={false} />
      </nav>

      <IndicadorCola />

      <div className="hidden min-w-0 text-right xl:block">
        <p className="truncate text-[0.8125rem] font-medium leading-4 text-texto">{usuario.nombre}</p>
        <p className="truncate text-[0.75rem] leading-4 text-texto-tenue">{etiquetaDeRol(usuario.rol)}</p>
      </div>

      <details className="relative lg:hidden">
        <summary className="flex h-9 cursor-pointer list-none items-center rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto [&::-webkit-details-marker]:hidden">
          Menú
        </summary>
        <nav
          aria-label="Principal"
          className="fixed inset-x-0 top-14 z-20 border-b border-borde bg-superficie px-4 py-2 shadow-[0_8px_16px_-12px_rgb(0_0_0/0.35)]"
        >
          <p className="px-3 pb-1 pt-1 text-[0.8125rem] text-texto-tenue">
            {usuario.nombre} · {etiquetaDeRol(usuario.rol)}
          </p>
          <Enlaces usuario={usuario} vertical />
        </nav>
      </details>

      <button
        type="button"
        onClick={() => void salir()}
        disabled={saliendo}
        className="h-9 shrink-0 cursor-pointer rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto-suave transition-colors hover:border-error hover:text-error disabled:cursor-not-allowed disabled:text-texto-tenue"
      >
        {saliendo ? "Cerrando…" : "Cerrar sesión"}
      </button>
    </div>
  );
}
