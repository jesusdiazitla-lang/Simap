"use client";

/**
 * Detalle de una orden de trabajo (RF-13, RF-14, RF-15; 06-fase3, 9.3).
 *
 * De arriba abajo: qué falló y dónde, quién hizo cada paso, qué puede hacer ahora quien la mira, y
 * la línea de tiempo completa. La pantalla se actualiza sola cada 30 segundos mientras está a la
 * vista; si una acción choca con algo que hizo otra persona, recarga y lo explica.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AccionesOrden } from "@/components/acciones-orden";
import { EstadoOrdenInsignia, HorometroEnRevision } from "@/components/estado";
import { HistorialOrden } from "@/components/historial-orden";
import { IconoAviso } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { fechaHora, hace, horas } from "@/lib/formato";
import {
  duracion,
  ETIQUETA_INTERVENCION,
  numeroOrden,
  obtenerOrden,
  type OrdenDetalle,
  type Persona,
} from "@/lib/ordenes";
import { useSondeo } from "@/lib/sondeo";

const ROLES: readonly Rol[] = ["supervisor", "tecnico_taller", "gerente", "administrador"];

export default function OrdenPage() {
  return (
    <Pantalla roles={ROLES} cargando="Orden de trabajo">
      {(usuario) => <Detalle usuario={usuario} />}
    </Pantalla>
  );
}

function Detalle({ usuario }: { readonly usuario: Usuario }) {
  const { id } = useParams<{ id: string }>();
  const [orden, setOrden] = useState<OrdenDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflicto, setConflicto] = useState<string | null>(null);

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      obtenerOrden(id, signal)
        .then((o) => {
          setOrden(o);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(
            e instanceof ErrorApi && e.estado === 404
              ? "Esta orden no existe."
              : e instanceof ErrorApi
                ? e.message
                : "No se pudo cargar la orden.",
          );
        }),
    [id],
  );

  useEffect(() => {
    const control = new AbortController();
    void cargar(control.signal);
    return () => control.abort();
  }, [cargar]);

  useSondeo(() => void cargar());

  if (error !== null && orden === null) {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Orden de trabajo">
          <p className="pb-4 text-[0.9375rem] text-error">{error}</p>
          <EnlaceBoton href="/ordenes">Volver a las órdenes</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (orden === null) {
    return (
      <Panel titulo="Orden de trabajo">
        <Esqueleto />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Link href="/ordenes" className="self-start text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline">
        ← Órdenes de trabajo
      </Link>

      {conflicto !== null ? (
        <p role="alert" className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 text-estado-aviso" />
          <span>{conflicto}</span>
        </p>
      ) : null}

      <Cabecera orden={orden} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
        <div className="flex flex-col gap-6">
          <Panel nivel={2} titulo="Qué hacer ahora">
            <AccionesOrden
              orden={orden}
              usuario={usuario}
              alCambiar={(o) => {
                setOrden(o);
                setConflicto(null);
              }}
              alConflicto={(mensaje) => {
                setConflicto(mensaje);
                void cargar();
              }}
            />
          </Panel>
          <Panel nivel={2} titulo="Historial">
            <HistorialOrden eventos={orden.eventos} />
          </Panel>
        </div>
        <Responsables orden={orden} />
      </div>
    </div>
  );
}

function Cabecera({ orden }: { readonly orden: OrdenDetalle }) {
  const datos: Array<[string, string | null]> = [
    ["Fecha de la falla", `${fechaHora(orden.fecha_falla)} · ${hace(orden.fecha_falla)}`],
    ["Horómetro", horas(orden.horometro_en_falla)],
    ["Temperatura", orden.temperatura === null ? null : `${Number(orden.temperatura)} °C`],
    ["Código de error", orden.codigo_error],
  ];
  return (
    <section className="rounded-[var(--radius-control)] border border-borde bg-superficie px-5 py-5 sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="font-mono text-[1.375rem] font-semibold leading-7 tracking-[0.04em] text-texto">
          {numeroOrden(orden.numero)}
        </h1>
        <EstadoOrdenInsignia estado={orden.estado} />
        {orden.requiere_revision ? <HorometroEnRevision /> : null}
      </div>
      <p className="pt-2 text-[1.0625rem] font-semibold leading-6 text-texto [overflow-wrap:anywhere]">
        <Link href={`/a/${orden.activo_codigo}`} className="text-accion underline-offset-2 hover:underline">
          {orden.activo_nombre}
        </Link>
        <span className="text-texto-suave"> · {orden.componente_nombre}</span>
      </p>
      <p className="max-w-[70ch] pt-2 text-[0.9375rem] leading-6 text-texto [overflow-wrap:anywhere]">{orden.descripcion}</p>

      {orden.estado === "cancelada" && orden.motivo_cancelacion !== null ? (
        <p className="mt-3 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna px-3 py-2 text-[0.9375rem] leading-6 text-texto [overflow-wrap:anywhere]">
          <span className="font-semibold">Cancelada:</span> {orden.motivo_cancelacion}
        </p>
      ) : null}

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-borde pt-4 sm:grid-cols-4">
        {datos.map(([nombre, valor]) => (
          <div key={nombre}>
            <dt className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">{nombre}</dt>
            <dd className="pt-1 text-[0.9375rem] text-texto">{valor ?? <span className="text-texto-tenue">—</span>}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Nombre({ persona }: { readonly persona: Persona | null }) {
  if (persona === null) return <span className="text-texto-tenue">Todavía nadie</span>;
  return (
    <>
      {persona.nombre}
      {persona.activo ? null : <span className="text-texto-tenue"> (dado de baja)</span>}
    </>
  );
}

function Responsables({ orden }: { readonly orden: OrdenDetalle }) {
  const filas: Array<[string, Persona | null, string | null]> = [
    ["Reportó", orden.reportado_por, orden.reportada_en],
    ["Reparó", orden.reparado_por, orden.reparada_en],
    ["Autorizó la salida", orden.autorizado_por, orden.fecha_salida_taller],
  ];
  return (
    <div className="flex flex-col gap-6">
      <Panel nivel={2} titulo="Responsables">
        <dl className="divide-y divide-borde">
          {filas.map(([paso, persona, cuando]) => (
            <div key={paso} className="py-2.5 first:pt-0 last:pb-0">
              <dt className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">{paso}</dt>
              <dd className="pt-0.5 text-[0.9375rem] text-texto">
                <Nombre persona={persona} />
                {cuando !== null && persona !== null ? (
                  <span className="block text-[0.8125rem] text-texto-tenue">{fechaHora(cuando)}</span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      </Panel>

      {orden.trabajo_realizado !== null ? (
        <Panel nivel={2} titulo="Trabajo realizado">
          <p className="text-[0.9375rem] leading-6 text-texto [overflow-wrap:anywhere]">{orden.trabajo_realizado}</p>
          {orden.tipo_intervencion !== null ? (
            <p className="pt-2 text-[0.875rem] text-texto-suave">
              Intervención: <span className="font-medium text-texto">{ETIQUETA_INTERVENCION[orden.tipo_intervencion]}</span>
            </p>
          ) : null}
        </Panel>
      ) : null}

      {orden.tiempo_fuera_servicio_min !== null ? (
        <Panel nivel={2} titulo="Tiempo fuera de servicio">
          <p className="text-[1.375rem] font-semibold leading-7 text-texto">{duracion(orden.tiempo_fuera_servicio_min)}</p>
          <p className="pt-1 text-[0.8125rem] text-texto-suave">De la falla a la autorización de salida, en tiempo de calendario.</p>
        </Panel>
      ) : null}

      <Panel nivel={2} titulo="Para el cálculo de riesgo">
        <dl className="text-[0.9375rem]">
          <dt className="text-texto-suave">Horas acumuladas del equipo en la falla</dt>
          <dd className="pt-0.5 font-semibold text-texto">{horas(orden.horas_acumuladas_en_falla)}</dd>
        </dl>
        <p className="pt-2 text-[0.8125rem] leading-5 text-texto-suave">
          Incluye las horas anteriores a un cambio de horómetro, si lo hubo. Es el dato que usa la
          predicción, no el número que marca el aparato.
        </p>
      </Panel>
    </div>
  );
}
