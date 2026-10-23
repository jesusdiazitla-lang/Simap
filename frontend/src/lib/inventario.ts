/**
 * Inventario de repuestos (RF-23 a RF-26; 07-fase4-prediccion-e-inventario.md). Tipos y llamadas.
 *
 * El stock no viaja en ningún cuerpo salvo como stock inicial del alta: después solo lo mueven
 * ingresos, consumos (al cerrar una orden) y ajustes por conteo, y cada uno queda en el libro.
 */

import { llamar } from "@/lib/api";
import type { Pagina } from "@/lib/activos";

export type TipoMovimiento = "inicial" | "ingreso" | "consumo" | "ajuste";

export interface Repuesto {
  readonly id: string;
  readonly nombre: string;
  readonly codigo: string;
  readonly stock_actual: number;
  readonly stock_minimo: number;
  /** Ausente para el técnico: consulta existencias, no costos (decisión 2). */
  readonly costo_unitario?: string;
  readonly activo?: boolean;
  readonly bajo_minimo: boolean;
}

export interface Movimiento {
  readonly id: string;
  readonly tipo: TipoMovimiento;
  readonly delta: number;
  readonly stock_resultante: number;
  readonly costo_unitario: string | null;
  readonly orden_id: string | null;
  readonly usuario_id: string;
  readonly nota: string | null;
  readonly creado_en: string;
}

export interface Linea {
  readonly repuesto_id: string;
  readonly codigo: string;
  readonly nombre: string;
  readonly cantidad: number;
  readonly stock_actual: number;
  readonly costo_unitario: string | null;
}

export interface Descuadre {
  readonly repuesto_id: string;
  readonly codigo: string;
  readonly stock_actual: number;
  readonly suma_libro: number;
}

export const ETIQUETA_MOVIMIENTO: Readonly<Record<TipoMovimiento, string>> = {
  inicial: "Stock inicial",
  ingreso: "Ingreso",
  consumo: "Consumo",
  ajuste: "Ajuste por conteo",
};

/** 1250.5 → «RD$ 1,250.50». La moneda es la de la planta piloto (República Dominicana). */
export function dinero(valor: string | number): string {
  const n = typeof valor === "string" ? Number(valor) : valor;
  return `RD$ ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function listarRepuestos(
  filtro: { readonly buscar?: string; readonly bajoMinimo?: boolean; readonly inactivos?: boolean; readonly cursor?: string },
  signal?: AbortSignal,
): Promise<Pagina<Repuesto>> {
  const q = new URLSearchParams();
  if (filtro.buscar) q.set("buscar", filtro.buscar);
  if (filtro.bajoMinimo) q.set("bajo_minimo", "true");
  if (filtro.inactivos) q.set("incluir_inactivos", "true");
  if (filtro.cursor) q.set("cursor", filtro.cursor);
  const sufijo = q.size > 0 ? `?${q.toString()}` : "";
  return llamar<Pagina<Repuesto>>(`/repuestos${sufijo}`, { signal });
}

export function obtenerRepuesto(id: string, signal?: AbortSignal): Promise<Repuesto> {
  return llamar<Repuesto>(`/repuestos/${id}`, { signal });
}

export function crearRepuesto(datos: {
  readonly nombre: string;
  readonly codigo: string;
  readonly stock_inicial: number;
  readonly stock_minimo: number;
  readonly costo_unitario: string;
}): Promise<Repuesto> {
  return llamar<Repuesto>("/repuestos", { method: "POST", cuerpo: datos });
}

export function editarRepuesto(
  id: string,
  cambios: Partial<{ nombre: string; stock_minimo: number; costo_unitario: string; activo: boolean }>,
): Promise<Repuesto> {
  return llamar<Repuesto>(`/repuestos/${id}`, { method: "PATCH", cuerpo: cambios });
}

export function registrarIngreso(id: string, cantidad: number, nota: string | null): Promise<Repuesto> {
  return llamar<Repuesto>(`/repuestos/${id}/ingresos`, {
    method: "POST",
    cuerpo: { cantidad, nota: nota || null },
  });
}

export function ajustarPorConteo(id: string, conteo: number, nota: string): Promise<Repuesto> {
  return llamar<Repuesto>(`/repuestos/${id}/ajuste`, { method: "POST", cuerpo: { conteo, nota } });
}

export function movimientos(id: string, cursor?: string, signal?: AbortSignal): Promise<Pagina<Movimiento>> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return llamar<Pagina<Movimiento>>(`/repuestos/${id}/movimientos${q}`, { signal });
}

export function conciliacion(signal?: AbortSignal): Promise<readonly Descuadre[]> {
  return llamar<readonly Descuadre[]>("/inventario/conciliacion", { signal });
}

export function lineasDeOrden(ordenId: string, signal?: AbortSignal): Promise<readonly Linea[]> {
  return llamar<readonly Linea[]>(`/ordenes/${ordenId}/repuestos`, { signal });
}

export function guardarLinea(ordenId: string, repuestoId: string, cantidad: number): Promise<readonly Linea[]> {
  return llamar<readonly Linea[]>(`/ordenes/${ordenId}/repuestos/${repuestoId}`, {
    method: "PUT",
    cuerpo: { cantidad },
  });
}

export function quitarLinea(ordenId: string, repuestoId: string): Promise<void> {
  return llamar<void>(`/ordenes/${ordenId}/repuestos/${repuestoId}`, { method: "DELETE" });
}
