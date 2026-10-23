"use client";

/**
 * Cómo se muestra un riesgo sin engañar (07-fase4, sección 10.2).
 *
 * 1. **Cada porcentaje va con su respaldo**: cuántas fallas lo sostienen y con qué confianza. Con
 *    confianza baja se escribe «estimado». Un 31 % sobre dos fallas y uno sobre treinta no son lo
 *    mismo, y la pantalla no finge que sí.
 * 2. **El nivel se escribe** (bajo, vigilar, alto) además del color, y la escala parte del umbral
 *    **de la empresa**, no de números fijos. Es el estado de una máquina: usa los colores de estado,
 *    nunca el azul de acción, y no es pulsable.
 * 3. **«Sin edad» y «sin modelo» no son un 0 %**: son un aviso con su acción. Mostrarlos como cero
 *    sería el error más peligroso de la interfaz.
 * 4. **Cada riesgo se explica en una línea**: edad, horizonte, fallas y, si aplica, el multiplicador.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Insignia } from "@/components/estado";
import { IconoAviso } from "@/components/iconos";
import type { Usuario } from "@/lib/auth";
import { hace, horas } from "@/lib/formato";
import {
  ETIQUETA_CONFIANZA,
  ETIQUETA_NIVEL,
  horizonteEnDias,
  nivel,
  numero,
  porcentaje,
  respaldo,
  riesgoWeibull,
  type Confianza,
  type Nivel,
  type RiesgoComponente,
  type RiesgoEquipo,
} from "@/lib/prediccion";

export function NivelRiesgo({ valor }: { readonly valor: Nivel }) {
  if (valor === "alto") {
    return (
      <Insignia tono="falla" icono={<IconoAviso className="h-3.5 w-3.5" />}>
        Riesgo {ETIQUETA_NIVEL[valor].toLowerCase()}
      </Insignia>
    );
  }
  if (valor === "vigilar") {
    return (
      <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>
        {ETIQUETA_NIVEL[valor]}
      </Insignia>
    );
  }
  return <Insignia tono="ok">Riesgo {ETIQUETA_NIVEL[valor].toLowerCase()}</Insignia>;
}

/** Confianza en neutro: dice cuánto creerle al número, no cómo está la máquina. */
export function ConfianzaInsignia({ valor }: { readonly valor: Confianza | null }) {
  if (valor === null) return null;
  return <Insignia tono="neutro">{ETIQUETA_CONFIANZA[valor]}</Insignia>;
}

/** El porcentaje grande, con «estimado» cuando la confianza es baja. */
export function Porcentaje({
  valor,
  confianza,
  tamano = "normal",
}: {
  readonly valor: number;
  readonly confianza: Confianza | null;
  readonly tamano?: "normal" | "grande";
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span
        className={
          tamano === "grande"
            ? "text-[1.5rem] font-semibold leading-7 tracking-[0.01em] text-texto"
            : "text-[1rem] font-semibold text-texto"
        }
      >
        {porcentaje(valor)}
      </span>
      {confianza === "baja" ? <span className="text-[0.8125rem] text-texto-suave">estimado</span> : null}
    </span>
  );
}

/** La explicación en una línea (10.2): «Esta pieza lleva 350 h; a esa edad…». */
export function Explicacion({
  c,
  horasPorDia,
}: {
  readonly c: RiesgoComponente;
  readonly horasPorDia: number | null;
}) {
  const r = numero(c.riesgo);
  const m = numero(c.multiplicador);
  if (c.estado_calculo !== "ok" || r === null || c.edad_horas === null || c.horizonte_horas === null) {
    return null;
  }
  const dias = horizonteEnDias(c.horizonte_horas, horasPorDia);
  return (
    <p className="text-[0.875rem] leading-5 text-texto-suave">
      Esta pieza lleva {horas(Math.round(c.edad_horas))}; a esa edad el modelo estima {porcentaje(r)} de
      falla en las próximas {horas(c.horizonte_horas)}
      {dias !== null ? ` (${dias})` : ""}. {respaldo(c.n_eventos)}.
      {m !== null && m > 1 ? ` Incluye +${Math.round((m - 1) * 100)} % por alertas de campo recientes.` : ""}
    </p>
  );
}

/** «Sin edad» / «sin modelo»: un aviso con la acción que lo resuelve, y quién puede hacerla. */
export function SinCalculo({
  c,
  activoId,
  usuario,
}: {
  readonly c: RiesgoComponente;
  readonly activoId: string;
  readonly usuario: Usuario;
}) {
  const admin = usuario.rol === "administrador";
  if (c.estado_calculo === "sin_edad") {
    return (
      <div className="flex flex-col gap-1">
        <Insignia tono="neutro" icono={<IconoAviso className="h-3.5 w-3.5" />}>
          Sin edad
        </Insignia>
        <p className="text-[0.875rem] leading-5 text-texto-suave">
          No se sabe cuándo se instaló la pieza actual, así que no hay riesgo que mostrar (no es un
          0 %). Se conocerá en el primer reemplazo, o{" "}
          {admin ? (
            <Link href={`/activos/${activoId}/componentes`} className="text-accion underline underline-offset-2">
              declárala ahora
            </Link>
          ) : (
            "el administrador puede declararla"
          )}
          .
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Insignia tono="neutro" icono={<IconoAviso className="h-3.5 w-3.5" />}>
        Sin modelo
      </Insignia>
      <p className="text-[0.875rem] leading-5 text-texto-suave">
        Este componente no tiene vida nominal declarada ni dos fallas registradas: no hay base para
        un riesgo (no es un 0 %).{" "}
        {admin ? (
          <Link href="/componentes" className="text-accion underline underline-offset-2">
            Declara su vida nominal
          </Link>
        ) : (
          "El administrador puede declarar su vida nominal."
        )}
      </p>
    </div>
  );
}

/** Riesgo de cada componente de un equipo, del más alto al más bajo. Sin cálculo, al final. */
export function RiesgoPorComponente({
  datos,
  usuario,
  verModelo,
}: {
  readonly datos: RiesgoEquipo;
  readonly usuario: Usuario;
  /** El técnico ve el riesgo, pero no el modelo (tabla 12.1). */
  readonly verModelo: boolean;
}) {
  const umbral = Number(datos.umbral);
  const ordenados = [...datos.componentes].sort(
    (a, b) => (numero(b.riesgo) ?? -1) - (numero(a.riesgo) ?? -1),
  );
  if (ordenados.length === 0) {
    return (
      <p className="text-[0.9375rem] leading-6 text-texto-suave">
        Este equipo todavía no tiene componentes registrados. Se registran solos con la primera falla
        reportada, o los declara el administrador con su edad.
      </p>
    );
  }
  return (
    <ul className="flex flex-col divide-y divide-borde">
      {ordenados.map((c) => {
        const r = numero(c.riesgo);
        return (
          <li key={c.componente_id} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-texto">
                {verModelo ? (
                  <Link href={`/componentes/${c.componente_id}/modelo`} className="text-accion underline-offset-2 hover:underline">
                    {c.componente}
                  </Link>
                ) : (
                  c.componente
                )}
              </span>
              {r !== null && c.estado_calculo === "ok" ? (
                <span className="flex flex-wrap items-center gap-2">
                  <Porcentaje valor={r} confianza={c.confianza} />
                  <NivelRiesgo valor={nivel(r, umbral)} />
                </span>
              ) : null}
            </div>
            {c.estado_calculo === "ok" ? (
              <>
                <Explicacion c={c} horasPorDia={datos.horas_por_dia} />
                <span className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-texto-tenue">
                  <ConfianzaInsignia valor={c.confianza} />
                  {c.calculado_en !== null ? <span>Calculado {hace(c.calculado_en)}</span> : null}
                </span>
              </>
            ) : (
              <SinCalculo c={c} activoId={datos.activo_id} usuario={usuario} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Curva de riesgo según la edad de la pieza, para un horizonte dado (la Figura 1 del documento).
 * SVG propio: un solo trazo, el umbral de la empresa como referencia punteada y, si se conoce, la
 * edad actual marcada. Sin librería de gráficos para una curva.
 */
export function CurvaRiesgo({
  beta,
  eta,
  horizonte,
  umbral,
  edadActual = null,
}: {
  readonly beta: number;
  readonly eta: number;
  readonly horizonte: number;
  readonly umbral: number;
  readonly edadActual?: number | null;
}) {
  // El ancho del SVG es el del contenedor, medido: con un viewBox fijo el texto se encogía a
  // 6 px en un móvil. Así las etiquetas miden siempre 12 px y en pantallas estrechas hay menos.
  const marco = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(560);
  useEffect(() => {
    const el = marco.current;
    if (el === null) return;
    const observador = new ResizeObserver(([e]) => setAncho(Math.max(260, Math.round(e.contentRect.width))));
    observador.observe(el);
    return () => observador.disconnect();
  }, []);
  const alto = 220;
  const m = { izq: 44, der: 12, arr: 12, aba: 32 };
  const maxEdad = Math.max(eta * 1.6, (edadActual ?? 0) * 1.1, 10);
  const puntos = Array.from({ length: 81 }, (_, i) => {
    const edad = (maxEdad * i) / 80;
    return [edad, riesgoWeibull(edad, horizonte, beta, eta)] as const;
  });
  const x = (edad: number) => m.izq + ((ancho - m.izq - m.der) * edad) / maxEdad;
  const y = (p: number) => m.arr + (alto - m.arr - m.aba) * (1 - p);
  const trazo = puntos.map(([e, p], i) => `${i === 0 ? "M" : "L"}${x(e).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const actual = edadActual !== null ? riesgoWeibull(edadActual, horizonte, beta, eta) : null;
  const marcas = [0, 0.25, 0.5, 0.75, 1];
  const pasos = ancho < 420 ? 2 : 4;

  return (
    <figure className="flex flex-col gap-2">
      {/* El SVG va en posición absoluta para que su ancho no cuente en el del contenedor: si contara,
          la rejilla crecería hasta el ancho del SVG y la medida nunca bajaría. */}
      <div ref={marco} className="relative w-full" style={{ height: alto }}>
      <svg
        width={ancho}
        height={alto}
        viewBox={`0 0 ${ancho} ${alto}`}
        className="absolute inset-0 block text-texto-tenue"
        role="img"
        aria-label={`Riesgo de falla en las próximas ${horizonte} horas según la edad de la pieza. Umbral de la empresa: ${porcentaje(umbral)}.`}
      >
        {marcas.map((p) => (
          <g key={p}>
            <line x1={m.izq} x2={ancho - m.der} y1={y(p)} y2={y(p)} stroke="var(--borde)" strokeWidth="1" />
            <text x={m.izq - 6} y={y(p) + 4} textAnchor="end" fontSize="12" fill="currentColor">
              {Math.round(p * 100)} %
            </text>
          </g>
        ))}
        {Array.from({ length: pasos + 1 }, (_, i) => {
          const edad = (maxEdad * i) / pasos;
          return (
            <text key={i} x={x(edad)} y={alto - 10} textAnchor={i === 0 ? "start" : i === pasos ? "end" : "middle"} fontSize="12" fill="currentColor">
              {Math.round(edad).toLocaleString("en-US")} h
            </text>
          );
        })}
        <line
          x1={m.izq}
          x2={ancho - m.der}
          y1={y(umbral)}
          y2={y(umbral)}
          stroke="var(--estado-aviso)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
        <text x={ancho - m.der} y={y(umbral) - 5} textAnchor="end" fontSize="12" fill="var(--estado-aviso)">
          Umbral {porcentaje(umbral)}
        </text>
        <path d={trazo} fill="none" stroke="var(--texto)" strokeWidth="2" />
        {edadActual !== null && actual !== null ? (
          <g>
            <line x1={x(edadActual)} x2={x(edadActual)} y1={m.arr} y2={alto - m.aba} stroke="var(--borde-fuerte)" strokeWidth="1" />
            <circle cx={x(edadActual)} cy={y(actual)} r="4.5" fill="var(--superficie)" stroke="var(--texto)" strokeWidth="2" />
          </g>
        ) : null}
      </svg>
      </div>
      <figcaption className="text-[0.8125rem] leading-5 text-texto-suave">
        Probabilidad de falla en las próximas {horas(horizonte)} según las horas de la pieza desde que
        se instaló. La línea punteada es el umbral de la empresa
        {edadActual !== null ? "; el punto, la edad de la pieza en este equipo" : ""}.
      </figcaption>
    </figure>
  );
}
