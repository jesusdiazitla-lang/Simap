"use client";

/**
 * Marco de la aplicación: barra superior, menú lateral, contenido y barra de estado.
 *
 * Es la estructura que reconoce quien ya usa un CMMS: una franja de identificación arriba, el menú
 * en árbol a la izquierda, el trabajo en el medio sobre un lienzo gris, y una barra de estado abajo
 * con la versión y a quién acudir. Nada de esto es decorativo; cada zona responde a una pregunta que el usuario se hace de
 * verdad: dónde estoy, qué tengo que hacer, y a quién aviso si falla.
 *
 * Sustituye a la hoja de bitácora de la primera versión, que el usuario rechazó por poco sobria
 * para una herramienta industrial. El razonamiento completo está en `globals.css` y en PRODUCT.md.
 */

import { useSyncExternalStore, type ReactNode } from "react";

/** Versión que se muestra en la barra de estado. Coincide con la del manual de usuario. */
const VERSION = "0.8.1";

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
  /**
   * Menú lateral (`ArbolNavegacion`). Desde `lg` queda fijo a la izquierda y la barra superior se
   * queda arriba al desplazarse, para que el menú no se vaya con el contenido. Por debajo de `lg`
   * no se pinta aquí: lo abre el botón «Menú» de la barra.
   */
  readonly lateral?: ReactNode;
  /**
   * Botón que abre el menú en pantallas estrechas. Va a la izquierda, junto a la marca: es el lado
   * del que sale el cajón, y lo aleja de «Cerrar sesión», que no pide confirmación.
   */
  readonly menu?: ReactNode;
}

export function Marco({ children, barra, centrado = false, subtitulo = true, lateral, menu }: MarcoProps) {
  const conLateral = lateral !== undefined;
  return (
    <div className="flex min-h-dvh flex-col bg-lienzo">
      {/* Barra y pie no se imprimen: lo que se imprime en SIMAP es una etiqueta, no la pantalla. */}
      <header
        className={[
          "border-b border-borde bg-superficie print:hidden",
          conLateral ? "sticky top-0 z-30" : "",
        ].join(" ")}
      >
        <div
          className={[
            "flex h-14 w-full items-center justify-between gap-4 px-4 sm:px-6",
            // Con menú lateral la aplicación ocupa todo el ancho, como un CMMS; la marca queda
            // encima de la columna del menú.
            conLateral ? "lg:pl-0" : "mx-auto max-w-6xl",
          ].join(" ")}
        >
          <div
            className={[
              "flex min-w-0 items-center gap-3",
              conLateral ? "lg:w-60 lg:shrink-0 lg:px-5" : "",
            ].join(" ")}
          >
            {menu}
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

      <div className="flex flex-1">
        {/* Con `lateral={null}` la columna se reserva vacía: así la pantalla de carga tiene la
            misma geometría que la cargada y nada salta cuando llega el menú. */}
        {conLateral ? (
          <aside className="hidden w-60 shrink-0 border-r border-borde bg-superficie print:hidden lg:block">
            <nav
              aria-label="Principal"
              className="sticky top-14 max-h-[calc(100dvh-3.5rem)] overflow-y-auto px-3 py-4"
            >
              {lateral}
            </nav>
          </aside>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
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
      </div>
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
