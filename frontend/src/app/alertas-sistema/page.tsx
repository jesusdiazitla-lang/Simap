"use client";

/**
 * Bandeja de alertas del sistema (RF-21, RF-26; 07-fase4, 6.3, 6.4 y 10.1).
 *
 * Dos pestañas: **Riesgo** (un componente superó el umbral de la empresa) y **Reorden** (un repuesto
 * quedó bajo el mínimo). Se abre en las vigentes; el historial son las resueltas y descartadas.
 *
 * Acciones de una alerta de riesgo (supervisor y administrador; el gerente solo lee):
 * - **Reconocer**: «la vi». No cambia el riesgo ni deja de vigilar.
 * - **Crear la orden predictiva**: cambiar la pieza antes de que falle. Abre la orden nueva.
 * - **Descartar**, con nota: silencia ese componente unos días. Pasado el plazo, si el riesgo sigue
 *   alto, vuelve a avisar.
 *
 * Si otra persona la gestionó antes (409), la bandeja se recarga y lo dice.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { Boton } from "@/components/boton";
import { Insignia } from "@/components/estado";
import { IconoAviso } from "@/components/iconos";
import { ConfianzaInsignia } from "@/components/riesgo";
import { Segmento } from "@/components/segmento";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol, Usuario } from "@/lib/auth";
import { fechaHora, hace } from "@/lib/formato";
import { numeroOrden } from "@/lib/ordenes";
import {
  crearOrdenPredictiva,
  descartarAlerta,
  listarAlertasSistema,
  numero,
  porcentaje,
  reconocerAlerta,
  type AlertaSistema,
  type EstadoAlertaSistema,
  type FiltroAlertas,
  type TipoAlertaSistema,
} from "@/lib/prediccion";
import { useSondeo } from "@/lib/sondeo";

const ROLES: readonly Rol[] = ["supervisor", "gerente", "administrador"];

export default function AlertasSistemaPage() {
  return (
    <Pantalla roles={ROLES} cargando="Alertas del sistema">
      {(usuario, sinRed) => <Bandeja usuario={usuario} sinRed={sinRed} />}
    </Pantalla>
  );
}

function EstadoInsignia({ estado }: { readonly estado: EstadoAlertaSistema }) {
  switch (estado) {
    case "activa":
      return (
        <Insignia tono="falla" icono={<IconoAviso className="h-3.5 w-3.5" />}>
          Activa
        </Insignia>
      );
    case "reconocida":
      return (
        <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>
          Reconocida
        </Insignia>
      );
    case "atendida":
      return <Insignia tono="aviso">Con orden</Insignia>;
    case "resuelta":
      return <Insignia tono="ok">Resuelta</Insignia>;
    default:
      return <Insignia tono="neutro">Descartada</Insignia>;
  }
}

function Bandeja({ usuario, sinRed }: { readonly usuario: Usuario; readonly sinRed: boolean }) {
  const [tipo, setTipo] = useState<TipoAlertaSistema>("riesgo");
  const [filtro, setFiltro] = useState<FiltroAlertas>("vigentes");
  const [alertas, setAlertas] = useState<readonly AlertaSistema[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const gestiona = usuario.rol === "supervisor" || usuario.rol === "administrador";

  const cargar = useCallback(
    (signal?: AbortSignal) =>
      listarAlertasSistema({ tipo, estado: filtro }, signal)
        .then((p) => {
          setAlertas(p.items);
          setCursor(p.next_cursor);
          setError(null);
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setError(e instanceof ErrorApi ? e.message : "No se pudo cargar la bandeja.");
        }),
    [tipo, filtro],
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
    const p = await listarAlertasSistema({ tipo, estado: filtro, cursor });
    setAlertas((a) => [...(a ?? []), ...p.items]);
    setCursor(p.next_cursor);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="max-w-[70ch]">
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Alertas del sistema</h1>
        <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
          Las genera SIMAP, no el personal: un componente que superó el umbral de riesgo de la empresa,
          o un repuesto que quedó bajo su mínimo.
          {usuario.rol === "gerente" ? " Solo lectura." : ""}
        </p>
      </div>

      {aviso !== null ? (
        <p role="alert" className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 shrink-0 text-estado-aviso" />
          <span>{aviso}</span>
        </p>
      ) : null}

      <section className="rounded-[var(--radius-control)] border border-borde bg-superficie">
        <div className="flex flex-wrap gap-3 border-b border-borde px-5 py-4 sm:px-6">
          <Segmento
            nombre="tipo-alerta"
            leyenda="Tipo de alerta"
            opciones={[["riesgo", "Riesgo"], ["reorden", "Reorden"]] as const}
            valor={tipo}
            alCambiar={(v) => {
              setTipo(v);
              setAlertas(null);
            }}
          />
          <Segmento
            nombre="estado-alerta"
            leyenda="Mostrar"
            opciones={[["vigentes", "Vigentes"], ["historial", "Historial"]] as const}
            valor={filtro}
            alCambiar={(v) => {
              setFiltro(v);
              setAlertas(null);
            }}
          />
        </div>

        <div className="px-5 py-4 sm:px-6">
          {error !== null && alertas === null ? (
            <p role="alert" className="text-[0.9375rem] text-error">{error}</p>
          ) : alertas === null ? (
            <Esqueleto />
          ) : alertas.length === 0 ? (
            <p className="py-2 text-[0.9375rem] leading-6 text-texto-suave">
              {filtro === "historial"
                ? "Todavía no hay alertas resueltas ni descartadas."
                : tipo === "riesgo"
                  ? "Ningún componente supera hoy el umbral de riesgo de la empresa."
                  : "Ningún repuesto está bajo su mínimo."}
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-borde">
              {alertas.map((a) =>
                a.tipo === "riesgo" ? (
                  <FilaRiesgo
                    key={a.id}
                    alerta={a}
                    gestiona={gestiona}
                    sinRed={sinRed}
                    alCambiar={(nueva) => setAlertas((lista) => (lista ?? []).map((x) => (x.id === nueva.id ? nueva : x)))}
                    alConflicto={(m) => {
                      setAviso(m);
                      void cargar();
                    }}
                  />
                ) : (
                  <FilaReorden key={a.id} alerta={a} />
                ),
              )}
            </ul>
          )}
        </div>
        {cursor !== null ? (
          <div className="border-t border-borde px-5 py-4 sm:px-6">
            <Boton tipo="button" variante="secundario" onClick={() => void cargarMas()}>
              Cargar más alertas
            </Boton>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function FilaRiesgo({
  alerta,
  gestiona,
  sinRed,
  alCambiar,
  alConflicto,
}: {
  readonly alerta: AlertaSistema;
  readonly gestiona: boolean;
  readonly sinRed: boolean;
  readonly alCambiar: (a: AlertaSistema) => void;
  readonly alConflicto: (mensaje: string) => void;
}) {
  const id = useId();
  const router = useRouter();
  const [enCurso, setEnCurso] = useState<string | null>(null);
  const [descartando, setDescartando] = useState(false);
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const vigente = alerta.estado === "activa" || alerta.estado === "reconocida";
  const r = numero(alerta.riesgo) ?? 0;

  async function ejecutar(nombre: string, accion: () => Promise<void>): Promise<void> {
    setEnCurso(nombre);
    setError(null);
    try {
      await accion();
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409) alConflicto(e.message);
      else setError(e instanceof ErrorApi ? e.message : "No se pudo completar la acción.");
    } finally {
      setEnCurso(null);
    }
  }

  return (
    <li className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-texto [overflow-wrap:anywhere]">
            {alerta.activo}
            <span className="font-normal text-texto-suave"> · </span>
            {alerta.componente_id !== null ? (
              <Link href={`/componentes/${alerta.componente_id}/modelo`} className="font-normal text-accion underline-offset-2 hover:underline">
                {alerta.componente}
              </Link>
            ) : null}
          </p>
          <p className="pt-0.5 text-[0.875rem] leading-5 text-texto-suave">
            Riesgo de {porcentaje(r)} al crearse, con el umbral en{" "}
            {porcentaje(numero(alerta.umbral) ?? 0)}. {fechaHora(alerta.creada_en)} · {hace(alerta.creada_en)}
          </p>
          {alerta.nota !== null ? (
            <p className="pt-1 text-[0.875rem] leading-5 text-texto [overflow-wrap:anywhere]">
              <span className="text-texto-suave">Nota:</span> {alerta.nota}
            </p>
          ) : null}
          {alerta.orden_id !== null && alerta.orden_numero !== null ? (
            <p className="pt-1 text-[0.875rem]">
              <Link href={`/ordenes/${alerta.orden_id}`} className="font-mono font-semibold tracking-[0.04em] text-accion underline-offset-2 hover:underline">
                {numeroOrden(alerta.orden_numero)}
              </Link>
              <span className="text-texto-suave"> · cambio planificado</span>
            </p>
          ) : null}
        </div>
        <span className="flex flex-wrap items-center gap-2">
          <EstadoInsignia estado={alerta.estado} />
          <ConfianzaInsignia valor={alerta.confianza} />
        </span>
      </div>

      {gestiona && vigente && !descartando ? (
        <div className="flex flex-wrap gap-2">
          <Boton
            tipo="button"
            deshabilitado={sinRed}
            enCurso={enCurso === "orden"}
            textoEnCurso="Creando la orden…"
            onClick={() =>
              void ejecutar("orden", async () => {
                const orden = await crearOrdenPredictiva(alerta.id);
                router.push(`/ordenes/${orden.id}`);
              })
            }
          >
            Crear orden predictiva
          </Boton>
          {alerta.estado === "activa" ? (
            <Boton
              tipo="button"
              variante="secundario"
              deshabilitado={sinRed}
              enCurso={enCurso === "reconocer"}
              onClick={() => void ejecutar("reconocer", async () => alCambiar(await reconocerAlerta(alerta.id)))}
            >
              Reconocer
            </Boton>
          ) : null}
          <Boton tipo="button" variante="secundario" deshabilitado={sinRed} onClick={() => setDescartando(true)}>
            Descartar…
          </Boton>
        </div>
      ) : null}

      {descartando ? (
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (nota.trim().length < 3) {
              setError("Escribe por qué no se actúa ahora (mínimo 3 letras).");
              return;
            }
            void ejecutar("descartar", async () => {
              alCambiar(await descartarAlerta(alerta.id, nota.trim()));
              setDescartando(false);
            });
          }}
          className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna p-3"
        >
          <label htmlFor={`${id}-nota`} className="text-[0.8125rem] font-medium text-texto">
            Por qué no se actúa ahora
          </label>
          <p className="-mt-2 text-[0.8125rem] leading-5 text-texto-suave">
            El componente queda en silencio unos días; si después sigue alto, vuelve a avisar. La nota no
            se borra: no escribas datos personales.
          </p>
          <textarea
            id={`${id}-nota`}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            maxLength={500}
            rows={2}
            className="w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 py-2 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
          />
          <div className="flex flex-wrap gap-2">
            <Boton tipo="button" variante="secundario" onClick={() => setDescartando(false)}>
              Volver
            </Boton>
            <Boton tipo="submit" variante="secundario" enCurso={enCurso === "descartar"} textoEnCurso="Descartando…">
              Descartar la alerta
            </Boton>
          </div>
        </form>
      ) : null}

      {error !== null ? (
        <p role="alert" className="text-[0.875rem] text-error">{error}</p>
      ) : null}
    </li>
  );
}

function FilaReorden({ alerta }: { readonly alerta: AlertaSistema }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-4 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="font-semibold text-texto [overflow-wrap:anywhere]">
          {alerta.repuesto_id !== null ? (
            <Link href={`/inventario/${alerta.repuesto_id}`} className="text-accion underline-offset-2 hover:underline">
              {alerta.repuesto}
            </Link>
          ) : (
            alerta.repuesto
          )}
          <span className="pl-2 font-mono text-[0.8125rem] font-normal tracking-[0.04em] text-texto-suave">{alerta.repuesto_codigo}</span>
        </p>
        <p className="pt-0.5 text-[0.875rem] leading-5 text-texto-suave">
          Quedó en {alerta.stock_al_alertar} con el mínimo en {alerta.stock_minimo_al_alertar}.{" "}
          {fechaHora(alerta.creada_en)} · {hace(alerta.creada_en)}
        </p>
        {alerta.estado !== "resuelta" ? (
          <p className="pt-0.5 text-[0.8125rem] text-texto-tenue">Se resuelve sola al registrar el ingreso.</p>
        ) : null}
      </div>
      <EstadoInsignia estado={alerta.estado} />
    </li>
  );
}
