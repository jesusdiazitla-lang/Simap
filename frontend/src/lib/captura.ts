/**
 * Enviar una captura de campo, o guardarla en el teléfono si no hay red.
 *
 * Es el punto en que una lectura o una alerta deja de depender de la cobertura: se intenta enviar
 * directamente y, si la red falla —o el teléfono ya sabe que no la hay—, se encola con **el mismo**
 * `cliente_id`. Si el envío directo sí había llegado y lo que se perdió fue la respuesta, la cola lo
 * reenviará y el servidor contestará «duplicado»: nunca hay dos filas.
 *
 * Un rechazo del servidor (equipo de baja, valor fuera de rango) no se encola: no entraría nunca, y
 * quien está delante del equipo puede corregirlo ahora.
 */

import { ErrorApi } from "@/lib/api";
import type { Activo } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import {
  registrarLectura,
  reportarAlerta,
  type Alerta,
  type CapturaAlerta,
  type CapturaLectura,
  type Lectura,
} from "@/lib/campo";
import { encolar } from "@/lib/offline-queue";

export type ResultadoLectura =
  | { readonly tipo: "enviado"; readonly estado: "creado" | "duplicado"; readonly lectura: Lectura }
  | { readonly tipo: "encolado" };

export type ResultadoAlerta =
  | { readonly tipo: "enviado"; readonly estado: "creado" | "duplicado"; readonly alerta: Alerta }
  | { readonly tipo: "encolado" };

function sinRed(error: unknown): boolean {
  return error instanceof ErrorApi && error.esFalloDeRed;
}

export async function enviarLectura(
  usuario: Usuario,
  activo: Activo,
  captura: CapturaLectura,
): Promise<ResultadoLectura> {
  if (navigator.onLine) {
    try {
      const r = await registrarLectura(activo.id, captura);
      return { tipo: "enviado", estado: r.estado, lectura: r.lectura };
    } catch (error) {
      if (!sinRed(error)) throw error;
    }
  }
  await encolar({
    tipo: "lectura",
    cliente_id: captura.cliente_id,
    activo_id: activo.id,
    equipo: activo.nombre,
    capturado_en: captura.capturado_en,
    valor: captura.valor,
    usuario_id: usuario.id,
    empresa_id: usuario.empresa_id,
  });
  return { tipo: "encolado" };
}

export async function enviarAlerta(
  usuario: Usuario,
  activo: Activo,
  captura: CapturaAlerta,
): Promise<ResultadoAlerta> {
  if (navigator.onLine) {
    try {
      const r = await reportarAlerta(activo.id, captura);
      return { tipo: "enviado", estado: r.estado, alerta: r.alerta };
    } catch (error) {
      if (!sinRed(error)) throw error;
    }
  }
  await encolar({
    tipo: "alerta",
    cliente_id: captura.cliente_id,
    activo_id: activo.id,
    equipo: activo.nombre,
    capturado_en: captura.capturado_en,
    sintoma: captura.sintoma,
    nota: captura.nota,
    usuario_id: usuario.id,
    empresa_id: usuario.empresa_id,
  });
  return { tipo: "encolado" };
}
