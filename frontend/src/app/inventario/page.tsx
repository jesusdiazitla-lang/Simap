"use client";

/**
 * Inventario de repuestos (RF-23, RF-26; 07-fase4, 10.1 y 10.3).
 *
 * Lista con stock, mínimo y la marca «bajo el mínimo». Roles por acción (decisión 2): el
 * administrador da de alta repuestos; el supervisor registra ingresos (desde el detalle); el técnico
 * consulta existencias, sin costos; el gerente solo lee. El stock no se edita: lo mueve el libro.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Insignia } from "@/components/estado";
import { IconoAviso } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { Segmento } from "@/components/segmento";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { crearRepuesto, dinero, listarRepuestos, type Repuesto } from "@/lib/inventario";

const ROLES: readonly Rol[] = ["supervisor", "tecnico_taller", "gerente", "administrador"];

export default function InventarioPage() {
  return (
    <Pantalla roles={ROLES} cargando="Inventario">
      {(usuario) => <Inventario usuario={usuario} />}
    </Pantalla>
  );
}

function BajoMinimo() {
  return (
    <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>
      Bajo el mínimo
    </Insignia>
  );
}

function Inventario({ usuario }: { readonly usuario: Usuario }) {
  const [filtro, setFiltro] = useState<"todos" | "bajos">("todos");
  const [buscar, setBuscar] = useState("");
  const [repuestos, setRepuestos] = useState<readonly Repuesto[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const admin = usuario.rol === "administrador";
  const veDetalle = usuario.rol !== "tecnico_taller";

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      listarRepuestos({ buscar: buscar.trim() || undefined, bajoMinimo: filtro === "bajos", inactivos: admin }, signal)
        .then((p) => {
          setRepuestos(p.items);
          setCursor(p.next_cursor);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof ErrorApi ? e.message : "No se pudo cargar el inventario.");
        }),
    [buscar, filtro, admin],
  );

  useEffect(() => {
    const control = new AbortController();
    const t = setTimeout(() => void cargar(control.signal), 250);
    return () => {
      clearTimeout(t);
      control.abort();
    };
  }, [cargar]);

  async function cargarMas(): Promise<void> {
    if (cursor === null) return;
    const p = await listarRepuestos({ buscar: buscar.trim() || undefined, bajoMinimo: filtro === "bajos", inactivos: admin, cursor });
    setRepuestos((a) => [...(a ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="max-w-[70ch]">
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Inventario de repuestos</h1>
        <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
          {usuario.rol === "tecnico_taller"
            ? "Existencias del almacén. Los repuestos que uses se anotan en la orden y se descuentan al cerrarla."
            : "Existencias, mínimos y el libro de cada repuesto. El stock solo cambia por ingresos, consumos de órdenes cerradas y conteos."}
        </p>
      </div>

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="flex flex-col gap-3 border-b border-borde px-5 py-4 sm:flex-row sm:items-center sm:px-6">
          <Segmento
            nombre="filtro-inventario"
            leyenda="Mostrar"
            opciones={[["todos", "Todos"], ["bajos", "Bajo el mínimo"]] as const}
            valor={filtro}
            alCambiar={(v) => {
              setFiltro(v);
              setRepuestos(null);
            }}
          />
          <label className="sr-only" htmlFor="buscar-repuesto">Buscar repuesto</label>
          <input
            id="buscar-repuesto"
            type="search"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            placeholder="Buscar por nombre o código"
            className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)] sm:max-w-xs"
          />
        </div>
        <div className="px-5 py-4 sm:px-6">
          {error !== null && repuestos === null ? (
            <p role="alert" className="text-[0.9375rem] text-error">{error}</p>
          ) : repuestos === null ? (
            <Esqueleto />
          ) : repuestos.length === 0 ? (
            <p className="py-2 text-[0.9375rem] text-texto-suave">
              {filtro === "bajos"
                ? "Ningún repuesto está bajo su mínimo."
                : buscar.trim() !== ""
                  ? "Ningún repuesto coincide con la búsqueda."
                  : admin
                    ? "Todavía no hay repuestos. Da de alta el primero abajo."
                    : "Todavía no hay repuestos. Los da de alta el administrador."}
            </p>
          ) : (
            <table className="w-full border-collapse text-left">
              <thead className="hidden md:table-header-group">
                <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
                  <th scope="col" className="pb-2 pr-4 font-medium">Repuesto</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-medium">Stock</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-medium">Mínimo</th>
                  {veDetalle ? <th scope="col" className="pb-2 pr-4 text-right font-medium">Costo unitario</th> : null}
                  <th scope="col" className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {repuestos.map((r) => (
                  <tr key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 border-b border-borde py-3 last:border-0 md:table-row md:py-0">
                    <td className="min-w-0 md:py-3 md:pr-4">
                      {veDetalle ? (
                        <Link href={`/inventario/${r.id}`} className="font-semibold text-accion underline-offset-2 hover:underline [overflow-wrap:anywhere]">
                          {r.nombre}
                        </Link>
                      ) : (
                        <span className="font-semibold text-texto [overflow-wrap:anywhere]">{r.nombre}</span>
                      )}
                      <span className="block font-mono text-[0.8125rem] tracking-[0.04em] text-texto-suave">{r.codigo}</span>
                    </td>
                    <td className="col-start-2 row-start-1 text-right text-[1rem] font-semibold text-texto md:py-3 md:pr-4">{r.stock_actual}</td>
                    <td className="col-start-1 text-[0.875rem] text-texto-suave md:py-3 md:pr-4 md:text-right md:text-[0.9375rem]">
                      <span className="md:hidden">Mínimo </span>
                      {r.stock_minimo}
                    </td>
                    {veDetalle ? (
                      <td className="hidden text-right text-texto-suave md:table-cell md:py-3 md:pr-4">
                        {r.costo_unitario !== undefined ? dinero(r.costo_unitario) : "—"}
                      </td>
                    ) : null}
                    <td className="col-start-2 flex flex-col items-end gap-1 md:table-cell md:py-3">
                      {r.bajo_minimo ? <BajoMinimo /> : null}
                      {r.activo === false ? <Insignia tono="neutro">Desactivado</Insignia> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()}>
              Cargar más repuestos
            </Boton>
          </div>
        ) : null}
      </section>

      {admin ? <Alta alCrear={() => void cargar()} /> : null}
    </div>
  );
}

function Alta({ alCrear }: { readonly alCrear: () => void }) {
  const [nombre, setNombre] = useState("");
  const [codigo, setCodigo] = useState("");
  const [stock, setStock] = useState("0");
  const [minimo, setMinimo] = useState("0");
  const [costo, setCosto] = useState("0.00");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [enCurso, setEnCurso] = useState(false);
  const [hecho, setHecho] = useState<string | null>(null);

  async function enviar(): Promise<void> {
    const e: Record<string, string> = {};
    if (nombre.trim().length < 2) e.nombre = "Al menos 2 letras.";
    if (codigo.trim() === "") e.codigo = "El código interno o del fabricante.";
    if (!/^\d+$/.test(stock)) e.stock_inicial = "Unidades enteras.";
    if (!/^\d+$/.test(minimo)) e.stock_minimo = "Unidades enteras.";
    if (!/^\d+(\.\d{1,2})?$/.test(costo.replace(",", "."))) e.costo_unitario = "Un importe, por ejemplo 125.50.";
    setErrores(e);
    setHecho(null);
    if (Object.keys(e).length > 0) return;
    setEnCurso(true);
    try {
      const r = await crearRepuesto({
        nombre: nombre.trim(),
        codigo: codigo.trim(),
        stock_inicial: Number(stock),
        stock_minimo: Number(minimo),
        costo_unitario: costo.replace(",", "."),
      });
      setHecho(`${r.nombre} (${r.codigo}) dado de alta${r.stock_actual > 0 ? ` con ${r.stock_actual} en el libro` : ""}.`);
      setNombre("");
      setCodigo("");
      setStock("0");
      setMinimo("0");
      setCosto("0.00");
      alCrear();
    } catch (fallo) {
      if (fallo instanceof ErrorApi && fallo.conflicto?.codigo === "codigo_repuesto_duplicado") {
        setErrores({ codigo: fallo.message });
      } else if (fallo instanceof ErrorApi) {
        setErrores({ ...fallo.campos, _: fallo.message });
      } else {
        setErrores({ _: "No se pudo dar de alta." });
      }
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel nivel={2} titulo="Nuevo repuesto" descripcion="El stock inicial entra al libro como primer movimiento. Después, el stock solo cambia por el libro.">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
        className="flex flex-col gap-4"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Nombre" nombre="nombre" valor={nombre} onCambio={setNombre} error={errores.nombre} maxLength={120} requerido autoComplete="off" />
          <Campo etiqueta="Código" nombre="codigo" valor={codigo} onCambio={setCodigo} error={errores.codigo} maxLength={60} requerido autoComplete="off" />
          <Campo etiqueta="Stock inicial" nombre="stock_inicial" modoTeclado="numeric" valor={stock} onCambio={(v) => setStock(v.replace(/\D/g, ""))} error={errores.stock_inicial} maxLength={7} />
          <Campo etiqueta="Stock mínimo" ayuda="Por debajo de este número se crea una alerta de reorden." nombre="stock_minimo" modoTeclado="numeric" valor={minimo} onCambio={(v) => setMinimo(v.replace(/\D/g, ""))} error={errores.stock_minimo} maxLength={7} />
          <Campo etiqueta="Costo unitario (RD$)" nombre="costo_unitario" valor={costo} onCambio={setCosto} error={errores.costo_unitario} maxLength={13} />
        </div>
        <div>
          <Boton enCurso={enCurso} textoEnCurso="Dando de alta…">Dar de alta</Boton>
        </div>
        {hecho !== null ? <p role="status" className="text-[0.9375rem] text-texto-suave">{hecho}</p> : null}
        {errores._ !== undefined ? <p role="alert" className="text-[0.9375rem] text-error">{errores._}</p> : null}
      </form>
    </Panel>
  );
}
