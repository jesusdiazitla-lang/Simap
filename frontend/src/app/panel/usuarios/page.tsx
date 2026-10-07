"use client";

/**
 * Personal de la empresa (RF-03): el administrador da de alta a su gente, le asigna el rol y la da de
 * baja.
 *
 * La contraseña de cada alta la genera SIMAP y se muestra **una sola vez**, igual que hace la consola
 * del operador: quien da de alta a alguien no la elige, así que no conserva acceso a esa cuenta una
 * vez que la persona la cambia. Si se pierde antes de entregarla, se genera otra.
 *
 * Dar de baja no borra a nadie: sus lecturas y alertas siguen firmadas con su nombre. Solo deja de
 * poder entrar, y su sesión abierta en cualquier teléfono deja de renovarse.
 */

import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Insignia } from "@/components/estado";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import { etiquetaDeRol, ROLES, type Rol, type Usuario } from "@/lib/auth";
import { fecha } from "@/lib/formato";
import {
  darDeAltaPersona,
  editarPersona,
  listarPersonal,
  restablecerClavePersona,
  type Persona,
  type PersonaConClave,
} from "@/lib/usuarios";

/** Qué hace cada rol, en una línea: para elegir sin tener que preguntar. */
const RESUMEN_ROL: Readonly<Record<Rol, string>> = {
  operario: "Registra horómetros y alertas escaneando los equipos.",
  supervisor: "Lo del operario, más revisar alertas y ver el historial.",
  tecnico_taller: "Atiende las órdenes de trabajo en el taller.",
  gerente: "Consulta equipos, alertas e indicadores. Solo lectura.",
  administrador: "Gestiona personal, equipos y el catálogo de componentes.",
};

export default function PersonalPage() {
  return (
    <Pantalla roles={["administrador"]} cargando="Personal de la empresa">
      {(usuario) => <Personal yo={usuario} />}
    </Pantalla>
  );
}

function Personal({ yo }: { readonly yo: Usuario }) {
  const [lista, setLista] = useState<readonly Persona[] | null>(null);
  const [clave, setClave] = useState<PersonaConClave | null>(null);

  useEffect(() => {
    listarPersonal().then(setLista).catch(() => setLista([]));
  }, []);

  function sustituir(p: Persona): void {
    setLista((l) => (l ?? []).map((x) => (x.id === p.id ? p : x)));
  }

  return (
    <div className="flex flex-col gap-6">
      {clave !== null ? <ClaveUnaVez datos={clave} alCerrar={() => setClave(null)} /> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start">
        <Panel titulo="Personal de la empresa" descripcion="Quién puede entrar en SIMAP y con qué rol.">
          {lista === null ? (
            <Esqueleto />
          ) : (
            <ul className="divide-y divide-borde">
              {lista.map((p) => (
                <FilaPersona key={p.id} persona={p} esYo={p.id === yo.id} alCambiar={sustituir} alClave={setClave} />
              ))}
            </ul>
          )}
        </Panel>

        <Alta
          alCrear={(r) => {
            setLista((l) => [...(l ?? []), r.usuario].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")));
            setClave(r);
          }}
        />
      </div>
    </div>
  );
}

/** La contraseña temporal, visible una sola vez. Arriba del todo: es lo que hay que hacer ahora. */
function ClaveUnaVez({ datos, alCerrar }: { readonly datos: PersonaConClave; readonly alCerrar: () => void }) {
  const [copiada, setCopiada] = useState(false);
  return (
    <section role="status" className="rounded-[var(--radius-control)] border-2 border-accion bg-superficie px-5 py-5 sm:px-6">
      <h2 className="text-[1.0625rem] font-semibold text-texto">Contraseña temporal de {datos.usuario.nombre}</h2>
      <p className="max-w-[65ch] pt-1 text-[0.9375rem] leading-6 text-texto-suave">
        Entrégasela a esa persona. Solo se muestra ahora: no se guarda en ningún sitio. Al entrar
        deberá cambiarla desde su panel.
      </p>
      <div className="flex flex-wrap items-center gap-3 pt-4">
        <code className="rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna px-3 py-2 font-mono text-[1.0625rem] tracking-wide text-texto select-all">
          {datos.password_temporal}
        </code>
        <span className="text-[0.875rem] text-texto-suave">para {datos.usuario.correo}</span>
      </div>
      <div className="flex flex-wrap gap-2 pt-4">
        <Boton
          tipo="button"
          variante="secundario"
          onClick={() => {
            void navigator.clipboard?.writeText(datos.password_temporal).then(() => setCopiada(true));
          }}
        >
          {copiada ? "Copiada" : "Copiar"}
        </Boton>
        <Boton tipo="button" variante="secundario" onClick={alCerrar}>
          Ya la entregué
        </Boton>
      </div>
    </section>
  );
}

function Alta({ alCrear }: { readonly alCrear: (r: PersonaConClave) => void }) {
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [rol, setRol] = useState<Rol>("operario");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);

  async function enviar(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    const fallos: Record<string, string> = {};
    if (nombre.trim().length < 2) fallos.nombre = "Escribe su nombre.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo.trim())) fallos.correo = "Escribe un correo válido.";
    setErrores(fallos);
    if (Object.keys(fallos).length > 0) return;
    setEnCurso(true);
    setAviso(null);
    try {
      alCrear(await darDeAltaPersona({ nombre: nombre.trim(), correo: correo.trim(), rol }));
      setNombre("");
      setCorreo("");
      setRol("operario");
    } catch (fallo) {
      if (fallo instanceof ErrorApi && fallo.estado === 409) setErrores({ correo: fallo.message });
      else setAviso(fallo instanceof ErrorApi ? fallo.message : "No se pudo dar de alta.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel nivel={2} titulo="Dar de alta a una persona">
      <form noValidate onSubmit={(e) => void enviar(e)} className="flex flex-col gap-1">
        <Campo id="persona-nombre" etiqueta="Nombre" nombre="nombre" valor={nombre} onCambio={setNombre} error={errores.nombre} requerido maxLength={200} autoComplete="off" />
        <Campo id="persona-correo" etiqueta="Correo" nombre="correo" tipo="email" valor={correo} onCambio={setCorreo} error={errores.correo} requerido autoComplete="off" />
        <fieldset className="pb-5">
          <legend className="pb-2 text-[0.8125rem] font-medium text-texto">Rol</legend>
          <div className="flex flex-col gap-2">
            {ROLES.map((r) => (
              <label
                key={r}
                className={[
                  "flex cursor-pointer flex-col rounded-[var(--radius-control)] border px-3 py-2.5 transition-colors",
                  "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accion",
                  rol === r ? "border-2 border-accion bg-[var(--accion-halo)]" : "border-borde-fuerte hover:border-accion",
                ].join(" ")}
              >
                <input type="radio" name="rol" className="sr-only" checked={rol === r} onChange={() => setRol(r)} />
                <span className={["text-[0.9375rem] font-semibold", rol === r ? "text-accion" : "text-texto"].join(" ")}>
                  {etiquetaDeRol(r)}
                </span>
                <span className="text-[0.8125rem] leading-5 text-texto-suave">{RESUMEN_ROL[r]}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <Boton anchoCompleto enCurso={enCurso} textoEnCurso="Dando de alta…">
          Dar de alta y generar contraseña
        </Boton>
        {aviso !== null ? <p role="alert" className="pt-2 text-[0.875rem] text-error">{aviso}</p> : null}
      </form>
    </Panel>
  );
}

function FilaPersona({
  persona,
  esYo,
  alCambiar,
  alClave,
}: {
  readonly persona: Persona;
  readonly esYo: boolean;
  readonly alCambiar: (p: Persona) => void;
  readonly alClave: (r: PersonaConClave) => void;
}) {
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmarBaja, setConfirmarBaja] = useState(false);

  async function hacer(accion: () => Promise<void>): Promise<void> {
    setEnCurso(true);
    setError(null);
    try {
      await accion();
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo completar.");
    } finally {
      setEnCurso(false);
      setConfirmarBaja(false);
    }
  }

  const idRol = `rol-${persona.id}`;

  return (
    <li className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <span className={["text-[0.9375rem] font-semibold", persona.activo ? "text-texto" : "text-texto-tenue"].join(" ")}>
            {persona.nombre}
          </span>
          {esYo ? <Insignia tono="neutro">Tú</Insignia> : null}
          {!persona.activo ? <Insignia tono="neutro">De baja</Insignia> : null}
        </p>
        <p className="text-[0.875rem] text-texto-suave [overflow-wrap:anywhere]">{persona.correo}</p>
        <p className="text-[0.8125rem] text-texto-tenue">Desde el {fecha(persona.creado_en)}</p>
        {error !== null ? <p role="alert" className="pt-1 text-[0.875rem] text-error">{error}</p> : null}
      </div>

      <div className="flex shrink-0 flex-col gap-2 sm:w-80">
        <label htmlFor={idRol} className="sr-only">
          Rol de {persona.nombre}
        </label>
        <select
          id={idRol}
          value={persona.rol}
          disabled={enCurso || !persona.activo || esYo}
          onChange={(e) => void hacer(async () => alCambiar(await editarPersona(persona.id, { rol: e.target.value as Rol })))}
          className="h-11 w-full cursor-pointer rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[0.9375rem] text-texto disabled:cursor-not-allowed disabled:bg-superficie-alterna disabled:text-texto-tenue"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {etiquetaDeRol(r)}
            </option>
          ))}
        </select>
        {esYo ? null : confirmarBaja ? (
          <div className="flex flex-col gap-2 rounded-[var(--radius-control)] border border-estado-aviso p-2">
            <p className="text-[0.8125rem] leading-5 text-texto">
              No podrá entrar, y su sesión abierta se cerrará. Lo que registró se conserva.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Boton tipo="button" variante="secundario" onClick={() => setConfirmarBaja(false)}>
                Cancelar
              </Boton>
              <Boton tipo="button" variante="secundario" enCurso={enCurso} textoEnCurso="…" onClick={() => void hacer(async () => alCambiar(await editarPersona(persona.id, { activo: false })))}>
                Dar de baja
              </Boton>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {persona.activo ? (
              <>
                <Boton tipo="button" variante="secundario" deshabilitado={enCurso} onClick={() => void hacer(async () => alClave(await restablecerClavePersona(persona.id)))}>
                  Nueva clave
                </Boton>
                <Boton tipo="button" variante="secundario" deshabilitado={enCurso} onClick={() => setConfirmarBaja(true)}>
                  Dar de baja
                </Boton>
              </>
            ) : (
              <Boton tipo="button" variante="secundario" deshabilitado={enCurso} onClick={() => void hacer(async () => alCambiar(await editarPersona(persona.id, { activo: true })))}>
                Reactivar
              </Boton>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
