"use client";

/**
 * Lecturas de horómetro que no cuadraban y nadie ha resuelto (05-fase2-activos-y-campo.md, 5.1;
 * revisión 0006).
 *
 * Mientras una lectura esté pendiente, el horómetro del equipo no se mueve con ella. Por eso va en
 * la misma pantalla que las alertas: es la otra cosa que el supervisor tiene que atender.
 *
 * Tres decisiones, con palabras del taller y no de la base de datos:
 * - **Es correcta**: el salto era real. Pasa a contar y mueve el horómetro.
 * - **Error al teclear**: se conserva, pero no cuenta para nada.
 * - **Se cambió el horómetro** (solo el administrador): empieza una serie nueva de horas.
 *
 * Si no hay nada pendiente, el panel lo dice en una línea en vez de desaparecer: el menú lateral
 * lleva aquí («Supervisión → Lecturas por revisar»), y un clic que no muestra nada parecería roto.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { RequiereRevision } from "@/components/estado";
import { Panel } from "@/components/marco";
import { ErrorApi } from "@/lib/api";
import {
  lecturasPorRevisar,
  resolverLectura,
  type LecturaPorRevisar,
  type Resolucion,
} from "@/lib/campo";
import { fechaHora, horas } from "@/lib/formato";

/** Ancla del menú lateral; `scroll-mt` deja el título a la vista bajo la barra fija. */
const ANCLA = "lecturas-por-revisar";

export function LecturasPorRevisar({ esAdministrador }: { readonly esAdministrador: boolean }) {
  const [lista, setLista] = useState<readonly LecturaPorRevisar[] | null>(null);

  useEffect(() => {
    const control = new AbortController();
    lecturasPorRevisar(control.signal)
      .then((p) => setLista(p.items))
      .catch(() => setLista([]));
    return () => control.abort();
  }, []);

  // La sección llega después de montar, cuando ya pasó el salto del navegador al ancla: si se vino
  // desde el menú, se baja ahora.
  useEffect(() => {
    if (lista !== null && window.location.hash === `#${ANCLA}`) {
      document.getElementById(ANCLA)?.scrollIntoView({ block: "start" });
    }
  }, [lista]);

  if (lista === null) return null;

  return (
    <div id={ANCLA} className="scroll-mt-20">
      {lista.length === 0 ? (
        <Panel nivel={2} titulo="Lecturas por revisar">
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            Ninguna pendiente. Aquí aparecen las lecturas que no cuadran con el historial de su equipo.
          </p>
        </Panel>
      ) : (
        <Panel
          nivel={2}
          titulo={`Lecturas por revisar (${lista.length})`}
          descripcion="No cuadraban con el historial del equipo. Hasta que decidas, el horómetro del equipo no se mueve con ellas."
        >
          <ul className="divide-y divide-borde">
            {lista.map((l) => (
              <Fila
                key={l.id}
                lectura={l}
                esAdministrador={esAdministrador}
                alResolver={() => setLista((actual) => (actual ?? []).filter((x) => x.id !== l.id))}
              />
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Fila({
  lectura,
  esAdministrador,
  alResolver,
}: {
  readonly lectura: LecturaPorRevisar;
  readonly esAdministrador: boolean;
  readonly alResolver: () => void;
}) {
  const [enCurso, setEnCurso] = useState<Resolucion | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resolver(r: Resolucion): Promise<void> {
    setEnCurso(r);
    setError(null);
    try {
      await resolverLectura(lectura.id, r);
      alResolver();
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo guardar.");
      setEnCurso(null);
    }
  }

  const ocupada = enCurso !== null;

  return (
    <li className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-[1.0625rem] font-semibold text-texto">{horas(lectura.valor_horometro)}</span>
          <RequiereRevision />
        </p>
        <p className="pt-1 text-[0.9375rem] text-texto-suave">
          <Link
            href={`/a/${lectura.activo_codigo}`}
            className="font-medium text-accion underline-offset-2 hover:underline"
          >
            {lectura.activo_nombre}
          </Link>
          {" · ahora marca "}
          {horas(lectura.horometro_vigente)}
        </p>
        {lectura.motivo_revision !== null ? (
          <p className="max-w-[65ch] pt-1 text-[0.875rem] leading-5 text-texto">{lectura.motivo_revision}</p>
        ) : null}
        <p className="pt-1 text-[0.8125rem] text-texto-tenue">Capturada el {fechaHora(lectura.capturado_en)}</p>
        {error !== null ? <p role="alert" className="pt-1 text-[0.875rem] text-error">{error}</p> : null}
      </div>
      <div className={["grid shrink-0 gap-2", esAdministrador ? "sm:grid-cols-3 lg:w-[38rem]" : "grid-cols-2 lg:w-80"].join(" ")}>
        <Boton tipo="button" variante="secundario" onClick={() => void resolver("descartada")} enCurso={enCurso === "descartada"} textoEnCurso="…" deshabilitado={ocupada && enCurso !== "descartada"}>
          Error al teclear
        </Boton>
        <Boton tipo="button" variante="secundario" onClick={() => void resolver("confirmada")} enCurso={enCurso === "confirmada"} textoEnCurso="…" deshabilitado={ocupada && enCurso !== "confirmada"}>
          Es correcta
        </Boton>
        {esAdministrador ? (
          <Boton tipo="button" variante="secundario" onClick={() => void resolver("reinicio")} enCurso={enCurso === "reinicio"} textoEnCurso="…" deshabilitado={ocupada && enCurso !== "reinicio"}>
            Se cambió el horómetro
          </Boton>
        ) : null}
      </div>
    </li>
  );
}
