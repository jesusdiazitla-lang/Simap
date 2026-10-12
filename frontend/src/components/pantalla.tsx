"use client";

/**
 * Envoltorio de toda pantalla del plano de datos con sesión.
 *
 * Resuelve una sola vez lo que todas necesitan antes de mostrar nada: quién está dentro, si puede
 * estar aquí, y qué enseñar mientras tanto. Así la carga, el error de red y el «tu rol no tiene
 * acceso» se ven igual en todas las pantallas, en vez de con cuatro redacciones distintas.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { ArbolNavegacion } from "@/components/arbol-navegacion";
import { AvisosCola } from "@/components/avisos-cola";
import { BarraSesion, MenuMovil } from "@/components/barra-sesion";
import { Boton } from "@/components/boton";
import { FechaHora, Marco, Panel } from "@/components/marco";
import type { Rol, Usuario } from "@/lib/auth";
import { useSesion } from "@/lib/sesion";

export function Esqueleto({ filas = 3 }: { readonly filas?: number }) {
  return (
    <div aria-busy="true" className="flex flex-col gap-4">
      <span className="sr-only">Cargando…</span>
      {Array.from({ length: filas }, (_, i) => (
        <div key={i} className="flex flex-col gap-2 border-b border-borde pb-4 last:border-0">
          <div className="h-4 w-44 rounded-[var(--radius-control)] bg-superficie-alterna" />
          <div className="h-3 w-72 max-w-full rounded-[var(--radius-control)] bg-superficie-alterna" />
        </div>
      ))}
    </div>
  );
}

export function Pantalla({
  roles,
  cargando = "Cargando",
  children,
}: {
  readonly roles?: readonly Rol[];
  /** Título del panel mientras carga: dice qué se está abriendo. */
  readonly cargando?: string;
  readonly children: (usuario: Usuario, sinRed: boolean) => ReactNode;
}) {
  const sesion = useSesion(roles);

  if (sesion.tipo === "cargando") {
    return (
      // Columna del menú reservada (vacía) y sin subtítulo: la misma geometría que la pantalla
      // cargada, para que nada salte cuando llega la sesión.
      <Marco barra={<FechaHora />} lateral={null} subtitulo={false}>
        <Panel titulo={cargando}>
          <Esqueleto />
        </Panel>
      </Marco>
    );
  }

  if (sesion.tipo === "error") {
    return (
      <Marco barra={<FechaHora />}>
        <Panel titulo="No se pudo abrir esta pantalla">
          <p className="max-w-[60ch] pb-4 text-[0.9375rem] leading-6 text-error">{sesion.mensaje}</p>
          <Boton tipo="button" onClick={() => window.location.reload()}>
            Volver a intentar
          </Boton>
        </Panel>
      </Marco>
    );
  }

  if (sesion.tipo === "sin-permiso") {
    return (
      <Marco
        barra={<BarraSesion usuario={sesion.usuario} />}
        lateral={<ArbolNavegacion usuario={sesion.usuario} />}
        menu={<MenuMovil usuario={sesion.usuario} />}
        subtitulo={false}
      >
        <div className="mx-auto max-w-xl">
          <Panel titulo="Esta pantalla no es para tu rol">
            <p className="pb-4 text-[0.9375rem] leading-6 text-texto-suave">
              Si crees que deberías poder entrar aquí, pídeselo al administrador de tu planta.
            </p>
            <Link href="/panel" className="font-semibold text-accion underline underline-offset-2">
              Volver al panel
            </Link>
          </Panel>
        </div>
      </Marco>
    );
  }

  return (
    <Marco
      barra={<BarraSesion usuario={sesion.usuario} />}
      lateral={<ArbolNavegacion usuario={sesion.usuario} />}
      menu={<MenuMovil usuario={sesion.usuario} />}
      subtitulo={false}
    >
      <AvisosCola usuario={sesion.usuario} />
      {children(sesion.usuario, sesion.sinRed)}
    </Marco>
  );
}

/** Enlace de navegación con aspecto de botón secundario, para acciones que llevan a otra pantalla. */
export function EnlaceBoton({
  href,
  children,
  primario = false,
}: {
  readonly href: string;
  readonly children: ReactNode;
  readonly primario?: boolean;
}) {
  return (
    <Link
      href={href}
      className={[
        "inline-flex h-12 items-center justify-center gap-2 rounded-[var(--radius-control)] border px-5 text-[0.9375rem] font-semibold transition-colors",
        primario
          ? "border-accion-relleno bg-accion-relleno text-accion-texto hover:border-accion-viva hover:bg-accion-viva"
          : "border-borde-fuerte bg-superficie text-texto hover:border-accion hover:text-accion",
      ].join(" ")}
    >
      {children}
    </Link>
  );
}
