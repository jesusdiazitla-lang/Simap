"use client";

/**
 * Registrar la lectura del horómetro (RF-08; 05-fase2-activos-y-campo.md, 7.3).
 *
 * Un solo campo, con teclado numérico y la última lectura al lado: quien escribe compara sin
 * levantar la vista. Si el número no cuadra —menor que el anterior, o un salto que el reloj no
 * permite—, la pantalla pide confirmar antes de enviar. Es la primera línea de defensa contra el
 * error más común, un dígito de más; el servidor vuelve a comprobarlo y, si tampoco cuadra, guarda
 * la lectura marcada para revisión sin mover el horómetro del equipo.
 *
 * El identificador de la captura se fija la primera vez que se intenta enviar y se reutiliza en
 * cualquier reintento: así una lectura enviada dos veces por mala cobertura entra una sola.
 */

import { useRef, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { IconoAviso, IconoHecho, IconoPendiente } from "@/components/iconos";
import { ErrorApi } from "@/lib/api";
import type { Activo } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import { nuevaCaptura, type Lectura } from "@/lib/campo";
import { enviarLectura } from "@/lib/captura";
import { hace, horas } from "@/lib/formato";

/** Holgura al comparar el salto con las horas de reloj. Igual que `HOROMETRO_TOLERANCIA_HORAS`. */
const TOLERANCIA_HORAS = 2;

type Aviso =
  | { readonly tipo: "hecho"; readonly texto: string }
  | { readonly tipo: "revision"; readonly texto: string }
  | { readonly tipo: "encolado" }
  | { readonly tipo: "error"; readonly texto: string };

function motivoDeDuda(activo: Activo, valor: number): string | null {
  if (activo.horometro_actualizado_en === null) return null;
  if (valor < activo.horometro_actual) {
    return `Es menor que la última lectura (${horas(activo.horometro_actual)}). ¿Se cambió o reinició el horómetro, o es un error al teclear?`;
  }
  const horasReloj = (Date.now() - new Date(activo.horometro_actualizado_en).getTime()) / 3_600_000;
  const salto = valor - activo.horometro_actual;
  if (salto > horasReloj + TOLERANCIA_HORAS) {
    return `Sube ${horas(salto)} desde la última lectura, y solo han pasado ${horas(Math.max(0, Math.round(horasReloj)))} de reloj. ¿Hay un dígito de más?`;
  }
  return null;
}

export function FormularioHorometro({
  usuario,
  activo,
  alRegistrar,
}: {
  readonly usuario: Usuario;
  readonly activo: Activo;
  /** Lectura aceptada sin marca: la pantalla actualiza la «última lectura». */
  readonly alRegistrar?: (lectura: Lectura) => void;
}) {
  const [valor, setValor] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [duda, setDuda] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const captura = useRef<{ cliente_id: string; capturado_en: string } | null>(null);
  const idFormulario = "form-horometro";

  /**
   * Horas enteras (05-fase2, sección 5.1). Admite separadores de miles bien puestos («48,215» o
   * «48 215»), pero un punto o una coma en cualquier otro sitio es un decimal: quitarlo sin más
   * convertía «4821.5» en 48 215, justo el dígito de más que esta pantalla intenta evitar.
   */
  function leer(): number | string {
    const texto = valor.trim();
    if (/^\d{1,7}$/.test(texto)) return Number(texto);
    if (/^\d{1,3}([.,\s])\d{3}(\1\d{3})?$/.test(texto)) return Number(texto.replace(/\D/g, ""));
    if (/^\d[\d.,\s]*[.,]\d{1,2}$/.test(texto)) {
      return "El horómetro se anota en horas enteras, sin decimales. Escribe solo la parte entera.";
    }
    return "Escribe las horas que marca el horómetro, solo con números.";
  }

  async function enviar(confirmado: boolean): Promise<void> {
    const n = leer();
    if (typeof n === "string") {
      setError(n);
      return;
    }
    setError(undefined);
    if (!confirmado) {
      const motivo = motivoDeDuda(activo, n);
      if (motivo !== null) {
        setDuda(motivo);
        return;
      }
    }
    setDuda(null);
    setEnCurso(true);
    captura.current ??= nuevaCaptura();
    try {
      const r = await enviarLectura(usuario, activo, { ...captura.current, valor: n });
      if (r.tipo === "encolado") {
        setAviso({ tipo: "encolado" });
      } else if (r.lectura.requiere_revision) {
        setAviso({
          tipo: "revision",
          texto: `${horas(r.lectura.valor_horometro)} guardadas, pero no cuadran con el historial. ${r.lectura.motivo_revision ?? ""} Un supervisor la revisará; el horómetro del equipo no cambia hasta entonces.`,
        });
      } else {
        setAviso({
          tipo: "hecho",
          texto:
            r.estado === "duplicado"
              ? `Esta lectura ya había llegado (${horas(r.lectura.valor_horometro)}). No se ha duplicado.`
              : `Lectura registrada: ${horas(r.lectura.valor_horometro)}.`,
        });
        alRegistrar?.(r.lectura);
      }
      setValor("");
      captura.current = null;
    } catch (fallo) {
      setAviso({
        tipo: "error",
        texto: fallo instanceof ErrorApi ? fallo.message : "No se pudo registrar. Vuelve a intentarlo.",
      });
    } finally {
      setEnCurso(false);
    }
  }

  const ultima =
    activo.horometro_actualizado_en === null
      ? "Sin lecturas todavía"
      : `Última: ${horas(activo.horometro_actual)} · ${hace(activo.horometro_actualizado_en)}`;

  return (
    <form
      id={idFormulario}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar(false);
      }}
      className="flex flex-col gap-3"
    >
      <Campo
        id="horometro-valor"
        etiqueta="Horas que marca el horómetro"
        nombre="valor"
        valor={valor}
        onCambio={(v) => {
          setValor(v);
          setDuda(null);
          setAviso(null);
        }}
        error={error}
        modoTeclado="numeric"
        ayuda={ultima}
        maxLength={9}
        autoComplete="off"
        grande
        deshabilitado={enCurso}
      />

      {duda !== null ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie-alterna p-3"
        >
          <p className="flex gap-2 text-[0.9375rem] leading-6 text-texto">
            <IconoAviso className="mt-0.5 text-estado-aviso" />
            <span>{duda}</span>
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Boton tipo="button" variante="secundario" onClick={() => setDuda(null)}>
              Corregir
            </Boton>
            <Boton tipo="button" onClick={() => void enviar(true)} enCurso={enCurso} textoEnCurso="Enviando…">
              Enviar igualmente
            </Boton>
          </div>
        </div>
      ) : (
        <Boton
          form={idFormulario}
          anchoCompleto
          enCurso={enCurso}
          textoEnCurso="Enviando…"
          deshabilitado={valor.trim() === ""}
        >
          Registrar lectura
        </Boton>
      )}

      <AvisoEnvio aviso={aviso} />
    </form>
  );
}

/** Resultado del envío. Un solo sitio para los dos formularios de campo. */
export function AvisoEnvio({ aviso }: { readonly aviso: Aviso | null }) {
  if (aviso === null) return <div role="status" aria-live="polite" />;
  const estilo =
    aviso.tipo === "hecho"
      ? "border-estado-ok"
      : aviso.tipo === "error"
        ? "border-error bg-error-fondo"
        : "border-estado-aviso";
  const icono =
    aviso.tipo === "hecho" ? (
      <IconoHecho className="mt-0.5 text-estado-ok" />
    ) : aviso.tipo === "encolado" ? (
      <IconoPendiente className="mt-0.5 text-estado-aviso" />
    ) : (
      <IconoAviso className={["mt-0.5", aviso.tipo === "error" ? "text-error" : "text-estado-aviso"].join(" ")} />
    );
  const texto =
    aviso.tipo === "encolado"
      ? "Sin conexión: quedó guardada en el teléfono y se enviará sola al volver la red."
      : aviso.texto;
  return (
    <div role={aviso.tipo === "error" ? "alert" : "status"} aria-live="polite">
      <p
        className={[
          "flex gap-2 rounded-[var(--radius-control)] border bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6",
          aviso.tipo === "error" ? "text-error" : "text-texto",
          estilo,
        ].join(" ")}
      >
        {icono}
        <span>{texto}</span>
      </p>
    </div>
  );
}

export type { Aviso };
