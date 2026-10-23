"use client";

/**
 * Equipos por riesgo de falla (RF-18, CU-04; 07-fase4, 10.1).
 *
 * Cada equipo aparece por su componente más riesgoso (`v_riesgo_activo`), del más alto al más bajo.
 * Cada fila dice cuánto respalda el número —fallas registradas y confianza— y cuándo se calculó: un
 * cálculo atrasado se ve atrasado, no como un número fresco (9.2). Los equipos sin cálculo (sin edad
 * o sin modelo) no aparecen aquí: se ven en la pantalla de cada equipo con su aviso y su acción.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { ConfianzaInsignia, NivelRiesgo, Porcentaje } from "@/components/riesgo";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { hace, horas } from "@/lib/formato";
import {
  leerConfiguracion,
  nivel,
  porcentaje,
  rankingDeRiesgo,
  respaldo,
  type Configuracion,
  type RiesgoActivo,
} from "@/lib/prediccion";
import { useSondeo } from "@/lib/sondeo";

const ROLES: readonly Rol[] = ["supervisor", "gerente", "administrador"];

export default function RiesgoPage() {
  return (
    <Pantalla roles={ROLES} cargando="Riesgo de falla">
      {(usuario) => <Ranking usuario={usuario} />}
    </Pantalla>
  );
}

function Ranking({ usuario }: { readonly usuario: Usuario }) {
  const [filas, setFilas] = useState<readonly RiesgoActivo[] | null>(null);
  const [config, setConfig] = useState<Configuracion | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      Promise.all([rankingDeRiesgo(undefined, signal), leerConfiguracion(signal)])
        .then(([p, c]) => {
          setFilas(p.items);
          setCursor(p.next_cursor);
          setConfig(c);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof ErrorApi ? e.message : "No se pudo cargar el riesgo.");
        }),
    [],
  );

  useEffect(() => {
    const control = new AbortController();
    void cargar(control.signal);
    return () => control.abort();
  }, [cargar]);

  useSondeo(() => {
    if (cursor === null) void cargar();
  });

  async function cargarMas(): Promise<void> {
    if (cursor === null) return;
    setCargandoMas(true);
    try {
      const p = await rankingDeRiesgo(cursor);
      setFilas((a) => [...(a ?? []), ...p.items]);
      setCursor(p.next_cursor);
    } finally {
      setCargandoMas(false);
    }
  }

  const umbral = config !== null ? Number(config.umbral_riesgo) : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[70ch]">
          <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Riesgo de falla</h1>
          <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
            {config !== null
              ? `Probabilidad de que cada equipo falle en las próximas ${horas(config.horizonte_horas)} de operación, por su componente más riesgoso. La empresa alerta desde el ${porcentaje(Number(config.umbral_riesgo))}.`
              : "Probabilidad de falla de cada equipo, por su componente más riesgoso."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <EnlaceBoton href="/alertas-sistema">Alertas del sistema</EnlaceBoton>
          {usuario.rol === "administrador" ? (
            <EnlaceBoton href="/configuracion/prediccion">Configuración</EnlaceBoton>
          ) : null}
        </div>
      </div>

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="px-5 py-4 sm:px-6">
          {error !== null && filas === null ? (
            <p role="alert" className="text-[0.9375rem] text-error">{error}</p>
          ) : filas === null || umbral === null ? (
            <Esqueleto />
          ) : filas.length === 0 ? (
            <p className="py-2 text-[0.9375rem] leading-6 text-texto-suave">
              Todavía no hay riesgos calculados. Un equipo tiene riesgo cuando sus componentes tienen
              edad conocida y un modelo: vida nominal declarada o dos fallas registradas.
            </p>
          ) : (
            <table className="w-full border-collapse text-left">
              <thead className="hidden md:table-header-group">
                <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
                  <th scope="col" className="pb-2 pr-4 font-medium">Equipo</th>
                  <th scope="col" className="pb-2 pr-4 font-medium">Componente crítico</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-medium">Riesgo</th>
                  <th scope="col" className="pb-2 pr-4 font-medium">Respaldo</th>
                  <th scope="col" className="pb-2 font-medium">Calculado</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => {
                  const r = Number(f.riesgo);
                  return (
                    <tr
                      key={f.activo_id}
                      className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 border-b border-borde py-3 last:border-0 md:table-row md:py-0"
                    >
                      <td className="min-w-0 md:py-3 md:pr-4">
                        <Link href={`/a/${f.codigo}`} className="font-semibold text-accion underline-offset-2 hover:underline [overflow-wrap:anywhere]">
                          {f.activo}
                        </Link>
                      </td>
                      <td className="col-start-1 min-w-0 text-[0.9375rem] md:py-3 md:pr-4">
                        <Link href={`/componentes/${f.componente_critico_id}/modelo`} className="text-texto underline-offset-2 hover:text-accion hover:underline">
                          {f.componente_critico}
                        </Link>
                        {f.edad_horas !== null ? (
                          <span className="block text-[0.8125rem] text-texto-tenue">Pieza de {horas(Math.round(f.edad_horas))}</span>
                        ) : null}
                      </td>
                      <td className="col-start-2 row-start-1 text-right md:py-3 md:pr-4">
                        <span className="flex flex-col items-end gap-1">
                          <Porcentaje valor={r} confianza={f.confianza} />
                          <NivelRiesgo valor={nivel(r, umbral)} />
                        </span>
                      </td>
                      <td className="col-start-1 text-[0.875rem] text-texto-suave md:py-3 md:pr-4">
                        <span className="block">{respaldo(f.n_eventos)}</span>
                        <ConfianzaInsignia valor={f.confianza} />
                      </td>
                      <td className="col-start-2 text-right text-[0.8125rem] text-texto-tenue md:py-3 md:text-left">
                        {hace(f.calculado_en)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()} enCurso={cargandoMas} textoEnCurso="Cargando…">
              Cargar más equipos
            </Boton>
          </div>
        ) : null}
        <footer className="border-t border-borde bg-superficie-alterna px-5 py-4 text-[0.8125rem] leading-5 text-texto-tenue sm:px-6">
          «Estimado»: el número se apoya sobre todo en la vida nominal declarada, con pocas o ninguna
          falla de la empresa. «Confianza alta» no quiere decir exacto: con muchas fallas el error
          sigue siendo de varios puntos.
        </footer>
      </section>
    </div>
  );
}
