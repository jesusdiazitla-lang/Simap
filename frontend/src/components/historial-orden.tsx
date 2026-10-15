/**
 * Línea de tiempo de una orden: quién, con qué rol, cuándo y qué (RF-14, RNF-06; 06-fase3, 9.3).
 *
 * Es la evidencia visible de la trazabilidad: cada paso con el nombre de quien lo dio —aunque hoy
 * esté dado de baja— y el rol **con el que actuó entonces**. Lo que el historial guarda en sus
 * datos se muestra también: el trabajo que se rechazó y los valores que cambió una corrección. No
 * se borra nada, así que la pantalla tampoco esconde nada.
 */

import { etiquetaDeRol, type Rol } from "@/lib/auth";
import { fechaHora, hace } from "@/lib/formato";
import {
  duracion,
  ETIQUETA_ESTADO_ORDEN,
  ETIQUETA_INTERVENCION,
  type Evento,
  type TipoIntervencion,
} from "@/lib/ordenes";

/** Nombres legibles de los campos que una edición o corrección puede cambiar. */
const CAMPO: Readonly<Record<string, string>> = {
  descripcion: "Descripción",
  trabajo_realizado: "Trabajo realizado",
  codigo_error: "Código de error",
  temperatura: "Temperatura",
  tipo_intervencion: "Tipo de intervención",
  requiere_revision: "Horómetro por confirmar",
  componente_id: "Componente",
};

function titulo(e: Evento): string {
  if (e.tipo === "creada") return "Falla reportada";
  if (e.tipo === "correccion") return "Corrección administrativa";
  if (e.tipo === "nota") return "Nota";
  if (e.estado_anterior === "reparada" && e.estado_nuevo === "en_taller") return "Cierre rechazado: vuelve al taller";
  if (e.estado_nuevo === "en_taller") return "Llevada al taller";
  if (e.estado_nuevo === "reparada") return "Marcada como reparada";
  if (e.estado_nuevo === "cerrada") return "Cierre autorizado: sale del taller";
  if (e.estado_nuevo === "cancelada") return "Orden cancelada";
  return e.estado_nuevo !== null ? ETIQUETA_ESTADO_ORDEN[e.estado_nuevo] : "Cambio";
}

function texto(valor: unknown): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (typeof valor === "boolean") return valor ? "Sí" : "No";
  if (typeof valor === "string" && valor in ETIQUETA_INTERVENCION) {
    return ETIQUETA_INTERVENCION[valor as TipoIntervencion];
  }
  return String(valor);
}

function Detalle({ e }: { readonly e: Evento }) {
  const datos = e.datos ?? {};
  const cambios = datos.cambios as Record<string, { antes: unknown; despues: unknown }> | undefined;
  const rechazado = datos.trabajo_rechazado as
    | { trabajo_realizado?: string; tipo_intervencion?: string }
    | undefined;
  const tipo = datos.tipo_intervencion as TipoIntervencion | undefined;
  const minutos = datos.tiempo_fuera_servicio_min as number | undefined;
  return (
    <>
      {tipo !== undefined && e.estado_nuevo === "reparada" ? (
        <p className="text-[0.875rem] text-texto-suave">Intervención: {ETIQUETA_INTERVENCION[tipo]}</p>
      ) : null}
      {minutos !== undefined ? (
        <p className="text-[0.875rem] text-texto-suave">Tiempo fuera de servicio: {duracion(minutos)}</p>
      ) : null}
      {rechazado !== undefined ? (
        <div className="mt-1 rounded-[var(--radius-control)] border border-borde bg-superficie-alterna px-3 py-2">
          <p className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">Trabajo rechazado</p>
          <p className="text-[0.875rem] leading-5 text-texto [overflow-wrap:anywhere]">
            {rechazado.trabajo_realizado ?? "—"}
          </p>
          {rechazado.tipo_intervencion !== undefined ? (
            <p className="text-[0.8125rem] text-texto-suave">{texto(rechazado.tipo_intervencion)}</p>
          ) : null}
        </div>
      ) : null}
      {cambios !== undefined ? (
        <dl className="mt-1 flex flex-col gap-1 text-[0.875rem]">
          {Object.entries(cambios).map(([campo, { antes, despues }]) => (
            <div key={campo} className="[overflow-wrap:anywhere]">
              <dt className="inline font-medium text-texto">{CAMPO[campo] ?? campo}: </dt>
              <dd className="inline text-texto-suave">
                {/* El nombre del componente no viaja en el evento: se dice que cambió, sin el id. */}
                {campo === "componente_id" ? "cambiado" : `${texto(antes)} → ${texto(despues)}`}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </>
  );
}

export function HistorialOrden({ eventos }: { readonly eventos: readonly Evento[] }) {
  return (
    <ol className="flex flex-col">
      {eventos.map((e, i) => (
        <li key={e.id} className="relative flex gap-3 pb-5 last:pb-0">
          {/* La guía vertical une los pasos; el punto es neutro: el estado lo dice la palabra. */}
          {i < eventos.length - 1 ? (
            <span aria-hidden="true" className="absolute left-[5px] top-4 h-full w-px bg-borde" />
          ) : null}
          <span aria-hidden="true" className="relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-[3px] border-2 border-borde-fuerte bg-superficie" />
          <div className="min-w-0 flex-1">
            <p className="text-[0.9375rem] font-semibold leading-6 text-texto">{titulo(e)}</p>
            <p className="text-[0.8125rem] leading-5 text-texto-suave">
              <span className="font-medium text-texto">{e.usuario.nombre}</span>
              {e.usuario.activo ? null : <span className="text-texto-tenue"> (dado de baja)</span>}
              {" · "}
              {etiquetaDeRol(e.rol_al_momento as Rol)}
              {" · "}
              <time dateTime={e.creado_en}>{fechaHora(e.creado_en)}</time>
              <span className="text-texto-tenue"> · {hace(e.creado_en)}</span>
            </p>
            {e.nota !== null ? (
              <p className="pt-1 text-[0.9375rem] leading-6 text-texto [overflow-wrap:anywhere]">{e.nota}</p>
            ) : null}
            <Detalle e={e} />
          </div>
        </li>
      ))}
    </ol>
  );
}
