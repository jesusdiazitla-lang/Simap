/**
 * Plano de control: sesión y operaciones de quien opera SIMAP.
 *
 * Deliberadamente separado de `src/lib/auth.ts`, que es el plano de datos. Comparten el cliente
 * HTTP y nada más: tipos distintos, rutas distintas y cookies distintas. Mezclarlos en un solo
 * módulo sería la forma más fácil de que un día una pantalla de cliente acabe llamando a un
 * endpoint de operador porque «ya estaba importado».
 *
 * Aquí tampoco se guarda ningún token: la sesión del operador viaja en cookies `httpOnly`
 * restringidas a `/api/v1/operador`, así que ni siquiera se envían en las peticiones del plano de
 * datos.
 */

import { ErrorApi, llamar } from "@/lib/api";

export interface Operador {
  readonly id: string;
  readonly nombre: string;
  readonly correo: string;
  readonly creado_en: string;
}

export interface SesionOperador {
  readonly operador: Operador;
  readonly expira_en_segundos: number;
}

export interface EmpresaResumen {
  readonly id: string;
  readonly nombre: string;
  readonly activa: boolean;
  readonly suspendida_en: string | null;
  readonly admin_nombre: string | null;
  readonly admin_correo: string | null;
  /** Equipos monitoreados, la unidad de cobro. `null` mientras la tabla de activos no exista (F2). */
  readonly equipos: number | null;
}

export interface ClaveTemporal {
  readonly correo: string;
  readonly password_temporal: string;
}

export interface AsientoBitacora {
  readonly id: string;
  readonly accion: string;
  readonly empresa_id: string | null;
  readonly detalle: string | null;
  readonly creado_en: string;
  readonly operador_nombre: string | null;
}

/** Cómo se lee cada acción de la bitácora. La clave es el valor que guarda la base. */
export const ETIQUETA_ACCION: Readonly<Record<string, string>> = {
  alta_empresa: "Alta de empresa",
  suspension: "Suspensión",
  reactivacion: "Reactivación",
  restablecer_clave: "Restablecer contraseña",
  edicion_empresa: "Edición de datos",
  cambio_clave_propia: "Cambio de contraseña propia",
};

export async function entrarComoOperador(
  correo: string,
  password: string,
): Promise<SesionOperador> {
  return llamar<SesionOperador>("/operador/login", {
    method: "POST",
    cuerpo: { correo, password },
    // Un 401 aquí significa «credenciales incorrectas», no «la sesión caducó».
    sinRefrescar: true,
  });
}

export async function salirDeLaConsola(): Promise<void> {
  await llamar<void>("/operador/logout", { method: "POST", sinRefrescar: true });
}

/** Quién opera la consola, o `null` si no hay sesión. */
export async function operadorActual(signal?: AbortSignal): Promise<Operador | null> {
  try {
    return await llamar<Operador>("/operador/yo", { signal, sinRefrescar: true });
  } catch (error) {
    if (error instanceof ErrorApi && error.estado === 401) return null;
    throw error;
  }
}

export async function listarEmpresas(signal?: AbortSignal): Promise<readonly EmpresaResumen[]> {
  return llamar<EmpresaResumen[]>("/operador/empresas", { signal, sinRefrescar: true });
}

export async function altaEmpresa(datos: {
  empresa: string;
  admin_nombre: string;
  admin_correo: string;
}): Promise<ClaveTemporal> {
  return llamar<ClaveTemporal>("/operador/empresas", {
    method: "POST",
    cuerpo: datos,
    sinRefrescar: true,
  });
}

export async function cambiarEstado(id: string, activa: boolean): Promise<EmpresaResumen> {
  return llamar<EmpresaResumen>(`/operador/empresas/${id}/${activa ? "reactivar" : "suspender"}`, {
    method: "POST",
    sinRefrescar: true,
  });
}

export async function renombrarEmpresa(id: string, nombre: string): Promise<EmpresaResumen> {
  return llamar<EmpresaResumen>(`/operador/empresas/${id}`, {
    method: "PATCH",
    cuerpo: { nombre },
    sinRefrescar: true,
  });
}

export async function restablecerClave(id: string): Promise<ClaveTemporal> {
  return llamar<ClaveTemporal>(`/operador/empresas/${id}/restablecer-clave`, {
    method: "POST",
    sinRefrescar: true,
  });
}

export async function leerBitacora(signal?: AbortSignal): Promise<readonly AsientoBitacora[]> {
  return llamar<AsientoBitacora[]>("/operador/bitacora", { signal, sinRefrescar: true });
}

/** El operador cambia su propia contraseña. Queda en la bitácora. */
export async function cambiarClaveOperador(actual: string, nueva: string): Promise<void> {
  await llamar<SesionOperador>("/operador/cambiar-clave", {
    method: "POST",
    cuerpo: { password_actual: actual, password_nueva: nueva },
    sinRefrescar: true,
  });
}
