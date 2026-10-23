"use client";

/**
 * Modelo de un componente (RF-17; 07-fase4, 5 y 10.1).
 *
 * β, η, cuántas fallas lo respaldan y su confianza; la curva de riesgo según la edad de la pieza; y
 * la curva de aprendizaje: cómo se movieron β y η a medida que llegaron fallas (`modelos_historial`).
 * Es la evidencia directa del capítulo IV de la tesis, y también la forma de que un supervisor vea
 * por qué el sistema dice lo que dice.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Insignia } from "@/components/estado";
import { Panel } from "@/components/marco";
import { ConfianzaInsignia, CurvaRiesgo } from "@/components/riesgo";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { fechaHora, hace, horas } from "@/lib/formato";
import {
  leerConfiguracion,
  modeloDelComponente,
  respaldo,
  type Configuracion,
  type Fuente,
  type Modelo,
} from "@/lib/prediccion";

const ROLES: readonly Rol[] = ["supervisor", "gerente", "administrador"];

const ETIQUETA_FUENTE: Readonly<Record<Fuente, string>> = {
  previo: "Solo la vida nominal declarada",
  mixto: "Vida nominal corregida con las fallas de la empresa",
  empresa: "Sobre todo, la historia de la empresa",
};

export default function ModeloPage() {
  return (
    <Pantalla roles={ROLES} cargando="Modelo del componente">
      {(usuario) => <Detalle usuario={usuario} />}
    </Pantalla>
  );
}

function desgaste(beta: number): string {
  if (beta > 1.15) return "Se desgasta con la edad: cuanto más tiempo lleva instalada, más probable es que falle.";
  if (beta < 0.85) return "Falla sobre todo al principio: piezas nuevas o mal instaladas.";
  return "Falla a un ritmo parecido a cualquier edad.";
}

function Detalle({ usuario }: { readonly usuario: Usuario }) {
  const { id } = useParams<{ id: string }>();
  const [modelo, setModelo] = useState<Modelo | null>(null);
  const [config, setConfig] = useState<Configuracion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const control = new AbortController();
    Promise.all([modeloDelComponente(id, control.signal), leerConfiguracion(control.signal)])
      .then(([m, c]) => {
        setModelo(m);
        setConfig(c);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi && e.estado === 404 ? "Este componente no existe." : "No se pudo cargar el modelo.");
      });
    return () => control.abort();
  }, [id]);

  if (error !== null) {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Modelo del componente">
          <p className="pb-4 text-[0.9375rem] text-error">{error}</p>
          <EnlaceBoton href="/riesgo">Volver al riesgo</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (modelo === null || config === null) {
    return (
      <Panel titulo="Modelo del componente">
        <Esqueleto />
      </Panel>
    );
  }

  const tiene = modelo.beta !== null && modelo.eta !== null;
  return (
    <div className="flex flex-col gap-6">
      <Link href="/riesgo" className="self-start text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline">
        ← Riesgo de falla
      </Link>
      <div className="max-w-[70ch]">
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">{modelo.componente}</h1>
        <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
          Un solo modelo para este componente en todos los equipos de la empresa, ajustado con sus
          fallas y con las piezas que siguen funcionando.
        </p>
      </div>

      {!tiene ? (
        <Panel nivel={2} titulo="Sin modelo todavía">
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            Hace falta la vida nominal del componente o dos fallas registradas para tener un modelo.
            {usuario.rol === "administrador" ? (
              <>
                {" "}
                <Link href="/componentes" className="text-accion underline underline-offset-2">
                  Declara su vida nominal
                </Link>
                .
              </>
            ) : (
              " La declara el administrador en el catálogo de componentes."
            )}
          </p>
        </Panel>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
          <Panel nivel={2} titulo="Curva de riesgo">
            <CurvaRiesgo
              beta={modelo.beta as number}
              eta={modelo.eta as number}
              horizonte={config.horizonte_horas}
              umbral={Number(config.umbral_riesgo)}
            />
          </Panel>
          <Panel
            nivel={2}
            titulo="Parámetros"
            pie={modelo.ajustado_en !== null ? `Versión ${modelo.version} · ajustado ${hace(modelo.ajustado_en)}` : undefined}
          >
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-3 text-[0.9375rem]">
              <dt className="text-texto-suave">Vida característica (η)</dt>
              <dd className="text-right font-semibold text-texto">{horas(Math.round(modelo.eta as number))}</dd>
              <dt className="text-texto-suave">Forma (β)</dt>
              <dd className="text-right font-semibold text-texto">{(modelo.beta as number).toFixed(2)}</dd>
              <dt className="text-texto-suave">Vida nominal declarada</dt>
              <dd className="text-right text-texto">
                {modelo.vida_nominal_horas !== null ? horas(modelo.vida_nominal_horas) : "—"}
              </dd>
              <dt className="text-texto-suave">Respaldo</dt>
              <dd className="text-right text-texto">{respaldo(modelo.n_eventos)}</dd>
              <dt className="text-texto-suave">Horas observadas</dt>
              <dd className="text-right text-texto">{horas(Math.round(modelo.exposicion_horas ?? 0))}</dd>
            </dl>
            <p className="pt-4 text-[0.875rem] leading-5 text-texto-suave">{desgaste(modelo.beta as number)}</p>
            <div className="flex flex-wrap items-center gap-2 pt-3">
              <ConfianzaInsignia valor={modelo.confianza} />
              {modelo.fuente !== null ? <Insignia tono="neutro">{ETIQUETA_FUENTE[modelo.fuente]}</Insignia> : null}
              {modelo.convergio === false ? <Insignia tono="aviso">El ajuste no convergió</Insignia> : null}
            </div>
          </Panel>
        </div>
      )}

      <Panel
        nivel={2}
        titulo="Curva de aprendizaje"
        descripcion="Una fila cada vez que cambió el número de fallas: cómo se movió el modelo a medida que la empresa acumuló historia."
      >
        {modelo.historial.length === 0 ? (
          <p className="text-[0.9375rem] text-texto-suave">Sin versiones todavía.</p>
        ) : (
          <table className="w-full border-collapse text-left text-[0.9375rem]">
            <thead>
              <tr className="border-b border-borde text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">
                <th scope="col" className="pb-2 pr-4 font-medium">Fallas</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium normal-case">η</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium normal-case">β</th>
                <th scope="col" className="hidden pb-2 pr-4 font-medium sm:table-cell">Confianza</th>
                <th scope="col" className="pb-2 font-medium">Ajustado</th>
              </tr>
            </thead>
            <tbody>
              {[...modelo.historial].reverse().map((h) => (
                <tr key={`${h.version}-${h.ajustado_en}`} className="border-b border-borde last:border-0">
                  <td className="py-2.5 pr-4 font-semibold text-texto">{h.n_eventos}</td>
                  <td className="whitespace-nowrap py-2.5 pr-4 text-right text-texto">{horas(Math.round(h.eta))}</td>
                  <td className="py-2.5 pr-4 text-right text-texto">{h.beta.toFixed(2)}</td>
                  <td className="hidden py-2.5 pr-4 sm:table-cell">
                    <ConfianzaInsignia valor={h.confianza} />
                  </td>
                  <td className="py-2.5 text-[0.875rem] text-texto-suave">{fechaHora(h.ajustado_en)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
