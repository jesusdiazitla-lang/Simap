/**
 * Cómo se escriben fechas, horas y horómetros en toda la aplicación. En un solo sitio para que el
 * mismo dato se lea igual en la ficha, en el historial y en la bandeja.
 */

const LOCAL = "es-DO";

/**
 * Zona de la plataforma (08-fase5, 10.3). Toda fecha se escribe en hora de Santo Domingo, no en la
 * del navegador: un supervisor de viaje o un aparato mal configurado verían, si no, otra hora que
 * la del parte y otro día que el de los indicadores, que se cortan en esta misma zona.
 */
export const ZONA = "America/Santo_Domingo";

/**
 * 4821 → «4,821 h». Con el separador de miles de `es-DO` (coma, como en República Dominicana), que
 * evita leer mal un dígito de más.
 */
export function horas(valor: number): string {
  return `${valor.toLocaleString(LOCAL)} h`;
}

export function fechaHora(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString(LOCAL, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: ZONA })} · ${d.toLocaleTimeString(LOCAL, { hour: "2-digit", minute: "2-digit", timeZone: ZONA })}`;
}

export function fecha(iso: string): string {
  return new Date(iso).toLocaleDateString(LOCAL, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: ZONA });
}

/**
 * «hace 3 h», «hace 2 días». Junto a la fecha exacta, no en su lugar: quien escanea quiere saber de
 * un vistazo si la última lectura es de esta ronda o de la semana pasada.
 */
export function hace(iso: string, ahora: number = Date.now()): string {
  const minutos = Math.round((ahora - new Date(iso).getTime()) / 60_000);
  if (minutos < 1) return "ahora mismo";
  if (minutos < 60) return `hace ${minutos} min`;
  const h = Math.round(minutos / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.round(h / 24)} días`;
}
