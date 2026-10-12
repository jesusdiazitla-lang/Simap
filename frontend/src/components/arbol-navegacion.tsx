"use client";

/**
 * Menú de la aplicación como árbol: un área de trabajo por rama y sus páginas colgando de ella.
 *
 * Es la navegación que reconoce quien ya usa un CMMS: a la izquierda, siempre a la vista, con las
 * áreas plegables. La misma pieza sirve para la barra lateral del escritorio y para el cajón del
 * móvil; solo cambia la altura de las filas, que en el teléfono sube a 48 px porque se toca con el
 * dedo y a veces con guantes.
 *
 * Las ramas que alguien pliega se recuerdan en este navegador. Cada pantalla monta su propio marco,
 * así que sin recordarlo el árbol se volvería a abrir entero en cada clic.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore, type ComponentType, type ReactNode } from "react";

import {
  IconoCuenta,
  IconoDesplegar,
  IconoEquipos,
  IconoEscanear,
  IconoInicio,
  IconoPersonal,
  IconoRevision,
} from "@/components/iconos";
import { arbolPara, hojaActual, type Area, type Usuario } from "@/lib/auth";

const ICONO_DE_AREA: Readonly<Record<Area, ComponentType<{ className?: string }>>> = {
  campo: IconoEscanear,
  equipos: IconoEquipos,
  supervision: IconoRevision,
  administracion: IconoPersonal,
  cuenta: IconoCuenta,
};

const INICIO = { nombre: "Inicio", ruta: "/panel" } as const;

// --- Ramas plegadas, recordadas en el navegador ---------------------------------
// Preferencia de quien usa este aparato, nada más: si el almacenamiento no está disponible
// (ventana privada, datos bloqueados) se guarda en memoria y el menú funciona igual.

const CLAVE = "simap.menu.plegadas";
const oyentes = new Set<() => void>();
let plegadas: string | null = null;

function leerPlegadas(): string {
  if (plegadas === null) {
    try {
      plegadas = window.localStorage.getItem(CLAVE) ?? "";
    } catch {
      plegadas = "";
    }
  }
  return plegadas;
}

function suscribir(avisar: () => void): () => void {
  oyentes.add(avisar);
  return () => oyentes.delete(avisar);
}

function alternar(area: Area): void {
  const conjunto = new Set(leerPlegadas().split(",").filter(Boolean));
  if (conjunto.has(area)) conjunto.delete(area);
  else conjunto.add(area);
  plegadas = [...conjunto].join(",");
  try {
    window.localStorage.setItem(CLAVE, plegadas);
  } catch {
    // Solo dura lo que la pestaña; no es un dato que haya que salvar.
  }
  oyentes.forEach((avisar) => avisar());
}

// En el servidor todo va desplegado: es lo que se ve mientras hidrata.
const nadaPlegado = (): string => "";

// --- Árbol -----------------------------------------------------------------------

export function ArbolNavegacion({
  usuario,
  tactil = false,
  alNavegar,
}: {
  readonly usuario: Usuario;
  /** Filas de 48 px para el cajón del teléfono; 36 px en la barra lateral. */
  readonly tactil?: boolean;
  /** El cajón se cierra al elegir: un ancla a la misma página no cambia de pantalla. */
  readonly alNavegar?: () => void;
}) {
  const ruta = usePathname();
  const plegado = useSyncExternalStore(suscribir, leerPlegadas, nadaPlegado);
  const ramas = arbolPara(usuario.rol);
  const actual = hojaActual([INICIO, ...ramas.flatMap((r) => r.hojas)], ruta);
  const alto = tactil ? "h-12" : "h-9";

  return (
    <ul className="flex flex-col gap-1">
      <li>
        <Hoja
          destino={INICIO}
          actual={actual === INICIO.ruta}
          alto={alto}
          alNavegar={alNavegar}
          icono={<IconoInicio />}
        />
      </li>
      {ramas.map((rama) => {
        const abierta = !plegado.split(",").includes(rama.area);
        const Icono = ICONO_DE_AREA[rama.area];
        const id = `menu-${rama.area}${tactil ? "-movil" : ""}`;
        return (
          <li key={rama.area} className="pt-2">
            <button
              type="button"
              aria-expanded={abierta}
              aria-controls={id}
              onClick={() => alternar(rama.area)}
              className={[
                "flex w-full cursor-pointer items-center gap-2.5 rounded-[var(--radius-control)] px-2 text-left text-[0.875rem] font-semibold text-texto transition-colors hover:bg-superficie-alterna",
                alto,
              ].join(" ")}
            >
              <Icono className="text-texto-tenue" />
              <span className="min-w-0 flex-1 truncate">{rama.nombre}</span>
              <IconoDesplegar className={["text-texto-tenue", abierta ? "" : "-rotate-90"].join(" ")} />
            </button>
            {/* La guía vertical de 1 px es la que dice «estas páginas son de esta área». Queda
                alineada con el centro del icono de la rama. */}
            <ul id={id} hidden={!abierta} className="ml-[1.0625rem] flex flex-col gap-0.5 border-l border-borde py-1 pl-2">
              {rama.hojas.map((hoja) => (
                <li key={hoja.ruta}>
                  <Hoja destino={hoja} actual={actual === hoja.ruta} alto={alto} alNavegar={alNavegar} guia />
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

function Hoja({
  destino,
  actual,
  alto,
  alNavegar,
  icono,
  guia = false,
}: {
  readonly destino: { readonly nombre: string; readonly ruta: string };
  readonly actual: boolean;
  readonly alto: string;
  readonly alNavegar?: () => void;
  readonly icono?: ReactNode;
  /** Hoja dentro de una rama: la página abierta oscurece su tramo de la guía vertical. */
  readonly guia?: boolean;
}) {
  return (
    <Link
      href={destino.ruta}
      onClick={alNavegar}
      aria-current={actual ? "page" : undefined}
      className={[
        "relative flex items-center gap-2.5 rounded-[var(--radius-control)] text-[0.875rem] transition-colors",
        icono !== undefined ? "px-2" : "px-3",
        alto,
        actual
          ? "bg-superficie-alterna font-semibold text-texto"
          : "font-medium text-texto-suave hover:bg-superficie-alterna hover:text-texto",
        // El tramo de guía de la página abierta: 1 px, neutro, encima de la línea de la rama.
        guia && actual ? "before:absolute before:-left-[9px] before:inset-y-1.5 before:w-px before:bg-texto" : "",
      ].join(" ")}
    >
      {icono !== undefined ? <span className={actual ? "text-texto" : "text-texto-tenue"}>{icono}</span> : null}
      <span className="min-w-0 truncate">{destino.nombre}</span>
    </Link>
  );
}
