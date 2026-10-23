/**
 * Predicción de fallas (RF-17 a RF-22; 07-fase4-prediccion-e-inventario.md). Tipos y llamadas.
 *
 * Los tipos reflejan `backend/app/schemas/prediccion.py`. Los porcentajes llegan como texto decimal
 * (`"0.25210"`): se convierten aquí, en un solo sitio.
 *
 * Mostrar el riesgo sin engañar (10.2): cada número va con cuántas fallas lo respaldan, «sin edad» y
 * «sin modelo» son avisos con su acción —nunca un 0 %— y el nivel se escribe con palabra, no solo con
 * color.
 */

import { llamar } from "@/lib/api";
import type { Pagina } from "@/lib/activos";
import type { OrdenDetalle } from "@/lib/ordenes";

export type EstadoCalculo = "ok" | "sin_edad" | "sin_modelo";
export type Fuente = "previo" | "mixto" | "empresa";
export type Confianza = "baja" | "media" | "alta";
export type EstadoAlertaSistema = "activa" | "reconocida" | "atendida" | "resuelta" | "descartada";
export type TipoAlertaSistema = "riesgo" | "reorden";
export type FiltroAlertas = "vigentes" | "historial";

export interface RiesgoComponente {
  readonly componente_id: string;
  readonly componente: string;
  readonly estado_calculo: EstadoCalculo;
  readonly edad_horas: number | null;
  readonly horizonte_horas: number | null;
  readonly beta: number | null;
  readonly eta: number | null;
  readonly riesgo_base: string | null;
  readonly multiplicador: string | null;
  readonly riesgo: string | null;
  readonly n_eventos: number | null;
  readonly fuente: Fuente | null;
  readonly confianza: Confianza | null;
  readonly calculado_en: string | null;
}

export interface RiesgoEquipo {
  readonly activo_id: string;
  readonly umbral: string;
  readonly horizonte_horas: number;
  readonly horas_por_dia: number | null;
  readonly alertas_de_campo: number;
  readonly alertas_minimas: number;
  readonly componentes: readonly RiesgoComponente[];
}

export interface RiesgoActivo {
  readonly activo_id: string;
  readonly activo: string;
  readonly codigo: string;
  readonly componente_critico_id: string;
  readonly componente_critico: string;
  readonly riesgo: string;
  readonly confianza: Confianza | null;
  readonly fuente: Fuente | null;
  readonly n_eventos: number | null;
  readonly edad_horas: number | null;
  readonly calculado_en: string;
}

export interface ComponenteEquipo {
  readonly componente_id: string;
  readonly nombre: string;
  readonly horas_instalacion_inicial: number | null;
  readonly estado_calculo: EstadoCalculo | null;
  readonly riesgo: number | null;
  /** Edad de la pieza en el último cálculo (cuenta las renovaciones de las órdenes cerradas). */
  readonly edad_horas: number | null;
}

export interface ComponentesEquipo {
  readonly activo_id: string;
  readonly horas_acumuladas: number;
  readonly componentes: readonly ComponenteEquipo[];
}

export interface HistorialModelo {
  readonly version: number;
  readonly beta: number;
  readonly eta: number;
  readonly n_eventos: number;
  readonly fuente: Fuente;
  readonly confianza: Confianza;
  readonly ajustado_en: string;
}

export interface Modelo {
  readonly componente_id: string;
  readonly componente: string;
  readonly vida_nominal_horas: number | null;
  readonly beta: number | null;
  readonly eta: number | null;
  readonly n_eventos: number | null;
  readonly n_vidas: number | null;
  readonly exposicion_horas: number | null;
  readonly fuente: Fuente | null;
  readonly confianza: Confianza | null;
  readonly convergio: boolean | null;
  readonly version: number | null;
  readonly ajustado_en: string | null;
  readonly historial: readonly HistorialModelo[];
}

export interface Configuracion {
  readonly umbral_riesgo: string;
  readonly horizonte_horas: number;
  readonly alertas_minimas: number;
  readonly ventana_alertas_dias: number;
  readonly multiplicador_alertas: string;
  readonly descarte_silencio_dias: number;
}

export interface AlertaSistema {
  readonly id: string;
  readonly tipo: TipoAlertaSistema;
  readonly estado: EstadoAlertaSistema;
  readonly activo_id: string | null;
  readonly activo: string | null;
  readonly componente_id: string | null;
  readonly componente: string | null;
  readonly repuesto_id: string | null;
  readonly repuesto: string | null;
  readonly repuesto_codigo: string | null;
  readonly riesgo: string | null;
  readonly umbral: string | null;
  readonly confianza: Confianza | null;
  readonly fuente: Fuente | null;
  readonly stock_al_alertar: number | null;
  readonly stock_minimo_al_alertar: number | null;
  readonly creada_en: string;
  readonly gestionada_en: string | null;
  readonly nota: string | null;
  readonly orden_id: string | null;
  readonly orden_numero: number | null;
}

// --- Lectura del riesgo ------------------------------------------------------------------------

/** Texto decimal de la API a número. `null` sigue siendo `null`: nunca se convierte en 0. */
export function numero(valor: string | null): number | null {
  return valor === null ? null : Number(valor);
}

/** 0.2521 → «25 %». Con menos de un 1 %, «menos de 1 %»: un 0 % sugeriría certeza. */
export function porcentaje(valor: number): string {
  if (valor > 0 && valor < 0.01) return "menos de 1 %";
  return `${Math.round(valor * 100)} %`;
}

export type Nivel = "bajo" | "vigilar" | "alto";

/**
 * Nivel por el umbral **de la empresa**, no por números fijos (10.2): alto desde el umbral,
 * vigilar desde el 80 % del umbral (la banda de histéresis de las alertas), bajo por debajo.
 */
export function nivel(riesgo: number, umbral: number): Nivel {
  if (riesgo >= umbral) return "alto";
  if (riesgo >= umbral * 0.8) return "vigilar";
  return "bajo";
}

export const ETIQUETA_NIVEL: Readonly<Record<Nivel, string>> = {
  bajo: "Bajo",
  vigilar: "Vigilar",
  alto: "Alto",
};

export const ETIQUETA_CONFIANZA: Readonly<Record<Confianza, string>> = {
  baja: "Confianza baja",
  media: "Confianza media",
  alta: "Confianza alta",
};

/** «12 fallas registradas» / «1 falla registrada» / «Sin fallas registradas». */
export function respaldo(nEventos: number | null): string {
  if (nEventos === null || nEventos === 0) return "Sin fallas registradas";
  return nEventos === 1 ? "1 falla registrada" : `${nEventos} fallas registradas`;
}

/** Equivalente informativo en días del horizonte (decisión 4). */
export function horizonteEnDias(horas: number, horasPorDia: number | null): string | null {
  if (horasPorDia === null || horasPorDia <= 0) return null;
  const dias = horas / horasPorDia;
  const redondo = dias < 1 ? "menos de un día" : dias < 1.5 ? "un día" : `${Math.round(dias)} días`;
  return `unos ${redondo} a ${Math.round(horasPorDia)} h diarias`.replace("unos menos", "menos");
}

/** Riesgo acumulado de Weibull: P(falla en las próximas h horas | edad a), con multiplicador m. */
export function riesgoWeibull(edad: number, h: number, beta: number, eta: number, m = 1): number {
  const acumulado = (a: number) => Math.pow(Math.max(a, 0) / eta, beta);
  return 1 - Math.exp(-m * (acumulado(edad + h) - acumulado(edad)));
}

// --- Llamadas -----------------------------------------------------------------------------------

export function riesgoDelEquipo(activoId: string, signal?: AbortSignal): Promise<RiesgoEquipo> {
  return llamar<RiesgoEquipo>(`/activos/${activoId}/riesgo`, { signal });
}

export function rankingDeRiesgo(cursor?: string, signal?: AbortSignal): Promise<Pagina<RiesgoActivo>> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return llamar<Pagina<RiesgoActivo>>(`/riesgos${q}`, { signal });
}

export function componentesDelEquipo(activoId: string, signal?: AbortSignal): Promise<ComponentesEquipo> {
  return llamar<ComponentesEquipo>(`/activos/${activoId}/componentes`, { signal });
}

export function declararEdad(
  activoId: string,
  componenteId: string,
  horas: number | null,
): Promise<ComponentesEquipo> {
  return llamar<ComponentesEquipo>(`/activos/${activoId}/componentes/${componenteId}`, {
    method: "PUT",
    cuerpo: { horas_instalacion_inicial: horas },
  });
}

export function modeloDelComponente(componenteId: string, signal?: AbortSignal): Promise<Modelo> {
  return llamar<Modelo>(`/componentes/${componenteId}/modelo`, { signal });
}

export function leerConfiguracion(signal?: AbortSignal): Promise<Configuracion> {
  return llamar<Configuracion>("/configuracion/prediccion", { signal });
}

export function guardarConfiguracion(cambios: Partial<Record<keyof Configuracion, string | number>>): Promise<Configuracion> {
  return llamar<Configuracion>("/configuracion/prediccion", { method: "PUT", cuerpo: cambios });
}

export function listarAlertasSistema(
  filtro: { readonly tipo: TipoAlertaSistema; readonly estado: FiltroAlertas; readonly activoId?: string; readonly cursor?: string },
  signal?: AbortSignal,
): Promise<Pagina<AlertaSistema>> {
  const q = new URLSearchParams({ tipo: filtro.tipo, estado: filtro.estado });
  if (filtro.activoId) q.set("activo_id", filtro.activoId);
  if (filtro.cursor) q.set("cursor", filtro.cursor);
  return llamar<Pagina<AlertaSistema>>(`/alertas-sistema?${q.toString()}`, { signal });
}

export function reconocerAlerta(id: string): Promise<AlertaSistema> {
  return llamar<AlertaSistema>(`/alertas-sistema/${id}/reconocer`, { method: "POST" });
}

export function descartarAlerta(id: string, nota: string): Promise<AlertaSistema> {
  return llamar<AlertaSistema>(`/alertas-sistema/${id}/descartar`, { method: "POST", cuerpo: { nota } });
}

export function crearOrdenPredictiva(id: string): Promise<OrdenDetalle> {
  return llamar<OrdenDetalle>(`/alertas-sistema/${id}/orden`, { method: "POST" });
}
