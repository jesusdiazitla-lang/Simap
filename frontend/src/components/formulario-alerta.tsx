"use client";

/**
 * Reportar una alerta: el equipo sigue funcionando, pero algo no va bien (RF-09; 7.3).
 *
 * Los síntomas son seis botones grandes de un toque, no una lista desplegable: con guantes, una
 * lista desplegable es tres toques precisos sobre una pantalla pequeña. Por dentro son radios de
 * verdad, así que el teclado y el lector de pantalla los entienden como «elige uno».
 *
 * La selección se marca en azul porque es un estado de interacción —lo has elegido tú—, no un
 * estado de la máquina: el color de estado queda libre para decir lo que le pasa al equipo.
 */

import { useId, useRef, useState } from "react";

import { Boton } from "@/components/boton";
import { AvisoEnvio, type Aviso } from "@/components/formulario-horometro";
import { IconoHecho } from "@/components/iconos";
import { ErrorApi } from "@/lib/api";
import type { Activo } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import { ETIQUETA_SINTOMA, MAX_NOTA, nuevaCaptura, SINTOMAS, type Sintoma } from "@/lib/campo";
import { enviarAlerta } from "@/lib/captura";
import { hace } from "@/lib/formato";

export function FormularioAlerta({
  usuario,
  activo,
}: {
  readonly usuario: Usuario;
  readonly activo: Activo;
}) {
  const [sintoma, setSintoma] = useState<Sintoma | null>(null);
  const [nota, setNota] = useState("");
  const [enCurso, setEnCurso] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const captura = useRef<{ cliente_id: string; capturado_en: string } | null>(null);
  const idNota = useId();
  const idFormulario = "form-alerta";

  async function enviar(): Promise<void> {
    if (sintoma === null) return;
    setEnCurso(true);
    captura.current ??= nuevaCaptura();
    try {
      const r = await enviarAlerta(usuario, activo, {
        ...captura.current,
        sintoma,
        nota: nota.trim() === "" ? null : nota.trim(),
      });
      if (r.tipo === "encolado") {
        setAviso({ tipo: "encolado" });
      } else {
        setAviso({
          tipo: "hecho",
          texto:
            r.estado === "duplicado"
              ? `Ya habías reportado ${ETIQUETA_SINTOMA[r.alerta.sintoma].toLowerCase()} en este equipo ${hace(r.alerta.capturado_en)}. No se ha duplicado.`
              : `Alerta registrada: ${ETIQUETA_SINTOMA[r.alerta.sintoma]}. El supervisor la verá en su bandeja.`,
        });
      }
      setSintoma(null);
      setNota("");
      captura.current = null;
    } catch (fallo) {
      setAviso({
        tipo: "error",
        texto: fallo instanceof ErrorApi ? fallo.message : "No se pudo reportar. Vuelve a intentarlo.",
      });
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <form
      id={idFormulario}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
      className="flex flex-col gap-4"
    >
      <fieldset>
        <legend className="pb-2 text-[0.8125rem] font-medium text-texto">¿Qué notas en el equipo?</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {SINTOMAS.map((s) => {
            const elegido = sintoma === s;
            return (
              <label
                key={s}
                className={[
                  "relative flex h-14 cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-control)] border text-[1rem] font-semibold transition-colors",
                  "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                  elegido
                    ? "border-2 border-accion bg-[var(--accion-halo)] text-accion"
                    : "border-borde-fuerte bg-superficie text-texto hover:border-accion",
                  enCurso ? "cursor-progress" : "",
                ].join(" ")}
              >
                <input
                  type="radio"
                  name="sintoma"
                  value={s}
                  checked={elegido}
                  onChange={() => {
                    setSintoma(s);
                    setAviso(null);
                  }}
                  disabled={enCurso}
                  className="sr-only"
                />
                {elegido ? <IconoHecho className="h-4 w-4" /> : null}
                {ETIQUETA_SINTOMA[s]}
              </label>
            );
          })}
        </div>
      </fieldset>

      <div>
        <label htmlFor={idNota} className="flex items-baseline justify-between pb-1.5 text-[0.8125rem] font-medium text-texto">
          <span>
            Nota <span className="font-normal text-texto-tenue">opcional</span>
          </span>
          <span className="font-normal text-texto-tenue" aria-hidden="true">
            {nota.length}/{MAX_NOTA}
          </span>
        </label>
        <textarea
          id={idNota}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          maxLength={MAX_NOTA}
          rows={2}
          disabled={enCurso}
          placeholder="Por ejemplo: golpeteo al arrancar, solo en frío"
          className="block w-full resize-y rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 py-2.5 text-[1rem] leading-6 text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)] disabled:bg-superficie-alterna"
        />
      </div>

      <Boton
        form={idFormulario}
        anchoCompleto
        enCurso={enCurso}
        textoEnCurso="Enviando…"
        deshabilitado={sintoma === null}
      >
        {sintoma === null ? "Elige un síntoma" : `Reportar ${ETIQUETA_SINTOMA[sintoma].toLowerCase()}`}
      </Boton>

      <AvisoEnvio aviso={aviso} />
    </form>
  );
}
