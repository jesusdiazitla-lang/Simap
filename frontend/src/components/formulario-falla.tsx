"use client";

/**
 * Reportar una falla: el equipo se detuvo o hay que llevarlo al taller (RF-11; 06-fase3, 6.2 y 9.2).
 *
 * Crea la orden de trabajo. Se abre desde la pantalla del equipo (escanear, completar, enviar) o
 * desde una alerta, con el equipo —y la alerta— ya cargados.
 *
 * QUÉ CUIDA ESTE FORMULARIO
 * -------------------------
 * - **El componente** se elige de una lista con buscador, en filas de un toque. Los que ya tienen
 *   una orden abierta en este equipo salen deshabilitados con su número: es el caso común del 409, y
 *   así no llega a ocurrir. El servidor sigue siendo quien decide.
 * - **El horómetro** se comprueba igual que una lectura de campo (`lib/horometro`): esta falla
 *   registra también una lectura, y un dígito de más aquí distorsiona el modelo de la fase 4.
 * - **Sin conexión** se guarda en el teléfono con el mismo identificador y se envía sola al volver la
 *   red (sección 9.5). No tiene número hasta llegar al servidor, y lo dice.
 * - **El historial no se borra**: lo escrito en la descripción queda para siempre en la orden, y el
 *   formulario lo advierte (sección 11.4).
 */

import Link from "next/link";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { AvisoEnvio, type Aviso } from "@/components/formulario-horometro";
import { IconoAviso, IconoHecho } from "@/components/iconos";
import { ErrorApi } from "@/lib/api";
import { listarComponentes, type Activo, type Componente } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import { nuevaCaptura } from "@/lib/campo";
import { hace, horas } from "@/lib/formato";
import { leerHorometro, motivoDeDuda } from "@/lib/horometro";
import { enviarFalla, numeroOrden, type OrdenDetalle } from "@/lib/ordenes";

const MAX_DESCRIPCION = 1000;
const MIN_DESCRIPCION = 5;
/** A partir de cuántos componentes aparece el buscador. Con pocos, estorba. */
const UMBRAL_BUSCADOR = 8;

// --- Catálogo guardado para reportar sin red ----------------------------------------------
// Es la lista de nombres de componentes de la empresa, no un dato sensible; se guarda por empresa
// para que en un teléfono compartido nadie vea el catálogo de otra. Si el almacenamiento no está
// disponible, el formulario funciona igual con red.

function claveCatalogo(empresaId: string): string {
  return `simap.componentes.${empresaId}`;
}

function catalogoGuardado(empresaId: string): readonly Componente[] | null {
  try {
    const crudo = window.localStorage.getItem(claveCatalogo(empresaId));
    return crudo === null ? null : (JSON.parse(crudo) as Componente[]);
  } catch {
    return null;
  }
}

function guardarCatalogo(empresaId: string, componentes: readonly Componente[]): void {
  try {
    window.localStorage.setItem(claveCatalogo(empresaId), JSON.stringify(componentes));
  } catch {
    // Sin almacenamiento, sin respaldo: con red el formulario no lo necesita.
  }
}

/** Temperatura opcional, con decimales y signo (de -100 a 999 °C). */
function leerTemperatura(valor: string): number | null | string {
  const texto = valor.trim().replace(",", ".");
  if (texto === "") return null;
  if (!/^-?\d{1,3}(\.\d{1,2})?$/.test(texto)) return "Escribe la temperatura en grados, por ejemplo 94.5.";
  const n = Number(texto);
  return n < -100 || n > 999 ? "La temperatura debe estar entre -100 y 999 °C." : n;
}

export function FormularioFalla({
  usuario,
  activo,
  alertaId = null,
  alCrear,
}: {
  readonly usuario: Usuario;
  readonly activo: Activo;
  /** La alerta que origina la orden (RF-16), si se abrió desde ella. */
  readonly alertaId?: string | null;
  /** La orden nació en el servidor: la pantalla puede llevar a ella. */
  readonly alCrear?: (orden: OrdenDetalle) => void;
}) {
  const [componentes, setComponentes] = useState<readonly Componente[] | null>(null);
  const [errorCatalogo, setErrorCatalogo] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("");
  const [componenteId, setComponenteId] = useState<string | null>(null);
  const [horometro, setHorometro] = useState("");
  const [temperatura, setTemperatura] = useState("");
  const [codigoError, setCodigoError] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [duda, setDuda] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [existente, setExistente] = useState<{ id: string; numero: number } | null>(null);
  const [creada, setCreada] = useState<OrdenDetalle | null>(null);
  // Guardada en el teléfono sin red. El formulario se retira: un segundo toque la encolaría otra vez
  // con un identificador nuevo, y serían dos órdenes.
  const [encolada, setEncolada] = useState(false);
  const captura = useRef<{ cliente_id: string; capturado_en: string } | null>(null);
  const idDescripcion = useId();
  const idFormulario = "form-falla";

  useEffect(() => {
    let vivo = true;
    listarComponentes()
      .then((lista) => {
        if (!vivo) return;
        setComponentes(lista);
        guardarCatalogo(usuario.empresa_id, lista);
      })
      .catch((e: unknown) => {
        if (!vivo) return;
        const guardado = catalogoGuardado(usuario.empresa_id);
        if (guardado !== null) setComponentes(guardado);
        else setErrorCatalogo(e instanceof ErrorApi ? e.message : "No se pudo cargar el catálogo de componentes.");
      });
    return () => {
      vivo = false;
    };
  }, [usuario.empresa_id]);

  /** Componente -> número de su orden abierta en este equipo. */
  const ocupados = useMemo(
    () => new Map((activo.ordenes_abiertas ?? []).map((o) => [o.componente_id, o.numero])),
    [activo.ordenes_abiertas],
  );

  const visibles = useMemo(() => {
    const t = filtro.trim().toLocaleLowerCase("es");
    return (componentes ?? []).filter((c) => t === "" || c.nombre.toLocaleLowerCase("es").includes(t));
  }, [componentes, filtro]);

  const elegido = componentes?.find((c) => c.id === componenteId) ?? null;

  function validar(): { horometro: number; temperatura: number | null } | null {
    const e: Record<string, string> = {};
    const n = leerHorometro(horometro);
    if (typeof n === "string") e.horometro = n;
    const t = leerTemperatura(temperatura);
    if (typeof t === "string") e.temperatura = t;
    if (componenteId === null) e.componente = "Elige el componente que falló, o «Otro (por identificar)».";
    const d = descripcion.trim();
    if (d.length < MIN_DESCRIPCION) e.descripcion = "Describe la falla en unas palabras (mínimo 5 letras).";
    setErrores(e);
    if (Object.keys(e).length > 0 || typeof n === "string" || typeof t === "string") return null;
    return { horometro: n, temperatura: t };
  }

  async function enviar(confirmado: boolean): Promise<void> {
    setAviso(null);
    setExistente(null);
    const datos = validar();
    if (datos === null || componenteId === null || elegido === null) return;
    if (!confirmado) {
      const motivo = motivoDeDuda(activo, datos.horometro);
      if (motivo !== null) {
        setDuda(motivo);
        return;
      }
    }
    setDuda(null);
    setEnCurso(true);
    captura.current ??= nuevaCaptura();
    try {
      const r = await enviarFalla(
        usuario,
        activo,
        {
          ...captura.current,
          componente_id: componenteId,
          horometro: datos.horometro,
          temperatura: datos.temperatura,
          codigo_error: codigoError.trim() === "" ? null : codigoError.trim(),
          descripcion: descripcion.trim(),
          alerta_id: alertaId,
        },
        elegido.nombre,
      );
      if (r.tipo === "encolado") {
        setEncolada(true);
      } else {
        setCreada(r.orden);
        alCrear?.(r.orden);
      }
      captura.current = null;
    } catch (fallo) {
      if (fallo instanceof ErrorApi && fallo.conflicto?.codigo === "orden_abierta_existente") {
        const c = fallo.conflicto;
        if (c.ordenId !== null && c.numero !== null) setExistente({ id: c.ordenId, numero: c.numero });
        // La falla no se creó; un reintento con el mismo identificador daría lo mismo.
        captura.current = null;
      }
      setAviso({
        tipo: "error",
        texto: fallo instanceof ErrorApi ? fallo.message : "No se pudo reportar la falla. Vuelve a intentarlo.",
      });
    } finally {
      setEnCurso(false);
    }
  }

  if (encolada) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="flex gap-2 rounded-[var(--radius-control)] border-2 border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 text-estado-aviso" />
          <span>
            <strong className="font-semibold">Sin conexión: la falla quedó guardada en este teléfono</strong> y se
            enviará sola al volver la red. Todavía no tiene número de orden. No borres los datos del navegador
            hasta que veas «Enviado».
          </span>
        </p>
        <Boton
          tipo="button"
          variante="secundario"
          onClick={() => {
            setEncolada(false);
            setComponenteId(null);
            setHorometro("");
            setTemperatura("");
            setCodigoError("");
            setDescripcion("");
          }}
        >
          Reportar otra falla
        </Boton>
      </div>
    );
  }

  if (creada !== null) {
    return (
      <div role="status" className="flex flex-col gap-4">
        <p className="flex gap-2 rounded-[var(--radius-control)] border border-estado-ok bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoHecho className="mt-0.5 text-estado-ok" />
          <span>
            Falla reportada: se abrió la orden <strong className="font-semibold">{numeroOrden(creada.numero)}</strong> para{" "}
            {creada.componente_nombre.toLowerCase()}. El taller la verá en su bandeja.
            {creada.requiere_revision
              ? " El horómetro no cuadraba con el historial: un supervisor tendrá que confirmarlo."
              : ""}
          </span>
        </p>
        <Link
          href={`/ordenes/${creada.id}`}
          className="inline-flex h-12 items-center justify-center rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-5 text-[0.9375rem] font-semibold text-texto transition-colors hover:border-accion hover:text-accion"
        >
          Abrir {numeroOrden(creada.numero)}
        </Link>
      </div>
    );
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
      className="flex flex-col gap-4"
    >
      <fieldset aria-describedby={errores.componente !== undefined ? "falla-componente-error" : undefined}>
        <legend className="pb-2 text-[0.8125rem] font-medium text-texto">
          ¿Qué componente falló? <span className="font-normal text-texto-tenue">obligatorio</span>
        </legend>
        {componentes === null ? (
          errorCatalogo !== null ? (
            <p className="text-[0.9375rem] text-error">{errorCatalogo}</p>
          ) : (
            <p className="text-[0.9375rem] text-texto-suave">Cargando el catálogo…</p>
          )
        ) : componentes.length === 0 ? (
          // Sin catálogo no hay orden posible: se dice qué falta y quién lo resuelve.
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            El catálogo de componentes de tu empresa está vacío, y una falla siempre se asigna a un
            componente.{" "}
            {usuario.rol === "administrador" ? (
              <Link href="/componentes" className="font-semibold text-accion underline underline-offset-2">
                Cárgalo en Equipos → Componentes
              </Link>
            ) : (
              "Pide al administrador de tu planta que lo cargue."
            )}
          </p>
        ) : (
          <>
            {componentes.length > UMBRAL_BUSCADOR ? (
              <div className="pb-2">
                <label htmlFor="falla-buscar" className="sr-only">
                  Buscar componente
                </label>
                <input
                  id="falla-buscar"
                  type="search"
                  value={filtro}
                  onChange={(e) => setFiltro(e.target.value)}
                  placeholder="Buscar componente"
                  className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
                />
              </div>
            ) : null}
            <div className="grid gap-2 sm:grid-cols-2">
              {visibles.map((c) => {
                const numero = ocupados.get(c.id);
                const ocupado = numero !== undefined;
                const marcado = componenteId === c.id;
                return (
                  <label
                    key={c.id}
                    className={[
                      "relative flex min-h-12 items-center gap-2 rounded-[var(--radius-control)] border px-3 py-2 text-[0.9375rem] font-medium transition-colors",
                      "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                      ocupado
                        ? "cursor-not-allowed border-borde-fuerte bg-superficie-alterna text-texto-tenue"
                        : marcado
                          ? "cursor-pointer border-2 border-accion bg-[var(--accion-halo)] text-accion"
                          : "cursor-pointer border-borde-fuerte bg-superficie text-texto hover:border-accion",
                    ].join(" ")}
                  >
                    <input
                      type="radio"
                      name="componente"
                      value={c.id}
                      checked={marcado}
                      disabled={ocupado || enCurso}
                      onChange={() => {
                        setComponenteId(c.id);
                        setErrores((previos) => {
                          const resto = { ...previos };
                          delete resto.componente;
                          return resto;
                        });
                      }}
                      className="sr-only"
                    />
                    {marcado ? <IconoHecho className="h-4 w-4" /> : null}
                    <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{c.nombre}</span>
                    {ocupado ? (
                      <span className="shrink-0 text-[0.8125rem] font-normal">
                        {numeroOrden(numero)} abierta
                      </span>
                    ) : null}
                  </label>
                );
              })}
              {visibles.length === 0 ? (
                <p className="text-[0.9375rem] text-texto-suave">Ningún componente coincide con «{filtro}».</p>
              ) : null}
            </div>
          </>
        )}
        <p id="falla-componente-error" aria-live="polite" className="min-h-6 pt-1 text-[0.8125rem] leading-5 text-error">
          {errores.componente ?? ""}
        </p>
      </fieldset>

      <Campo
        id="falla-horometro"
        etiqueta="Horas que marca el horómetro"
        nombre="horometro"
        valor={horometro}
        onCambio={(v) => {
          setHorometro(v);
          setDuda(null);
        }}
        error={errores.horometro}
        modoTeclado="numeric"
        ayuda={ultima}
        maxLength={9}
        autoComplete="off"
        requerido
        grande
        deshabilitado={enCurso}
      />

      <div className="grid gap-x-4 sm:grid-cols-2">
        <Campo
          id="falla-temperatura"
          etiqueta="Temperatura (°C)"
          nombre="temperatura"
          valor={temperatura}
          onCambio={setTemperatura}
          error={errores.temperatura}
          modoTeclado="text"
          maxLength={7}
          autoComplete="off"
          deshabilitado={enCurso}
        />
        <Campo
          id="falla-codigo"
          etiqueta="Código de error del equipo"
          nombre="codigo_error"
          valor={codigoError}
          onCambio={setCodigoError}
          maxLength={50}
          autoComplete="off"
          deshabilitado={enCurso}
        />
      </div>

      <div>
        <label htmlFor={idDescripcion} className="flex items-baseline justify-between pb-1.5 text-[0.8125rem] font-medium text-texto">
          <span>
            Qué pasó <span className="font-normal text-texto-tenue">obligatorio</span>
          </span>
          <span className="font-normal text-texto-tenue" aria-hidden="true">
            {descripcion.length}/{MAX_DESCRIPCION}
          </span>
        </label>
        <p id={`${idDescripcion}-ayuda`} className="-mt-0.5 pb-1.5 text-[0.8125rem] leading-5 text-texto-suave">
          Queda para siempre en la orden: no escribas datos personales.
        </p>
        <textarea
          id={idDescripcion}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          maxLength={MAX_DESCRIPCION}
          rows={3}
          disabled={enCurso}
          aria-invalid={errores.descripcion !== undefined}
          aria-describedby={`${idDescripcion}-ayuda ${idDescripcion}-error`}
          placeholder="Por ejemplo: se detuvo por sobrecalentamiento al arrancar"
          className={[
            "block w-full resize-y rounded-[var(--radius-control)] border bg-superficie px-3 py-2.5 text-[1rem] leading-6 text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)] disabled:bg-superficie-alterna",
            errores.descripcion !== undefined ? "border-error" : "border-borde-fuerte",
          ].join(" ")}
        />
        <p id={`${idDescripcion}-error`} aria-live="polite" className="min-h-6 pt-1 text-[0.8125rem] leading-5 text-error">
          {errores.descripcion ?? ""}
        </p>
      </div>

      {duda !== null ? (
        <div role="alert" className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie-alterna p-3">
          <p className="flex gap-2 text-[0.9375rem] leading-6 text-texto">
            <IconoAviso className="mt-0.5 text-estado-aviso" />
            <span>{duda}</span>
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Boton tipo="button" variante="secundario" onClick={() => setDuda(null)}>
              Corregir
            </Boton>
            <Boton tipo="button" onClick={() => void enviar(true)} enCurso={enCurso} textoEnCurso="Enviando…">
              Reportar igualmente
            </Boton>
          </div>
        </div>
      ) : (
        <Boton form={idFormulario} anchoCompleto enCurso={enCurso} textoEnCurso="Enviando…" deshabilitado={componenteId === null}>
          {elegido === null ? "Elige el componente" : `Reportar falla: ${elegido.nombre.toLowerCase()}`}
        </Boton>
      )}

      <AvisoEnvio aviso={aviso} />
      {existente !== null ? (
        <Link href={`/ordenes/${existente.id}`} className="font-semibold text-accion underline underline-offset-2">
          Abrir {numeroOrden(existente.numero)}
        </Link>
      ) : null}
    </form>
  );
}
