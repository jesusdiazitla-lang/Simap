"use client";

/**
 * Bandeja de alertas (RF-09; 05-fase2-activos-y-campo.md, 5.2 y 7.1).
 *
 * El supervisor ve las de la planta y las marca como revisadas o descartadas; el operario ve solo las
 * que reportó él, para saber qué pasó con ellas; el gerente y el administrador consultan. Por defecto
 * se abren las pendientes, que es lo que hay que atender.
 *
 * Revisar o descartar deja constancia de quién y cuándo, y no se deshace: en la fase 4 las alertas
 * pendientes suben el riesgo del equipo, así que la decisión tiene consecuencias.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { EstadoAlertaInsignia } from "@/components/estado";
import { LecturasPorRevisar } from "@/components/lecturas-por-revisar";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import {
  ETIQUETA_SINTOMA,
  listarAlertas,
  revisarAlerta,
  type Alerta,
  type EstadoAlerta,
} from "@/lib/campo";
import { fechaHora, hace } from "@/lib/formato";

const ROLES: readonly Rol[] = ["operario", "supervisor", "administrador", "gerente"];

export default function AlertasPage() {
  return (
    <Pantalla roles={ROLES} cargando="Alertas">
      {(usuario) => <Bandeja usuario={usuario} />}
    </Pantalla>
  );
}

function Bandeja({ usuario }: { readonly usuario: Usuario }) {
  const [estado, setEstado] = useState<EstadoAlerta | null>("pendiente");
  const [alertas, setAlertas] = useState<readonly Alerta[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revisa = usuario.rol === "supervisor" || usuario.rol === "administrador";
  const esOperario = usuario.rol === "operario";

  useEffect(() => {
    const control = new AbortController();
    void listarAlertas({ estado }, control.signal)
      .then((p) => {
        setAlertas(p.items);
        setCursor(p.next_cursor);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi ? e.message : "No se pudo cargar la bandeja.");
      });
    return () => control.abort();
  }, [estado]);

  async function cargarMas(): Promise<void> {
    if (cursor === null) return;
    const p = await listarAlertas({ estado, cursor });
    setAlertas((a) => [...(a ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  const filtros: Array<[EstadoAlerta | null, string]> = [
    ["pendiente", "Pendientes"],
    ["revisada", "Revisadas"],
    ["descartada", "Descartadas"],
    [null, "Todas"],
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">
          {esOperario ? "Mis alertas" : "Alertas"}
        </h1>
        <p className="pt-1 text-[0.9375rem] text-texto-suave">
          {esOperario
            ? "Las alertas que has reportado y qué se hizo con ellas."
            : "Síntomas que el personal notó en los equipos. Revisa las pendientes."}
        </p>
      </div>

      {revisa ? <LecturasPorRevisar esAdministrador={usuario.rol === "administrador"} /> : null}

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="border-b border-borde px-5 py-4 sm:px-6">
          <fieldset>
            <legend className="sr-only">Estado</legend>
            <div className="flex flex-wrap gap-2">
              {filtros.map(([valor, nombre]) => (
                <label
                  key={nombre}
                  className={[
                    "flex h-11 cursor-pointer items-center rounded-[var(--radius-control)] border px-4 text-[0.875rem] font-medium transition-colors",
                    "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                    estado === valor
                      ? "border-accion bg-[var(--accion-halo)] text-accion"
                      : "border-borde-fuerte bg-superficie text-texto-suave hover:text-texto",
                  ].join(" ")}
                >
                  <input type="radio" name="estado-alerta" className="sr-only" checked={estado === valor} onChange={() => setEstado(valor)} />
                  {nombre}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="px-5 py-2 sm:px-6">
          {error !== null ? (
            <p role="alert" className="py-3 text-[0.9375rem] text-error">{error}</p>
          ) : alertas === null ? (
            <div className="py-3"><Esqueleto /></div>
          ) : alertas.length === 0 ? (
            <p className="py-4 text-[0.9375rem] text-texto-suave">
              {estado === "pendiente" ? "No hay alertas pendientes." : "No hay alertas con este estado."}
            </p>
          ) : (
            <ul className="divide-y divide-borde">
              {alertas.map((a) => (
                <FilaAlerta
                  key={a.id}
                  alerta={a}
                  revisa={revisa}
                  alCambiar={(nueva) =>
                    setAlertas((lista) =>
                      (lista ?? [])
                        .map((x) => (x.id === nueva.id ? nueva : x))
                        // En «Pendientes», la revisada sale de la lista: ya no está pendiente.
                        .filter((x) => estado === null || x.estado === estado),
                    )
                  }
                />
              ))}
            </ul>
          )}
        </div>

        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()}>
              Cargar más
            </Boton>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function FilaAlerta({
  alerta,
  revisa,
  alCambiar,
}: {
  readonly alerta: Alerta;
  readonly revisa: boolean;
  readonly alCambiar: (a: Alerta) => void;
}) {
  const [enCurso, setEnCurso] = useState<"revisada" | "descartada" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function marcar(estado: "revisada" | "descartada"): Promise<void> {
    setEnCurso(estado);
    setError(null);
    try {
      const nueva = await revisarAlerta(alerta.id, estado);
      alCambiar({ ...nueva, activo_nombre: alerta.activo_nombre, activo_codigo: alerta.activo_codigo });
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo guardar.");
      setEnCurso(null);
    }
  }

  return (
    <li className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[1rem] font-semibold text-texto">{ETIQUETA_SINTOMA[alerta.sintoma]}</span>
          <EstadoAlertaInsignia estado={alerta.estado} />
        </div>
        <p className="pt-1 text-[0.9375rem] text-texto-suave">
          {alerta.activo_codigo ? (
            <Link href={`/a/${alerta.activo_codigo}`} className="font-medium text-accion underline-offset-2 hover:underline">
              {alerta.activo_nombre ?? "Equipo"}
            </Link>
          ) : (
            (alerta.activo_nombre ?? "Equipo")
          )}
        </p>
        {alerta.nota !== null ? (
          <p className="max-w-[65ch] pt-1 text-[0.9375rem] leading-6 text-texto [overflow-wrap:anywhere]">«{alerta.nota}»</p>
        ) : null}
        <p className="pt-1 text-[0.8125rem] text-texto-tenue">
          {fechaHora(alerta.capturado_en)} · {hace(alerta.capturado_en)}
        </p>
        {error !== null ? <p role="alert" className="pt-1 text-[0.875rem] text-error">{error}</p> : null}
      </div>
      {revisa && alerta.estado === "pendiente" ? (
        <div className="grid shrink-0 grid-cols-2 gap-2 sm:w-64">
          <Boton tipo="button" variante="secundario" onClick={() => void marcar("descartada")} enCurso={enCurso === "descartada"} textoEnCurso="…" deshabilitado={enCurso === "revisada"}>
            Descartar
          </Boton>
          <Boton tipo="button" variante="secundario" onClick={() => void marcar("revisada")} enCurso={enCurso === "revisada"} textoEnCurso="…" deshabilitado={enCurso === "descartada"}>
            Revisada
          </Boton>
        </div>
      ) : null}
    </li>
  );
}
