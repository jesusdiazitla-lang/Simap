"use client";

/**
 * Reportar una falla de un equipo concreto (RF-11; 06-fase3, 9.1). Supervisor o administrador.
 *
 * Es la entrada desde la bandeja de alertas («Convertir en orden», RF-16): llega con `?alerta=id` y
 * la orden nace vinculada a esa alerta. Desde la etiqueta QR, el mismo formulario está en la propia
 * pantalla del equipo, que es la que funciona sin conexión.
 */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { FormularioFalla } from "@/components/formulario-falla";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { obtenerActivo, type Activo } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";

const sinSuscripcion = (): (() => void) => () => undefined;
const alertaDeLaDireccion = (): string | null =>
  new URLSearchParams(window.location.search).get("alerta");
const sinAlerta = (): null => null;

export default function FallaPage() {
  return (
    <Pantalla roles={["supervisor", "administrador"]} cargando="Reportar falla">
      {(usuario) => <Reporte usuario={usuario} />}
    </Pantalla>
  );
}

function Reporte({ usuario }: { readonly usuario: Usuario }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [activo, setActivo] = useState<Activo | null>(null);
  const [error, setError] = useState<string | null>(null);
  // De la dirección, que es estado del navegador: en el servidor no hay alerta que leer.
  const alertaId = useSyncExternalStore(sinSuscripcion, alertaDeLaDireccion, sinAlerta);

  useEffect(() => {
    const control = new AbortController();
    obtenerActivo(id, control.signal)
      .then(setActivo)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi && e.estado === 404 ? "Este equipo no existe." : "No se pudo cargar el equipo.");
      });
    return () => control.abort();
  }, [id]);

  if (error !== null) {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Reportar falla">
          <p className="pb-4 text-[0.9375rem] text-error">{error}</p>
          <EnlaceBoton href="/alertas">Volver a las alertas</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (activo === null) {
    return (
      <div className="mx-auto max-w-3xl">
        <Panel titulo="Reportar falla">
          <Esqueleto />
        </Panel>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Panel
        titulo={`Reportar falla: ${activo.nombre}`}
        descripcion={
          alertaId !== null
            ? "La orden nacerá vinculada a la alerta de la que vienes, y la alerta pasará a «En orden de trabajo»."
            : "Abre una orden de trabajo. El taller la verá en su bandeja."
        }
      >
        {activo.estado === "baja" ? (
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            Este equipo está dado de baja y ya no admite registros.
          </p>
        ) : (
          <FormularioFalla
            usuario={usuario}
            activo={activo}
            alertaId={alertaId}
            alCrear={(orden) => router.push(`/ordenes/${orden.id}`)}
          />
        )}
      </Panel>
    </div>
  );
}
