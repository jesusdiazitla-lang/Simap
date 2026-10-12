"use client";

/**
 * Barra superior de toda pantalla con sesión: quién está dentro, estado de la cola y «Cerrar
 * sesión», siempre a la vista.
 *
 * La navegación no va aquí: desde `lg` vive en el menú lateral del marco. Por debajo, el botón
 * «Menú» (`MenuMovil`) —con palabra, no un icono de tres rayas que quien no lo conoce no ve— abre ese
 * mismo árbol en un cajón desde la izquierda, para que el operario no pierda pantalla con un menú
 * siempre fijo. Lo coloca el marco a la izquierda, lejos de «Cerrar sesión».
 */

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ArbolNavegacion } from "@/components/arbol-navegacion";
import { IndicadorCola } from "@/components/indicador-cola";
import { etiquetaDeRol, type Usuario } from "@/lib/auth";
import { cerrarSesion } from "@/lib/sesion";

/** Botón «Menú» y su cajón, para pantallas estrechas. El marco lo coloca junto a la marca. */
export function MenuMovil({ usuario }: { readonly usuario: Usuario }) {
  const [abierto, setAbierto] = useState(false);
  const boton = useRef<HTMLButtonElement>(null);
  const ruta = usePathname();
  const [rutaAlAbrir, setRutaAlAbrir] = useState(ruta);

  // Si la ruta cambia con el cajón abierto (atrás del navegador), se cierra: el cajón pertenecía a
  // la pantalla anterior. Se ajusta durante el render, no en un efecto, como recomienda React.
  if (abierto && ruta !== rutaAlAbrir) {
    setAbierto(false);
  }

  useEffect(() => {
    if (!abierto) return;
    function alTeclear(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        setAbierto(false);
        boton.current?.focus();
      }
    }
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [abierto]);

  return (
    <div className="lg:hidden">
      <button
        ref={boton}
        type="button"
        aria-expanded={abierto}
        aria-controls="menu-movil"
        onClick={() => {
          setRutaAlAbrir(ruta);
          setAbierto((a) => !a);
        }}
        className={[
          "flex h-9 cursor-pointer items-center rounded-[var(--radius-control)] border px-3 text-[0.8125rem] font-medium transition-colors",
          // Abierto se marca como control activo; la palabra no cambia, para que nunca se lea
          // «Cerrar …» al lado de «Cerrar sesión».
          abierto
            ? "border-accion bg-accion-halo text-accion"
            : "border-borde-fuerte text-texto hover:border-accion hover:text-accion",
        ].join(" ")}
      >
        Menú
      </button>

      {abierto ? (
        <>
          {/* Fondo atenuado: dice que el contenido sigue ahí debajo, y tocarlo cierra el cajón. */}
          <div
            aria-hidden="true"
            onClick={() => setAbierto(false)}
            className="fixed inset-x-0 bottom-0 top-14 z-20 bg-[rgb(0_0_0/0.32)]"
          />
          <nav
            id="menu-movil"
            aria-label="Principal"
            className="fixed bottom-0 left-0 top-14 z-30 w-[min(20rem,85vw)] overflow-y-auto border-r border-borde bg-superficie px-3 pb-6 pt-3 shadow-[8px_0_16px_-12px_rgb(0_0_0/0.35)]"
          >
            <p className="truncate px-2 pb-3 text-[0.8125rem] text-texto-tenue">
              {usuario.nombre} · {etiquetaDeRol(usuario.rol)}
            </p>
            <ArbolNavegacion usuario={usuario} tactil alNavegar={() => setAbierto(false)} />
          </nav>
        </>
      ) : null}
    </div>
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
      <IndicadorCola />

      <div className="hidden min-w-0 text-right lg:block">
        <p className="truncate text-[0.8125rem] font-medium leading-4 text-texto">{usuario.nombre}</p>
        <p className="truncate text-[0.75rem] leading-4 text-texto-tenue">{etiquetaDeRol(usuario.rol)}</p>
      </div>

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
