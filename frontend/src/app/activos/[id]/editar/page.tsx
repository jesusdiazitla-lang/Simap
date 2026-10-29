"use client";

/** Editar la ficha técnica de un equipo (RF-06). El código QR y el horómetro no se editan aquí. */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { FormularioActivo } from "@/components/formulario-activo";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { adelantarObservacion, editarActivo, obtenerActivo, type Activo } from "@/lib/activos";
import { fecha } from "@/lib/formato";

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
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
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
      {activo !== null && activo.creado_en ? <Observacion activo={activo} alCambiar={setActivo} /> : null}
    </div>
  );
}

/**
 * Desde cuándo se observa el equipo (08-fase5, decisión 8): es el inicio de sus horas de calendario
 * para la disponibilidad. Solo se adelanta, para cargar la historia de antes de usar SIMAP.
 */
function Observacion({ activo, alCambiar }: { readonly activo: Activo; readonly alCambiar: (a: Activo) => void }) {
  const [dia, setDia] = useState("");
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [hecho, setHecho] = useState(false);
  return (
    <Panel
      nivel={2}
      titulo="Desde cuándo se observa"
      descripcion={`Las horas de calendario de este equipo cuentan desde el ${fecha(activo.creado_en as string)}. Adelántala solo si cargas historia de antes de usar SIMAP.`}
    >
      <form
        noValidate
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={async (e) => {
          e.preventDefault();
          setEnCurso(true);
          setError(undefined);
          setHecho(false);
          try {
            alCambiar(await adelantarObservacion(activo.id, dia));
            setHecho(true);
            setDia("");
          } catch (err) {
            setError(err instanceof ErrorApi ? err.message : "No se pudo guardar.");
          } finally {
            setEnCurso(false);
          }
        }}
      >
        <div className="sm:w-56">
          <Campo id="observado-desde" etiqueta="Nueva fecha" nombre="observado_desde" tipo="date" valor={dia} onCambio={setDia} error={error} />
        </div>
        <Boton tipo="submit" variante="secundario" deshabilitado={dia === ""} enCurso={enCurso} textoEnCurso="Guardando…">
          Adelantar
        </Boton>
      </form>
      {hecho ? <p role="status" className="pt-2 text-[0.875rem] text-estado-ok">Fecha actualizada.</p> : null}
    </Panel>
  );
}
