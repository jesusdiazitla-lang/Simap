"use client";

/**
 * Componentes de un equipo y edad de la pieza instalada (07-fase4, 6.1; decisión 7).
 *
 * El administrador dice qué componentes tiene el equipo y **a qué horas del equipo** se instaló la
 * unidad actual: 0 si el equipo era nuevo, vacío si no se sabe. Sin esa edad no hay riesgo, y la
 * pantalla destaca esos componentes. Inventar una edad produciría alarmas o tranquilidad falsas.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Boton } from "@/components/boton";
import { Insignia } from "@/components/estado";
import { IconoAviso } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { listarComponentes, obtenerActivo, type Activo, type Componente } from "@/lib/activos";
import type { Rol } from "@/lib/auth";
import { horas } from "@/lib/formato";
import {
  componentesDelEquipo,
  declararEdad,
  porcentaje,
  type ComponenteEquipo,
  type ComponentesEquipo,
} from "@/lib/prediccion";

const ROLES: readonly Rol[] = ["administrador"];
const COMODIN = "Otro (por identificar)";

export default function ComponentesDelEquipoPage() {
  return (
    <Pantalla roles={ROLES} cargando="Componentes del equipo">
      {() => <Detalle />}
    </Pantalla>
  );
}

function Detalle() {
  const { id } = useParams<{ id: string }>();
  const [activo, setActivo] = useState<Activo | null>(null);
  const [datos, setDatos] = useState<ComponentesEquipo | null>(null);
  const [catalogo, setCatalogo] = useState<readonly Componente[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const control = new AbortController();
    Promise.all([obtenerActivo(id, control.signal), componentesDelEquipo(id, control.signal), listarComponentes()])
      .then(([a, d, c]) => {
        setActivo(a);
        setDatos(d);
        setCatalogo(c.filter((x) => x.activo && x.nombre !== COMODIN));
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi && e.estado === 404 ? "Este equipo no existe." : "No se pudo cargar el equipo.");
      });
    return () => control.abort();
  }, [id]);

  if (error !== null) {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Componentes del equipo">
          <p className="pb-4 text-[0.9375rem] text-error">{error}</p>
          <EnlaceBoton href="/activos">Volver a los equipos</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (activo === null || datos === null) {
    return (
      <Panel titulo="Componentes del equipo">
        <Esqueleto />
      </Panel>
    );
  }

  const registrados = new Set(datos.componentes.map((c) => c.componente_id));
  const sinEdad = datos.componentes.filter((c) => c.horas_instalacion_inicial === null).length;
  const disponibles = catalogo.filter((c) => !registrados.has(c.id));

  return (
    <div className="flex flex-col gap-6">
      <Link href={`/a/${activo.codigo}`} className="self-start text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline">
        ← {activo.nombre}
      </Link>
      <div className="max-w-[70ch]">
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Componentes y edad de las piezas</h1>
        <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
          {activo.nombre} acumula {horas(datos.horas_acumuladas)}. Para cada componente, escribe a cuántas
          horas del equipo se instaló la pieza que tenía al empezar a usar SIMAP: 0 si el equipo era nuevo;
          vacío si no se sabe. Los cambios posteriores los toma SIMAP de las órdenes cerradas.
        </p>
      </div>

      {sinEdad > 0 ? (
        <p className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 shrink-0 text-estado-aviso" />
          <span>
            {sinEdad === 1 ? "Un componente no tiene" : `${sinEdad} componentes no tienen`} edad: no se les
            puede calcular el riesgo hasta que se declare o hasta el primer reemplazo.
          </span>
        </p>
      ) : null}

      <Panel nivel={2} titulo="Componentes registrados">
        {datos.componentes.length === 0 ? (
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            Ninguno todavía. Añade abajo los componentes del equipo, o se registrarán solos con la primera
            falla que se reporte.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-borde">
            {datos.componentes.map((c) => (
              <FilaEdad key={c.componente_id} activoId={id} c={c} maximo={datos.horas_acumuladas} alGuardar={setDatos} />
            ))}
          </ul>
        )}
      </Panel>

      {disponibles.length > 0 ? (
        <Agregar activoId={id} disponibles={disponibles} maximo={datos.horas_acumuladas} alGuardar={setDatos} />
      ) : null}
    </div>
  );
}

function validar(texto: string, maximo: number): string | null {
  if (texto.trim() === "") return null;
  if (!/^\d+$/.test(texto)) return "Solo horas enteras.";
  if (Number(texto) > maximo) return `No puede pasar de las ${horas(maximo)} que acumula el equipo.`;
  return null;
}

function FilaEdad({
  activoId,
  c,
  maximo,
  alGuardar,
}: {
  readonly activoId: string;
  readonly c: ComponenteEquipo;
  readonly maximo: number;
  readonly alGuardar: (d: ComponentesEquipo) => void;
}) {
  const id = useId();
  const [texto, setTexto] = useState(c.horas_instalacion_inicial?.toString() ?? "");
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const original = c.horas_instalacion_inicial?.toString() ?? "";
  const cambiado = texto !== original;

  async function guardar(): Promise<void> {
    const problema = validar(texto, maximo);
    if (problema !== null) {
      setError(problema);
      return;
    }
    setEnCurso(true);
    setError(null);
    try {
      alGuardar(await declararEdad(activoId, c.componente_id, texto.trim() === "" ? null : Number(texto)));
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo guardar.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="font-semibold text-texto">{c.nombre}</p>
        <p className="pt-0.5 text-[0.8125rem] text-texto-suave">
          {c.horas_instalacion_inicial === null ? (
            <Insignia tono="neutro" icono={<IconoAviso className="h-3.5 w-3.5" />}>Sin edad</Insignia>
          ) : (
            <>
              Pieza de {horas(c.edad_horas ?? Math.max(0, maximo - c.horas_instalacion_inicial))}
              {c.riesgo !== null ? ` · riesgo ${porcentaje(c.riesgo)}` : ""}
            </>
          )}
        </p>
      </div>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void guardar();
        }}
        className="flex flex-col gap-1"
      >
        <label htmlFor={`${id}-h`} className="text-[0.8125rem] font-medium text-texto">
          Pieza inicial a las (horas del equipo)
        </label>
        <div className="flex gap-2">
          <input
            id={`${id}-h`}
            inputMode="numeric"
            value={texto}
            onChange={(e) => setTexto(e.target.value.replace(/\D/g, ""))}
            aria-invalid={error !== null}
            placeholder="No se sabe"
            className="h-12 w-36 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-right text-[1rem] text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
          />
          <Boton tipo="submit" variante="secundario" deshabilitado={!cambiado} enCurso={enCurso} textoEnCurso="Guardando…">
            Guardar
          </Boton>
        </div>
        {error !== null ? <p role="alert" className="text-[0.8125rem] text-error">{error}</p> : null}
      </form>
    </li>
  );
}

function Agregar({
  activoId,
  disponibles,
  maximo,
  alGuardar,
}: {
  readonly activoId: string;
  readonly disponibles: readonly Componente[];
  readonly maximo: number;
  readonly alGuardar: (d: ComponentesEquipo) => void;
}) {
  const id = useId();
  const [componente, setComponente] = useState("");
  const [texto, setTexto] = useState("");
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(): Promise<void> {
    const problema = validar(texto, maximo);
    if (problema !== null) {
      setError(problema);
      return;
    }
    setEnCurso(true);
    setError(null);
    try {
      alGuardar(await declararEdad(activoId, componente, texto.trim() === "" ? null : Number(texto)));
      setComponente("");
      setTexto("");
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo añadir.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel nivel={2} titulo="Añadir un componente" descripcion="Del catálogo de la empresa.">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label htmlFor={`${id}-c`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
            Componente
          </label>
          <select
            id={`${id}-c`}
            value={componente}
            onChange={(e) => setComponente(e.target.value)}
            className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
          >
            <option value="">Elige un componente</option>
            {disponibles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-h`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
            Instalada a las (horas)
          </label>
          <input
            id={`${id}-h`}
            inputMode="numeric"
            value={texto}
            onChange={(e) => setTexto(e.target.value.replace(/\D/g, ""))}
            placeholder="No se sabe"
            className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-right text-[1rem] text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)] sm:w-36"
          />
        </div>
        <Boton tipo="submit" deshabilitado={componente === ""} enCurso={enCurso} textoEnCurso="Añadiendo…">
          {componente === "" ? "Elige un componente" : "Añadir"}
        </Boton>
      </form>
      {error !== null ? <p role="alert" className="pt-2 text-[0.875rem] text-error">{error}</p> : null}
    </Panel>
  );
}
