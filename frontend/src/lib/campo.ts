/**
 * Registro de campo: lecturas de horómetro y alertas (RF-08, RF-09). Tipos y llamadas a la API.
 *
 * El envío individual y el de la cola sin conexión usan el mismo `cliente_id`: lo genera el
 * teléfono **antes** del primer intento, y si ese intento se pierde por la red, la cola lo reenvía
 * con el mismo identificador. El servidor responde «duplicado» en vez de crear dos filas.
 */

import { llamar } from "@/lib/api";
import type { Pagina } from "@/lib/activos";

export const SINTOMAS = ["ruido", "vibracion", "calor", "olor", "fuga", "otro"] as const;
export type Sintoma = (typeof SINTOMAS)[number];

/** Se guardan sin tildes; se muestran con ellas. */
export const ETIQUETA_SINTOMA: Readonly<Record<Sintoma, string>> = {
  ruido: "Ruido",
  vibracion: "Vibración",
  calor: "Calor",
  olor: "Olor",
  fuga: "Fuga",
  otro: "Otro",
};

export type EstadoAlerta = "pendiente" | "revisada" | "descartada" | "convertida_en_orden";

export const ETIQUETA_ESTADO_ALERTA: Readonly<Record<EstadoAlerta, string>> = {
  pendiente: "Pendiente",
  revisada: "Revisada",
  descartada: "Descartada",
  convertida_en_orden: "En orden de trabajo",
};

export const MAX_NOTA = 500;

export interface Lectura {
  readonly id: string;
  readonly activo_id: string;
  readonly valor_horometro: number;
  readonly capturado_en: string;
  readonly fecha: string;
  readonly requiere_revision: boolean;
  readonly motivo_revision: string | null;
  readonly registrado_por: string;
  /** Si fue marcada: cómo se resolvió, o `null` mientras está pendiente. */
  readonly resolucion: Resolucion | null;
  readonly revisada_en: string | null;
}

export type Resolucion = "confirmada" | "descartada" | "reinicio";

/** Una lectura pendiente, con lo necesario para decidir sin abrir el equipo. */
export interface LecturaPorRevisar extends Lectura {
  readonly activo_nombre: string;
  readonly activo_codigo: string;
  readonly horometro_vigente: number;
}

export async function lecturasPorRevisar(signal?: AbortSignal): Promise<Pagina<LecturaPorRevisar>> {
  return llamar("/lecturas/por-revisar?limite=50", { signal });
}

export async function resolverLectura(id: string, resolucion: Resolucion): Promise<Lectura> {
  return llamar(`/lecturas/${encodeURIComponent(id)}`, { method: "PATCH", cuerpo: { resolucion } });
}

export interface Alerta {
  readonly id: string;
  readonly activo_id: string;
  readonly sintoma: Sintoma;
  readonly nota: string | null;
  readonly estado: EstadoAlerta;
  readonly capturado_en: string;
  readonly fecha: string;
  readonly reportado_por: string;
  readonly revisada_por: string | null;
  readonly revisada_en: string | null;
  /** Solo en la bandeja: el equipo, para no pedirlo aparte por cada fila. */
  readonly activo_nombre?: string | null;
  readonly activo_codigo?: string | null;
}

export interface CapturaLectura {
  readonly cliente_id: string;
  readonly capturado_en: string;
  readonly valor: number;
}

export interface CapturaAlerta {
  readonly cliente_id: string;
  readonly capturado_en: string;
  readonly sintoma: Sintoma;
  readonly nota: string | null;
}

export async function registrarLectura(
  activoId: string,
  captura: CapturaLectura,
): Promise<{ estado: "creado" | "duplicado"; lectura: Lectura }> {
  return llamar(`/activos/${encodeURIComponent(activoId)}/lecturas`, {
    method: "POST",
    cuerpo: captura,
  });
}

export async function reportarAlerta(
  activoId: string,
  captura: CapturaAlerta,
): Promise<{ estado: "creado" | "duplicado"; alerta: Alerta }> {
  return llamar(`/activos/${encodeURIComponent(activoId)}/alertas`, {
    method: "POST",
    cuerpo: captura,
  });
}

export async function historialLecturas(
  activoId: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<Pagina<Lectura>> {
  const c = cursor === null ? "" : `&cursor=${encodeURIComponent(cursor)}`;
  return llamar(`/activos/${encodeURIComponent(activoId)}/lecturas?limite=20${c}`, { signal });
}

export async function listarAlertas(
  filtros: { estado?: EstadoAlerta | null; activoId?: string | null; cursor?: string | null },
  signal?: AbortSignal,
): Promise<Pagina<Alerta>> {
  const p = new URLSearchParams({ limite: "50" });
  if (filtros.estado) p.set("estado", filtros.estado);
  if (filtros.activoId) p.set("activo_id", filtros.activoId);
  if (filtros.cursor) p.set("cursor", filtros.cursor);
  return llamar(`/alertas?${p.toString()}`, { signal });
}

export async function revisarAlerta(
  id: string,
  estado: "revisada" | "descartada",
): Promise<Alerta> {
  return llamar(`/alertas/${encodeURIComponent(id)}`, { method: "PATCH", cuerpo: { estado } });
}

/**
 * UUID v4 aleatorio.
 *
 * `crypto.randomUUID()` solo existe en contexto seguro (HTTPS o localhost). Al probar desde un
 * teléfono por la red local sin HTTPS no está, y sin este respaldo el envío fallaría justo en la
 * prueba de campo. `getRandomValues` sí está en cualquier contexto y es igual de aleatorio.
 */
export function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** Una captura nueva: identificador e instante se fijan aquí, una sola vez, antes de enviar. */
export function nuevaCaptura(): { cliente_id: string; capturado_en: string } {
  return { cliente_id: uuid(), capturado_en: new Date().toISOString() };
}
