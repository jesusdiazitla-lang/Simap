"use client";

/**
 * Las dos gráficas del panel del gerente (08-fase5, 10.4): disponibilidad por mes (línea) y costo de
 * repuestos por mes (columnas apiladas: planificado y por falla).
 *
 * SVG propio, sin biblioteca de gráficos, como la curva de riesgo de la fase 4. Cada una:
 * - mide su contenedor, así el texto siempre mide 12 px y en pantallas estrechas hay menos marcas;
 * - tiene una zona por mes que responde al cursor **y al foco del teclado** (Tab) y escribe el
 *   detalle en una línea con `aria-live`, encima de la gráfica, sin tapar nada;
 * - lleva leyenda cuando hay más de una serie (el color nunca identifica solo) y «Ver como tabla».
 *
 * La línea de disponibilidad es una sola serie y va en tinta. Las columnas usan `--serie-planificado`
 * y `--serie-falla`, validadas con el validador de paletas en los dos temas: ni el azul de acción ni
 * los colores de estado de máquina.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { dinero, etiquetaMes, porcentajeFino, type MesIndicador } from "@/lib/paneles";

const ALTO = 200;
const MARGEN = { izq: 52, der: 12, arr: 12, aba: 28 };

function useAncho(): [React.RefObject<HTMLDivElement | null>, number] {
  const marco = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(560);
  useEffect(() => {
    const el = marco.current;
    if (el === null) return;
    const observador = new ResizeObserver(([e]) => setAncho(Math.max(260, Math.round(e.contentRect.width))));
    observador.observe(el);
    return () => observador.disconnect();
  }, []);
  return [marco, ancho];
}

function Grafica({
  titulo,
  descripcion,
  leyenda,
  detalle,
  tabla,
  children,
}: {
  readonly titulo: string;
  readonly descripcion: string;
  readonly leyenda?: ReactNode;
  readonly detalle: string;
  readonly tabla: ReactNode;
  readonly children: (ancho: number) => ReactNode;
}) {
  const [marco, ancho] = useAncho();
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="flex flex-col gap-1">
        <span className="text-[0.9375rem] font-semibold text-texto">{titulo}</span>
        <span className="text-[0.8125rem] leading-5 text-texto-suave">{descripcion}</span>
      </figcaption>
      {leyenda}
      <p aria-live="polite" className="min-h-5 text-[0.8125rem] leading-5 text-texto [font-variant-numeric:tabular-nums]">
        {detalle}
      </p>
      {/* El SVG va en posición absoluta: su ancho no debe ensanchar la rejilla (ver CurvaRiesgo). */}
      <div ref={marco} className="relative h-[200px] w-full">
        <svg
          width={ancho}
          height={ALTO}
          viewBox={`0 0 ${ancho} ${ALTO}`}
          className="absolute inset-0 block text-texto-tenue"
          role="img"
          aria-label={`${titulo}. ${descripcion} Los datos están también en la tabla.`}
        >
          {children(ancho)}
        </svg>
      </div>
      <details className="text-[0.875rem]">
        <summary className="inline-flex min-h-11 cursor-pointer items-center font-medium text-accion underline-offset-2 hover:underline">
          Ver como tabla
        </summary>
        <div className="overflow-x-auto pt-2">{tabla}</div>
      </details>
    </figure>
  );
}

function ejeX(meses: readonly MesIndicador[], ancho: number): { x: (i: number) => number; paso: number; cada: number } {
  const util = ancho - MARGEN.izq - MARGEN.der;
  const paso = util / Math.max(meses.length, 1);
  // Etiquetas de ~44 px: en un teléfono se muestra una de cada dos o tres.
  const cada = Math.max(1, Math.ceil(46 / paso));
  return { x: (i) => MARGEN.izq + paso * (i + 0.5), paso, cada };
}

function Etiquetas({ meses, x, cada }: { readonly meses: readonly MesIndicador[]; readonly x: (i: number) => number; readonly cada: number }) {
  return (
    <>
      {meses.map((m, i) =>
        i % cada === 0 ? (
          <text key={m.mes} x={x(i)} y={ALTO - 8} textAnchor="middle" fontSize="12" fill="currentColor">
            {etiquetaMes(m.mes, false)}
          </text>
        ) : null,
      )}
    </>
  );
}

function ZonaMes({
  i,
  x,
  paso,
  etiqueta,
  activo,
  alActivar,
}: {
  readonly i: number;
  readonly x: (i: number) => number;
  readonly paso: number;
  readonly etiqueta: string;
  readonly activo: boolean;
  readonly alActivar: (i: number | null) => void;
}) {
  return (
    <rect
      x={x(i) - paso / 2}
      y={MARGEN.arr}
      width={paso}
      height={ALTO - MARGEN.arr - MARGEN.aba}
      fill={activo ? "var(--superficie-alterna)" : "transparent"}
      tabIndex={0}
      role="img"
      aria-label={etiqueta}
      className="cursor-default outline-none focus-visible:stroke-[var(--accion)] focus-visible:stroke-2"
      onMouseEnter={() => alActivar(i)}
      onMouseLeave={() => alActivar(null)}
      onFocus={() => alActivar(i)}
      onBlur={() => alActivar(null)}
    />
  );
}

function disponibilidad(m: MesIndicador): number | null {
  return m.horas_calendario > 0 ? 1 - m.paradas_total_h / m.horas_calendario : null;
}

export function GraficaDisponibilidad({ meses }: { readonly meses: readonly MesIndicador[] }) {
  const [activo, setActivo] = useState<number | null>(null);
  const valores = meses.map(disponibilidad);
  const conDato = valores.filter((v): v is number => v !== null);
  // El eje no parte de cero (todo estaría pegado arriba), pero nunca pasa de 100 %.
  const piso = conDato.length ? Math.max(0, Math.floor(Math.min(...conDato) * 20) / 20 - 0.05) : 0.8;
  const texto = (i: number) => {
    const v = valores[i];
    return `${etiquetaMes(meses[i].mes)}: ${porcentajeFino(v)} · ${meses[i].equipos} ${meses[i].equipos === 1 ? "equipo" : "equipos"}`;
  };
  return (
    <Grafica
      titulo="Disponibilidad por mes"
      descripcion="Porcentaje de las horas de calendario en que el equipo no estuvo parado."
      detalle={activo === null ? "Pasa el cursor o el foco por un mes para ver el detalle." : texto(activo)}
      tabla={
        <table className="w-full min-w-[22rem] text-left [font-variant-numeric:tabular-nums]">
          <thead>
            <tr className="border-b border-borde text-texto-suave">
              <th scope="col" className="py-1.5 pr-4 font-medium">Mes</th>
              <th scope="col" className="py-1.5 pr-4 text-right font-medium">Disponibilidad</th>
              <th scope="col" className="py-1.5 text-right font-medium">Equipos</th>
            </tr>
          </thead>
          <tbody>
            {meses.map((m, i) => (
              <tr key={m.mes} className="border-b border-borde last:border-0">
                <td className="py-1.5 pr-4">{etiquetaMes(m.mes)}</td>
                <td className="py-1.5 pr-4 text-right">{porcentajeFino(valores[i])}</td>
                <td className="py-1.5 text-right">{m.equipos}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {(ancho) => {
        const { x, paso, cada } = ejeX(meses, ancho);
        const y = (v: number) => MARGEN.arr + (ALTO - MARGEN.arr - MARGEN.aba) * (1 - (v - piso) / (1 - piso));
        const marcas = [piso, (piso + 1) / 2, 1];
        let trazo = "";
        valores.forEach((v, i) => {
          if (v === null) return;
          trazo += `${trazo === "" || valores[i - 1] === null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
        });
        return (
          <>
            {meses.map((m, i) => (
              <ZonaMes key={m.mes} i={i} x={x} paso={paso} etiqueta={texto(i)} activo={activo === i} alActivar={setActivo} />
            ))}
            {marcas.map((p) => (
              <g key={p} aria-hidden="true">
                <line x1={MARGEN.izq} x2={ancho - MARGEN.der} y1={y(p)} y2={y(p)} stroke="var(--borde)" strokeWidth="1" />
                <text x={MARGEN.izq - 6} y={y(p) + 4} textAnchor="end" fontSize="12" fill="currentColor">
                  {Math.round(p * 100)} %
                </text>
              </g>
            ))}
            <path d={trazo} fill="none" stroke="var(--texto)" strokeWidth="2" pointerEvents="none" />
            {valores.map((v, i) =>
              v === null ? null : (
                <circle
                  key={meses[i].mes}
                  cx={x(i)}
                  cy={y(v)}
                  r={activo === i ? 5 : 4}
                  fill="var(--superficie)"
                  stroke="var(--texto)"
                  strokeWidth="2"
                  pointerEvents="none"
                />
              ),
            )}
            <Etiquetas meses={meses} x={x} cada={cada} />
          </>
        );
      }}
    </Grafica>
  );
}

export function GraficaCosto({ meses }: { readonly meses: readonly MesIndicador[] }) {
  const [activo, setActivo] = useState<number | null>(null);
  const plan = meses.map((m) => Number(m.costo_planificadas));
  const falla = meses.map((m) => Number(m.costo_fallas));
  const tope = Math.max(1, ...meses.map((_, i) => plan[i] + falla[i]));
  if (meses.every((_, i) => plan[i] + falla[i] === 0)) {
    // Sin consumos, una gráfica de ceros con un eje inventado no dice nada: se dice con palabras.
    return (
      <figure className="flex flex-col gap-1">
        <figcaption className="text-[0.9375rem] font-semibold text-texto">Costo de repuestos por mes</figcaption>
        <p className="text-[0.875rem] leading-5 text-texto-suave">
          No se consumieron repuestos en el periodo. Los consumos aparecen al cerrar órdenes con repuestos anotados.
        </p>
      </figure>
    );
  }
  const texto = (i: number) =>
    `${etiquetaMes(meses[i].mes)}: ${dinero(plan[i] + falla[i])} (planificado ${dinero(plan[i])}, por falla ${dinero(falla[i])})`;
  return (
    <Grafica
      titulo="Costo de repuestos por mes"
      descripcion="Repuestos consumidos al cerrar órdenes, a precio del momento, según fueran trabajo planificado o por falla."
      leyenda={
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[0.8125rem] text-texto-suave" aria-label="Leyenda">
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-3 w-3 rounded-[2px] bg-[var(--serie-planificado)]" />
            Planificado
          </li>
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-3 w-3 rounded-[2px] bg-[var(--serie-falla)]" />
            Por falla
          </li>
        </ul>
      }
      detalle={activo === null ? "Pasa el cursor o el foco por un mes para ver el detalle." : texto(activo)}
      tabla={
        <table className="w-full min-w-[26rem] text-left [font-variant-numeric:tabular-nums]">
          <thead>
            <tr className="border-b border-borde text-texto-suave">
              <th scope="col" className="py-1.5 pr-4 font-medium">Mes</th>
              <th scope="col" className="py-1.5 pr-4 text-right font-medium">Planificado</th>
              <th scope="col" className="py-1.5 pr-4 text-right font-medium">Por falla</th>
              <th scope="col" className="py-1.5 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {meses.map((m, i) => (
              <tr key={m.mes} className="border-b border-borde last:border-0">
                <td className="py-1.5 pr-4">{etiquetaMes(m.mes)}</td>
                <td className="py-1.5 pr-4 text-right">{dinero(plan[i])}</td>
                <td className="py-1.5 pr-4 text-right">{dinero(falla[i])}</td>
                <td className="py-1.5 text-right">{dinero(plan[i] + falla[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {(ancho) => {
        const { x, paso, cada } = ejeX(meses, ancho);
        const base = ALTO - MARGEN.aba;
        const escala = (v: number) => ((ALTO - MARGEN.arr - MARGEN.aba) * v) / tope;
        const barra = Math.min(28, paso * 0.6);
        // Columnas desde cero; el segmento superior lleva el extremo redondeado (4 px) y entre los
        // dos queda un hueco de 2 px del color de la superficie.
        const columna = (cx: number, y0: number, alto: number, redondo: boolean) => {
          const r = redondo ? Math.min(4, alto / 2, barra / 2) : 0;
          const xi = cx - barra / 2;
          const yt = y0 - alto;
          return `M${xi},${y0} V${yt + r} Q${xi},${yt} ${xi + r},${yt} H${xi + barra - r} Q${xi + barra},${yt} ${xi + barra},${yt + r} V${y0} Z`;
        };
        return (
          <>
            {meses.map((m, i) => (
              <ZonaMes key={m.mes} i={i} x={x} paso={paso} etiqueta={texto(i)} activo={activo === i} alActivar={setActivo} />
            ))}
            {[0, tope / 2, tope].map((v) => (
              <g key={v} aria-hidden="true">
                <line x1={MARGEN.izq} x2={ancho - MARGEN.der} y1={base - escala(v)} y2={base - escala(v)} stroke="var(--borde)" strokeWidth="1" />
                <text x={MARGEN.izq - 6} y={base - escala(v) + 4} textAnchor="end" fontSize="12" fill="currentColor">
                  {v >= 1000 ? `${Math.round(v / 1000).toLocaleString("es-DO")} mil` : Math.round(v).toLocaleString("es-DO")}
                </text>
              </g>
            ))}
            {meses.map((m, i) => {
              const hp = escala(plan[i]);
              const hf = escala(falla[i]);
              const hueco = hp > 0 && hf > 0 ? 2 : 0;
              return (
                <g key={m.mes} pointerEvents="none">
                  {hp > 0 ? <path d={columna(x(i), base, hp, hf === 0)} fill="var(--serie-planificado)" /> : null}
                  {hf > 0 ? <path d={columna(x(i), base - hp - hueco, Math.max(hf - hueco, 1), true)} fill="var(--serie-falla)" /> : null}
                </g>
              );
            })}
            <Etiquetas meses={meses} x={x} cada={cada} />
          </>
        );
      }}
    </Grafica>
  );
}
