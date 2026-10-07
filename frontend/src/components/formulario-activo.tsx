"use client";

/**
 * Ficha técnica de un equipo: alta y edición (RF-04, RF-06).
 *
 * Solo el nombre es obligatorio. Lo demás se rellena cuando se sabe: exigir el número de serie de
 * un compresor de 1998 haría que alguien escribiera «no sé» y ensuciara la ficha.
 *
 * El código QR no aparece aquí: lo genera el servidor al dar de alta y no se edita. Tampoco el
 * horómetro vigente: solo lo mueven las lecturas. En el alta sí se pide el valor del día, que queda
 * como primera lectura del historial.
 */

import { useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { ErrorApi } from "@/lib/api";
import type { Activo, Criticidad, FichaActivo } from "@/lib/activos";

const CRITICIDADES: Array<[Criticidad | null, string]> = [
  [null, "Sin indicar"],
  ["alta", "Alta"],
  ["media", "Media"],
  ["baja", "Baja"],
];

export function FormularioActivo({
  inicial,
  textoBoton,
  conHorometro,
  guardar,
}: {
  readonly inicial: Activo | null;
  readonly textoBoton: string;
  /** Pedir el horómetro del día: solo en el alta. */
  readonly conHorometro: boolean;
  readonly guardar: (ficha: FichaActivo, horometro: number) => Promise<void>;
}) {
  const [nombre, setNombre] = useState(inicial?.nombre ?? "");
  const [tipo, setTipo] = useState(inicial?.tipo ?? "");
  const [ubicacion, setUbicacion] = useState(inicial?.ubicacion ?? "");
  const [criticidad, setCriticidad] = useState<Criticidad | null>(inicial?.criticidad ?? null);
  const [marca, setMarca] = useState(inicial?.marca ?? "");
  const [modelo, setModelo] = useState(inicial?.modelo ?? "");
  const [serie, setSerie] = useState(inicial?.numero_serie ?? "");
  const [instalacion, setInstalacion] = useState(inicial?.fecha_instalacion ?? "");
  const [horometro, setHorometro] = useState("");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);

  const opcional = (v: string): string | null => (v.trim() === "" ? null : v.trim());

  async function enviar(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    const fallos: Record<string, string> = {};
    if (nombre.trim().length < 2) fallos.nombre = "Escribe el nombre del equipo.";
    const h = horometro.trim() === "" ? 0 : Number(horometro.replace(/[\s.,]/g, ""));
    if (conHorometro && (!Number.isInteger(h) || h < 0)) {
      fallos.horometro_inicial = "Solo números: las horas que marca hoy el horómetro.";
    }
    setErrores(fallos);
    if (Object.keys(fallos).length > 0) {
      setAviso("Revisa los campos marcados.");
      return;
    }
    setAviso(null);
    setEnCurso(true);
    try {
      await guardar(
        {
          nombre: nombre.trim(),
          tipo: opcional(tipo),
          ubicacion: opcional(ubicacion),
          criticidad,
          marca: opcional(marca),
          modelo: opcional(modelo),
          numero_serie: opcional(serie),
          fecha_instalacion: opcional(instalacion),
        },
        h,
      );
    } catch (error) {
      setEnCurso(false);
      if (error instanceof ErrorApi && Object.keys(error.campos).length > 0) setErrores({ ...error.campos });
      setAviso(error instanceof ErrorApi ? error.message : "No se pudo guardar. Vuelve a intentarlo.");
    }
  }

  return (
    <form noValidate onSubmit={(e) => void enviar(e)} className="flex flex-col gap-1">
      <Campo id="activo-nombre" etiqueta="Nombre" nombre="nombre" valor={nombre} onCambio={setNombre} error={errores.nombre} requerido maxLength={120} autoComplete="off" />
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Campo id="activo-tipo" etiqueta="Tipo" nombre="tipo" valor={tipo} onCambio={setTipo} error={errores.tipo} maxLength={120} autoComplete="off" />
        <Campo id="activo-ubicacion" etiqueta="Ubicación" nombre="ubicacion" valor={ubicacion} onCambio={setUbicacion} error={errores.ubicacion} maxLength={120} autoComplete="off" />
      </div>

      <fieldset className="pb-6">
        <legend className="pb-1.5 text-[0.8125rem] font-medium text-texto">Criticidad</legend>
        <p className="-mt-0.5 pb-2 text-[0.8125rem] leading-5 text-texto-suave">
          Cuánto afecta a la producción que este equipo se detenga.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {CRITICIDADES.map(([valor, texto]) => (
            <label
              key={texto}
              className={[
                "flex h-12 cursor-pointer items-center justify-center rounded-[var(--radius-control)] border text-[0.9375rem] font-medium transition-colors",
                "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                criticidad === valor
                  ? "border-2 border-accion bg-[var(--accion-halo)] text-accion"
                  : "border-borde-fuerte bg-superficie text-texto hover:border-accion",
              ].join(" ")}
            >
              <input type="radio" name="criticidad" className="sr-only" checked={criticidad === valor} onChange={() => setCriticidad(valor)} />
              {texto}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-x-4 sm:grid-cols-2">
        <Campo id="activo-marca" etiqueta="Marca" nombre="marca" valor={marca} onCambio={setMarca} error={errores.marca} maxLength={120} autoComplete="off" />
        <Campo id="activo-modelo" etiqueta="Modelo" nombre="modelo" valor={modelo} onCambio={setModelo} error={errores.modelo} maxLength={120} autoComplete="off" />
        <Campo id="activo-serie" etiqueta="Número de serie" nombre="numero_serie" valor={serie} onCambio={setSerie} error={errores.numero_serie} maxLength={120} autoComplete="off" />
        <Campo id="activo-instalacion" etiqueta="Fecha de instalación" nombre="fecha_instalacion" tipo="date" valor={instalacion} onCambio={setInstalacion} error={errores.fecha_instalacion} />
      </div>

      {conHorometro ? (
        <div className="sm:w-1/2 sm:pr-2">
          <Campo
            id="activo-horometro"
            etiqueta="Horómetro hoy"
            nombre="horometro_inicial"
            valor={horometro}
            onCambio={setHorometro}
            error={errores.horometro_inicial}
            modoTeclado="numeric"
            ayuda="Si lo sabes, queda como primera lectura. Si no, déjalo vacío."
            maxLength={9}
            autoComplete="off"
          />
        </div>
      ) : null}

      <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center">
        <Boton enCurso={enCurso} textoEnCurso="Guardando…">
          {textoBoton}
        </Boton>
        {aviso !== null ? (
          <p role="alert" className="text-[0.9375rem] text-error">
            {aviso}
          </p>
        ) : null}
      </div>
    </form>
  );
}
