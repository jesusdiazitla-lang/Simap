/**
 * Personal de la empresa, gestionado por su administrador (RF-03). Tipos y llamadas a la API.
 *
 * La contraseña de cada alta la genera el servidor y llega una sola vez, en la respuesta: no se
 * guarda en ningún sitio del navegador.
 */

import { llamar } from "@/lib/api";
import type { Rol } from "@/lib/auth";

export interface Persona {
  readonly id: string;
  readonly nombre: string;
  readonly correo: string;
  readonly rol: Rol;
  readonly activo: boolean;
  readonly creado_en: string;
}

export interface PersonaConClave {
  readonly usuario: Persona;
  readonly password_temporal: string;
}

export async function listarPersonal(): Promise<readonly Persona[]> {
  return llamar<Persona[]>("/usuarios");
}

export async function darDeAltaPersona(datos: {
  nombre: string;
  correo: string;
  rol: Rol;
}): Promise<PersonaConClave> {
  return llamar<PersonaConClave>("/usuarios", { method: "POST", cuerpo: datos });
}

export async function editarPersona(
  id: string,
  cambios: { nombre?: string; rol?: Rol; activo?: boolean },
): Promise<Persona> {
  return llamar<Persona>(`/usuarios/${encodeURIComponent(id)}`, { method: "PATCH", cuerpo: cambios });
}

export async function restablecerClavePersona(id: string): Promise<PersonaConClave> {
  return llamar<PersonaConClave>(`/usuarios/${encodeURIComponent(id)}/restablecer-clave`, {
    method: "POST",
  });
}
