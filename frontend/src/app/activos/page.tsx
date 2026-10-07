"use client";

/**
 * Lista de equipos de la empresa, con búsqueda y filtro por estado (05-fase2-activos-y-campo.md,
 * 7.1). Paginada por cursor: «Cargar más» pide la página siguiente sin repetir ni saltar equipos
 * aunque alguien dé de alta otro mientras tanto.
 *
 * En escritorio es una tabla, que es como se compara una columna de horómetros. En el móvil una
 * tabla de seis columnas no cabe sin desplazamiento horizontal, así que cada fila se apila: nombre
 * arriba, datos debajo, y la fila entera lleva a la ficha.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Criticidad, EstadoEquipo } from "@/components/estado";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { listarActivos, type Activo, type EstadoActivo } from "@/lib/activos";
import type { Rol, Usuario } from "@/lib/auth";
import { hace, horas } from "@/lib/formato";

const ROLES: readonly Rol[] = ["supervisor", "administrador", "gerente"];

export default function ActivosPage() {
  return (
    <Pantalla roles={ROLES} cargando="Equipos">
      {(usuario) => <Lista usuario={usuario} />}
    </Pantalla>
  );
}

function Lista({ usuario }: { readonly usuario: Usuario }) {
  const [texto, setTexto] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [estado, setEstado] = useState<EstadoActivo | null>("activo");
  const [items, setItems] = useState<readonly Activo[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // La búsqueda se lanza al dejar de teclear, no con cada letra.
  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim()), 300);
    return () => clearTimeout(t);
  }, [texto]);

  useEffect(() => {
    const control = new AbortController();
    void listarActivos({ q: busqueda, estado }, control.signal)
      .then((p) => {
        setItems(p.items);
        setCursor(p.next_cursor);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi ? e.message : "No se pudo cargar la lista.");
      });
    return () => control.abort();
  }, [busqueda, estado]);

  async function cargarMas(): Promise<void> {
    if (cursor === null) return;
    setCargandoMas(true);
    try {
      const p = await listarActivos({ q: busqueda, estado, cursor });
      setItems((anteriores) => [...(anteriores ?? []), ...p.items]);
      setCursor(p.next_cursor);
    } finally {
      setCargandoMas(false);
    }
  }

  const filtros: Array<[EstadoActivo | null, string]> = [
    ["activo", "En servicio"],
    ["baja", "Dados de baja"],
    [null, "Todos"],
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Equipos</h1>
          <p className="pt-1 text-[0.9375rem] text-texto-suave">
            Cada equipo lleva su etiqueta QR. Ábrelo para ver su ficha e historial.
          </p>
        </div>
        {usuario.rol === "administrador" ? (
          <EnlaceBoton href="/activos/nuevo" primario>
            Dar de alta un equipo
          </EnlaceBoton>
        ) : null}
      </div>

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="flex flex-col gap-3 border-b border-borde px-5 py-4 sm:flex-row sm:items-end sm:px-6">
          <div className="sm:w-80">
            <Campo
              id="buscar-equipo"
              etiqueta="Buscar"
              nombre="q"
              tipo="search"
              valor={texto}
              onCambio={setTexto}
              autoComplete="off"
              maxLength={120}
            />
          </div>
          <fieldset className="pb-7">
            <legend className="sr-only">Estado</legend>
            <div className="inline-flex rounded-[var(--radius-control)] border border-borde-fuerte">
              {filtros.map(([valor, nombre]) => (
                <label
                  key={nombre}
                  className={[
                    "flex h-12 cursor-pointer items-center px-4 text-[0.875rem] font-medium transition-colors first:rounded-l-[var(--radius-control)] last:rounded-r-[var(--radius-control)] [&:not(:first-child)]:border-l [&:not(:first-child)]:border-borde-fuerte",
                    "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accion",
                    estado === valor ? "bg-[var(--accion-halo)] text-accion" : "bg-superficie text-texto-suave hover:text-texto",
                  ].join(" ")}
                >
                  <input
                    type="radio"
                    name="estado"
                    className="sr-only"
                    checked={estado === valor}
                    onChange={() => setEstado(valor)}
                  />
                  {nombre}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="px-5 py-4 sm:px-6">
          {error !== null ? (
            <p role="alert" className="text-[0.9375rem] text-error">
              {error}
            </p>
          ) : items === null ? (
            <Esqueleto />
          ) : items.length === 0 ? (
            <SinEquipos buscando={busqueda !== ""} admin={usuario.rol === "administrador"} />
          ) : (
            <TablaEquipos items={items} />
          )}
        </div>

        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()} enCurso={cargandoMas} textoEnCurso="Cargando…">
              Cargar más equipos
            </Boton>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function SinEquipos({ buscando, admin }: { readonly buscando: boolean; readonly admin: boolean }) {
  if (buscando) {
    return <p className="py-4 text-[0.9375rem] text-texto-suave">Ningún equipo coincide con la búsqueda.</p>;
  }
  return (
    <div className="flex flex-col items-start gap-3 py-4">
      <p className="max-w-[60ch] text-[0.9375rem] leading-6 text-texto-suave">
        {admin
          ? "Todavía no hay equipos. Da de alta el primero: SIMAP le genera su código QR para imprimir y pegar en la máquina."
          : "Todavía no hay equipos dados de alta. Los registra el administrador de tu planta."}
      </p>
    </div>
  );
}

function TablaEquipos({ items }: { readonly items: readonly Activo[] }) {
  return (
    <table className="w-full border-collapse text-left">
      <thead className="hidden md:table-header-group">
        <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
          <th scope="col" className="pb-2 pr-4 font-medium">Equipo</th>
          <th scope="col" className="pb-2 pr-4 font-medium">Ubicación</th>
          <th scope="col" className="pb-2 pr-4 font-medium">Criticidad</th>
          <th scope="col" className="pb-2 pr-4 text-right font-medium">Horómetro</th>
          <th scope="col" className="pb-2 font-medium">Estado</th>
        </tr>
      </thead>
      <tbody>
        {items.map((a) => (
          <tr
            key={a.id}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 border-b border-borde py-3 last:border-0 md:table-row md:py-0"
          >
            <td className="min-w-0 md:py-3 md:pr-4">
              <Link
                href={`/a/${a.codigo}`}
                className="font-semibold text-accion underline-offset-2 hover:underline [overflow-wrap:anywhere]"
              >
                {a.nombre}
              </Link>
              <span className="block font-mono text-[0.8125rem] tracking-[0.06em] text-texto-tenue">
                {a.codigo_corto}
              </span>
            </td>
            <td className="col-start-1 text-[0.875rem] text-texto-suave md:py-3 md:pr-4 md:text-[0.9375rem]">
              {a.ubicacion ?? <span className="text-texto-tenue">—</span>}
            </td>
            <td className="hidden md:table-cell md:py-3 md:pr-4">
              <Criticidad valor={a.criticidad} />
            </td>
            <td className="col-start-2 row-start-1 text-right md:py-3 md:pr-4">
              <span className="block font-semibold text-texto">
                {a.horometro_actualizado_en === null ? "—" : horas(a.horometro_actual)}
              </span>
              {a.horometro_actualizado_en !== null ? (
                <span className="block text-[0.75rem] text-texto-tenue">{hace(a.horometro_actualizado_en)}</span>
              ) : null}
            </td>
            <td className="col-start-2 row-start-2 justify-self-end md:py-3">
              <EstadoEquipo estado={a.estado} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
