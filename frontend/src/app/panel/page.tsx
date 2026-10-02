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
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { FechaHora, Marco, Panel } from "@/components/marco";
import {
  ACCIONES_POR_ROL,
  etiquetaDeRol,
  salir,
  usuarioActual,
  type Accion,
  type Usuario,
} from "@/lib/auth";

type Estado =
  | { readonly tipo: "cargando" }
  | { readonly tipo: "listo"; readonly usuario: Usuario }
  | { readonly tipo: "error"; readonly mensaje: string };

export default function PanelPage() {
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [saliendo, setSaliendo] = useState(false);
  // Cada reintento cambia este numero y vuelve a disparar el efecto. router.refresh() no sirve:
  // esta pagina es de cliente y sus datos no vienen del servidor de Next, vienen de la API.
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    const control = new AbortController();
    void (async () => {
      try {
        const usuario = await usuarioActual(control.signal);
        if (usuario === null) {
          router.replace("/login");
          return;
        }
        setEstado({ tipo: "listo", usuario });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setEstado({
          tipo: "error",
          mensaje:
            "No se pudo hablar con el servidor de SIMAP. Comprueba la conexión o avisa a quien lo " +
            "administra.",
        });
      }
    })();
    return () => control.abort();
  }, [router, intento]);

  async function cerrarSesion(): Promise<void> {
    setSaliendo(true);
    try {
      await salir();
    } finally {
      // Se navega al acceso aunque el logout falle: dejar a alguien atrapado en una pantalla con
      // sesión medio cerrada es peor que volver a pedir credenciales, sobre todo en un aparato
      // compartido entre turnos.
      router.replace("/login");
    }
  }

  if (estado.tipo === "cargando") {
    return (
      <Marco barra={<FechaHora />}>
        <Panel titulo="Cargando tu panel">
          {/* Esqueleto con la forma real de lo que va a llegar, no un girador en medio de la nada:
              así la página no da un salto cuando entran los datos. */}
          <div aria-busy="true" aria-live="polite" className="flex flex-col gap-4">
            <span className="sr-only">Cargando tu panel…</span>
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex flex-col gap-2 border-b border-borde pb-4 last:border-0">
                <div className="h-4 w-44 rounded-[var(--radius-control)] bg-superficie-alterna" />
                <div className="h-3 w-72 max-w-full rounded-[var(--radius-control)] bg-superficie-alterna" />
              </div>
            ))}
          </div>
        </Panel>
      </Marco>
    );
  }

  if (estado.tipo === "error") {
    return (
      <Marco barra={<FechaHora />}>
        <Panel titulo="No se pudo cargar el panel">
          <p className="max-w-[60ch] pb-4 text-[0.9375rem] leading-6 text-error">{estado.mensaje}</p>
          <Boton
            tipo="button"
            onClick={() => {
              setEstado({ tipo: "cargando" });
              setIntento((n) => n + 1);
            }}
          >
            Volver a intentar
          </Boton>
        </Panel>
      </Marco>
    );
  }

  const { usuario } = estado;
  const acciones = ACCIONES_POR_ROL[usuario.rol];

  return (
    <Marco
      barra={
        <div className="flex min-w-0 items-center gap-4">
          <FechaHora />
          <div className="hidden min-w-0 text-right sm:block">
            <p className="truncate text-[0.8125rem] font-medium leading-4 text-texto">
              {usuario.nombre}
            </p>
            <p className="truncate text-[0.75rem] leading-4 text-texto-tenue">
              {etiquetaDeRol(usuario.rol)}
            </p>
          </div>
          {/* Cerrar sesión, siempre visible y en secundario: el aparato puede pasar entre turnos,
              y el azul está reservado a las acciones de trabajo, no a salir. */}
          <button
            type="button"
            onClick={() => void cerrarSesion()}
            disabled={saliendo}
            className="h-9 shrink-0 cursor-pointer rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto-suave transition-colors hover:border-error hover:text-error disabled:cursor-not-allowed disabled:text-texto-tenue"
          >
            {saliendo ? "Cerrando…" : "Cerrar sesión"}
          </button>
        </div>
      }
    >
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

        <Panel titulo="Tu cuenta">
          <Link
            href="/panel/clave"
            className="inline-flex h-11 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.875rem] font-medium text-texto transition-colors hover:bg-superficie-alterna"
          >
            Cambiar contraseña
          </Link>
        </Panel>
      </div>
    </Marco>
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
