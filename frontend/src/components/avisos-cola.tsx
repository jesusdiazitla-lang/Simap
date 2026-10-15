"use client";

/**
 * Lo que la cola sin conexión no pudo entregar, dicho a quien lo capturó (05-fase2, sección 7.5).
 *
 * Dos casos, y en los dos el dato no va a llegar nunca, así que reintentar no sirve y callarlo sería
 * peor: la persona creería que su lectura está en el sistema.
 *
 * - **Rechazado por el servidor.** Lo capturado sin red llegó, pero no se pudo aceptar: el equipo se
 *   dio de baja mientras tanto, la captura tenía más de 14 días, un valor fuera de rango. Se lista con
 *   su motivo, tal como lo escribe el servidor, para que la persona pueda volver a registrarlo bien.
 * - **Capturas de otra persona descartadas.** En un teléfono compartido, lo que alguien capturó y no
 *   envió antes de que pasaran 7 días sin que volviera a entrar se descarta.
 *
 * Va en todas las pantallas con sesión, encima del contenido: es lo único que tiene que ver aunque
 * no vuelva a abrir el equipo. Desaparece al pulsar «Entendido».
 *
 * Desde la fase 3 hay un tercer aviso: **reportes de falla aún sin enviar**. Perder uno es más grave
 * que perder una lectura —es una máquina parada de la que el taller no sabe nada—, así que se
 * muestran aparte y con más peso que el indicador de la barra (06-fase3, 9.5). Y una falla rechazada
 * porque el componente ya tenía orden abierta dice cuál, con enlace: «No se creó: ya existe OT-0009».
 */

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { Boton } from "@/components/boton";
import { IconoAviso, IconoPendiente } from "@/components/iconos";
import type { Usuario } from "@/lib/auth";
import { ETIQUETA_SINTOMA } from "@/lib/campo";
import { fechaHora, horas } from "@/lib/formato";
import { numeroOrden } from "@/lib/ordenes";
import {
  descartarRechazados,
  estadoCola,
  estadoColaServidor,
  olvidarAvisoDescartados,
  suscribirCola,
  type ItemCola,
} from "@/lib/offline-queue";

function queEra(item: ItemCola): string {
  if (item.tipo === "lectura") return `Horómetro ${horas(item.valor ?? 0)}`;
  if (item.tipo === "falla") return `Falla: ${item.falla?.componente_nombre ?? "componente"}`;
  return `Alerta: ${item.sintoma !== undefined ? ETIQUETA_SINTOMA[item.sintoma] : "síntoma"}`;
}

export function AvisosCola({ usuario }: { readonly usuario: Usuario }) {
  const cola = useSyncExternalStore(suscribirCola, estadoCola, estadoColaServidor);
  const [cerrando, setCerrando] = useState(false);
  const rechazados = cola.rechazados.filter((i) => i.usuario_id === usuario.id);
  const fallas = cola.fallasPendientes.filter((i) => i.usuario_id === usuario.id);

  if (rechazados.length === 0 && cola.descartadosAjenos === 0 && fallas.length === 0) return null;

  return (
    <div className="flex flex-col gap-3 pb-6">
      {fallas.length > 0 ? (
        <section
          role="status"
          className="rounded-[var(--radius-control)] border-2 border-estado-aviso bg-superficie px-5 py-4 sm:px-6"
        >
          <h2 className="flex items-center gap-2 text-[1rem] font-semibold text-texto">
            <IconoPendiente className="text-estado-aviso" />
            {fallas.length === 1
              ? "Un reporte de falla sin enviar"
              : `${fallas.length} reportes de falla sin enviar`}
          </h2>
          <p className="max-w-[65ch] pt-1 text-[0.9375rem] leading-6 text-texto-suave">
            Están guardados en este teléfono y se enviarán solos al volver la red; hasta entonces el
            taller no los ve y no tienen número de orden. No borres los datos del navegador.
          </p>
          <ul className="flex flex-col divide-y divide-borde pt-2">
            {fallas.map((item) => (
              <li key={item.cliente_id} className="py-2">
                <p className="text-[0.9375rem] font-semibold text-texto [overflow-wrap:anywhere]">
                  {item.equipo} · {queEra(item)}
                </p>
                <p className="text-[0.8125rem] text-texto-tenue">Reportada el {fechaHora(item.capturado_en)}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {rechazados.length > 0 ? (
        <section
          role="alert"
          className="rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-5 py-4 sm:px-6"
        >
          <h2 className="flex items-center gap-2 text-[1rem] font-semibold text-texto">
            <IconoAviso className="text-estado-aviso" />
            {rechazados.length === 1
              ? "Un registro hecho sin conexión no se pudo guardar"
              : `${rechazados.length} registros hechos sin conexión no se pudieron guardar`}
          </h2>
          <p className="max-w-[65ch] pt-1 text-[0.9375rem] leading-6 text-texto-suave">
            {rechazados.length === 1
              ? "Llegó al servidor, pero no se aceptó. Si sigue siendo necesario, vuelve a registrarlo desde el equipo."
              : "Llegaron al servidor, pero no se aceptaron. Si sigue siendo necesario, vuelve a registrarlos desde el equipo."}
          </p>
          <ul className="flex flex-col divide-y divide-borde pt-2">
            {rechazados.map((item) => (
              <li key={item.cliente_id} className="py-2.5">
                <p className="text-[0.9375rem] font-semibold text-texto [overflow-wrap:anywhere]">
                  {item.equipo} · {queEra(item)}
                </p>
                {item.codigo === "orden_abierta_existente" && item.orden_id && item.numero ? (
                  <p className="text-[0.875rem] leading-5 text-texto">
                    No se creó: ya existe{" "}
                    <Link href={`/ordenes/${item.orden_id}`} className="font-semibold text-accion underline underline-offset-2">
                      {numeroOrden(item.numero)}
                    </Link>{" "}
                    para ese componente.
                  </p>
                ) : (
                  <p className="text-[0.875rem] leading-5 text-texto">{item.motivo ?? "Motivo no indicado."}</p>
                )}
                <p className="text-[0.8125rem] text-texto-tenue">Capturado el {fechaHora(item.capturado_en)}</p>
              </li>
            ))}
          </ul>
          <div className="pt-2">
            <Boton
              tipo="button"
              variante="secundario"
              enCurso={cerrando}
              textoEnCurso="Un momento…"
              onClick={() => {
                setCerrando(true);
                void descartarRechazados(usuario.id).finally(() => setCerrando(false));
              }}
            >
              Entendido
            </Boton>
          </div>
        </section>
      ) : null}

      {cola.descartadosAjenos > 0 ? (
        <section
          role="status"
          className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6"
        >
          <p className="max-w-[65ch] text-[0.9375rem] leading-6 text-texto">
            {cola.descartadosAjenos === 1
              ? "Se descartó un registro que otra persona hizo en este teléfono"
              : `Se descartaron ${cola.descartadosAjenos} registros que otra persona hizo en este teléfono`}{" "}
            sin conexión y que llevaban más de 7 días sin enviarse, porque no volvió a entrar.
          </p>
          <Boton tipo="button" variante="secundario" onClick={olvidarAvisoDescartados}>
            Entendido
          </Boton>
        </section>
      ) : null}
    </div>
  );
}
