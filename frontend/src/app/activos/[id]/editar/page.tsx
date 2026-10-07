"use client";

/** Editar la ficha técnica de un equipo (RF-06). El código QR y el horómetro no se editan aquí. */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FormularioActivo } from "@/components/formulario-activo";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { editarActivo, obtenerActivo, type Activo } from "@/lib/activos";

export default function EditarActivoPage() {
  return (
    <Pantalla roles={["administrador"]} cargando="Editar equipo">
      {() => <Editar />}
    </Pantalla>
  );
}

function Editar() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [activo, setActivo] = useState<Activo | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="mx-auto max-w-3xl">
      <Panel titulo={activo === null ? "Editar equipo" : `Editar «${activo.nombre}»`}>
        {error !== null ? (
          <p role="alert" className="text-[0.9375rem] text-error">
            {error}
          </p>
        ) : activo === null ? (
          <Esqueleto />
        ) : (
          <FormularioActivo
            inicial={activo}
            textoBoton="Guardar cambios"
            conHorometro={false}
            guardar={async (ficha) => {
              const actualizado = await editarActivo(activo.id, ficha);
              router.replace(`/a/${actualizado.codigo}`);
            }}
          />
        )}
      </Panel>
    </div>
  );
}
