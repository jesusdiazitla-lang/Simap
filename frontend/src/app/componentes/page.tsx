"use client";

/**
 * Catálogo de componentes de la empresa (05-fase2-activos-y-campo.md, 5 y 7.1).
 *
 * Los componentes se renombran y se desactivan, no se borran: en la fase 3 cada orden de trabajo dice
 * qué componente falló, y en la fase 4 el riesgo se calcula por componente. Desactivar uno lo saca de
 * las listas de elección sin romper la historia que ya lo nombra.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Insignia } from "@/components/estado";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import {
  cargarPlantilla,
  crearComponente,
  editarComponente,
  listarComponentes,
  type Componente,
} from "@/lib/activos";

export default function ComponentesPage() {
  return (
    <Pantalla roles={["administrador"]} cargando="Catálogo de componentes">
      {() => <Catalogo />}
    </Pantalla>
  );
}

function Catalogo() {
  const [lista, setLista] = useState<readonly Componente[] | null>(null);
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [enCurso, setEnCurso] = useState(false);

  useEffect(() => {
    listarComponentes(true)
      .then(setLista)
      .catch(() => setLista([]));
  }, []);

  function sustituir(c: Componente): void {
    setLista((l) => (l ?? []).map((x) => (x.id === c.id ? c : x)));
  }

  async function crear(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (nombre.trim().length < 2) {
      setError("Escribe el nombre del componente.");
      return;
    }
    setEnCurso(true);
    try {
      const c = await crearComponente(nombre.trim(), descripcion.trim() === "" ? null : descripcion.trim());
      setLista((l) => [...(l ?? []), c].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")));
      setNombre("");
      setDescripcion("");
      setError(undefined);
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo crear.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <Panel
        titulo="Catálogo de componentes"
        descripcion="Las partes de los equipos que pueden fallar. Sobre cada una se calculará el riesgo."
      >
        {lista === null ? (
          <Esqueleto />
        ) : lista.length === 0 ? (
          <CatalogoVacio
            alCargar={(nuevos) =>
              setLista([...nuevos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")))
            }
          />
        ) : (
          <ul className="divide-y divide-borde">
            {lista.map((c) => (
              <FilaComponente key={c.id} componente={c} alCambiar={sustituir} />
            ))}
          </ul>
        )}
      </Panel>

      <Panel nivel={2} titulo="Añadir componente">
        <form noValidate onSubmit={(e) => void crear(e)} className="flex flex-col gap-1">
          <Campo id="componente-nombre" etiqueta="Nombre" nombre="nombre" valor={nombre} onCambio={setNombre} error={error} requerido maxLength={120} autoComplete="off" />
          <Campo id="componente-descripcion" etiqueta="Descripción" nombre="descripcion" valor={descripcion} onCambio={setDescripcion} maxLength={500} autoComplete="off" />
          <Boton variante="secundario" anchoCompleto enCurso={enCurso} textoEnCurso="Añadiendo…" deshabilitado={nombre.trim() === ""}>
            Añadir al catálogo
          </Boton>
        </form>
      </Panel>
    </div>
  );
}

/**
 * Las empresas nuevas nacen con el catálogo inicial. Las que se dieron de alta antes de que existiera
 * llegan vacías: en vez de una caja en blanco, se ofrece cargarlo con un toque.
 */
function CatalogoVacio({ alCargar }: { readonly alCargar: (c: readonly Componente[]) => void }) {
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-start gap-4">
      <p className="max-w-[60ch] text-[0.9375rem] leading-6 text-texto-suave">
        El catálogo está vacío. Puedes empezar con el catálogo inicial de SIMAP —motor, tren motriz,
        sistema hidráulico, rodamientos y otros cuatro— y ajustarlo después a tus equipos, o añadir
        los tuyos uno a uno.
      </p>
      <Boton
        tipo="button"
        enCurso={enCurso}
        textoEnCurso="Cargando…"
        onClick={() => {
          setEnCurso(true);
          void cargarPlantilla()
            .then(alCargar)
            .catch((e: unknown) => {
              setError(e instanceof ErrorApi ? e.message : "No se pudo cargar.");
              setEnCurso(false);
            });
        }}
      >
        Cargar catálogo inicial
      </Boton>
      {error !== null ? <p role="alert" className="text-[0.875rem] text-error">{error}</p> : null}
    </div>
  );
}

function FilaComponente({
  componente,
  alCambiar,
}: {
  readonly componente: Componente;
  readonly alCambiar: (c: Componente) => void;
}) {
  const [editando, setEditando] = useState<"nombre" | "vida" | null>(null);
  const [nombre, setNombre] = useState(componente.nombre);
  const [vida, setVida] = useState(componente.vida_nominal_horas?.toString() ?? "");
  const [error, setError] = useState<string | undefined>();
  const [enCurso, setEnCurso] = useState(false);

  async function guardar(cambios: {
    nombre?: string;
    activo?: boolean;
    vida_nominal_horas?: number | null;
  }): Promise<void> {
    setEnCurso(true);
    try {
      alCambiar(await editarComponente(componente.id, cambios));
      setEditando(null);
      setError(undefined);
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo guardar.");
    } finally {
      setEnCurso(false);
    }
  }

  if (editando === "vida") {
    const n = Number(vida);
    const vacia = vida.trim() === "";
    const valida = vacia || (/^\d+$/.test(vida) && n >= 10 && n <= 1_000_000);
    return (
      <li className="py-3 first:pt-0 last:pb-0">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (!valida) {
              setError("Entre 10 y 1,000,000 horas, o vacío si no se conoce.");
              return;
            }
            void guardar({ vida_nominal_horas: vacia ? null : n });
          }}
          className="flex flex-col gap-1"
        >
          <Campo
            id={`vida-${componente.id}`}
            etiqueta={`Vida nominal de ${componente.nombre}, en horas`}
            ayuda="Lo que dura normalmente según el fabricante o la experiencia de la planta. El modelo parte de aquí y se corrige con las fallas reales. Vacío si no se conoce."
            nombre="vida_nominal_horas"
            modoTeclado="numeric"
            valor={vida}
            onCambio={(v) => setVida(v.replace(/\D/g, ""))}
            error={error}
            maxLength={7}
            autoFocus
            autoComplete="off"
          />
          <div className="flex gap-2">
            <Boton enCurso={enCurso} textoEnCurso="Guardando…">Guardar</Boton>
            <Boton tipo="button" variante="secundario" onClick={() => setEditando(null)}>
              Cancelar
            </Boton>
          </div>
        </form>
      </li>
    );
  }

  if (editando === "nombre") {
    return (
      <li className="py-3 first:pt-0 last:pb-0">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void guardar({ nombre: nombre.trim() });
          }}
          className="flex flex-col gap-1"
        >
          <Campo id={`renombrar-${componente.id}`} etiqueta="Nuevo nombre" nombre="nombre" valor={nombre} onCambio={setNombre} error={error} maxLength={120} autoFocus autoComplete="off" />
          <div className="flex gap-2">
            <Boton enCurso={enCurso} textoEnCurso="Guardando…">Guardar</Boton>
            <Boton tipo="button" variante="secundario" onClick={() => setEditando(null)}>
              Cancelar
            </Boton>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className={["text-[0.9375rem] font-semibold", componente.activo ? "text-texto" : "text-texto-tenue"].join(" ")}>
          {componente.nombre}
        </p>
        {componente.descripcion !== null ? (
          <p className="text-[0.875rem] leading-5 text-texto-suave">{componente.descripcion}</p>
        ) : null}
        <p className="pt-0.5 text-[0.8125rem] text-texto-tenue">
          {componente.vida_nominal_horas !== null
            ? `Vida nominal: ${componente.vida_nominal_horas.toLocaleString("en-US")} h · `
            : "Sin vida nominal · "}
          <Link href={`/componentes/${componente.id}/modelo`} className="text-accion underline-offset-2 hover:underline">
            Ver modelo
          </Link>
        </p>
        {error !== undefined ? <p role="alert" className="text-[0.8125rem] text-error">{error}</p> : null}
      </div>
      <div className="flex items-center gap-2">
        {!componente.activo ? <Insignia tono="neutro">Desactivado</Insignia> : null}
        <button
          type="button"
          onClick={() => setEditando("vida")}
          className="h-11 cursor-pointer rounded-[var(--radius-control)] px-3 text-[0.875rem] font-medium text-accion hover:underline"
        >
          Vida nominal
        </button>
        <button
          type="button"
          onClick={() => setEditando("nombre")}
          className="h-11 cursor-pointer rounded-[var(--radius-control)] px-3 text-[0.875rem] font-medium text-accion hover:underline"
        >
          Renombrar
        </button>
        <button
          type="button"
          disabled={enCurso}
          onClick={() => void guardar({ activo: !componente.activo })}
          className="h-11 cursor-pointer rounded-[var(--radius-control)] px-3 text-[0.875rem] font-medium text-accion hover:underline disabled:cursor-progress"
        >
          {componente.activo ? "Desactivar" : "Reactivar"}
        </button>
      </div>
    </li>
  );
}
