"use client";

/**
 * Pantalla del equipo: lo que se abre al escanear su etiqueta (RF-07; 05-fase2-activos-y-campo.md,
 * 7.2). Se sirve en `/a/{código}` —es lo que codifica el QR— mediante una reescritura de
 * `next.config.ts`, y lee el código de la barra de direcciones.
 *
 * ORDEN DE LA PANTALLA, Y POR QUÉ
 * --------------------------------
 * 1. **Primero, qué máquina es**: nombre, ubicación, código y última lectura con su fecha. Quien
 *    escanea confirma que la etiqueta corresponde a la máquina que tiene delante; una etiqueta
 *    pegada en el equipo equivocado mandaría datos a otro activo y contaminaría su historial sin que
 *    nada fallara técnicamente.
 * 2. **Después, lo que su rol puede hacer**, sin menús intermedios: el operario tiene el horómetro y
 *    la alerta a la vista. Escanear, rellenar, enviar: tres pasos (RNF-03).
 * 3. **El historial y la gestión**, para quien los usa.
 *
 * SIN COBERTURA
 * -------------
 * Si no hay red, se muestra la ficha guardada la última vez que esta persona escaneó el equipo,
 * marcada como no actualizada, y los formularios siguen funcionando: lo registrado queda en la cola
 * del teléfono.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EstadoEquipo, Criticidad, EstadoAlertaInsignia, RequiereRevision } from "@/components/estado";
import { FormularioAlerta } from "@/components/formulario-alerta";
import { FormularioFalla } from "@/components/formulario-falla";
import { FormularioHorometro } from "@/components/formulario-horometro";
import { IconoAviso, IconoImprimir } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { EnlaceBoton, Esqueleto, Pantalla } from "@/components/pantalla";
import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { RiesgoPorComponente } from "@/components/riesgo";
import { ErrorApi } from "@/lib/api";
import {
  activoPorCodigo,
  darDeBaja,
  regenerarCodigo,
  reiniciarHorometro,
  type Activo,
} from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import {
  ETIQUETA_SINTOMA,
  historialLecturas,
  listarAlertas,
  type Alerta,
  type Lectura,
} from "@/lib/campo";
import { fecha, fechaHora, hace, horas } from "@/lib/formato";
import { equipoGuardado, guardarEquipo, guardarRiesgo } from "@/lib/offline-queue";
import { leerHorometro } from "@/lib/horometro";
import { ETIQUETA_ESTADO_ORDEN, numeroOrden } from "@/lib/ordenes";
import {
  listarAlertasSistema,
  numero,
  porcentaje,
  riesgoDelEquipo,
  type AlertaSistema,
  type RiesgoEquipo,
} from "@/lib/prediccion";
import { normalizarCodigo, presentarCodigo } from "@/lib/qr";

type Carga =
  | { readonly tipo: "cargando" }
  | {
      readonly tipo: "listo";
      readonly activo: Activo;
      readonly guardadoEn: number | null;
      /** Sin red: el último riesgo guardado en este teléfono, si lo hay. */
      readonly riesgoGuardado: RiesgoEquipo | null;
    }
  | { readonly tipo: "no-encontrado" }
  | { readonly tipo: "sin-datos" }
  | { readonly tipo: "error"; readonly mensaje: string };

function codigoDeLaDireccion(): string | null {
  const m = /^\/a\/([^/]+)$/.exec(window.location.pathname);
  return m === null ? null : normalizarCodigo(decodeURIComponent(m[1]));
}

export default function EquipoPage() {
  return (
    <Pantalla cargando="Abriendo el equipo">
      {(usuario, sinRed) => <Equipo usuario={usuario} sinRed={sinRed} />}
    </Pantalla>
  );
}

function Equipo({ usuario, sinRed }: { readonly usuario: Usuario; readonly sinRed: boolean }) {
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });

  useEffect(() => {
    const codigo = codigoDeLaDireccion();
    const control = new AbortController();
    void (async () => {
      if (codigo === null) {
        setCarga({ tipo: "no-encontrado" });
        return;
      }
      try {
        const activo = await activoPorCodigo(codigo, control.signal);
        await guardarEquipo(usuario.id, activo);
        setCarga({ tipo: "listo", activo, guardadoEn: null, riesgoGuardado: null });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ErrorApi && error.estado === 404) {
          setCarga({ tipo: "no-encontrado" });
          return;
        }
        if (error instanceof ErrorApi && error.esFalloDeRed) {
          const guardado = await equipoGuardado(usuario.id, codigo);
          setCarga(
            guardado === null
              ? { tipo: "sin-datos" }
              : {
                  tipo: "listo",
                  activo: guardado.activo,
                  guardadoEn: guardado.guardado_en,
                  // Lo guardó esta misma pantalla con la respuesta de riesgoDelEquipo.
                  riesgoGuardado: (guardado.riesgo as RiesgoEquipo | null) ?? null,
                },
          );
          return;
        }
        setCarga({
          tipo: "error",
          mensaje: error instanceof ErrorApi ? error.message : "No se pudo abrir el equipo.",
        });
      }
    })();
    return () => control.abort();
  }, [usuario.id, sinRed]);

  if (carga.tipo === "cargando") {
    return (
      <Panel titulo="Abriendo el equipo">
        <Esqueleto />
      </Panel>
    );
  }
  if (carga.tipo === "no-encontrado") {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="No encontramos este equipo">
          <p className="pb-4 text-[0.9375rem] leading-6 text-texto-suave">
            Este código no corresponde a ningún equipo de tu empresa. Si la etiqueta se reimprimió hace
            poco, puede que la vieja ya no sirva: avisa a tu supervisor.
          </p>
          <EnlaceBoton href="/escanear">Escanear otra etiqueta</EnlaceBoton>
        </Panel>
      </div>
    );
  }
  if (carga.tipo === "sin-datos") {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="Sin conexión">
          <p className="text-[0.9375rem] leading-6 text-texto-suave">
            Este teléfono no tiene red y este equipo no está guardado en él, porque no lo has escaneado
            antes con cobertura. Anota la lectura y regístrala cuando vuelva la red.
          </p>
        </Panel>
      </div>
    );
  }
  if (carga.tipo === "error") {
    return (
      <div className="mx-auto max-w-xl">
        <Panel titulo="No se pudo abrir el equipo">
          <p className="text-[0.9375rem] leading-6 text-error">{carga.mensaje}</p>
        </Panel>
      </div>
    );
  }

  return (
    <FichaEquipo
      usuario={usuario}
      inicial={carga.activo}
      guardadoEn={carga.guardadoEn}
      riesgoGuardado={carga.riesgoGuardado}
    />
  );
}

function FichaEquipo({
  usuario,
  inicial,
  guardadoEn,
  riesgoGuardado,
}: {
  readonly usuario: Usuario;
  readonly inicial: Activo;
  readonly guardadoEn: number | null;
  readonly riesgoGuardado: RiesgoEquipo | null;
}) {
  const [activo, setActivo] = useState(inicial);
  const rol = usuario.rol;
  const capturaEnCampo = (rol === "operario" || rol === "supervisor") && activo.estado === "activo";
  const veHistorial = rol === "supervisor" || rol === "administrador" || rol === "gerente";
  const gestiona = rol === "administrador";
  // Reportar falla: supervisor y administrador (06-fase3, tabla 11.1). Funciona sin red: se queda en
  // la cola del teléfono, como una lectura.
  const reportaFalla = (rol === "supervisor" || rol === "administrador") && activo.estado === "activo";

  const alRegistrar = useCallback((l: Lectura) => {
    setActivo((a) =>
      l.valor_horometro >= a.horometro_actual
        ? { ...a, horometro_actual: l.valor_horometro, horometro_actualizado_en: l.capturado_en }
        : a,
    );
  }, []);

  return (
    <div className="flex flex-col gap-6">
      {guardadoEn !== null ? (
        <p
          role="status"
          className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto"
        >
          <IconoAviso className="mt-0.5 text-estado-aviso" />
          <span>
            Sin conexión. Ves los datos guardados en este teléfono (
            {hace(new Date(guardadoEn).toISOString())}), que pueden no estar al día. Lo que
            registres se enviará solo al volver la red.
          </span>
        </p>
      ) : null}

      <Identidad activo={activo} />

      <EnFalla activo={activo} veOrdenes={rol !== "operario"} />

      {rol !== "operario" && guardadoEn === null ? <TarjetaRiesgo usuario={usuario} activo={activo} /> : null}
      {rol !== "operario" && guardadoEn !== null && riesgoGuardado !== null ? (
        <RiesgoSinConexion usuario={usuario} datos={riesgoGuardado} />
      ) : null}

      {activo.estado === "baja" ? (
        <p className="flex gap-2 rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 text-texto-suave" />
          <span>
            Este equipo está dado de baja
            {activo.dado_de_baja_en !== null ? ` desde el ${fecha(activo.dado_de_baja_en)}` : ""}. Ya no
            admite lecturas ni alertas. Si sigue funcionando, avisa al administrador de tu planta.
          </span>
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        {capturaEnCampo ? (
          <>
            <Panel nivel={2} titulo="Registrar horómetro">
              <FormularioHorometro usuario={usuario} activo={activo} alRegistrar={alRegistrar} />
            </Panel>
            <Panel nivel={2} titulo="Reportar alerta" descripcion="El equipo sigue funcionando, pero algo no va bien.">
              <FormularioAlerta usuario={usuario} activo={activo} />
            </Panel>
          </>
        ) : null}

        {reportaFalla ? <ReportarFalla usuario={usuario} activo={activo} /> : null}

        <FichaTecnica activo={activo} />

        {gestiona && guardadoEn === null ? <Gestion activo={activo} alCambiar={setActivo} /> : null}
      </div>

      {veHistorial && guardadoEn === null ? <Historial activo={activo} /> : null}
    </div>
  );
}

function Identidad({ activo }: { readonly activo: Activo }) {
  const lugar = [activo.ubicacion, activo.tipo].filter((x) => x !== null && x !== "").join(" · ");
  return (
    <section className="rounded-[var(--radius-control)] border border-borde bg-superficie px-5 py-5 sm:px-6">
      <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="text-[1.375rem] font-semibold leading-7 text-texto [overflow-wrap:anywhere]">
            {activo.nombre}
          </h1>
          <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
            {lugar !== "" ? lugar : "Sin ubicación registrada"}
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-3">
            <EstadoEquipo estado={activo.estado} />
            {activo.criticidad !== null ? <Criticidad valor={activo.criticidad} /> : null}
          </div>
        </div>
        {/* Los dos datos que se comprueban al escanear: que la etiqueta es la de esta máquina, y
            cuánto marcaba la última vez. Etiqueta encima del valor, como en una placa. */}
        <dl className="grid shrink-0 grid-cols-2 gap-x-8 gap-y-1 border-t border-borde pt-4 md:border-0 md:pt-0">
          <div>
            <dt className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">Código</dt>
            <dd className="pt-1 font-mono text-[1.0625rem] font-semibold leading-7 tracking-[0.08em] text-texto">
              {presentarCodigo(activo.codigo)}
            </dd>
          </div>
          <div>
            <dt className="text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue">Horómetro</dt>
            <dd className="pt-1">
              <span className="block text-[1.375rem] font-semibold leading-7 text-texto">
                {activo.horometro_actualizado_en === null ? "—" : horas(activo.horometro_actual)}
              </span>
              <span className="block text-[0.8125rem] leading-5 text-texto-tenue">
                {activo.horometro_actualizado_en === null
                  ? "Sin lecturas todavía"
                  : hace(activo.horometro_actualizado_en)}
              </span>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function FichaTecnica({ activo }: { readonly activo: Activo }) {
  const filas: Array<[string, string | null]> = [
    ["Tipo", activo.tipo],
    ["Ubicación", activo.ubicacion],
    ["Marca", activo.marca],
    ["Modelo", activo.modelo],
    ["Número de serie", activo.numero_serie],
    ["Instalado", activo.fecha_instalacion === null ? null : fecha(activo.fecha_instalacion)],
  ];
  return (
    <Panel nivel={2} titulo="Ficha técnica">
      <dl className="divide-y divide-borde">
        {filas.map(([nombre, valor]) => (
          <div key={nombre} className="grid grid-cols-[9rem_minmax(0,1fr)] gap-3 py-2.5 first:pt-0 last:pb-0">
            <dt className="text-[0.875rem] text-texto-suave">{nombre}</dt>
            <dd className="text-[0.9375rem] text-texto [overflow-wrap:anywhere]">
              {valor === null || valor === "" ? <span className="text-texto-tenue">—</span> : valor}
            </dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function Gestion({ activo, alCambiar }: { readonly activo: Activo; readonly alCambiar: (a: Activo) => void }) {
  const [confirmar, setConfirmar] = useState<"baja" | "codigo" | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ejecutar(): Promise<void> {
    setEnCurso(true);
    setError(null);
    try {
      const actualizado =
        confirmar === "baja" ? await darDeBaja(activo.id) : await regenerarCodigo(activo.id);
      alCambiar(actualizado);
      if (confirmar === "codigo") {
        // La dirección es el código: la vieja ya no resuelve, así que se pasa a la nueva sin
        // recargar, para que un refresco de la pantalla no dé «no encontrado».
        window.history.replaceState(null, "", `/a/${actualizado.codigo}`);
      }
      setConfirmar(null);
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo completar la acción.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <Panel nivel={2} titulo="Gestión del equipo">
      <p className="pb-3 text-[0.9375rem]">
        <Link href={`/activos/${activo.id}/componentes`} className="font-medium text-accion underline-offset-2 hover:underline">
          Componentes y edad de las piezas
        </Link>
        <span className="block text-[0.8125rem] text-texto-suave">
          Sin la edad de una pieza no se puede calcular su riesgo.
        </span>
      </p>
      <div className="flex flex-col gap-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <EnlaceBoton href={`/activos/${activo.id}/editar`}>Editar ficha</EnlaceBoton>
          <EnlaceBoton href={`/activos/${activo.id}/etiqueta`}>
            <IconoImprimir />
            Imprimir etiqueta
          </EnlaceBoton>
        </div>

        {confirmar === null ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <Boton tipo="button" variante="secundario" onClick={() => setConfirmar("codigo")}>
              Regenerar código
            </Boton>
            {activo.estado === "activo" ? (
              <Boton tipo="button" variante="secundario" onClick={() => setConfirmar("baja")}>
                Dar de baja
              </Boton>
            ) : null}
          </div>
        ) : (
          <div role="alert" className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie-alterna p-3">
            <p className="text-[0.9375rem] leading-6 text-texto">
              {confirmar === "baja"
                ? "El equipo dejará de admitir lecturas y alertas. Su historial se conserva y su etiqueta seguirá abriendo esta ficha."
                : "La etiqueta actual dejará de funcionar en este momento y habrá que imprimir y pegar una nueva. Úsalo si la etiqueta se copió o se dañó."}
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Boton tipo="button" variante="secundario" onClick={() => setConfirmar(null)}>
                Cancelar
              </Boton>
              <Boton tipo="button" onClick={() => void ejecutar()} enCurso={enCurso} textoEnCurso="Un momento…">
                {confirmar === "baja" ? "Dar de baja" : "Regenerar"}
              </Boton>
            </div>
          </div>
        )}
        {error !== null ? (
          <p role="alert" className="text-[0.875rem] text-error">
            {error}
          </p>
        ) : null}

        <ReiniciarHorometro activo={activo} alCambiar={alCambiar} />
      </div>
    </Panel>
  );
}

/**
 * Cambio o reinicio del horómetro (06-fase3, 5.1). Solo el administrador, y con confirmación
 * explícita: el valor del aparato vuelve a un número bajo, pero las horas de vida del equipo —lo
 * que mide el cálculo de riesgo— no se pierden.
 */
function ReiniciarHorometro({
  activo,
  alCambiar,
}: {
  readonly activo: Activo;
  readonly alCambiar: (a: Activo) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [valor, setValor] = useState("0");
  const [error, setError] = useState<string | undefined>();
  const [enCurso, setEnCurso] = useState(false);
  const [hecho, setHecho] = useState<string | null>(null);
  const acumuladas = (activo.horometro_offset ?? 0) + activo.horometro_actual;

  async function confirmar(): Promise<void> {
    const n = leerHorometro(valor);
    if (typeof n === "string") {
      setError(n);
      return;
    }
    setError(undefined);
    setEnCurso(true);
    try {
      const actualizado = await reiniciarHorometro(activo.id, n);
      alCambiar(actualizado);
      setHecho(
        `Horómetro reiniciado en ${horas(n)}. El equipo conserva sus ${horas(acumuladas)} acumuladas.`,
      );
      setAbierto(false);
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo reiniciar el horómetro.");
    } finally {
      setEnCurso(false);
    }
  }

  if (!abierto) {
    return (
      <div className="flex flex-col gap-2 border-t border-borde pt-3">
        <Boton tipo="button" variante="secundario" onClick={() => setAbierto(true)}>
          Cambio o reinicio del horómetro…
        </Boton>
        {hecho !== null ? (
          <p role="status" className="text-[0.875rem] text-texto-suave">
            {hecho}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <div role="region" aria-label="Reiniciar horómetro" className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie-alterna p-3">
      <p className="text-[0.9375rem] leading-6 text-texto">
        Úsalo cuando el horómetro se cambió por uno nuevo o se puso a cero. Ahora marca{" "}
        {horas(activo.horometro_actual)}; el equipo acumula {horas(acumuladas)} y las conservará.
      </p>
      <Campo
        etiqueta="Qué marca el horómetro ahora"
        nombre="nuevo"
        valor={valor}
        onCambio={setValor}
        error={error}
        modoTeclado="numeric"
        maxLength={9}
        autoComplete="off"
        grande
      />
      <div className="grid grid-cols-2 gap-2">
        <Boton tipo="button" variante="secundario" onClick={() => setAbierto(false)}>
          Cancelar
        </Boton>
        <Boton tipo="button" onClick={() => void confirmar()} enCurso={enCurso} textoEnCurso="Un momento…">
          Reiniciar
        </Boton>
      </div>
    </div>
  );
}

/**
 * Aviso de equipo en falla (06-fase3, sección 8): lo ve cualquiera, operario incluido, para no
 * registrar lecturas de rutina sobre una máquina que está en el taller sin saberlo. Quien puede ver
 * las órdenes tiene además el enlace a cada una.
 */
function EnFalla({ activo, veOrdenes }: { readonly activo: Activo; readonly veOrdenes: boolean }) {
  const abiertas = activo.ordenes_abiertas ?? [];
  if (abiertas.length === 0) return null;
  return (
    <section
      aria-label="Equipo en falla"
      className="flex gap-3 rounded-[var(--radius-control)] border border-estado-falla bg-superficie px-4 py-3"
    >
      <IconoAviso className="mt-0.5 text-estado-falla" />
      <div className="min-w-0">
        <p className="text-[0.9375rem] font-semibold leading-6 text-texto">
          En falla: {abiertas.length === 1 ? "una orden abierta" : `${abiertas.length} órdenes abiertas`}
        </p>
        <ul className="flex flex-col gap-0.5 pt-0.5">
          {abiertas.map((o) => (
            <li key={o.id} className="text-[0.9375rem] leading-6 text-texto-suave">
              {veOrdenes ? (
                <Link href={`/ordenes/${o.id}`} className="font-mono font-semibold text-accion underline-offset-2 hover:underline">
                  {numeroOrden(o.numero)}
                </Link>
              ) : (
                <span className="font-mono font-semibold text-texto">{numeroOrden(o.numero)}</span>
              )}{" "}
              · {o.componente_nombre} · {ETIQUETA_ESTADO_ORDEN[o.estado]}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** Reportar una falla desde la propia pantalla del equipo: escanear, completar, enviar. */
function ReportarFalla({ usuario, activo }: { readonly usuario: Usuario; readonly activo: Activo }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <Panel
      nivel={2}
      titulo="Reportar falla"
      descripcion="El equipo se detuvo o hay que llevarlo al taller: abre una orden de trabajo."
    >
      {abierto ? (
        <FormularioFalla usuario={usuario} activo={activo} />
      ) : (
        <Boton tipo="button" variante="secundario" anchoCompleto onClick={() => setAbierto(true)}>
          Reportar una falla
        </Boton>
      )}
    </Panel>
  );
}

function Historial({ activo }: { readonly activo: Activo }) {
  const [lecturas, setLecturas] = useState<readonly Lectura[] | null>(null);
  const [alertas, setAlertas] = useState<readonly Alerta[] | null>(null);

  useEffect(() => {
    const control = new AbortController();
    void historialLecturas(activo.id, null, control.signal)
      .then((p) => setLecturas(p.items))
      .catch(() => setLecturas([]));
    void listarAlertas({ activoId: activo.id }, control.signal)
      .then((p) => setAlertas(p.items.slice(0, 10)))
      .catch(() => setAlertas([]));
    return () => control.abort();
  }, [activo.id, activo.horometro_actual]);

  return (
    <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
      <Panel nivel={2} titulo="Lecturas de horómetro">
        {lecturas === null ? (
          <Esqueleto filas={2} />
        ) : lecturas.length === 0 ? (
          <p className="text-[0.9375rem] text-texto-suave">Todavía no hay lecturas de este equipo.</p>
        ) : (
          <ol className="divide-y divide-borde">
            {lecturas.map((l) => (
              <li key={l.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5 first:pt-0 last:pb-0">
                <span className="text-[1rem] font-semibold text-texto">{horas(l.valor_horometro)}</span>
                <span className="text-[0.8125rem] text-texto-tenue">{fechaHora(l.capturado_en)}</span>
                {l.requiere_revision ? (
                  <span className="flex basis-full flex-col gap-1">
                    <RequiereRevision resolucion={l.resolucion} />
                    <span className="text-[0.8125rem] leading-5 text-texto-suave">{l.motivo_revision}</span>
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Panel>
      <Panel nivel={2} titulo="Alertas de este equipo">
        {alertas === null ? (
          <Esqueleto filas={2} />
        ) : alertas.length === 0 ? (
          <p className="text-[0.9375rem] text-texto-suave">Nadie ha reportado alertas de este equipo.</p>
        ) : (
          <ol className="divide-y divide-borde">
            {alertas.map((a) => (
              <li key={a.id} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[1rem] font-semibold text-texto">{ETIQUETA_SINTOMA[a.sintoma]}</span>
                  <EstadoAlertaInsignia estado={a.estado} />
                </span>
                {a.nota !== null ? (
                  <span className="text-[0.875rem] leading-5 text-texto-suave [overflow-wrap:anywhere]">{a.nota}</span>
                ) : null}
                <span className="text-[0.8125rem] text-texto-tenue">{fechaHora(a.capturado_en)}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}


/**
 * Riesgo de falla del equipo (F4, 10.1): cada componente con su respaldo, y las alertas del sistema
 * vigentes. El operario no lo ve (tabla 12.1); el técnico ve el riesgo pero no la bandeja.
 */
/**
 * Sin red: el último riesgo que este teléfono vio del equipo, marcado como tal (07-fase4, 10.2).
 * Cada componente conserva la hora de su cálculo; sin red no hay acciones ni enlaces al modelo.
 */
function RiesgoSinConexion({ usuario, datos }: { readonly usuario: Usuario; readonly datos: RiesgoEquipo }) {
  return (
    <Panel
      nivel={2}
      titulo="Riesgo de falla"
      descripcion={`Último cálculo conocido, guardado en este teléfono. Sin conexión no se actualiza. Umbral de la empresa: ${porcentaje(Number(datos.umbral))}.`}
    >
      <RiesgoPorComponente datos={datos} usuario={usuario} verModelo={false} />
    </Panel>
  );
}

function TarjetaRiesgo({ usuario, activo }: { readonly usuario: Usuario; readonly activo: Activo }) {
  const [datos, setDatos] = useState<RiesgoEquipo | null>(null);
  const [alertas, setAlertas] = useState<readonly AlertaSistema[]>([]);
  const [error, setError] = useState<string | null>(null);
  const veBandeja = usuario.rol !== "tecnico_taller";

  useEffect(() => {
    const control = new AbortController();
    riesgoDelEquipo(activo.id, control.signal)
      .then((r) => {
        setDatos(r);
        // Para verlo sin red como último valor conocido (10.2). Si no se puede guardar, da igual.
        void guardarRiesgo(usuario.id, activo.codigo, r).catch(() => undefined);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ErrorApi ? e.message : "No se pudo calcular el riesgo.");
      });
    if (veBandeja) {
      listarAlertasSistema({ tipo: "riesgo", estado: "vigentes", activoId: activo.id }, control.signal)
        .then((p) => setAlertas(p.items))
        .catch(() => setAlertas([]));
    }
    return () => control.abort();
  }, [activo.id, activo.codigo, usuario.id, veBandeja]);

  return (
    <Panel
      nivel={2}
      titulo="Riesgo de falla"
      descripcion={
        datos !== null
          ? `Probabilidad de falla de cada componente en las próximas ${horas(datos.horizonte_horas)} de operación. Umbral de la empresa: ${porcentaje(Number(datos.umbral))}.`
          : undefined
      }
    >
      {error !== null ? (
        <p role="alert" className="text-[0.9375rem] text-error">{error}</p>
      ) : datos === null ? (
        <Esqueleto filas={2} />
      ) : (
        <div className="flex flex-col gap-4">
          {alertas.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {alertas.map((a) => (
                <li
                  key={a.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-control)] border border-estado-falla bg-superficie px-3 py-2.5 text-[0.9375rem] text-texto"
                >
                  <span className="flex gap-2">
                    <IconoAviso className="mt-0.5 shrink-0 text-estado-falla" />
                    <span>
                      Alerta de riesgo: {a.componente} al {porcentaje(numero(a.riesgo) ?? 0)}
                      {a.estado === "atendida" && a.orden_numero !== null
                        ? ` · cambio planificado en ${numeroOrden(a.orden_numero)}`
                        : a.estado === "reconocida"
                          ? " · reconocida"
                          : ""}
                    </span>
                  </span>
                  <Link href="/alertas-sistema" className="text-[0.875rem] font-medium text-accion underline-offset-2 hover:underline">
                    Ver en la bandeja
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
          {datos.alertas_de_campo >= datos.alertas_minimas ? (
            <p className="text-[0.875rem] leading-5 text-texto-suave">
              {datos.alertas_de_campo} alertas de campo recientes: el riesgo de este equipo se calcula
              con el multiplicador de la empresa.
            </p>
          ) : null}
          <RiesgoPorComponente datos={datos} usuario={usuario} verModelo={veBandeja} />
        </div>
      )}
    </Panel>
  );
}
