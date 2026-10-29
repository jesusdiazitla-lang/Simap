/**
 * Paneles por rol e indicadores del gerente (08-fase5, secciones 8.4 y 10; RF-27, RF-28).
 *
 * La API arma el panel del rol de la sesión: este módulo solo trae los widgets y les da formato.
 * Las razones llegan ya armadas sobre los totales del periodo; aquí no se recalcula nada, solo se
 * escribe sin engañar (10.3): un dato ausente es «—», una razón sin denominador es «sin datos», y el
 * MTBF nunca aparece sin su respaldo.
 */

import { llamar } from "@/lib/api";
import { dinero } from "@/lib/inventario";

export type EstadoWidget = "ok" | "degradado";

export interface Widget<T> {
  readonly estado: EstadoWidget;
  /** Solo un código corto: el detalle del error queda en el registro del servidor (RNF-02). */
  readonly motivo?: "error" | "tiempo_agotado";
  readonly datos: T | null;
  readonly ms: number;
}

export interface MiLectura {
  readonly id: string;
  readonly equipo: string;
  readonly codigo: string;
  readonly valor: number;
  readonly capturado_en: string;
  readonly estado: "registrada" | "en_revision" | "reinicio" | "descartada";
}

export interface MiAlerta {
  readonly id: string;
  readonly equipo: string;
  readonly codigo: string;
  readonly sintoma: string;
  readonly capturado_en: string;
  readonly estado: "pendiente" | "revisada" | "descartada" | "convertida_en_orden";
}

export interface OrdenPanel {
  readonly id: string;
  readonly numero: number;
  readonly estado: "reportada" | "en_taller" | "reparada";
  readonly es_predictiva: boolean;
  readonly equipo: string;
  readonly codigo: string;
  readonly planta: string | null;
  readonly componente: string;
  readonly fecha_falla: string;
  readonly horas_abierta?: number;
  readonly reparada_en?: string;
  readonly tipo_intervencion?: string;
}

export interface Contadores {
  readonly alertas_campo: number;
  readonly alertas_sistema: number;
  readonly ordenes_abiertas: number;
  readonly lecturas_por_confirmar: number;
}

export interface AlertaCampoPanel {
  readonly id: string;
  readonly equipo: string;
  readonly codigo: string;
  readonly planta: string | null;
  readonly sintoma: string;
  readonly capturado_en: string;
  readonly reporto: string;
}

export interface AlertaSistemaPanel {
  readonly id: string;
  readonly tipo: "riesgo" | "reorden";
  readonly estado: "activa" | "reconocida";
  readonly riesgo: number | null;
  readonly creada_en: string;
  readonly equipo: string | null;
  readonly componente: string | null;
  readonly repuesto: string | null;
  readonly repuesto_codigo: string | null;
  readonly stock: number | null;
  readonly stock_minimo: number | null;
}

export interface Resumen {
  readonly horas_calendario: number;
  readonly paradas_total_h: number;
  readonly paradas_falla_h: number;
  readonly paradas_planificadas_h: number;
  readonly disponibilidad: number | null;
  readonly disponibilidad_sin_planificadas: number | null;
  readonly utilizacion: number | null;
  readonly horas_operadas: number;
  readonly fallas: number;
  readonly fallas_en_revision: number;
  readonly mtbf_h: number | null;
  readonly mtbf_es_cota_inferior: boolean;
  readonly mtbf_ic: readonly [number, number | null] | null;
  readonly fallas_cerradas: number;
  readonly mttr_h: number | null;
  readonly planificadas_cerradas: number;
  readonly costo_fallas: string;
  readonly costo_planificadas: string;
  readonly costo_total: string;
  readonly porcentaje_planificado: number | null;
}

export interface MesIndicador {
  /** Primer día del mes (`AAAA-MM-DD`), en la zona de la plataforma. */
  readonly mes: string;
  readonly equipos: number;
  readonly horas_calendario: number;
  readonly paradas_total_h: number;
  readonly paradas_falla_h: number;
  readonly fallas: number;
  readonly horas_operadas: number;
  readonly costo_fallas: string;
  readonly costo_planificadas: string;
}

export interface Indicadores {
  readonly desde: string;
  readonly hasta: string;
  readonly resumen: Resumen;
  readonly meses: readonly MesIndicador[];
}

export interface RepuestoCosto {
  readonly codigo: string;
  readonly nombre: string;
  readonly unidades: number;
  readonly costo: string;
}

export interface RiesgoTop {
  readonly activo_id: string;
  readonly equipo: string;
  readonly codigo: string;
  readonly planta: string | null;
  readonly criticidad: "alta" | "media" | "baja" | null;
  readonly componente: string;
  readonly riesgo: number;
  readonly confianza: "baja" | "media" | "alta" | null;
  readonly fuente: "previo" | "mixto" | "empresa" | null;
  readonly n_eventos: number | null;
  readonly horizonte_horas: number | null;
  /** Umbral de alerta de la empresa: el nivel se lee contra él. */
  readonly umbral: number | null;
  readonly calculado_en: string;
}

export interface Cobertura {
  readonly equipos_activos: number;
  readonly con_riesgo: number;
  readonly sin_edad: number;
  readonly sin_modelo_o_sin_componentes: number;
}

export interface Salud {
  readonly ultimo_calculo: string | null;
  readonly pares_sin_edad: number;
  readonly pares_sin_modelo: number;
  readonly modelos_confianza_baja: number;
  readonly repuestos_bajo_minimo: number;
  readonly lecturas_por_confirmar: number;
  readonly usuarios_activos: number;
  readonly prediccion_configurada: boolean;
}

export interface WidgetsPanel {
  readonly mis_lecturas?: Widget<readonly MiLectura[]>;
  readonly mis_alertas?: Widget<readonly MiAlerta[]>;
  readonly cola_taller?: Widget<readonly OrdenPanel[]>;
  readonly mis_trabajos?: Widget<readonly OrdenPanel[]>;
  readonly contadores?: Widget<Contadores>;
  readonly alertas_campo?: Widget<readonly AlertaCampoPanel[]>;
  readonly alertas_sistema?: Widget<readonly AlertaSistemaPanel[]>;
  readonly ordenes_abiertas?: Widget<readonly OrdenPanel[]>;
  readonly indicadores?: Widget<Indicadores>;
  readonly repuestos_costo?: Widget<readonly RepuestoCosto[]>;
  readonly riesgo_top?: Widget<readonly RiesgoTop[]>;
  readonly riesgo_cobertura?: Widget<Cobertura>;
  readonly salud?: Widget<Salud>;
}

export interface Panel {
  readonly rol: string;
  readonly widgets: WidgetsPanel;
  readonly degradados: readonly string[];
  readonly desde: string;
  readonly hasta: string;
  readonly planta: string | null;
}

export interface FiltrosPanel {
  readonly planta?: string;
  readonly desde?: string;
  readonly hasta?: string;
}

export function leerPanel(filtros: FiltrosPanel, signal?: AbortSignal): Promise<Panel> {
  const q = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) if (valor) q.set(clave, valor);
  const texto = q.toString();
  return llamar<Panel>(`/panel${texto ? `?${texto}` : ""}`, { signal });
}

export function listarPlantas(signal?: AbortSignal): Promise<readonly string[]> {
  return llamar<readonly string[]>("/plantas", { signal });
}

// --- Formato (10.3) -------------------------------------------------------------------------------

const LOCAL = "es-DO";
const ZONA = "America/Santo_Domingo";
export const VACIO = "—";

/** 0.9972 → «99.7 %». Una razón sin denominador no es 100 %: «sin datos». */
export function porcentajeFino(valor: number | null, decimales = 1): string {
  if (valor === null) return "sin datos";
  return `${(valor * 100).toLocaleString(LOCAL, { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} %`;
}

/** 3840.4 → «3,840 h»; 15.62 → «15.6 h». Con menos de 100 h, un decimal. */
export function horasCortas(valor: number | null): string {
  if (valor === null) return VACIO;
  const decimales = Math.abs(valor) < 100 ? 1 : 0;
  return `${valor.toLocaleString(LOCAL, { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} h`;
}

export function entero(valor: number): string {
  return valor.toLocaleString(LOCAL);
}

export { dinero };

/** «2026-10-01» → «oct. 2026», cortado en la zona de la plataforma (decisión 11). */
export function etiquetaMes(mes: string, conAnio = true): string {
  const [a, m] = mes.split("-").map(Number);
  // Mediodía en Santo Domingo: lejos de cualquier medianoche, el mes no puede correrse.
  const fecha = new Date(Date.UTC(a, m - 1, 1, 16));
  return fecha.toLocaleDateString(LOCAL, { month: "short", ...(conAnio ? { year: "numeric" } : {}), timeZone: ZONA });
}

export interface TextoMtbf {
  readonly valor: string;
  readonly nota: string;
}

/**
 * El MTBF nunca se muestra como un número pelado. Sin fallas no existe: se dice «al menos» con el
 * límite inferior. Con fallas, va con cuántas lo respaldan y su intervalo del 90 %.
 */
export function textoMtbf(r: Pick<Resumen, "mtbf_h" | "mtbf_es_cota_inferior" | "mtbf_ic" | "horas_operadas" | "fallas">): TextoMtbf {
  if (r.horas_operadas <= 0) return { valor: VACIO, nota: "Sin horas operadas en el periodo" };
  if (r.mtbf_es_cota_inferior || r.mtbf_h === null) {
    const piso = r.mtbf_ic ? r.mtbf_ic[0] : r.horas_operadas;
    return { valor: `≥ ${horasCortas(piso)}`, nota: "Sin fallas en el periodo: al menos este valor (95 % de confianza)" };
  }
  const ic = r.mtbf_ic;
  const rango = ic ? ` · IC 90 %: ${horasCortas(ic[0])} a ${ic[1] === null ? "sin tope" : horasCortas(ic[1])}` : "";
  return { valor: horasCortas(r.mtbf_h), nota: `${entero(r.fallas)} ${r.fallas === 1 ? "falla" : "fallas"}${rango}` };
}

export const ETIQUETA_LECTURA: Readonly<Record<MiLectura["estado"], string>> = {
  registrada: "Registrada",
  en_revision: "En revisión",
  reinicio: "Reinicio",
  descartada: "Descartada",
};

export const ETIQUETA_ALERTA: Readonly<Record<MiAlerta["estado"], string>> = {
  pendiente: "Pendiente de revisión",
  revisada: "Revisada",
  descartada: "Descartada",
  convertida_en_orden: "Se abrió una orden",
};

export const ETIQUETA_SINTOMA: Readonly<Record<string, string>> = {
  ruido: "Ruido",
  vibracion: "Vibración",
  calor: "Calor",
  olor: "Olor",
  fuga: "Fuga",
  otro: "Otro",
};
