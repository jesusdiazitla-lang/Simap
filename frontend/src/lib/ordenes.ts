/**
 * Órdenes de trabajo (RF-11 a RF-16; 06-fase3-ordenes-de-trabajo.md). Tipos y llamadas a la API.
 *
 * Los tipos reflejan `backend/app/schemas/orden_trabajo.py`. Ninguna llamada envía la empresa,
 * quién actúa, el estado ni las horas: los fija el servidor, y si el cliente los enviara recibiría
 * un 422.
 */

import { ErrorApi, llamar } from "@/lib/api";
import type { Activo, Pagina } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import { encolar } from "@/lib/offline-queue";

export type EstadoOrden = "reportada" | "en_taller" | "reparada" | "cerrada" | "cancelada";
export type TipoIntervencion = "reemplazo" | "reparacion" | "ajuste";
export type FiltroOrdenes = "abiertas" | "cerradas" | "canceladas";

export const ETIQUETA_ESTADO_ORDEN: Readonly<Record<EstadoOrden, string>> = {
  reportada: "Reportada",
  en_taller: "En taller",
  reparada: "Reparada",
  cerrada: "Cerrada",
  cancelada: "Cancelada",
};

export const TIPOS_INTERVENCION: readonly TipoIntervencion[] = ["reemplazo", "reparacion", "ajuste"];

/** Con la consecuencia para el modelo dicha en la misma línea (decisión 4 de la fase). */
export const ETIQUETA_INTERVENCION: Readonly<Record<TipoIntervencion, string>> = {
  reemplazo: "Reemplazo",
  reparacion: "Reparación",
  ajuste: "Ajuste",
};

export const AYUDA_INTERVENCION: Readonly<Record<TipoIntervencion, string>> = {
  reemplazo: "Se cambió el componente por uno nuevo: su vida vuelve a empezar.",
  reparacion: "Se arregló el mismo componente: no cuenta como nuevo.",
  ajuste: "Se calibró, apretó o limpió: no cuenta como nuevo.",
};

/** OT-0001. La base guarda el entero; esto es solo cómo se lee. */
export function numeroOrden(numero: number): string {
  return `OT-${String(numero).padStart(4, "0")}`;
}

export interface Persona {
  readonly id: string;
  readonly nombre: string;
  /** `false` si hoy está dado de baja. Su nombre sigue en el historial (06-fase3, 5.2). */
  readonly activo: boolean;
}

export interface OrdenResumen {
  readonly id: string;
  readonly numero: number;
  readonly estado: EstadoOrden;
  readonly activo_id: string;
  readonly activo_nombre: string;
  readonly activo_codigo: string;
  readonly componente_id: string;
  readonly componente_nombre: string;
  readonly horometro_en_falla: number;
  readonly fecha_falla: string;
  readonly reportada_en: string;
  readonly requiere_revision: boolean;
  readonly tipo_intervencion: TipoIntervencion | null;
  readonly tiempo_fuera_servicio_min: number | null;
  /** Cambio planificado desde una alerta de riesgo (F4, 6.4), no una falla. */
  readonly es_predictiva: boolean;
  readonly alerta_sistema_id: string | null;
}

export type TipoEvento = "creada" | "transicion" | "nota" | "correccion";

export interface Evento {
  readonly id: string;
  readonly tipo: TipoEvento;
  readonly estado_anterior: EstadoOrden | null;
  readonly estado_nuevo: EstadoOrden | null;
  readonly usuario: Persona;
  readonly rol_al_momento: string;
  readonly nota: string | null;
  readonly datos: Record<string, unknown> | null;
  readonly creado_en: string;
}

export interface OrdenDetalle extends OrdenResumen {
  readonly cliente_id: string;
  readonly alerta_origen_id: string | null;
  readonly lectura_id: string | null;
  readonly horas_acumuladas_en_falla: number;
  readonly temperatura: string | number | null;
  readonly codigo_error: string | null;
  readonly descripcion: string;
  readonly trabajo_realizado: string | null;
  readonly motivo_cancelacion: string | null;
  readonly motivo_revision: string | null;
  readonly en_taller_en: string | null;
  readonly reparada_en: string | null;
  readonly fecha_salida_taller: string | null;
  readonly reportado_por: Persona;
  readonly reparado_por: Persona | null;
  readonly autorizado_por: Persona | null;
  readonly eventos: readonly Evento[];
}

export function estaAbierta(estado: EstadoOrden): boolean {
  return estado === "reportada" || estado === "en_taller" || estado === "reparada";
}

// --- Consulta ------------------------------------------------------------------------

export async function listarOrdenes(
  filtros: { estado?: FiltroOrdenes | null; activoId?: string | null; cursor?: string | null },
  signal?: AbortSignal,
): Promise<Pagina<OrdenResumen>> {
  const p = new URLSearchParams({ limite: "50" });
  if (filtros.estado) p.set("estado", filtros.estado);
  if (filtros.activoId) p.set("activo_id", filtros.activoId);
  if (filtros.cursor) p.set("cursor", filtros.cursor);
  // El servidor responde con ETag y `no-cache`: el navegador revalida solo con If-None-Match y,
  // si nada cambió, recibe un 304 que entrega la copia que ya tenía (06-fase3, 9.4).
  return llamar(`/ordenes?${p.toString()}`, { signal });
}

export async function obtenerOrden(id: string, signal?: AbortSignal): Promise<OrdenDetalle> {
  return llamar(`/ordenes/${encodeURIComponent(id)}`, { signal });
}

// --- Reporte de falla -----------------------------------------------------------------

export interface CapturaFalla {
  readonly cliente_id: string;
  readonly capturado_en: string;
  readonly componente_id: string;
  readonly horometro: number;
  readonly temperatura: number | null;
  readonly codigo_error: string | null;
  readonly descripcion: string;
  readonly alerta_id: string | null;
}

export type ResultadoFalla =
  | { readonly tipo: "enviado"; readonly estado: "creado" | "duplicado"; readonly orden: OrdenDetalle }
  | { readonly tipo: "encolado" };

export async function reportarFalla(
  activoId: string,
  captura: CapturaFalla,
): Promise<{ estado: "creado" | "duplicado"; orden: OrdenDetalle }> {
  return llamar(`/activos/${encodeURIComponent(activoId)}/fallas`, { method: "POST", cuerpo: captura });
}

/**
 * Envía la falla o, sin red, la deja en la cola del teléfono con el mismo `cliente_id` (06-fase3,
 * 9.5). Si el envío directo llegó y lo que se perdió fue la respuesta, la cola la reenviará y el
 * servidor contestará «duplicado»: nunca hay dos órdenes. Un rechazo del servidor (componente con
 * orden abierta, equipo de baja) no se encola: no entraría nunca, y quien está delante puede actuar.
 */
export async function enviarFalla(
  usuario: Usuario,
  activo: Activo,
  captura: CapturaFalla,
  componenteNombre: string,
): Promise<ResultadoFalla> {
  if (navigator.onLine) {
    try {
      const r = await reportarFalla(activo.id, captura);
      return { tipo: "enviado", estado: r.estado, orden: r.orden };
    } catch (error) {
      if (!(error instanceof ErrorApi && error.esFalloDeRed)) throw error;
    }
  }
  // La cola se sincroniza por `/campo/lotes`, que es del personal de campo (operario y supervisor,
  // 06-fase3, sección 8). Una falla que el administrador dejara en cola no entraría nunca: se le
  // dice ahora, mientras puede anotarla y reportarla con red.
  if (usuario.rol !== "supervisor") {
    throw new ErrorApi(
      0,
      "Sin conexión. El reporte de falla del administrador necesita red: anótala y repórtala al volver la cobertura.",
    );
  }
  await encolar({
    tipo: "falla",
    cliente_id: captura.cliente_id,
    activo_id: activo.id,
    equipo: activo.nombre,
    capturado_en: captura.capturado_en,
    falla: {
      componente_id: captura.componente_id,
      componente_nombre: componenteNombre,
      horometro: captura.horometro,
      temperatura: captura.temperatura,
      codigo_error: captura.codigo_error,
      descripcion: captura.descripcion,
      alerta_id: captura.alerta_id,
    },
    usuario_id: usuario.id,
    empresa_id: usuario.empresa_id,
  });
  return { tipo: "encolado" };
}

// --- Transiciones y demás acciones (06-fase3, sección 8) ----------------------------------

function accion(id: string, ruta: string, cuerpo?: unknown): Promise<OrdenDetalle> {
  return llamar(`/ordenes/${encodeURIComponent(id)}/${ruta}`, { method: "POST", cuerpo });
}

export const llevarAlTaller = (id: string) => accion(id, "en-taller");

export const marcarReparada = (id: string, trabajo_realizado: string, tipo_intervencion: TipoIntervencion) =>
  accion(id, "reparada", { trabajo_realizado, tipo_intervencion });

export const autorizarCierre = (id: string, nota: string | null) =>
  accion(id, "cerrar", nota === null ? undefined : { nota });

export const rechazarCierre = (id: string, nota: string) => accion(id, "rechazar-cierre", { nota });

export const cancelarOrden = (id: string, motivo: string) => accion(id, "cancelar", { motivo });

export const agregarNota = (id: string, nota: string) => accion(id, "notas", { nota });

export const confirmarHorometro = (id: string) => accion(id, "confirmar-horometro");

export interface CambiosOrden {
  readonly descripcion?: string;
  readonly codigo_error?: string | null;
  readonly componente_id?: string;
}

export async function editarOrden(id: string, cambios: CambiosOrden): Promise<OrdenDetalle> {
  return llamar(`/ordenes/${encodeURIComponent(id)}`, { method: "PATCH", cuerpo: cambios });
}

export interface Correccion {
  readonly nota: string;
  readonly descripcion?: string;
  readonly trabajo_realizado?: string;
  readonly codigo_error?: string | null;
  readonly tipo_intervencion?: TipoIntervencion;
}

export const corregirOrden = (id: string, correccion: Correccion) => accion(id, "correccion", correccion);

/** «2 h 05 min», «3 días 4 h». Para el tiempo fuera de servicio (RF-15). */
export function duracion(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  if (h < 48) return m === 0 ? `${h} h` : `${h} h ${String(m).padStart(2, "0")} min`;
  const d = Math.floor(h / 24);
  const resto = h % 24;
  return resto === 0 ? `${d} días` : `${d} días ${resto} h`;
}

/** El equipo falló antes de la intervención: la orden predictiva pasa a ser una falla (F4, 6.4). */
export function convertirEnFalla(
  id: string,
  datos: { readonly horometro: number; readonly fecha_falla: string },
): Promise<OrdenDetalle> {
  return llamar<OrdenDetalle>(`/ordenes/${id}/convertir-en-falla`, { method: "POST", cuerpo: datos });
}
