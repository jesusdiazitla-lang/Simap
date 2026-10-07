"use client";

/**
 * Panel de entrada, distinto según el rol (RF-03).
 *
 * El rol se pregunta al servidor con `GET /auth/yo` en cada carga, no se guarda en el navegador: si
 * se guardara, cualquiera podría cambiarlo a `administrador` desde las herramientas del navegador y
 * ver el menú completo. El menú no otorga permisos —cada endpoint los comprueba en el backend— pero
 * mostrar opciones que no se pueden usar es una mentira de interfaz.
 *
 * Las acciones que todavía no existen se muestran **desactivadas con su fase**, no escondidas. Quien
 * usa el sistema ve el alcance real de su rol, y quien evalúa el proyecto ve el avance sin abrir el
 * plan. Lo pendiente no lleva el azul de acción: en este sistema ese color significa exactamente
 * «aquí se puede hacer algo».
 */

import Link from "next/link";

import { Panel } from "@/components/marco";
import { Pantalla } from "@/components/pantalla";
import { ACCIONES_POR_ROL, etiquetaDeRol, type Accion, type Usuario } from "@/lib/auth";

export default function PanelPage() {
  return <Pantalla cargando="Cargando tu panel">{(usuario) => <Inicio usuario={usuario} />}</Pantalla>;
}

function Inicio({ usuario }: { readonly usuario: Usuario }) {
  const acciones = ACCIONES_POR_ROL[usuario.rol];
  return (
    <div className="flex flex-col gap-6">
      <Panel
        titulo={etiquetaDeRol(usuario.rol)}
        descripcion={`Sesión de ${usuario.nombre} · ${usuario.correo}`}
        pie="Todo lo que registres queda asociado a tu nombre. Si este aparato lo usa otra persona después de ti, cierra la sesión antes de dejarlo."
      >
        <ul className="flex flex-col">
          {acciones.map((accion) => (
            <li key={accion.nombre} className="border-b border-borde last:border-0">
              <FilaDeAccion accion={accion} />
            </li>
          ))}
        </ul>
      </Panel>

      <Panel nivel={2} titulo="Tu cuenta">
        <Link
          href="/panel/clave"
          className="inline-flex h-11 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.875rem] font-medium text-texto transition-colors hover:bg-superficie-alterna"
        >
          Cambiar contraseña
        </Link>
      </Panel>
    </div>
  );
}

function FilaDeAccion({ accion }: { readonly accion: Accion }) {
  const disponible = accion.ruta !== undefined;

  const contenido = (
    <>
      <div className="flex items-baseline justify-between gap-4">
        <span
          className={[
            "text-[0.9375rem] font-semibold leading-6",
            disponible ? "text-accion" : "text-texto-suave",
          ].join(" ")}
        >
          {accion.nombre}
        </span>
        {!disponible && accion.fase !== undefined ? (
          // El estado va en texto, no solo en color: quien no distingue el azul del gris tiene que
          // poder saber igual qué está disponible.
          <span className="shrink-0 rounded-[var(--radius-control)] border border-borde bg-superficie-alterna px-2 py-0.5 text-[0.6875rem] font-medium uppercase tracking-wide text-texto-tenue">
            Llega en {accion.fase}
          </span>
        ) : null}
      </div>
      <p className="max-w-[70ch] pt-0.5 text-[0.875rem] leading-5 text-texto-suave">
        {accion.descripcion}
      </p>
    </>
  );

  if (!disponible) {
    return <div className="py-3 opacity-75">{contenido}</div>;
  }

  return (
    <Link
      href={accion.ruta as string}
      className="-mx-2 block rounded-[var(--radius-control)] px-2 py-3 transition-colors hover:bg-superficie-alterna"
    >
      {contenido}
    </Link>
  );
}
