"use client";

/**
 * Repuestos usados en una orden (RF-24; 07-fase4, 10.3).
 *
 * Mientras la orden está abierta, el técnico (y el supervisor o el administrador) busca el repuesto
 * por nombre o código y fija la cantidad; corregir es volver a guardar la cantidad. El stock se
 * muestra al lado **como orientación**: el descuento lo hace el servidor al cerrar la orden, y si no
 * alcanza, el cierre se rechaza con lo que falta (decisiones 1 y 3).
 *
 * Con la orden cerrada, la lista es lo que se consumió. El técnico no ve costos (decisión 2).
 */

import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { Boton } from "@/components/boton";
import { ErrorApi } from "@/lib/api";
import type { Usuario } from "@/lib/auth";
import {
  dinero,
  guardarLinea,
  listarRepuestos,
  quitarLinea,
  type Linea,
  type Repuesto,
} from "@/lib/inventario";
import type { OrdenDetalle } from "@/lib/ordenes";

const ABIERTAS = new Set(["reportada", "en_taller", "reparada"]);

export function RepuestosOrden({
  orden,
  usuario,
  lineas,
  alCambiar,
}: {
  readonly orden: OrdenDetalle;
  readonly usuario: Usuario;
  readonly lineas: readonly Linea[] | null;
  readonly alCambiar: (lineas: readonly Linea[]) => void;
}) {
  const abierta = ABIERTAS.has(orden.estado);
  const edita =
    abierta && ["tecnico_taller", "supervisor", "administrador"].includes(usuario.rol);
  const veCostos = usuario.rol !== "tecnico_taller";
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  async function cambiar(repuestoId: string, cantidad: number | null): Promise<void> {
    setOcupado(repuestoId);
    setError(null);
    try {
      if (cantidad === null) {
        await quitarLinea(orden.id, repuestoId);
        alCambiar((lineas ?? []).filter((l) => l.repuesto_id !== repuestoId));
      } else {
        alCambiar(await guardarLinea(orden.id, repuestoId, cantidad));
      }
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo guardar el repuesto.");
    } finally {
      setOcupado(null);
    }
  }

  const total = (lineas ?? []).reduce(
    (suma, l) => suma + (l.costo_unitario === null ? 0 : Number(l.costo_unitario) * l.cantidad),
    0,
  );

  return (
    <div className="flex flex-col gap-4">
      {lineas === null ? (
        <p className="text-[0.9375rem] text-texto-suave">Cargando repuestos…</p>
      ) : lineas.length === 0 ? (
        <p className="text-[0.9375rem] leading-6 text-texto-suave">
          {abierta
            ? "Sin repuestos anotados. Anota aquí lo que se use en la reparación: se descuenta del almacén al cerrar la orden."
            : "Esta orden no consumió repuestos."}
        </p>
      ) : (
        <table className="w-full border-collapse text-left text-[0.9375rem]">
          <thead>
            <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
              <th scope="col" className="pb-2 pr-3 font-medium">Repuesto</th>
              <th scope="col" className="pb-2 pr-3 text-right font-medium">Cantidad</th>
              {abierta ? <th scope="col" className="pb-2 pr-3 text-right font-medium">En almacén</th> : null}
              {veCostos ? <th scope="col" className="pb-2 text-right font-medium">Costo</th> : null}
              {edita ? <th scope="col" className="pb-2 text-right font-medium"><span className="sr-only">Quitar</span></th> : null}
            </tr>
          </thead>
          <tbody>
            {lineas.map((l) => {
              const noAlcanza = abierta && l.stock_actual < l.cantidad;
              return (
                <tr key={l.repuesto_id} className="border-b border-borde last:border-0">
                  <td className="py-2.5 pr-3">
                    <span className="block font-medium text-texto [overflow-wrap:anywhere]">{l.nombre}</span>
                    <span className="block font-mono text-[0.8125rem] tracking-[0.04em] text-texto-suave">{l.codigo}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-right">
                    {edita ? (
                      <Cantidad
                        key={l.cantidad}
                        valor={l.cantidad}
                        nombre={l.nombre}
                        ocupado={ocupado === l.repuesto_id}
                        alGuardar={(n) => void cambiar(l.repuesto_id, n)}
                      />
                    ) : (
                      <span className="font-semibold text-texto">{l.cantidad}</span>
                    )}
                  </td>
                  {abierta ? (
                    <td className="py-2.5 pr-3 text-right">
                      <span className={noAlcanza ? "font-semibold text-estado-aviso" : "text-texto-suave"}>
                        {l.stock_actual}
                      </span>
                      {noAlcanza ? <span className="block text-[0.75rem] text-estado-aviso">No alcanza</span> : null}
                    </td>
                  ) : null}
                  {veCostos ? (
                    <td className="py-2.5 text-right text-texto-suave">
                      {l.costo_unitario === null ? "—" : dinero(Number(l.costo_unitario) * l.cantidad)}
                    </td>
                  ) : null}
                  {edita ? (
                    <td className="py-2.5 pl-2 text-right">
                      <button
                        type="button"
                        onClick={() => void cambiar(l.repuesto_id, null)}
                        disabled={ocupado === l.repuesto_id}
                        className="h-10 rounded-[var(--radius-control)] px-2 text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline disabled:text-texto-tenue"
                      >
                        Quitar
                      </button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
          {veCostos && lineas.length > 0 ? (
            <tfoot>
              <tr>
                <td colSpan={abierta ? 3 : 2} className="pt-3 text-right text-[0.8125rem] text-texto-suave">
                  {abierta ? "Costo estimado al precio de hoy" : "Costo al precio del cierre"}
                </td>
                <td className="pt-3 text-right font-semibold text-texto">{dinero(total)}</td>
                {edita ? <td /> : null}
              </tr>
            </tfoot>
          ) : null}
        </table>
      )}

      {edita ? (
        <Agregar
          yaAnotados={new Set((lineas ?? []).map((l) => l.repuesto_id))}
          alAgregar={(id, cantidad) => void cambiar(id, cantidad)}
          ocupado={ocupado !== null}
        />
      ) : null}

      {error !== null ? (
        <p role="alert" className="text-[0.9375rem] text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Cantidad({
  valor,
  nombre,
  ocupado,
  alGuardar,
}: {
  readonly valor: number;
  readonly nombre: string;
  readonly ocupado: boolean;
  readonly alGuardar: (n: number) => void;
}) {
  // Vuelve al valor guardado cuando cambia: quien la monta le pone `key={cantidad}`.
  const [texto, setTexto] = useState(String(valor));
  const n = Number(texto);
  const valido = /^\d+$/.test(texto) && n >= 1 && n <= 10000;
  return (
    <input
      aria-label={`Cantidad de ${nombre}`}
      inputMode="numeric"
      value={texto}
      disabled={ocupado}
      onChange={(e) => setTexto(e.target.value.replace(/\D/g, ""))}
      onBlur={() => {
        if (valido && n !== valor) alGuardar(n);
        else setTexto(String(valor));
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      className="h-10 w-20 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-2 text-right text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)] disabled:bg-superficie-alterna disabled:text-texto-tenue"
    />
  );
}

/** Buscar un repuesto por nombre o código y añadirlo con su cantidad. */
function Agregar({
  yaAnotados,
  alAgregar,
  ocupado,
}: {
  readonly yaAnotados: ReadonlySet<string>;
  readonly alAgregar: (repuestoId: string, cantidad: number) => void;
  readonly ocupado: boolean;
}) {
  const id = useId();
  const [buscar, setBuscar] = useState("");
  const [resultados, setResultados] = useState<readonly Repuesto[]>([]);
  const [elegido, setElegido] = useState<Repuesto | null>(null);
  const [cantidad, setCantidad] = useState("1");

  const buscando = buscar.trim().length >= 2 && elegido === null;
  useEffect(() => {
    if (!buscando) return;
    const control = new AbortController();
    const t = setTimeout(() => {
      listarRepuestos({ buscar: buscar.trim() }, control.signal)
        .then((p) => setResultados(p.items))
        .catch(() => setResultados([]));
    }, 250);
    return () => {
      clearTimeout(t);
      control.abort();
    };
  }, [buscar, buscando]);
  const visibles = buscando ? resultados : [];

  const n = Number(cantidad);
  const valido = elegido !== null && /^\d+$/.test(cantidad) && n >= 1 && n <= 10000;

  return (
    <div className="flex flex-col gap-3 border-t border-borde pt-4">
      <label htmlFor={`${id}-buscar`} className="text-[0.8125rem] font-medium text-texto">
        Añadir un repuesto
      </label>
      {elegido === null ? (
        <>
          <input
            id={`${id}-buscar`}
            type="search"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            placeholder="Nombre o código, por ejemplo «filtro» o «RP-014»"
            autoComplete="off"
            className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
          />
          {visibles.length > 0 ? (
            <ul className="divide-y divide-borde rounded-[var(--radius-control)] border border-borde-fuerte">
              {visibles.map((r) => {
                const anotado = yaAnotados.has(r.id);
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      disabled={anotado}
                      onClick={() => setElegido(r)}
                      className="flex min-h-12 w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-superficie-alterna disabled:cursor-not-allowed disabled:text-texto-tenue"
                    >
                      <span className="min-w-0">
                        <span className="block font-medium [overflow-wrap:anywhere]">{r.nombre}</span>
                        <span className="block font-mono text-[0.8125rem] tracking-[0.04em] text-texto-suave">{r.codigo}</span>
                      </span>
                      <span className="shrink-0 text-[0.875rem] text-texto-suave">
                        {anotado ? "Ya anotado" : `${r.stock_actual} en almacén`}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : buscar.trim().length >= 2 ? (
            <p className="text-[0.875rem] text-texto-suave">
              Ningún repuesto activo coincide. Si falta en el catálogo, lo da de alta el administrador en{" "}
              <Link href="/inventario" className="text-accion underline underline-offset-2">Inventario</Link>.
            </p>
          ) : null}
        </>
      ) : (
        <div className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna p-3 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <p className="font-medium text-texto [overflow-wrap:anywhere]">{elegido.nombre}</p>
            <p className="text-[0.8125rem] text-texto-suave">
              <span className="font-mono tracking-[0.04em]">{elegido.codigo}</span> · {elegido.stock_actual} en almacén
            </p>
          </div>
          <div>
            <label htmlFor={`${id}-cantidad`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
              Cantidad
            </label>
            <input
              id={`${id}-cantidad`}
              inputMode="numeric"
              value={cantidad}
              onChange={(e) => setCantidad(e.target.value.replace(/\D/g, ""))}
              className="h-12 w-24 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-right text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
            />
          </div>
          <div className="flex gap-2">
            <Boton tipo="button" variante="secundario" onClick={() => setElegido(null)}>
              Otro
            </Boton>
            <Boton
              tipo="button"
              variante="secundario"
              deshabilitado={!valido}
              enCurso={ocupado}
              textoEnCurso="Guardando…"
              onClick={() => {
                if (elegido === null || !valido) return;
                alAgregar(elegido.id, n);
                setElegido(null);
                setBuscar("");
                setCantidad("1");
              }}
            >
              Añadir
            </Boton>
          </div>
        </div>
      )}
    </div>
  );
}
