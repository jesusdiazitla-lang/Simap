"use client";

/**
 * Consola del operador de SIMAP: dar de alta clientes y mantenerlos.
 *
 * Lo que se ve aquí es **todo** lo que el plano de control puede ver: nombre de la empresa, quién
 * es su administrador, si está activa y cuántos equipos tiene monitoreados. Ni un activo, ni una
 * orden, ni una lectura. No es que la pantalla no los pinte: es que el rol de base de datos con el
 * que se atienden estas peticiones no tiene permiso para leerlos.
 *
 * La contraseña temporal aparece **una sola vez**, al crear la empresa o al restablecerla. No se
 * guarda en claro en ningún sitio, así que si se cierra el aviso sin copiarla hay que generar otra.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { EtiquetaConsola, FechaHora, Marco, Panel } from "@/components/marco";
import { ErrorApi } from "@/lib/api";
import {
  altaEmpresa,
  cambiarEstado,
  ETIQUETA_ACCION,
  leerBitacora,
  listarEmpresas,
  operadorActual,
  renombrarEmpresa,
  restablecerClave,
  salirDeLaConsola,
  type AsientoBitacora,
  type ClaveTemporal,
  type EmpresaResumen,
  type Operador,
} from "@/lib/operador";

const esquemaAlta = z.object({
  empresa: z.string().trim().min(2, "El nombre de la empresa es demasiado corto."),
  admin_nombre: z.string().trim().min(2, "El nombre de la persona es demasiado corto."),
  admin_correo: z
    .string()
    .trim()
    .min(1, "Escribe el correo del administrador.")
    .email("Ese correo no tiene un formato válido."),
});

type CampoAlta = "empresa" | "admin_nombre" | "admin_correo";

export default function ConsolaPage() {
  const router = useRouter();
  const [operador, setOperador] = useState<Operador | null>(null);
  const [empresas, setEmpresas] = useState<readonly EmpresaResumen[]>([]);
  const [bitacora, setBitacora] = useState<readonly AsientoBitacora[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clave, setClave] = useState<ClaveTemporal | null>(null);
  const [ocupada, setOcupada] = useState<string | null>(null);

  const recargar = useCallback(async (signal?: AbortSignal): Promise<void> => {
    const [lista, asientos] = await Promise.all([listarEmpresas(signal), leerBitacora(signal)]);
    setEmpresas(lista);
    setBitacora(asientos);
  }, []);

  useEffect(() => {
    const control = new AbortController();
    void (async () => {
      try {
        const yo = await operadorActual(control.signal);
        if (yo === null) {
          router.replace("/operador/login");
          return;
        }
        setOperador(yo);
        await recargar(control.signal);
      } catch (fallo) {
        if (fallo instanceof DOMException && fallo.name === "AbortError") return;
        setError(
          fallo instanceof ErrorApi
            ? fallo.message
            : "No se pudo cargar la consola. Comprueba la conexión.",
        );
      } finally {
        setCargando(false);
      }
    })();
    return () => control.abort();
  }, [router, recargar]);

  async function conEmpresa(id: string, accion: () => Promise<unknown>): Promise<void> {
    setOcupada(id);
    setError(null);
    try {
      await accion();
      await recargar();
    } catch (fallo) {
      setError(fallo instanceof ErrorApi ? fallo.message : "No se pudo completar la acción.");
    } finally {
      setOcupada(null);
    }
  }

  if (cargando) {
    return (
      <Marco barra={<EtiquetaConsola />}>
        <Panel titulo="Cargando la consola">
          <div aria-busy="true" aria-live="polite" className="flex flex-col gap-3">
            <span className="sr-only">Cargando…</span>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-4 w-full max-w-md rounded-[var(--radius-control)] bg-superficie-alterna"
              />
            ))}
          </div>
        </Panel>
      </Marco>
    );
  }

  return (
    <Marco
      barra={
        <div className="flex min-w-0 items-center gap-3">
          <EtiquetaConsola />
          <FechaHora />
          <span className="hidden truncate text-[0.8125rem] text-texto-suave md:block">
            {operador?.nombre}
          </span>
          <button
            type="button"
            onClick={() => {
              void salirDeLaConsola().finally(() => router.replace("/operador/login"));
            }}
            className="h-9 shrink-0 cursor-pointer rounded-[var(--radius-control)] border border-borde-fuerte px-3 text-[0.8125rem] font-medium text-texto-suave transition-colors hover:border-error hover:text-error"
          >
            Cerrar sesión
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-6">
        {error !== null ? (
          <p
            role="alert"
            className="rounded-[var(--radius-control)] border border-error bg-error-fondo px-3 py-2 text-[0.875rem] leading-5 text-error"
          >
            {error}
          </p>
        ) : null}

        {clave !== null ? <AvisoClave clave={clave} onCerrar={() => setClave(null)} /> : null}

        <FormularioAlta
          onCreada={async (nueva) => {
            setClave(nueva);
            await recargar();
          }}
        />

        <TablaEmpresas
          empresas={empresas}
          ocupada={ocupada}
          onSuspender={(e) => conEmpresa(e.id, () => cambiarEstado(e.id, !e.activa))}
          onRenombrar={(e, nombre) => conEmpresa(e.id, () => renombrarEmpresa(e.id, nombre))}
          onRestablecer={(e) =>
            conEmpresa(e.id, async () => setClave(await restablecerClave(e.id)))
          }
        />

        <Bitacora asientos={bitacora} />

        <Panel titulo="Tu cuenta" descripcion={operador?.correo}>
          <Link
            href="/operador/clave"
            className="inline-flex h-11 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.875rem] font-medium text-texto transition-colors hover:bg-superficie-alterna"
          >
            Cambiar mi contraseña
          </Link>
        </Panel>
      </div>
    </Marco>
  );
}

/** La contraseña temporal, que solo existe en esta respuesta. */
function AvisoClave({
  clave,
  onCerrar,
}: {
  readonly clave: ClaveTemporal;
  readonly onCerrar: () => void;
}) {
  return (
    <section
      role="alert"
      className="rounded-[var(--radius-control)] border border-accion bg-superficie p-4"
    >
      <h2 className="text-[0.9375rem] font-semibold text-texto">Contraseña temporal</h2>
      <p className="pt-1 text-[0.875rem] leading-5 text-texto-suave">
        Cópiala y entrégasela a <strong className="font-semibold text-texto">{clave.correo}</strong>
        . No se guarda en ningún sitio: si cierras este aviso sin copiarla, tendrás que generar otra.
      </p>
      <div className="flex flex-wrap items-center gap-3 pt-3">
        <code className="select-all rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie-alterna px-3 py-2 font-mono text-[1rem] text-texto">
          {clave.password_temporal}
        </code>
        <Boton
          tipo="button"
          variante="secundario"
          onClick={() => void navigator.clipboard?.writeText(clave.password_temporal)}
        >
          Copiar
        </Boton>
        <Boton tipo="button" variante="secundario" onClick={onCerrar}>
          Cerrar
        </Boton>
      </div>
    </section>
  );
}

function FormularioAlta({
  onCreada,
}: {
  readonly onCreada: (clave: ClaveTemporal) => Promise<void>;
}) {
  const [empresa, setEmpresa] = useState("");
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [errores, setErrores] = useState<Partial<Record<CampoAlta, string>>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);

  async function enviar(evento: React.FormEvent<HTMLFormElement>): Promise<void> {
    evento.preventDefault();
    if (enCurso) return;

    const datos = { empresa, admin_nombre: nombre, admin_correo: correo };
    const resultado = esquemaAlta.safeParse(datos);
    if (!resultado.success) {
      const nuevos: Partial<Record<CampoAlta, string>> = {};
      for (const problema of resultado.error.issues) {
        const campo = problema.path[0] as CampoAlta | undefined;
        if (campo !== undefined) nuevos[campo] ??= problema.message;
      }
      setErrores(nuevos);
      return;
    }

    setErrores({});
    setAviso(null);
    setEnCurso(true);
    try {
      const clave = await altaEmpresa(resultado.data);
      setEmpresa("");
      setNombre("");
      setCorreo("");
      await onCreada(clave);
    } catch (fallo) {
      setAviso(fallo instanceof ErrorApi ? fallo.message : "No se pudo dar de alta la empresa.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel
      titulo="Dar de alta una empresa"
      descripcion="Crea la empresa y su primer administrador. La contraseña la genera SIMAP y se muestra una sola vez."
    >
      <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Campo
            id="alta-empresa"
            etiqueta="Empresa"
            nombre="empresa"
            valor={empresa}
            onCambio={setEmpresa}
            error={errores.empresa}
            requerido
            deshabilitado={enCurso}
          />
          <Campo
            id="alta-admin-nombre"
            etiqueta="Administrador"
            nombre="admin_nombre"
            valor={nombre}
            onCambio={setNombre}
            error={errores.admin_nombre}
            requerido
            deshabilitado={enCurso}
          />
          <Campo
            id="alta-admin-correo"
            etiqueta="Correo del administrador"
            nombre="admin_correo"
            tipo="email"
            valor={correo}
            onCambio={setCorreo}
            error={errores.admin_correo}
            autoComplete="off"
            requerido
            deshabilitado={enCurso}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Boton enCurso={enCurso} textoEnCurso="Creando…">
            Crear empresa
          </Boton>
          {aviso !== null ? (
            <p role="alert" className="text-[0.875rem] leading-5 text-error">
              {aviso}
            </p>
          ) : null}
        </div>
      </form>
    </Panel>
  );
}

function TablaEmpresas({
  empresas,
  ocupada,
  onSuspender,
  onRenombrar,
  onRestablecer,
}: {
  readonly empresas: readonly EmpresaResumen[];
  readonly ocupada: string | null;
  readonly onSuspender: (empresa: EmpresaResumen) => void;
  readonly onRenombrar: (empresa: EmpresaResumen, nombre: string) => void;
  readonly onRestablecer: (empresa: EmpresaResumen) => void;
}) {
  const [filtro, setFiltro] = useState("");

  // Filtrado en el cliente y no en el servidor: la lista de clientes de un operador se cuenta por
  // decenas o cientos, no por miles, así que ya está entera en memoria y hacer un viaje por cada
  // tecla sería peor para todos. El día que haga falta paginar, el filtro se sube al endpoint.
  const termino = filtro.trim().toLowerCase();
  const visibles =
    termino === ""
      ? empresas
      : empresas.filter(
          (e) =>
            e.nombre.toLowerCase().includes(termino) ||
            (e.admin_correo ?? "").toLowerCase().includes(termino),
        );

  return (
    <Panel
      titulo={`Empresas clientes (${empresas.length})`}
      descripcion="Solo lo necesario para facturar y dar soporte. Los datos de mantenimiento de cada empresa no son visibles desde aquí."
    >
      {empresas.length > 8 ? (
        <div className="pb-4">
          <label htmlFor="filtro-empresas" className="sr-only">
            Buscar por empresa o correo del administrador
          </label>
          <input
            id="filtro-empresas"
            type="search"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            placeholder="Buscar por empresa o correo…"
            className="h-10 w-full max-w-sm rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[0.875rem] text-texto transition-colors focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]"
          />
          <p aria-live="polite" className="pt-1.5 text-[0.8125rem] text-texto-tenue">
            {termino === ""
              ? `${empresas.length} empresas`
              : `${visibles.length} de ${empresas.length}`}
          </p>
        </div>
      ) : null}

      {empresas.length === 0 ? (
        <p className="text-[0.9375rem] leading-6 text-texto-suave">
          Todavía no hay ninguna empresa dada de alta. Usa el formulario de arriba para crear la
          primera.
        </p>
      ) : visibles.length === 0 ? (
        <p className="text-[0.9375rem] leading-6 text-texto-suave">
          Ninguna empresa coincide con «{filtro.trim()}».
        </p>
      ) : (
        // overflow-x en el contenedor y no en la página: una tabla ancha se desplaza dentro de su
        // panel, sin arrastrar consigo el resto de la pantalla.
        <div className="-mx-5 overflow-x-auto sm:-mx-6">
          <table className="w-full min-w-[46rem] border-collapse text-[0.875rem]">
            <thead>
              <tr className="border-b border-borde text-left text-[0.75rem] uppercase tracking-wide text-texto-tenue">
                <th scope="col" className="px-5 py-2 font-medium sm:px-6">
                  Empresa
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Administrador
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Equipos
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Estado
                </th>
                <th scope="col" className="px-5 py-2 text-right font-medium sm:px-6">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((empresa) => (
                <FilaEmpresa
                  key={empresa.id}
                  empresa={empresa}
                  ocupada={ocupada === empresa.id}
                  onSuspender={onSuspender}
                  onRenombrar={onRenombrar}
                  onRestablecer={onRestablecer}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function FilaEmpresa({
  empresa,
  ocupada,
  onSuspender,
  onRenombrar,
  onRestablecer,
}: {
  readonly empresa: EmpresaResumen;
  readonly ocupada: boolean;
  readonly onSuspender: (empresa: EmpresaResumen) => void;
  readonly onRenombrar: (empresa: EmpresaResumen, nombre: string) => void;
  readonly onRestablecer: (empresa: EmpresaResumen) => void;
}) {
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(empresa.nombre);

  return (
    <tr className="border-b border-borde last:border-0 align-middle">
      <td className="px-5 py-3 sm:px-6">
        {editando ? (
          <div className="flex items-center gap-2">
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              aria-label={`Nuevo nombre de ${empresa.nombre}`}
              className="h-9 w-full min-w-0 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-2 text-[0.875rem] text-texto focus:border-accion focus:outline-none"
            />
            <button
              type="button"
              onClick={() => {
                setEditando(false);
                if (nombre.trim() !== empresa.nombre) onRenombrar(empresa, nombre);
              }}
              className="h-9 shrink-0 cursor-pointer text-[0.8125rem] font-medium text-accion"
            >
              Guardar
            </button>
          </div>
        ) : (
          <span className="font-medium text-texto">{empresa.nombre}</span>
        )}
      </td>

      <td className="px-3 py-3 text-texto-suave">
        {empresa.admin_correo ?? <span className="text-texto-tenue">sin administrador</span>}
      </td>

      <td className="px-3 py-3 text-right tabular-nums text-texto-suave">
        {/* `null` no es cero: la tabla de activos llega en F2 y hasta entonces no hay nada que
            contar. Pintar un 0 aquí acabaría en una factura equivocada. */}
        {empresa.equipos ?? <span className="text-texto-tenue">— F2</span>}
      </td>

      <td className="px-3 py-3">
        <EstadoEmpresa activa={empresa.activa} />
      </td>

      <td className="px-5 py-3 text-right sm:px-6">
        <div className="flex flex-wrap justify-end gap-2">
          <AccionFila
            texto={editando ? "Cancelar" : "Renombrar"}
            onClick={() => {
              setNombre(empresa.nombre);
              setEditando((v) => !v);
            }}
            ocupada={ocupada}
          />
          <AccionFila
            texto="Restablecer clave"
            onClick={() => onRestablecer(empresa)}
            ocupada={ocupada}
          />
          <AccionFila
            texto={empresa.activa ? "Suspender" : "Reactivar"}
            onClick={() => onSuspender(empresa)}
            ocupada={ocupada}
            peligrosa={empresa.activa}
          />
        </div>
      </td>
    </tr>
  );
}

function AccionFila({
  texto,
  onClick,
  ocupada,
  peligrosa = false,
}: {
  readonly texto: string;
  readonly onClick: () => void;
  readonly ocupada: boolean;
  readonly peligrosa?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={ocupada}
      className={[
        "h-8 cursor-pointer rounded-[var(--radius-control)] border px-2.5 text-[0.8125rem] font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:border-borde disabled:text-texto-tenue",
        peligrosa
          ? "border-borde-fuerte text-texto-suave hover:border-error hover:text-error"
          : "border-borde-fuerte text-accion hover:border-accion",
      ].join(" ")}
    >
      {texto}
    </button>
  );
}

/** El estado va con texto además de color: nunca solo con el color. */
function EstadoEmpresa({ activa }: { readonly activa: boolean }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 text-[0.8125rem] font-medium",
        activa ? "text-estado-ok" : "text-estado-falla",
      ].join(" ")}
    >
      <span aria-hidden="true" className="h-2 w-2 rounded-full bg-current" />
      {activa ? "Activa" : "Suspendida"}
    </span>
  );
}

function Bitacora({ asientos }: { readonly asientos: readonly AsientoBitacora[] }) {
  return (
    <Panel
      titulo="Bitácora"
      descripcion="Toda acción sobre una empresa queda registrada, incluido quién la hizo."
    >
      {asientos.length === 0 ? (
        <p className="text-[0.9375rem] leading-6 text-texto-suave">Todavía no hay movimientos.</p>
      ) : (
        <ul className="flex flex-col">
          {asientos.map((asiento) => (
            <li
              key={asiento.id}
              className="flex flex-col gap-0.5 border-b border-borde py-2.5 last:border-0 sm:flex-row sm:items-baseline sm:gap-4"
            >
              <time
                dateTime={asiento.creado_en}
                className="shrink-0 tabular-nums text-[0.8125rem] text-texto-tenue sm:w-40"
              >
                {new Date(asiento.creado_en).toLocaleString("es-DO", {
                  day: "2-digit",
                  month: "2-digit",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              <span className="shrink-0 text-[0.8125rem] font-medium text-texto sm:w-48">
                {ETIQUETA_ACCION[asiento.accion] ?? asiento.accion}
              </span>
              <span className="min-w-0 flex-1 text-[0.875rem] text-texto-suave">
                {asiento.detalle}
              </span>
              <span className="shrink-0 text-[0.8125rem] text-texto-tenue">
                {asiento.operador_nombre}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
