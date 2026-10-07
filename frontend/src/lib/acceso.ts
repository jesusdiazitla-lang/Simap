/**
 * Una sola pantalla de acceso para los dos planos: usuarios de una empresa y operador de SIMAP.
 *
 * LA SEPARACIÓN SIGUE AHÍ, SOLO QUE NO EN LA URL
 * ----------------------------------------------
 * Por debajo no cambia nada: cada plano tiene su endpoint, su rol de base de datos, sus cookies y
 * su límite de intentos (ver «Dos planos» en README.md). Lo único que se unifica es la pantalla:
 * con un correo y una contraseña, primero se prueba la entrada de las plantas y, si no abre, la del
 * operador. Este módulo es el único punto que conoce las dos, para que `lib/auth.ts` y
 * `lib/operador.ts` sigan sin importarse entre sí.
 *
 * QUÉ SE PRUEBA Y CUÁNDO
 * ----------------------
 * - Entra en una planta → listo. Es el caso más frecuente, así que va primero y cuesta un solo hash.
 * - La planta dice 403 (empresa suspendida, usuario de baja) → se muestra tal cual: la contraseña
 *   era correcta, y probar el operador después no tendría sentido.
 * - La planta dice 401 o 429 → se prueba el operador. Si abre, se entra en la consola; si no, se
 *   muestra el error de la planta. Así el límite de intentos de las plantas no deja fuera al
 *   operador, y viceversa: cada entrada lleva su propio contador.
 *
 * Si el mismo correo y la misma contraseña valen en los dos planos, gana la planta. Con contraseñas
 * distintas cada una abre la suya, así que no hay ambigüedad; para la cuenta de operador conviene un
 * correo que no se use en ninguna planta.
 *
 * Un fallo cuesta dos comprobaciones de Argon2 en el servidor en vez de una. Las dos ramas lo pagan
 * igual —el servidor compara siempre contra algún hash, exista el correo o no—, así que el tiempo de
 * respuesta no delata en qué plano existe un correo.
 */

import { ErrorApi } from "@/lib/api";
import { entrar, type Sesion } from "@/lib/auth";
import { entrarComoOperador } from "@/lib/operador";

export type Acceso =
  | { readonly plano: "empresa"; readonly sesion: Sesion }
  | { readonly plano: "operador" };

export async function acceder(correo: string, password: string): Promise<Acceso> {
  let errorPlanta: ErrorApi;
  try {
    return { plano: "empresa", sesion: await entrar(correo, password) };
  } catch (error) {
    if (!(error instanceof ErrorApi) || (error.estado !== 401 && error.estado !== 429)) throw error;
    errorPlanta = error;
  }

  try {
    await entrarComoOperador(correo, password);
    return { plano: "operador" };
  } catch (error) {
    // Un fallo de red o un límite de intentos de la consola se dicen tal cual. Cualquier otro
    // rechazo del operador se tapa con el de la planta: decir «no eres operador» confirmaría a
    // quien prueba que ese correo no tiene cuenta de operador.
    if (error instanceof ErrorApi && (error.esFalloDeRed || error.estado === 429)) throw error;
    throw errorPlanta;
  }
}
