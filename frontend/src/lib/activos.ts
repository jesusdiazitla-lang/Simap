/**
 * Equipos y catálogo de componentes (RF-04..07). Tipos y llamadas a la API, sin pantalla.
 *
 * Los tipos reflejan exactamente las respuestas de `backend/app/schemas/activo.py`. No hay aquí
 * ningún `empresa_id`: el servidor lo saca del token y el cliente no tiene por qué conocerlo.
 */

import { llamar } from "@/lib/api";

export type Criticidad = "alta" | "media" | "baja";
export type EstadoActivo = "activo" | "baja";

export interface Activo {
  readonly id: string;
  readonly nombre: string;
  readonly tipo: string | null;
  readonly ubicacion: string | null;
  readonly criticidad: Criticidad | null;
  readonly marca: string | null;
  readonly modelo: string | null;
  readonly numero_serie: string | null;
  readonly fecha_instalacion: string | null;
  readonly estado: EstadoActivo;
  readonly dado_de_baja_en: string | null;
  readonly horometro_actual: number;
  readonly horometro_actualizado_en: string | null;
  readonly fecha_ultima_falla: string | null;
  readonly codigo: string;
  readonly codigo_corto: string;
  readonly url_qr: string;
  /** Horas acumuladas antes del último cambio o reinicio del horómetro (F3). */
  readonly horometro_offset?: number;
  /** Tiene alguna orden de trabajo abierta. Derivado en el servidor. */
  readonly en_falla?: boolean;
  /** Solo en la ficha de un equipo: sus órdenes abiertas. Las ve cualquier rol. */
  readonly ordenes_abiertas?: readonly OrdenAbierta[];
}

/** Lo que cualquiera ve en la ficha de un equipo en falla, operario incluido. */
export interface OrdenAbierta {
  readonly id: string;
  readonly numero: number;
  readonly estado: "reportada" | "en_taller" | "reparada";
  readonly componente_id: string;
  readonly componente_nombre: string;
}

export interface Pagina<T> {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
}

/** Ficha técnica editable. Sin código ni empresa: el servidor rechaza esos campos. */
export interface FichaActivo {
  nombre: string;
  tipo: string | null;
  ubicacion: string | null;
  criticidad: Criticidad | null;
  marca: string | null;
  modelo: string | null;
  numero_serie: string | null;
  fecha_instalacion: string | null;
}

export interface Componente {
  readonly id: string;
  readonly nombre: string;
  readonly descripcion: string | null;
  readonly activo: boolean;
  /** Vida nominal en horas (F4, decisión 6): el centro del conocimiento previo del modelo. */
  readonly vida_nominal_horas: number | null;
}

export const ETIQUETA_CRITICIDAD: Readonly<Record<Criticidad, string>> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

function consulta(parametros: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== null && valor !== undefined && valor !== "") p.set(clave, String(valor));
  }
  const texto = p.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function listarActivos(
  filtros: { q?: string; estado?: EstadoActivo | null; cursor?: string | null; limite?: number },
  signal?: AbortSignal,
): Promise<Pagina<Activo>> {
  return llamar<Pagina<Activo>>(
    `/activos${consulta({ q: filtros.q, estado: filtros.estado, cursor: filtros.cursor, limite: filtros.limite ?? 50 })}`,
    { signal },
  );
}

export async function activoPorCodigo(codigo: string, signal?: AbortSignal): Promise<Activo> {
  return llamar<Activo>(`/activos/por-codigo/${encodeURIComponent(codigo)}`, { signal });
}

export async function obtenerActivo(id: string, signal?: AbortSignal): Promise<Activo> {
  return llamar<Activo>(`/activos/${encodeURIComponent(id)}`, { signal });
}

export async function crearActivo(
  ficha: FichaActivo & { horometro_inicial: number },
): Promise<Activo> {
  return llamar<Activo>("/activos", { method: "POST", cuerpo: ficha });
}

export async function editarActivo(id: string, ficha: Partial<FichaActivo>): Promise<Activo> {
  return llamar<Activo>(`/activos/${encodeURIComponent(id)}`, { method: "PATCH", cuerpo: ficha });
}

export async function darDeBaja(id: string): Promise<Activo> {
  return llamar<Activo>(`/activos/${encodeURIComponent(id)}/baja`, { method: "POST" });
}

export async function regenerarCodigo(id: string): Promise<Activo> {
  return llamar<Activo>(`/activos/${encodeURIComponent(id)}/regenerar-codigo`, { method: "POST" });
}

/** Cambio o reinicio del horómetro (F3, 5.1). Solo el administrador. */
export async function reiniciarHorometro(id: string, nuevo: number): Promise<Activo> {
  return llamar<Activo>(`/activos/${encodeURIComponent(id)}/reinicio-horometro`, {
    method: "POST",
    cuerpo: { nuevo },
  });
}

/** Dirección de la etiqueta SVG. Mismo origen: el navegador adjunta la cookie de sesión. */
export function urlEtiqueta(id: string): string {
  return `/api/v1/activos/${encodeURIComponent(id)}/etiqueta.svg`;
}

export async function listarComponentes(incluirInactivos = false): Promise<readonly Componente[]> {
  return llamar<Componente[]>(`/componentes${incluirInactivos ? "?incluir_inactivos=true" : ""}`);
}

export async function crearComponente(nombre: string, descripcion: string | null): Promise<Componente> {
  return llamar<Componente>("/componentes", { method: "POST", cuerpo: { nombre, descripcion } });
}

export async function editarComponente(
  id: string,
  cambios: {
    nombre?: string;
    descripcion?: string | null;
    activo?: boolean;
    vida_nominal_horas?: number | null;
  },
): Promise<Componente> {
  return llamar<Componente>(`/componentes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    cuerpo: cambios,
  });
}

/** Añade los componentes del catálogo inicial que falten. Devuelve los añadidos. */
export async function cargarPlantilla(): Promise<readonly Componente[]> {
  return llamar<Componente[]>("/componentes/plantilla", { method: "POST" });
}
