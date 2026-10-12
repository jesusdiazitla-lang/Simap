"use client";

/**
 * Marco de la aplicación: barra superior, contenido y barra de estado.
 *
 * Es la estructura que reconoce quien ya usa un CMMS: una franja de identificación arriba, el
 * trabajo en el medio sobre un lienzo gris, y una barra de estado abajo con la versión y a quién
 * acudir. Nada de esto es decorativo; cada zona responde a una pregunta que el usuario se hace de
 * verdad: dónde estoy, qué tengo que hacer, y a quién aviso si falla.
 *
 * Sustituye a la hoja de bitácora de la primera versión, que el usuario rechazó por poco sobria
 * para una herramienta industrial. El razonamiento completo está en `globals.css` y en PRODUCT.md.
 */

import { useSyncExternalStore, type ReactNode } from "react";

/** Versión que se muestra en la barra de estado. Coincide con la del manual de usuario. */
const VERSION = "0.7.1";

interface MarcoProps {
  /** Lo que el usuario tiene delante. */
  readonly children: ReactNode;
  /** Zona derecha de la barra superior: identidad de la sesión, cerrar sesión. */
  readonly barra?: ReactNode;
  /**
   * Baja el contenido hasta el centro óptico, para pantallas de una sola pieza (acceso, carga,
   * error). Sin esto quedan pegadas arriba y en un monitor alto medio lienzo se ve vacío.
   *
   * Es un desplazamiento fijo (12vh), **no** un `justify-center`. Centrar de verdad hace que el
   * bloque se recoloque cada vez que su altura cambia: al aparecer el mensaje de error el panel
   * crece y el conjunto sube la mitad de lo que creció, así que el botón se mueve bajo el cursor
   * justo cuando el usuario va a volver a pulsarlo. Con un desplazamiento fijo se ve igual de
   * centrado y no se mueve nada.
   */
  readonly centrado?: boolean;
  /**
   * Nombre largo del sistema junto a «SIMAP». Las pantallas con navegación lo quitan: con los
   * enlaces, el estado de la cola y quién está dentro, en un portátil ya no cabe y se cortaba.
   */
  readonly subtitulo?: boolean;
}

export function Marco({ children, barra, centrado = false, subtitulo = true }: MarcoProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-lienzo">
      {/* Barra y pie no se imprimen: lo que se imprime en SIMAP es una etiqueta, no la pantalla. */}
      <header className="border-b border-borde bg-superficie print:hidden">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-baseline gap-3">
            <span className="text-[0.9375rem] font-bold tracking-[0.08em] text-texto">SIMAP</span>
            {/* El nombre largo solo en pantalla ancha: en móvil roba sitio y no aporta nada a
                quien ya está dentro del sistema. */}
            <span
              className={[
                "truncate text-[0.8125rem] text-texto-tenue",
                subtitulo ? "hidden sm:block" : "hidden",
              ].join(" ")}
            >
              Sistema Inteligente de Mantenimiento Predictivo
            </span>
          </div>
          {barra}
        </div>
      </header>

      <main className="flex-1">
        <div
          className={[
            "mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 sm:py-10",
            centrado ? "sm:pt-[12vh]" : "",
          ].join(" ")}
        >
          {children}
        </div>
      </main>

      <footer className="border-t border-borde bg-superficie print:hidden">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-3 text-[0.75rem] leading-5 text-texto-tenue sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>SIMAP v{VERSION}</span>
          <span>Soporte: el administrador de SIMAP en tu planta</span>
        </div>
      </footer>
    </div>
  );
}

/**
 * Panel: la caja blanca sobre el lienzo gris donde vive un bloque de trabajo.
 *
 * Borde de 1 px y sin sombra. Lo que lo separa del fondo es el contraste entre la superficie blanca
 * y el lienzo gris, no una elevación simulada: en una herramienta de trabajo no hay nada flotando.
 */
export function Panel({
  titulo,
  descripcion,
  children,
  pie,
  nivel = 1,
}: {
  readonly titulo: string;
  readonly descripcion?: string;
  readonly children: ReactNode;
  readonly pie?: ReactNode;
  /**
   * Nivel del título. 1 cuando el panel es la pantalla (acceso, panel); 2 cuando es una sección de
   * una pantalla que ya tiene su propio título, para que el lector de pantalla no anuncie cinco
   * encabezados principales en la ficha de un equipo.
   */
  readonly nivel?: 1 | 2;
}) {
  const Titulo = nivel === 1 ? "h1" : "h2";
  return (
    <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
      <header className="border-b border-borde px-5 py-4 sm:px-6">
        <Titulo className="text-[1.0625rem] font-semibold leading-6 text-texto">{titulo}</Titulo>
        {descripcion !== undefined ? (
          <p className="pt-1 text-[0.875rem] leading-5 text-texto-suave">{descripcion}</p>
        ) : null}
      </header>

      <div className="px-5 py-5 sm:px-6">{children}</div>

      {pie !== undefined ? (
        <footer className="border-t border-borde bg-superficie-alterna px-5 py-4 text-[0.8125rem] leading-5 text-texto-tenue sm:px-6">
          {pie}
        </footer>
      ) : null}
    </section>
  );
}

/**
 * Marca de que se está en la consola del proveedor y no en la aplicación de una empresa.
 *
 * Va en texto y no solo en color: quien abre las dos en pestañas distintas tiene que poder
 * distinguirlas de un vistazo, y el color no sirve para todo el mundo.
 */
export function EtiquetaConsola() {
  return (
    <span className="rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna px-2 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-texto-suave">
      Consola del operador
    </span>
  );
}

/**
 * Fecha y hora de la sesión, en la barra superior.
 *
 * Dato real, no adorno: en un registro con responsables importa cuándo se hizo cada cosa. Se lee
 * con `useSyncExternalStore` porque el reloj del sistema es estado externo a React, y la
 * instantánea devuelve el número de minuto —un valor estable entre llamadas— en lugar de un `Date`
 * nuevo cada vez, que dejaría a React re-renderizando sin parar.
 */
export function FechaHora() {
  const minuto = useSyncExternalStore(suscribirAlMinuto, minutoActual, sinHoraEnElServidor);
  if (minuto === null) {
    // En el servidor no se pinta: la hora que importa es la de quien usa la aplicación, y pintar la
    // del servidor provocaría además una discrepancia al hidratar. El hueco queda reservado.
    return <span className="hidden min-w-[9.5rem] text-right md:block" />;
  }
  const ahora = new Date(minuto * 60_000);
  return (
    <span className="hidden min-w-[9.5rem] text-right text-[0.8125rem] text-texto-tenue md:block">
      {ahora.toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" })}
      {" · "}
      {ahora.toLocaleTimeString("es-DO", { hour: "2-digit", minute: "2-digit" })}
    </span>
  );
}

function suscribirAlMinuto(alCambiar: () => void): () => void {
  const reloj = setInterval(alCambiar, 60_000);
  return () => clearInterval(reloj);
}

const minutoActual = (): number => Math.floor(Date.now() / 60_000);
const sinHoraEnElServidor = (): null => null;
