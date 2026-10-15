"use client";

/**
 * Lo que se puede hacer con una orden, según el rol y el estado (RF-13; 06-fase3, 9.3 y 11.1).
 *
 * Solo aparece lo que el rol y el estado permiten. Ocultar un botón es comodidad: la seguridad la
 * impone el servidor, que comprueba el rol en cada ruta y el estado en cada UPDATE.
 *
 * - **Autorizar el cierre** no se hace de un toque: antes se muestra lo que se va a firmar (trabajo,
 *   técnico, tipo de intervención y tiempo fuera de servicio), porque tiene consecuencias para el
 *   modelo de la fase 4.
 * - **Sin conexión**, los botones se deshabilitan y lo dicen: una transición encolada se aplicaría
 *   sobre un estado que quizá ya cambió (decisión 6).
 * - **Si otra persona se adelantó** (409), la pantalla recarga la orden y dice qué pasó, en lugar de
 *   un error genérico.
 * - Un solo botón azul relleno a la vez: el de la acción que toca ahora.
 */

import { useEffect, useId, useState, useSyncExternalStore, type ReactNode } from "react";

import { Boton } from "@/components/boton";
import { IconoAviso, IconoSinRed } from "@/components/iconos";
import { ErrorApi } from "@/lib/api";
import { listarComponentes, type Componente } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import {
  agregarNota,
  autorizarCierre,
  AYUDA_INTERVENCION,
  cancelarOrden,
  confirmarHorometro,
  corregirOrden,
  duracion,
  editarOrden,
  estaAbierta,
  ETIQUETA_INTERVENCION,
  llevarAlTaller,
  marcarReparada,
  rechazarCierre,
  TIPOS_INTERVENCION,
  type OrdenDetalle,
  type TipoIntervencion,
} from "@/lib/ordenes";

type Accion = (orden: OrdenDetalle) => Promise<OrdenDetalle>;

function suscribirRed(avisar: () => void): () => void {
  window.addEventListener("online", avisar);
  window.addEventListener("offline", avisar);
  return () => {
    window.removeEventListener("online", avisar);
    window.removeEventListener("offline", avisar);
  };
}

function useEnLinea(): boolean {
  return useSyncExternalStore(suscribirRed, () => navigator.onLine, () => true);
}

/** Minutos desde la falla hasta ahora: lo que marcará el cierre si se autoriza en este momento. */
function minutosHastaAhora(fechaFalla: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(fechaFalla).getTime()) / 60_000));
}

export function AccionesOrden({
  orden,
  usuario,
  alCambiar,
  alConflicto,
}: {
  readonly orden: OrdenDetalle;
  readonly usuario: Usuario;
  /** La acción salió bien: la pantalla pinta la orden devuelta. */
  readonly alCambiar: (orden: OrdenDetalle) => void;
  /** Otra persona se adelantó: la pantalla recarga y muestra este mensaje. */
  readonly alConflicto: (mensaje: string) => void;
}) {
  const enLinea = useEnLinea();
  const [enCurso, setEnCurso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);

  const rol = usuario.rol;
  const supervisa = rol === "supervisor" || rol === "administrador";
  const abierta = estaAbierta(orden.estado);

  async function ejecutar(nombre: string, accion: Accion): Promise<void> {
    setEnCurso(nombre);
    setError(null);
    try {
      alCambiar(await accion(orden));
      setAbierto(null);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409) {
        alConflicto(e.message);
        setAbierto(null);
      } else {
        setError(e instanceof ErrorApi ? e.message : "No se pudo completar la acción.");
      }
    } finally {
      setEnCurso(null);
    }
  }

  const bloques: ReactNode[] = [];

  if (orden.requiere_revision && supervisa && (abierta || rol === "administrador")) {
    bloques.push(
      <Bloque key="horometro" titulo="Horómetro por confirmar">
        <p className="text-[0.9375rem] leading-6 text-texto-suave">
          {orden.motivo_revision} Mientras no se confirme, esta falla no cuenta para el cálculo de riesgo.
          {abierta ? "" : " La orden está cerrada: confirmarlo queda como corrección en el historial."}
        </p>
        <Boton
          tipo="button"
          variante="secundario"
          deshabilitado={!enLinea}
          enCurso={enCurso === "horometro"}
          onClick={() => void ejecutar("horometro", (o) => confirmarHorometro(o.id))}
        >
          El horómetro es correcto
        </Boton>
      </Bloque>,
    );
  }

  if (orden.estado === "reportada" && (supervisa || rol === "tecnico_taller")) {
    bloques.push(
      <Bloque key="taller" titulo="Siguiente paso">
        <p className="text-[0.9375rem] leading-6 text-texto-suave">
          El equipo entra al taller. Queda anotado quién lo llevó y cuándo.
        </p>
        <Boton
          tipo="button"
          deshabilitado={!enLinea}
          enCurso={enCurso === "taller"}
          textoEnCurso="Un momento…"
          onClick={() => void ejecutar("taller", (o) => llevarAlTaller(o.id))}
        >
          Llevar al taller
        </Boton>
      </Bloque>,
    );
  }

  if (orden.estado === "en_taller" && rol === "tecnico_taller") {
    bloques.push(
      <Reparar
        key="reparar"
        enLinea={enLinea}
        enCurso={enCurso === "reparar"}
        alEnviar={(trabajo, tipo) => void ejecutar("reparar", (o) => marcarReparada(o.id, trabajo, tipo))}
      />,
    );
  }

  if (orden.estado === "reparada" && supervisa) {
    bloques.push(
      <Autorizar
        key="autorizar"
        orden={orden}
        enLinea={enLinea}
        enCurso={enCurso}
        abierto={abierto}
        setAbierto={setAbierto}
        alAutorizar={(nota) => void ejecutar("cerrar", (o) => autorizarCierre(o.id, nota))}
        alRechazar={(nota) => void ejecutar("rechazar", (o) => rechazarCierre(o.id, nota))}
      />,
    );
  }

  if (abierta && supervisa) {
    bloques.push(
      <Editar
        key="editar"
        orden={orden}
        enLinea={enLinea}
        enCurso={enCurso === "editar"}
        abierto={abierto === "editar"}
        alAbrir={() => setAbierto(abierto === "editar" ? null : "editar")}
        alGuardar={(cambios) => void ejecutar("editar", (o) => editarOrden(o.id, cambios))}
      />,
      <ConMotivo
        key="cancelar"
        titulo="Cancelar la orden"
        explicacion="Para una falla reportada por error o duplicada. No se borra: queda en el historial con el motivo, y el componente queda libre para otra orden."
        etiqueta="Motivo de la cancelación"
        boton="Cancelar la orden"
        minimo={10}
        enLinea={enLinea}
        enCurso={enCurso === "cancelar"}
        abierto={abierto === "cancelar"}
        alAbrir={() => setAbierto(abierto === "cancelar" ? null : "cancelar")}
        alEnviar={(motivo) => void ejecutar("cancelar", (o) => cancelarOrden(o.id, motivo))}
      />,
    );
  }

  if (orden.estado === "cerrada" && rol === "administrador") {
    bloques.push(
      <Corregir
        key="corregir"
        orden={orden}
        enLinea={enLinea}
        enCurso={enCurso === "corregir"}
        abierto={abierto === "corregir"}
        alAbrir={() => setAbierto(abierto === "corregir" ? null : "corregir")}
        alEnviar={(c) => void ejecutar("corregir", (o) => corregirOrden(o.id, c))}
      />,
    );
  }

  if (supervisa || rol === "tecnico_taller") {
    bloques.push(
      <ConMotivo
        key="nota"
        titulo="Añadir una nota"
        explicacion="Queda en el historial con tu nombre, también con la orden cerrada. No escribas datos personales: no se puede borrar."
        etiqueta="Nota"
        boton="Añadir nota"
        minimo={1}
        enLinea={enLinea}
        enCurso={enCurso === "nota"}
        abierto={abierto === "nota"}
        alAbrir={() => setAbierto(abierto === "nota" ? null : "nota")}
        alEnviar={(nota) => void ejecutar("nota", (o) => agregarNota(o.id, nota))}
        secundaria
      />,
    );
  }

  if (bloques.length === 0) {
    return (
      <p className="text-[0.9375rem] leading-6 text-texto-suave">
        {rol === "gerente"
          ? "Consulta: el gerente ve las órdenes pero no las mueve."
          : abierta
            ? "Esta orden no tiene acciones para tu rol en este estado."
            : "Orden terminada. No admite más cambios."}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {!enLinea ? (
        <p role="status" className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoSinRed className="mt-0.5 text-estado-aviso" />
          <span>
            Sin conexión. Los cambios de una orden necesitan red: dependen de su estado actual, que
            puede haber cambiado. Vuelve a intentarlo cuando haya cobertura.
          </span>
        </p>
      ) : null}
      <div className="flex flex-col divide-y divide-borde">{bloques}</div>
      {error !== null ? (
        <p role="alert" className="text-[0.9375rem] text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Bloque({ titulo, children }: { readonly titulo: string; readonly children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
      <h3 className="text-[0.9375rem] font-semibold text-texto">{titulo}</h3>
      {children}
    </section>
  );
}

function AreaTexto({
  id,
  etiqueta,
  valor,
  onCambio,
  maximo,
  filas = 3,
  ayuda,
}: {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (v: string) => void;
  readonly maximo: number;
  readonly filas?: number;
  readonly ayuda?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-baseline justify-between pb-1.5 text-[0.8125rem] font-medium text-texto">
        <span>{etiqueta}</span>
        <span className="font-normal text-texto-tenue" aria-hidden="true">
          {valor.length}/{maximo}
        </span>
      </label>
      {ayuda !== undefined ? <p className="-mt-0.5 pb-1.5 text-[0.8125rem] leading-5 text-texto-suave">{ayuda}</p> : null}
      <textarea
        id={id}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        maxLength={maximo}
        rows={filas}
        className="block w-full resize-y rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 py-2.5 text-[1rem] leading-6 text-texto placeholder:text-texto-tenue focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
      />
    </div>
  );
}

function TiposIntervencion({
  valor,
  onCambio,
  nombre,
}: {
  readonly valor: TipoIntervencion | null;
  readonly onCambio: (t: TipoIntervencion) => void;
  readonly nombre: string;
}) {
  return (
    <fieldset>
      <legend className="pb-2 text-[0.8125rem] font-medium text-texto">Tipo de intervención</legend>
      <div className="grid gap-2 sm:grid-cols-3">
        {TIPOS_INTERVENCION.map((t) => {
          const marcado = valor === t;
          return (
            <label
              key={t}
              className={[
                "flex cursor-pointer flex-col gap-0.5 rounded-[var(--radius-control)] border px-3 py-2.5 transition-colors",
                "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                marcado ? "border-2 border-accion bg-[var(--accion-halo)]" : "border-borde-fuerte bg-superficie hover:border-accion",
              ].join(" ")}
            >
              <input type="radio" name={nombre} value={t} checked={marcado} onChange={() => onCambio(t)} className="sr-only" />
              <span className={["text-[0.9375rem] font-semibold", marcado ? "text-accion" : "text-texto"].join(" ")}>
                {ETIQUETA_INTERVENCION[t]}
              </span>
              <span className="text-[0.8125rem] leading-5 text-texto-suave">{AYUDA_INTERVENCION[t]}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function Reparar({
  enLinea,
  enCurso,
  alEnviar,
}: {
  readonly enLinea: boolean;
  readonly enCurso: boolean;
  readonly alEnviar: (trabajo: string, tipo: TipoIntervencion) => void;
}) {
  const id = useId();
  const [trabajo, setTrabajo] = useState("");
  const [tipo, setTipo] = useState<TipoIntervencion | null>(null);
  const valido = trabajo.trim().length >= 10 && tipo !== null;
  return (
    <Bloque titulo="Registrar la reparación">
      <AreaTexto
        id={`${id}-trabajo`}
        etiqueta="Trabajo realizado"
        ayuda="Qué se hizo, con suficiente detalle para que quien autorice lo entienda (mínimo 10 letras)."
        valor={trabajo}
        onCambio={setTrabajo}
        maximo={2000}
        filas={4}
      />
      <TiposIntervencion valor={tipo} onCambio={setTipo} nombre={`${id}-tipo`} />
      <Boton
        tipo="button"
        deshabilitado={!valido || !enLinea}
        enCurso={enCurso}
        textoEnCurso="Guardando…"
        onClick={() => tipo !== null && alEnviar(trabajo.trim(), tipo)}
      >
        {valido ? "Marcar como reparada" : "Describe el trabajo y elige el tipo"}
      </Boton>
    </Bloque>
  );
}

function Autorizar({
  orden,
  enLinea,
  enCurso,
  abierto,
  setAbierto,
  alAutorizar,
  alRechazar,
}: {
  readonly orden: OrdenDetalle;
  readonly enLinea: boolean;
  readonly enCurso: string | null;
  readonly abierto: string | null;
  readonly setAbierto: (v: string | null) => void;
  readonly alAutorizar: (nota: string | null) => void;
  readonly alRechazar: (nota: string) => void;
}) {
  const id = useId();
  const [nota, setNota] = useState("");
  const [motivo, setMotivo] = useState("");
  const [minutos, setMinutos] = useState(() => minutosHastaAhora(orden.fecha_falla));
  // El tiempo fuera de servicio sigue corriendo mientras se lee el resumen.
  useEffect(() => {
    const t = setInterval(() => setMinutos(minutosHastaAhora(orden.fecha_falla)), 60_000);
    return () => clearInterval(t);
  }, [orden.fecha_falla]);

  return (
    <Bloque titulo="Autorizar la salida del taller">
      {abierto === "autorizar" ? (
        <div role="region" aria-label="Lo que vas a firmar" className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna p-3">
          <p className="text-[0.8125rem] font-medium text-texto">Vas a firmar:</p>
          <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-[0.9375rem]">
            <dt className="text-texto-suave">Trabajo</dt>
            <dd className="text-texto [overflow-wrap:anywhere]">{orden.trabajo_realizado}</dd>
            <dt className="text-texto-suave">Técnico</dt>
            <dd className="text-texto">{orden.reparado_por?.nombre ?? "—"}</dd>
            <dt className="text-texto-suave">Intervención</dt>
            <dd className="text-texto">
              {orden.tipo_intervencion !== null ? ETIQUETA_INTERVENCION[orden.tipo_intervencion] : "—"}
              {orden.tipo_intervencion !== null ? (
                <span className="block text-[0.8125rem] text-texto-suave">{AYUDA_INTERVENCION[orden.tipo_intervencion]}</span>
              ) : null}
            </dd>
            <dt className="text-texto-suave">Fuera de servicio</dt>
            <dd className="text-texto">{duracion(minutos)}, desde la falla hasta ahora</dd>
          </dl>
          <AreaTexto id={`${id}-nota`} etiqueta="Nota (opcional)" valor={nota} onCambio={setNota} maximo={1000} filas={2} />
          <div className="grid gap-2 sm:grid-cols-2">
            <Boton tipo="button" variante="secundario" onClick={() => setAbierto(null)}>
              Volver
            </Boton>
            <Boton
              tipo="button"
              deshabilitado={!enLinea}
              enCurso={enCurso === "cerrar"}
              textoEnCurso="Autorizando…"
              onClick={() => alAutorizar(nota.trim() === "" ? null : nota.trim())}
            >
              Autorizar y cerrar
            </Boton>
          </div>
        </div>
      ) : abierto === "rechazar" ? (
        <div className="flex flex-col gap-3">
          <AreaTexto
            id={`${id}-motivo`}
            etiqueta="Por qué vuelve al taller"
            ayuda="El técnico la verá en el historial. Lo que escribió se conserva (mínimo 10 letras)."
            valor={motivo}
            onCambio={setMotivo}
            maximo={1000}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <Boton tipo="button" variante="secundario" onClick={() => setAbierto(null)}>
              Volver
            </Boton>
            <Boton
              tipo="button"
              variante="secundario"
              deshabilitado={motivo.trim().length < 10 || !enLinea}
              enCurso={enCurso === "rechazar"}
              textoEnCurso="Un momento…"
              onClick={() => alRechazar(motivo.trim())}
            >
              Devolver al taller
            </Boton>
          </div>
        </div>
      ) : (
        <>
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            El técnico la marcó como reparada. Revisa lo que hizo antes de autorizar: el tipo de
            intervención decide si el componente cuenta como nuevo para el cálculo de riesgo.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Boton tipo="button" deshabilitado={!enLinea} onClick={() => setAbierto("autorizar")}>
              Revisar y autorizar
            </Boton>
            <Boton tipo="button" variante="secundario" deshabilitado={!enLinea} onClick={() => setAbierto("rechazar")}>
              Rechazar el cierre
            </Boton>
          </div>
        </>
      )}
    </Bloque>
  );
}

function ConMotivo({
  titulo,
  explicacion,
  etiqueta,
  boton,
  minimo,
  enLinea,
  enCurso,
  abierto,
  alAbrir,
  alEnviar,
  secundaria = false,
}: {
  readonly titulo: string;
  readonly explicacion: string;
  readonly etiqueta: string;
  readonly boton: string;
  readonly minimo: number;
  readonly enLinea: boolean;
  readonly enCurso: boolean;
  readonly abierto: boolean;
  readonly alAbrir: () => void;
  readonly alEnviar: (texto: string) => void;
  readonly secundaria?: boolean;
}) {
  const id = useId();
  const [texto, setTexto] = useState("");
  if (!abierto) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0">
        <h3 className="text-[0.9375rem] font-semibold text-texto">{titulo}</h3>
        <Boton tipo="button" variante="secundario" deshabilitado={!enLinea} onClick={alAbrir}>
          {secundaria ? boton : `${boton}…`}
        </Boton>
      </section>
    );
  }
  return (
    <Bloque titulo={titulo}>
      <p className="text-[0.9375rem] leading-6 text-texto-suave">{explicacion}</p>
      <AreaTexto id={`${id}-texto`} etiqueta={etiqueta} valor={texto} onCambio={setTexto} maximo={1000} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Boton tipo="button" variante="secundario" onClick={alAbrir}>
          Volver
        </Boton>
        <Boton
          tipo="button"
          variante="secundario"
          deshabilitado={texto.trim().length < minimo || !enLinea}
          enCurso={enCurso}
          textoEnCurso="Un momento…"
          onClick={() => alEnviar(texto.trim())}
        >
          {boton}
        </Boton>
      </div>
    </Bloque>
  );
}

function Editar({
  orden,
  enLinea,
  enCurso,
  abierto,
  alAbrir,
  alGuardar,
}: {
  readonly orden: OrdenDetalle;
  readonly enLinea: boolean;
  readonly enCurso: boolean;
  readonly abierto: boolean;
  readonly alAbrir: () => void;
  readonly alGuardar: (cambios: { componente_id?: string; descripcion?: string; codigo_error?: string | null }) => void;
}) {
  const id = useId();
  const [componentes, setComponentes] = useState<readonly Componente[] | null>(null);
  const [componenteId, setComponenteId] = useState(orden.componente_id);
  const [descripcion, setDescripcion] = useState(orden.descripcion);
  const [codigo, setCodigo] = useState(orden.codigo_error ?? "");

  useEffect(() => {
    if (!abierto || componentes !== null) return;
    void listarComponentes().then(setComponentes).catch(() => setComponentes([]));
  }, [abierto, componentes]);

  if (!abierto) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0">
        <div>
          <h3 className="text-[0.9375rem] font-semibold text-texto">Corregir los datos de la falla</h3>
          <p className="text-[0.8125rem] text-texto-suave">Por ejemplo, el componente, si se reportó «por identificar».</p>
        </div>
        <Boton tipo="button" variante="secundario" deshabilitado={!enLinea} onClick={alAbrir}>
          Editar…
        </Boton>
      </section>
    );
  }

  const cambios = {
    ...(componenteId !== orden.componente_id ? { componente_id: componenteId } : {}),
    ...(descripcion.trim() !== orden.descripcion ? { descripcion: descripcion.trim() } : {}),
    ...(codigo.trim() !== (orden.codigo_error ?? "") ? { codigo_error: codigo.trim() === "" ? null : codigo.trim() } : {}),
  };
  const valido = Object.keys(cambios).length > 0 && descripcion.trim().length >= 5;

  return (
    <Bloque titulo="Corregir los datos de la falla">
      <div>
        <label htmlFor={`${id}-componente`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
          Componente
        </label>
        <select
          id={`${id}-componente`}
          value={componenteId}
          onChange={(e) => setComponenteId(e.target.value)}
          className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
        >
          <option value={orden.componente_id}>{orden.componente_nombre}</option>
          {(componentes ?? [])
            .filter((c) => c.id !== orden.componente_id)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
        </select>
      </div>
      <AreaTexto id={`${id}-descripcion`} etiqueta="Qué pasó" valor={descripcion} onCambio={setDescripcion} maximo={1000} />
      <div>
        <label htmlFor={`${id}-codigo`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
          Código de error
        </label>
        <input
          id={`${id}-codigo`}
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          maxLength={50}
          className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Boton tipo="button" variante="secundario" onClick={alAbrir}>
          Volver
        </Boton>
        <Boton tipo="button" variante="secundario" deshabilitado={!valido || !enLinea} enCurso={enCurso} textoEnCurso="Guardando…" onClick={() => alGuardar(cambios)}>
          Guardar cambios
        </Boton>
      </div>
    </Bloque>
  );
}

function Corregir({
  orden,
  enLinea,
  enCurso,
  abierto,
  alAbrir,
  alEnviar,
}: {
  readonly orden: OrdenDetalle;
  readonly enLinea: boolean;
  readonly enCurso: boolean;
  readonly abierto: boolean;
  readonly alAbrir: () => void;
  readonly alEnviar: (c: { nota: string; tipo_intervencion?: TipoIntervencion; trabajo_realizado?: string; codigo_error?: string | null }) => void;
}) {
  const id = useId();
  const [tipo, setTipo] = useState<TipoIntervencion | null>(orden.tipo_intervencion);
  const [trabajo, setTrabajo] = useState(orden.trabajo_realizado ?? "");
  const [codigo, setCodigo] = useState(orden.codigo_error ?? "");
  const [nota, setNota] = useState("");

  if (!abierto) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0">
        <div>
          <h3 className="text-[0.9375rem] font-semibold text-texto">Corrección administrativa</h3>
          <p className="text-[0.8125rem] text-texto-suave">Para un error de digitación en una orden cerrada. Queda en el historial.</p>
        </div>
        <Boton tipo="button" variante="secundario" deshabilitado={!enLinea} onClick={alAbrir}>
          Corregir…
        </Boton>
      </section>
    );
  }

  const cambios = {
    ...(tipo !== null && tipo !== orden.tipo_intervencion ? { tipo_intervencion: tipo } : {}),
    ...(trabajo.trim() !== (orden.trabajo_realizado ?? "") && trabajo.trim().length >= 10 ? { trabajo_realizado: trabajo.trim() } : {}),
    ...(codigo.trim() !== (orden.codigo_error ?? "") ? { codigo_error: codigo.trim() === "" ? null : codigo.trim() } : {}),
  };
  const valido = Object.keys(cambios).length > 0 && nota.trim().length >= 10;

  return (
    <Bloque titulo="Corrección administrativa">
      <p className="flex gap-2 text-[0.9375rem] leading-6 text-texto-suave">
        <IconoAviso className="mt-0.5 shrink-0 text-estado-aviso" />
        <span>
          Cambiar el tipo de intervención cambia cómo cuenta esta falla para el cálculo de riesgo. El
          estado, las fechas y los responsables no se corrigen.
        </span>
      </p>
      <TiposIntervencion valor={tipo} onCambio={setTipo} nombre={`${id}-tipo`} />
      <AreaTexto id={`${id}-trabajo`} etiqueta="Trabajo realizado" valor={trabajo} onCambio={setTrabajo} maximo={2000} />
      <div>
        <label htmlFor={`${id}-codigo`} className="block pb-1.5 text-[0.8125rem] font-medium text-texto">
          Código de error
        </label>
        <input
          id={`${id}-codigo`}
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          maxLength={50}
          className="h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
        />
      </div>
      <AreaTexto
        id={`${id}-nota`}
        etiqueta="Por qué se corrige"
        ayuda="Obligatorio (mínimo 10 letras). Queda junto a los valores anteriores en el historial."
        valor={nota}
        onCambio={setNota}
        maximo={1000}
        filas={2}
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <Boton tipo="button" variante="secundario" onClick={alAbrir}>
          Volver
        </Boton>
        <Boton tipo="button" variante="secundario" deshabilitado={!valido || !enLinea} enCurso={enCurso} textoEnCurso="Guardando…" onClick={() => alEnviar({ ...cambios, nota: nota.trim() })}>
          Guardar corrección
        </Boton>
      </div>
    </Bloque>
  );
}
