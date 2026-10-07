/**
 * Lo que se lee de un QR y a dónde se puede ir después de entrar.
 *
 * Las dos funciones de este módulo deciden a qué dirección se navega a partir de un dato que no
 * controla SIMAP: el contenido de una etiqueta pegada en una máquina, y el parámetro `next` de una
 * URL que alguien pudo fabricar. Por eso son estrictas y no «arreglan» nada
 * (05-fase2-activos-y-campo.md, secciones 7.2 y 7.4).
 */

/** Ocho caracteres sin I, O, 0 ni 1. Igual que `ALFABETO` en `backend/app/services/qr.py`. */
export const ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const PATRON_CODIGO = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$/;

/** Lo que alguien tecleó de la etiqueta (`xk7p-2qh9`) convertido en código, o `null`. */
export function normalizarCodigo(tecleado: string): string | null {
  const limpio = tecleado.replace(/[\s-]/g, "").toUpperCase();
  return PATRON_CODIGO.test(limpio) ? limpio : null;
}

/** `XK7P2QH9` → `XK7P-2QH9`. */
export function presentarCodigo(codigo: string): string {
  return `${codigo.slice(0, 4)}-${codigo.slice(4)}`;
}

/**
 * El código de equipo que contiene un QR leído con el escáner de la app, o `null`.
 *
 * Solo acepta exactamente `{origen de SIMAP}/a/{código}`. Un QR ajeno pegado encima de una etiqueta
 * —una URL de otro sitio, un enlace que imita la ruta, un `javascript:`— no lleva a ninguna parte
 * desde dentro de la app. La cámara nativa del teléfono no pasa por aquí: abre la URL y el
 * navegador ya muestra a qué sitio va.
 */
export function codigoDesdeQr(contenido: string, origenPropio: string): string | null {
  let url: URL;
  try {
    url = new URL(contenido.trim());
  } catch {
    return null;
  }
  if (url.origin !== new URL(origenPropio).origin) return null;
  if (url.search !== "" || url.hash !== "") return null;
  const coincidencia = /^\/a\/([^/]+)$/.exec(url.pathname);
  if (coincidencia === null) return null;
  const codigo = coincidencia[1];
  return PATRON_CODIGO.test(codigo) ? codigo : null;
}

/**
 * El destino `next` de `/login?next=...`, si es seguro; si no, `null`.
 *
 * Solo rutas internas: una barra al principio y no dos (`//otro.sitio` es una URL absoluta para el
 * navegador), sin barras invertidas (algunos navegadores las tratan como `/`), sin esquema ni
 * caracteres de control. Cualquier otra cosa se descarta y quien entra va a su panel: una
 * redirección abierta permitiría usar el login de SIMAP para mandar a alguien, ya autenticado, a un
 * sitio que imita al de verdad.
 */
export function destinoSeguro(next: string | null | undefined): string | null {
  if (next === null || next === undefined) return null;
  if (next.length === 0 || next.length > 200) return null;
  if (!next.startsWith("/") || next.startsWith("//")) return null;
  if (next.includes("\\")) return null;
  if (/[\u0000-\u001f\u007f]/.test(next)) return null;
  if (/^\/(login|operador)(\/|$|\?)/.test(next)) return null;
  return next;
}
