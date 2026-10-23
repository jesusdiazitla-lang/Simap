"use client";

/**
 * Un repuesto y su libro de movimientos (RF-23, RF-26; 07-fase4, 6.5, 6.6 y 10.3).
 *
 * El libro se muestra con el stock resultante en cada fila: cualquiera puede revisar de dónde sale
 * el número actual. Acciones por rol (decisión 2): ingreso de mercancía (supervisor y
 * administrador); editar nombre, mínimo, costo o desactivar, y ajustar por conteo físico con nota
 * (solo administrador). El técnico no entra aquí: consulta existencias en la lista.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Insignia } from "@/components/estado";
import { IconoAviso } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { fechaHora } from "@/lib/formato";
import {
  ajustarPorConteo,
  dinero,
  editarRepuesto,
  ETIQUETA_MOVIMIENTO,
  movimientos,
  obtenerRepuesto,
  registrarIngreso,
  type Movimiento,
  type Repuesto,
} from "@/lib/inventario";

const ROLES: readonly Rol[] = ["supervisor", "gerente", "administrador"];

export default function RepuestoPage() {
  return (
    <Pantalla roles={ROLES} cargando="Repuesto">
      {(usuario, sinRed) => <Detalle usuario={usuario} sinRed={sinRed} />}
    </Pantalla>
  );
}

function Detalle({ usuario, sinRed }: { readonly usuario: Usuario; readonly sinRed: boolean }) {
  const { id } = useParams<{ id: string }>();
  const [repuesto, setRepuesto] = useState<Repuesto | null>(null);
  const [libro, setLibro] = useState<readonly Movimiento[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const admin = usuario.rol === "administrador";
  const ingresa = admin || usuario.rol === "supervisor";

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      Promise.all([obtenerRepuesto(id, signal), movimientos(id, undefined, signal)])
        .then(([r, p]) => {
          setRepuesto(r);
          setLibro(p.items);
          setCursor(p.next_cursor);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof ErrorApi && e.estado === 404 ? "Este repuesto no existe." : "No se pudo cargar el repuesto.");
        }),
    [id],
  );

  useEffect(() => {
    const control = new AbortController();
    void cargar(control.signal);
    return () => control.abort();
  }, [cargar]);

  if (error !== null && repuesto === null) {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Repuesto">
          <p className="pb-4 text-[0.9375rem] text-error">{error}</p>
          <EnlaceBoton href="/inventario">Volver al inventario</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (repuesto === null || libro === null) {
    return (
      <Panel titulo="Repuesto">
        <Esqueleto />
      </Panel>
    );
  }

  async function masMovimientos(): Promise<void> {
    if (cursor === null) return;
    const p = await movimientos(id, cursor);
    setLibro((l) => [...(l ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  const alMover = (r: Repuesto) => {
    setRepuesto(r);
    void cargar();
  };

  return (
    <div className="flex flex-col gap-6">
      <Link href="/inventario" className="self-start text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline">
        ← Inventario
      </Link>

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[1.375rem] font-semibold leading-7 text-texto [overflow-wrap:anywhere]">{repuesto.nombre}</h1>
          {repuesto.bajo_minimo ? (
            <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>Bajo el mínimo</Insignia>
          ) : null}
          {repuesto.activo === false ? <Insignia tono="neutro">Desactivado</Insignia> : null}
        </div>
        <p className="pt-1 font-mono text-[0.875rem] tracking-[0.04em] text-texto-suave">{repuesto.codigo}</p>
        <dl className="mt-4 grid grid-cols-3 gap-x-6 gap-y-3 border-t border-borde pt-4">
          {(
            [
              ["En almacén", String(repuesto.stock_actual)],
              ["Mínimo", String(repuesto.stock_minimo)],
              ["Costo unitario", repuesto.costo_unitario !== undefined ? dinero(repuesto.costo_unitario) : "—"],
            ] as const
          ).map(([nombre, valor]) => (
            <div key={nombre}>
              <dt className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">{nombre}</dt>
              <dd className="pt-1 text-[1.0625rem] font-semibold text-texto">{valor}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
        <Panel nivel={2} titulo="Libro de movimientos" descripcion="Solo se agrega: nadie puede modificarlo ni borrarlo.">
          {libro.length === 0 ? (
            <p className="text-[0.9375rem] text-texto-suave">Sin movimientos todavía.</p>
          ) : (
            <table className="w-full border-collapse text-left text-[0.9375rem]">
              <thead>
                <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
                  <th scope="col" className="pb-2 pr-3 font-medium">Movimiento</th>
                  <th scope="col" className="pb-2 pr-3 text-right font-medium">Cambio</th>
                  <th scope="col" className="pb-2 text-right font-medium">Queda</th>
                </tr>
              </thead>
              <tbody>
                {libro.map((m) => (
                  <tr key={m.id} className="border-b border-borde last:border-0">
                    <td className="py-2.5 pr-3">
                      <span className="block font-medium text-texto">{ETIQUETA_MOVIMIENTO[m.tipo]}</span>
                      <span className="block text-[0.8125rem] text-texto-tenue">
                        {fechaHora(m.creado_en)}
                        {m.orden_id !== null ? (
                          <>
                            {" · "}
                            <Link href={`/ordenes/${m.orden_id}`} className="text-accion underline-offset-2 hover:underline">
                              ver la orden
                            </Link>
                          </>
                        ) : null}
                      </span>
                      {m.nota !== null ? (
                        <span className="block text-[0.8125rem] text-texto-suave [overflow-wrap:anywhere]">{m.nota}</span>
                      ) : null}
                    </td>
                    <td className={`py-2.5 pr-3 text-right font-semibold ${m.delta < 0 ? "text-texto" : "text-texto"}`}>
                      {m.delta > 0 ? `+${m.delta}` : `−${Math.abs(m.delta)}`}
                    </td>
                    <td className="py-2.5 text-right text-texto-suave">{m.stock_resultante}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {cursor !== null ? (
            <div className="pt-4">
              <Boton tipo="button" variante="secundario" onClick={() => void masMovimientos()}>
                Movimientos anteriores
              </Boton>
            </div>
          ) : null}
        </Panel>

        <div className="flex flex-col gap-6">
          {ingresa ? <Ingreso repuesto={repuesto} sinRed={sinRed} alMover={alMover} /> : null}
          {admin ? <Editar repuesto={repuesto} sinRed={sinRed} alGuardar={setRepuesto} /> : null}
          {admin ? <Conteo repuesto={repuesto} sinRed={sinRed} alMover={alMover} /> : null}
        </div>
      </div>
    </div>
  );
}

function Ingreso({
  repuesto,
  sinRed,
  alMover,
}: {
  readonly repuesto: Repuesto;
  readonly sinRed: boolean;
  readonly alMover: (r: Repuesto) => void;
}) {
  const [cantidad, setCantidad] = useState("");
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [enCurso, setEnCurso] = useState(false);
  const n = Number(cantidad);
  const valido = /^\d+$/.test(cantidad) && n >= 1;

  return (
    <Panel nivel={2} titulo="Registrar un ingreso" descripcion="Mercancía que llega al almacén.">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!valido) return;
          setEnCurso(true);
          setError(undefined);
          registrarIngreso(repuesto.id, n, nota.trim() || null)
            .then((r) => {
              alMover(r);
              setCantidad("");
              setNota("");
            })
            .catch((fallo: unknown) => setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo registrar."))
            .finally(() => setEnCurso(false));
        }}
        className="flex flex-col gap-3"
      >
        <Campo etiqueta="Cantidad" nombre="cantidad" modoTeclado="numeric" valor={cantidad} onCambio={(v) => setCantidad(v.replace(/\D/g, ""))} error={error} maxLength={7} />
        <Campo etiqueta="Nota (opcional)" ayuda="Factura, proveedor… Sin datos personales: no se borra." nombre="nota" valor={nota} onCambio={setNota} maxLength={500} autoComplete="off" />
        <div>
          <Boton deshabilitado={!valido || sinRed} enCurso={enCurso} textoEnCurso="Registrando…">
            {valido ? `Ingresar ${n}` : "Escribe la cantidad"}
          </Boton>
        </div>
      </form>
    </Panel>
  );
}

function Editar({
  repuesto,
  sinRed,
  alGuardar,
}: {
  readonly repuesto: Repuesto;
  readonly sinRed: boolean;
  readonly alGuardar: (r: Repuesto) => void;
}) {
  const [nombre, setNombre] = useState(repuesto.nombre);
  const [minimo, setMinimo] = useState(String(repuesto.stock_minimo));
  const [costo, setCosto] = useState(repuesto.costo_unitario ?? "0.00");
  const [error, setError] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);

  async function guardar(cambios: Parameters<typeof editarRepuesto>[1]): Promise<void> {
    setEnCurso(true);
    setError(null);
    try {
      alGuardar(await editarRepuesto(repuesto.id, cambios));
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo guardar.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel nivel={2} titulo="Datos del repuesto" descripcion="El stock no se edita aquí: solo lo mueven ingresos, consumos y conteos.">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!/^\d+$/.test(minimo) || !/^\d+(\.\d{1,2})?$/.test(costo.replace(",", ".")) || nombre.trim().length < 2) {
            setError("Revisa los datos: nombre de al menos 2 letras, mínimo entero y costo como 125.50.");
            return;
          }
          void guardar({ nombre: nombre.trim(), stock_minimo: Number(minimo), costo_unitario: costo.replace(",", ".") });
        }}
        className="flex flex-col gap-3"
      >
        <Campo etiqueta="Nombre" nombre="nombre" valor={nombre} onCambio={setNombre} maxLength={120} autoComplete="off" />
        <Campo etiqueta="Stock mínimo" nombre="stock_minimo" modoTeclado="numeric" valor={minimo} onCambio={(v) => setMinimo(v.replace(/\D/g, ""))} maxLength={7} />
        <Campo etiqueta="Costo unitario (RD$)" ayuda="Los consumos guardan el costo del momento: cambiarlo no altera lo ya consumido." nombre="costo" valor={costo} onCambio={setCosto} maxLength={13} />
        <div className="flex flex-wrap gap-2">
          <Boton variante="secundario" deshabilitado={sinRed} enCurso={enCurso} textoEnCurso="Guardando…">Guardar</Boton>
          <Boton
            tipo="button"
            variante="secundario"
            deshabilitado={sinRed}
            onClick={() => void guardar({ activo: repuesto.activo === false })}
          >
            {repuesto.activo === false ? "Reactivar" : "Desactivar"}
          </Boton>
        </div>
        {error !== null ? <p role="alert" className="text-[0.875rem] text-error">{error}</p> : null}
      </form>
    </Panel>
  );
}

function Conteo({
  repuesto,
  sinRed,
  alMover,
}: {
  readonly repuesto: Repuesto;
  readonly sinRed: boolean;
  readonly alMover: (r: Repuesto) => void;
}) {
  const [conteo, setConteo] = useState("");
  const [nota, setNota] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const n = Number(conteo);
  const valido = /^\d+$/.test(conteo) && nota.trim().length >= 3;
  const diferencia = valido ? n - repuesto.stock_actual : 0;

  return (
    <Panel nivel={2} titulo="Ajuste por conteo físico" descripcion="Cuando el conteo del almacén no coincide con el sistema. Queda en el libro con la diferencia y tu nota.">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!valido) {
            setError("Escribe lo que contaste y por qué no coincide (mínimo 3 letras).");
            return;
          }
          if (!confirmando) {
            setConfirmando(true);
            setError(null);
            return;
          }
          setEnCurso(true);
          ajustarPorConteo(repuesto.id, n, nota.trim())
            .then((r) => {
              alMover(r);
              setConteo("");
              setNota("");
              setConfirmando(false);
            })
            .catch((fallo: unknown) => setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo ajustar."))
            .finally(() => setEnCurso(false));
        }}
        className="flex flex-col gap-3"
      >
        <Campo etiqueta="Unidades contadas" nombre="conteo" modoTeclado="numeric" valor={conteo} onCambio={(v) => { setConteo(v.replace(/\D/g, "")); setConfirmando(false); }} maxLength={7} />
        <Campo etiqueta="Por qué no coincide" nombre="nota" valor={nota} onCambio={(v) => { setNota(v); setConfirmando(false); }} maxLength={500} autoComplete="off" requerido />
        {confirmando ? (
          <p role="status" className="rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna px-3 py-2 text-[0.9375rem] text-texto">
            {diferencia === 0
              ? "Coincide con el sistema: no se asentará nada."
              : `El stock pasará de ${repuesto.stock_actual} a ${n} (${diferencia > 0 ? "+" : "−"}${Math.abs(diferencia)}). Pulsa otra vez para confirmar.`}
          </p>
        ) : null}
        <div>
          <Boton variante="secundario" deshabilitado={sinRed} enCurso={enCurso} textoEnCurso="Ajustando…">
            {confirmando ? "Confirmar el ajuste" : "Revisar el ajuste"}
          </Boton>
        </div>
        {error !== null ? <p role="alert" className="text-[0.875rem] text-error">{error}</p> : null}
      </form>
    </Panel>
  );
}
