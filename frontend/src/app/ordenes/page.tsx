"use client";

/**
 * Bandeja de órdenes de trabajo (RF-13, RF-14; 06-fase3, 9.1 y 9.4).
 *
 * Se abre en «Abiertas», que es lo que hay que atender: el técnico ve qué tomar, el supervisor qué
 * autorizar. Cerradas y canceladas son el historial. La lista se actualiza sola cada 30 segundos
 * mientras la pestaña está a la vista, para que dos personas mirando la misma bandeja vean lo mismo
 * sin recargar.
 *
 * Como la de equipos: tabla en escritorio, filas apiladas en el móvil.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { EstadoOrdenInsignia, HorometroEnRevision } from "@/components/estado";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { fechaHora, hace, horas } from "@/lib/formato";
import { duracion, listarOrdenes, numeroOrden, type FiltroOrdenes, type OrdenResumen } from "@/lib/ordenes";
import { useSondeo } from "@/lib/sondeo";

const ROLES: readonly Rol[] = ["supervisor", "tecnico_taller", "gerente", "administrador"];

export default function OrdenesPage() {
  return (
    <Pantalla roles={ROLES} cargando="Órdenes de trabajo">
      {(usuario) => <Bandeja usuario={usuario} />}
    </Pantalla>
  );
}

const DESCRIPCION_POR_ROL: Partial<Record<Rol, string>> = {
  tecnico_taller: "Toma las órdenes reportadas y registra el trabajo realizado al terminar.",
  supervisor: "Fallas de la planta. Autoriza o rechaza el cierre de lo que el taller ya reparó.",
  administrador: "Todas las fallas de la empresa, con quién hizo cada paso.",
  gerente: "Fallas abiertas y su historial. Solo lectura.",
};

function Bandeja({ usuario }: { readonly usuario: Usuario }) {
  const [filtro, setFiltro] = useState<FiltroOrdenes>("abiertas");
  const [ordenes, setOrdenes] = useState<readonly OrdenResumen[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      listarOrdenes({ estado: filtro }, signal)
        .then((p) => {
          setOrdenes(p.items);
          setCursor(p.next_cursor);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          // Un fallo del sondeo no borra lo que ya se ve: solo se avisa si no había nada.
          setError(e instanceof ErrorApi ? e.message : "No se pudo cargar la bandeja.");
        }),
    [filtro],
  );

  useEffect(() => {
    const control = new AbortController();
    void cargar(control.signal);
    return () => control.abort();
  }, [cargar]);

  // Solo la primera página se refresca: si alguien cargó más, no se le recorta la lista.
  useSondeo(() => {
    if (cursor === null) void cargar();
  });

  async function cargarMas(): Promise<void> {
    if (cursor === null) return;
    setCargandoMas(true);
    try {
      const p = await listarOrdenes({ estado: filtro, cursor });
      setOrdenes((a) => [...(a ?? []), ...p.items]);
      setCursor(p.next_cursor);
    } finally {
      setCargandoMas(false);
    }
  }

  const filtros: Array<[FiltroOrdenes, string]> = [
    ["abiertas", "Abiertas"],
    ["cerradas", "Cerradas"],
    ["canceladas", "Canceladas"],
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Órdenes de trabajo</h1>
        <p className="pt-1 text-[0.9375rem] text-texto-suave">{DESCRIPCION_POR_ROL[usuario.rol]}</p>
      </div>

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="border-b border-borde px-5 py-4 sm:px-6">
          <fieldset>
            <legend className="sr-only">Mostrar</legend>
            <div className="inline-flex rounded-[var(--radius-control)] border border-borde-fuerte">
              {filtros.map(([valor, nombre]) => (
                <label
                  key={valor}
                  className={[
                    "flex h-12 cursor-pointer items-center px-4 text-[0.875rem] font-medium transition-colors first:rounded-l-[var(--radius-control)] last:rounded-r-[var(--radius-control)] [&:not(:first-child)]:border-l [&:not(:first-child)]:border-borde-fuerte",
                    "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accion",
                    filtro === valor ? "bg-[var(--accion-halo)] text-accion" : "bg-superficie text-texto-suave hover:text-texto",
                  ].join(" ")}
                >
                  <input type="radio" name="filtro-ordenes" className="sr-only" checked={filtro === valor}
                    onChange={() => {
                      setFiltro(valor);
                      setOrdenes(null);
                    }}
                  />
                  {nombre}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="px-5 py-4 sm:px-6">
          {error !== null && ordenes === null ? (
            <p role="alert" className="text-[0.9375rem] text-error">
              {error}
            </p>
          ) : ordenes === null ? (
            <Esqueleto />
          ) : ordenes.length === 0 ? (
            <p className="py-2 text-[0.9375rem] text-texto-suave">
              {filtro === "abiertas"
                ? "No hay órdenes abiertas. Las fallas se reportan desde la pantalla de cada equipo."
                : filtro === "cerradas"
                  ? "Todavía no se ha cerrado ninguna orden."
                  : "No hay órdenes canceladas."}
            </p>
          ) : (
            <TablaOrdenes ordenes={ordenes} filtro={filtro} />
          )}
        </div>

        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()} enCurso={cargandoMas} textoEnCurso="Cargando…">
              Cargar más órdenes
            </Boton>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function TablaOrdenes({
  ordenes,
  filtro,
}: {
  readonly ordenes: readonly OrdenResumen[];
  readonly filtro: FiltroOrdenes;
}) {
  return (
    <table className="w-full border-collapse text-left">
      <thead className="hidden md:table-header-group">
        <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
          <th scope="col" className="pb-2 pr-4 font-medium">Orden</th>
          <th scope="col" className="pb-2 pr-4 font-medium">Equipo y componente</th>
          <th scope="col" className="pb-2 pr-4 font-medium">Falla</th>
          <th scope="col" className="pb-2 pr-4 text-right font-medium">
            {filtro === "cerradas" ? "Fuera de servicio" : "Horómetro"}
          </th>
          <th scope="col" className="pb-2 font-medium">Estado</th>
        </tr>
      </thead>
      <tbody>
        {ordenes.map((o) => (
          <tr
            key={o.id}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 border-b border-borde py-3 last:border-0 md:table-row md:py-0"
          >
            <td className="md:py-3 md:pr-4">
              <Link href={`/ordenes/${o.id}`} className="font-mono text-[0.9375rem] font-semibold tracking-[0.04em] text-accion underline-offset-2 hover:underline">
                {numeroOrden(o.numero)}
              </Link>
            </td>
            <td className="col-start-1 min-w-0 md:py-3 md:pr-4">
              <span className="block font-semibold text-texto [overflow-wrap:anywhere]">{o.activo_nombre}</span>
              <span className="block text-[0.875rem] text-texto-suave">{o.componente_nombre}</span>
            </td>
            <td className="col-start-1 text-[0.875rem] text-texto-suave md:py-3 md:pr-4 md:text-[0.9375rem]">
              <span className="block">{fechaHora(o.fecha_falla)}</span>
              <span className="block text-[0.8125rem] text-texto-tenue">{hace(o.fecha_falla)}</span>
            </td>
            <td className="col-start-2 row-start-1 text-right md:py-3 md:pr-4">
              <span className="font-semibold text-texto">
                {filtro === "cerradas" && o.tiempo_fuera_servicio_min !== null
                  ? duracion(o.tiempo_fuera_servicio_min)
                  : horas(o.horometro_en_falla)}
              </span>
            </td>
            <td className="col-start-2 row-start-2 flex flex-col items-end gap-1 md:table-cell md:py-3 md:items-start">
              <span className="flex flex-col items-end gap-1 md:items-start">
                <EstadoOrdenInsignia estado={o.estado} />
                {o.requiere_revision ? <HorometroEnRevision /> : null}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
