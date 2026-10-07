"use client";

/**
 * Vista de impresión de la etiqueta de un equipo (05-fase2-activos-y-campo.md, 6.3).
 *
 * La etiqueta la dibuja el servidor en SVG —vectorial, nítida a cualquier tamaño— y aquí se muestra
 * a su tamaño real en milímetros, con las recomendaciones de la sección 6.3 al lado. Al imprimir
 * desaparece todo lo demás: barra, instrucciones y botones.
 */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { IconoHecho, IconoImprimir } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { obtenerActivo, urlEtiqueta, type Activo } from "@/lib/activos";

export default function EtiquetaPage() {
  return (
    <Pantalla roles={["administrador", "supervisor"]} cargando="Etiqueta">
      {() => <Etiqueta />}
    </Pantalla>
  );
}

function Etiqueta() {
  const { id } = useParams<{ id: string }>();
  const [activo, setActivo] = useState<Activo | null>(null);
  const [nuevo] = useState(() =>
    typeof window !== "undefined" && new URLSearchParams(window.location.search).has("nuevo"),
  );

  useEffect(() => {
    const control = new AbortController();
    obtenerActivo(id, control.signal).then(setActivo).catch(() => undefined);
    return () => control.abort();
  }, [id]);

  if (activo === null) {
    return (
      <Panel titulo="Etiqueta">
        <Esqueleto />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {nuevo ? (
        <p role="status" className="flex gap-2 rounded-[var(--radius-control)] border border-estado-ok bg-superficie px-3 py-2.5 text-[0.9375rem] text-texto print:hidden">
          <IconoHecho className="mt-0.5 text-estado-ok" />
          <span>«{activo.nombre}» dado de alta. Imprime su etiqueta y pégala en la máquina.</span>
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-start">
        <section className="flex justify-center rounded-[var(--radius-control)] border border-borde bg-white p-6 print:border-0 print:p-0">
          {/* eslint-disable-next-line @next/next/no-img-element -- SVG del API con su tamaño en mm; next/image lo rasterizaría. */}
          <img
            src={urlEtiqueta(activo.id)}
            alt={`Etiqueta QR de ${activo.nombre}, código ${activo.codigo_corto}`}
            className="h-auto w-[45mm] max-w-full"
          />
        </section>

        <div className="print:hidden">
          <Panel titulo={`Etiqueta de «${activo.nombre}»`} descripcion={`Código ${activo.codigo_corto}`}>
            <ul className="flex list-disc flex-col gap-2 pb-5 pl-5 text-[0.9375rem] leading-6 text-texto">
              <li>Imprime a 3 × 3 cm como mínimo, en vinilo o poliéster laminado.</li>
              <li>Pégala en una superficie plana y visible, lejos de fuentes de calor.</li>
              <li>
                Antes de imprimir todas, prueba a escanear esta a unos 50 cm con el teléfono más modesto
                de la planta.
              </li>
              <li>Reimprimir no cambia el código: la etiqueta vieja y la nueva abren lo mismo.</li>
            </ul>
            <div className="flex flex-wrap gap-2">
              <Boton tipo="button" onClick={() => window.print()}>
                <span className="inline-flex items-center gap-2">
                  <IconoImprimir />
                  Imprimir
                </span>
              </Boton>
              <EnlaceBoton href={`/a/${activo.codigo}`}>Ver ficha del equipo</EnlaceBoton>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
