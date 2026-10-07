/**
 * Insignias de estado: de un equipo, de una alerta, de una lectura.
 *
 * Aquí se estrenan los colores de estado de máquina (`--estado-ok`, `--estado-aviso`,
 * `--estado-falla`), reservados en el sistema desde la fase 1. Siguen las dos reglas que justifican
 * tenerlos separados del azul de acción:
 *
 * 1. **Nunca son pulsables.** Una insignia informa; si se pudiera pulsar, el verde pasaría a
 *    significar también «aquí se hace algo», y el par verde/rojo es justamente el que no distingue
 *    alguien con deuteranopía.
 * 2. **Nunca van solos.** Siempre llevan la palabra, y los que piden atención, además, un icono.
 *
 * Borde y texto del color, fondo neutro: un relleno saturado convertiría cada fila de una tabla en
 * un semáforo, y en una lista de cincuenta alertas el color dejaría de distinguir nada.
 */

import type { ReactNode } from "react";

import { IconoAviso, IconoBaja } from "@/components/iconos";

type Tono = "ok" | "aviso" | "falla" | "neutro";

const POR_TONO: Readonly<Record<Tono, string>> = {
  ok: "border-estado-ok text-estado-ok",
  aviso: "border-estado-aviso text-estado-aviso",
  falla: "border-estado-falla text-estado-falla",
  neutro: "border-borde-fuerte text-texto-suave",
};

export function Insignia({
  tono,
  children,
  icono,
}: {
  readonly tono: Tono;
  readonly children: ReactNode;
  readonly icono?: ReactNode;
}) {
  return (
    <span
      className={[
        "inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-[var(--radius-control)] border bg-superficie px-2",
        "text-[0.75rem] font-semibold leading-none",
        POR_TONO[tono],
      ].join(" ")}
    >
      {icono}
      {children}
    </span>
  );
}

export function EstadoEquipo({ estado }: { readonly estado: "activo" | "baja" }) {
  return estado === "activo" ? (
    <Insignia tono="ok">En servicio</Insignia>
  ) : (
    <Insignia tono="neutro" icono={<IconoBaja className="h-3.5 w-3.5" />}>
      Dado de baja
    </Insignia>
  );
}

/**
 * Criticidad: cuánto importa un equipo para la producción, **no** su estado. Por eso va en neutro y
 * no con los colores de estado: pintar de rojo un equipo crítico que funciona perfectamente le
 * diría a quien mira la lista que algo falla.
 */
export function Criticidad({ valor }: { readonly valor: "alta" | "media" | "baja" | null }) {
  if (valor === null) return <span className="text-texto-tenue">—</span>;
  return <Insignia tono="neutro">Criticidad {valor}</Insignia>;
}

export function EstadoAlertaInsignia({
  estado,
}: {
  readonly estado: "pendiente" | "revisada" | "descartada" | "convertida_en_orden";
}) {
  switch (estado) {
    case "pendiente":
      return (
        <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>
          Pendiente
        </Insignia>
      );
    case "revisada":
      return <Insignia tono="ok">Revisada</Insignia>;
    case "descartada":
      return <Insignia tono="neutro">Descartada</Insignia>;
    default:
      return <Insignia tono="neutro">En orden de trabajo</Insignia>;
  }
}

/** Estado de una lectura que no cuadraba: pendiente, o cómo la resolvió un supervisor. */
export function RequiereRevision({
  resolucion = null,
}: {
  readonly resolucion?: "confirmada" | "descartada" | "reinicio" | null;
}) {
  switch (resolucion) {
    case "confirmada":
      return <Insignia tono="ok">Confirmada</Insignia>;
    case "descartada":
      return <Insignia tono="neutro">Descartada</Insignia>;
    case "reinicio":
      return <Insignia tono="neutro">Reinicio del horómetro</Insignia>;
    default:
      return (
        <Insignia tono="aviso" icono={<IconoAviso className="h-3.5 w-3.5" />}>
          Para revisar
        </Insignia>
      );
  }
}
