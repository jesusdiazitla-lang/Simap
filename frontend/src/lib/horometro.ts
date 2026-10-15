/**
 * Lo que la pantalla comprueba de un horómetro antes de enviarlo. Lo usan la lectura de campo y el
 * reporte de falla, que registra también una lectura (06-fase3, 6.2): las dos tienen que avisar
 * igual de un dígito de más.
 */

import type { Activo } from "@/lib/activos";
import { horas } from "@/lib/formato";

/** Holgura al comparar el salto con las horas de reloj. Igual que `HOROMETRO_TOLERANCIA_HORAS`. */
const TOLERANCIA_HORAS = 2;

/**
 * Horas enteras (05-fase2, sección 5.1). Devuelve el número, o el mensaje de por qué no lo es.
 *
 * Admite separadores de miles bien puestos («48,215» o «48 215»), pero un punto o una coma en
 * cualquier otro sitio es un decimal: quitarlo sin más convertía «4821.5» en 48 215, justo el dígito
 * de más que estas pantallas intentan evitar.
 */
export function leerHorometro(valor: string): number | string {
  const texto = valor.trim();
  if (/^\d{1,7}$/.test(texto)) return Number(texto);
  if (/^\d{1,3}([.,\s])\d{3}(\1\d{3})?$/.test(texto)) return Number(texto.replace(/\D/g, ""));
  if (/^\d[\d.,\s]*[.,]\d{1,2}$/.test(texto)) {
    return "El horómetro se anota en horas enteras, sin decimales. Escribe solo la parte entera.";
  }
  return "Escribe las horas que marca el horómetro, solo con números.";
}

/**
 * Por qué este valor no cuadra con la última lectura del equipo, o `null` si cuadra. La pantalla
 * pide confirmar antes de enviar; el servidor vuelve a comprobarlo y, si tampoco cuadra, guarda el
 * dato marcado para revisión.
 */
export function motivoDeDuda(activo: Activo, valor: number): string | null {
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
