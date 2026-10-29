"use client";

/**
 * Panel de cada rol (08-fase5, sección 10; RF-27, RF-28).
 *
 * Una sola ruta que muestra la vista del rol de la sesión: el operario, sus lecturas y alertas y en
 * qué quedaron; el técnico, la cola del taller; el supervisor, lo que espera revisión; el gerente,
 * los indicadores, el riesgo y los costos; el administrador, lo del supervisor y lo del gerente más
 * el estado de la plataforma. El rol lo decide la API con la sesión, no esta página.
 *
 * Cada sección es un widget independiente: si uno no está disponible (por ejemplo, porque el
 * cálculo de riesgo cayó), esa sección lo dice sin mostrar el error y el resto sigue (RNF-02).
 *
 * Los filtros viven en la URL: recargar o compartir el enlace conserva lo que se está mirando. El
 * de planta ordena la vista; no limita lo que el usuario puede ver (decisión 1), y la pantalla lo
 * dice para que nadie lo tome por un control de acceso.
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { Boton } from "@/components/boton";
import { EstadoAlertaInsignia, EstadoOrdenInsignia, Insignia } from "@/components/estado";
import { GraficaCosto, GraficaDisponibilidad } from "@/components/graficas";
import { IconoAviso } from "@/components/iconos";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ConfianzaInsignia, NivelRiesgo } from "@/components/riesgo";
import { ErrorApi } from "@/lib/api";
import type { Usuario } from "@/lib/auth";
import { fechaHora, hace, horas } from "@/lib/formato";
import { numeroOrden } from "@/lib/ordenes";
import {
  ETIQUETA_LECTURA,
  ETIQUETA_SINTOMA,
  VACIO,
  dinero,
  entero,
  horasCortas,
  leerPanel,
  listarPlantas,
  porcentajeFino,
  textoMtbf,
  type AlertaCampoPanel,
  type AlertaSistemaPanel,
  type Cobertura,
  type Contadores,
  type FiltrosPanel,
  type Indicadores,
  type MiAlerta,
  type MiLectura,
  type OrdenPanel,
  type Panel as DatosPanel,
  type RepuestoCosto,
  type RiesgoTop,
  type Salud,
  type Widget,
} from "@/lib/paneles";
import { nivel, porcentaje } from "@/lib/prediccion";

const TITULO_POR_ROL: Readonly<Record<string, string>> = {
  operario: "Mi panel",
  tecnico_taller: "Panel del taller",
  supervisor: "Panel del supervisor",
  gerente: "Panel del gerente",
  administrador: "Panel del administrador",
};

/** Roles con filtro de planta, y los que además filtran por periodo (10.1). */
const CON_PLANTA = new Set(["supervisor", "gerente", "administrador"]);
const CON_PERIODO = new Set(["gerente", "administrador"]);

export default function PanelPage() {
  return (
    <Pantalla cargando="Cargando tu panel">
      {(usuario) => (
        <Suspense fallback={<Esqueleto />}>
          <Inicio usuario={usuario} />
        </Suspense>
      )}
    </Pantalla>
  );
}

type Carga =
  | { readonly tipo: "cargando" }
  | { readonly tipo: "listo"; readonly panel: DatosPanel; readonly en: string }
  | { readonly tipo: "error"; readonly mensaje: string; readonly periodo: boolean };

function Inicio({ usuario }: { readonly usuario: Usuario }) {
  const parametros = useSearchParams();
  const filtros: FiltrosPanel = {
    planta: parametros.get("planta") ?? undefined,
    desde: parametros.get("desde") ?? undefined,
    hasta: parametros.get("hasta") ?? undefined,
  };
  const clave = parametros.toString();
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });

  useEffect(() => {
    const control = new AbortController();
    leerPanel(
      {
        planta: parametros.get("planta") ?? undefined,
        desde: parametros.get("desde") ?? undefined,
        hasta: parametros.get("hasta") ?? undefined,
      },
      control.signal,
    )
      .then((panel) => setCarga({ tipo: "listo", panel, en: new Date().toISOString() }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        const periodo = e instanceof ErrorApi && e.estado === 422;
        setCarga({
          tipo: "error",
          periodo,
          mensaje: periodo
            ? "Revisa las fechas: el inicio debe ser anterior al fin, sin pasar de 24 meses ni estar en el futuro."
            : e instanceof ErrorApi
              ? e.message
              : "No se pudo cargar el panel.",
        });
      });
    return () => control.abort();
    // `clave` resume los tres filtros de la URL: se recarga cuando cambia cualquiera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave]);

  const titulo = TITULO_POR_ROL[usuario.rol] ?? "Tu panel";
  const degradados = carga.tipo === "listo" ? carga.panel.degradados.length : 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">{titulo}</h1>
        <p className="text-[0.875rem] leading-5 text-texto-suave">
          {carga.tipo === "listo" ? `Actualizado ${fechaHora(carga.en)}` : `Sesión de ${usuario.nombre}`}
        </p>
        {degradados > 0 ? (
          <p role="status" className="flex items-start gap-2 pt-1 text-[0.875rem] leading-5 text-texto">
            <IconoAviso className="mt-0.5 h-4 w-4 shrink-0 text-estado-aviso" />
            {degradados === 1
              ? "1 sección no está disponible ahora; el resto funciona con normalidad."
              : `${degradados} secciones no están disponibles ahora; el resto funciona con normalidad.`}
          </p>
        ) : null}
      </header>

      {CON_PLANTA.has(usuario.rol) ? (
        <Filtros conPeriodo={CON_PERIODO.has(usuario.rol)} actuales={filtros} />
      ) : null}

      {carga.tipo === "cargando" ? (
        <Panel nivel={2} titulo="Cargando">
          <Esqueleto filas={4} />
        </Panel>
      ) : carga.tipo === "error" ? (
        <Panel nivel={2} titulo={carga.periodo ? "Ese periodo no es válido" : "No se pudo cargar el panel"}>
          <p role="alert" className="text-[0.9375rem] leading-6 text-error">
            {carga.mensaje}
          </p>
        </Panel>
      ) : (
        <Secciones panel={carga.panel} en={carga.en} />
      )}

      <Panel nivel={2} titulo="Tu cuenta">
        <Link
          href="/panel/clave"
          className="inline-flex h-11 items-center rounded-[var(--radius-control)] border border-borde-fuerte px-4 text-[0.875rem] font-medium text-texto transition-colors hover:bg-superficie-alterna"
        >
          Cambiar contraseña
        </Link>
      </Panel>
    </div>
  );
}

// --- Filtros ----------------------------------------------------------------------------------------

function Filtros({ conPeriodo, actuales }: { readonly conPeriodo: boolean; readonly actuales: FiltrosPanel }) {
  const router = useRouter();
  const ruta = usePathname();
  const [plantas, setPlantas] = useState<readonly string[]>([]);
  const [planta, setPlanta] = useState(actuales.planta ?? "");
  const [desde, setDesde] = useState(actuales.desde ?? "");
  const [hasta, setHasta] = useState(actuales.hasta ?? "");

  useEffect(() => {
    const control = new AbortController();
    listarPlantas(control.signal)
      .then(setPlantas)
      .catch(() => setPlantas([]));
    return () => control.abort();
  }, []);

  const cambiado =
    planta !== (actuales.planta ?? "") || desde !== (actuales.desde ?? "") || hasta !== (actuales.hasta ?? "");

  function aplicar(): void {
    const q = new URLSearchParams();
    if (planta) q.set("planta", planta);
    if (conPeriodo && desde) q.set("desde", desde);
    if (conPeriodo && hasta) q.set("hasta", hasta);
    const texto = q.toString();
    router.replace(texto ? `${ruta}?${texto}` : ruta);
  }

  const caja =
    "h-12 w-full rounded-[var(--radius-control)] border border-borde-fuerte bg-superficie px-3 text-[1rem] text-texto focus:border-accion focus:outline-none focus:ring-2 focus:ring-[var(--accion-halo)]";

  return (
    <section aria-label="Filtros" className="rounded-[var(--radius-control)] border border-borde bg-superficie px-5 py-4 sm:px-6">
      <form
        className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,14rem)_minmax(0,11rem)_minmax(0,11rem)_auto] lg:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          aplicar();
        }}
      >
        <label className="flex flex-col gap-1.5 text-[0.8125rem] font-medium text-texto">
          Planta
          <select value={planta} onChange={(e) => setPlanta(e.target.value)} className={caja}>
            <option value="">Todas</option>
            {plantas.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        {conPeriodo ? (
          <>
            <label className="flex flex-col gap-1.5 text-[0.8125rem] font-medium text-texto">
              Desde
              <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className={caja} />
            </label>
            <label className="flex flex-col gap-1.5 text-[0.8125rem] font-medium text-texto">
              Hasta
              <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className={caja} />
            </label>
          </>
        ) : null}
        <div className="sm:self-end">
          <Boton tipo="submit" deshabilitado={!cambiado}>
            Aplicar
          </Boton>
        </div>
      </form>
      <p className="pt-3 text-[0.8125rem] leading-5 text-texto-tenue">
        El filtro de planta ordena la vista; no limita lo que tu usuario puede ver.
        {conPeriodo ? " Sin fechas, se muestran los últimos 12 meses." : ""}
      </p>
    </section>
  );
}

// --- Secciones por rol ------------------------------------------------------------------------------

function Secciones({ panel, en }: { readonly panel: DatosPanel; readonly en: string }) {
  const w = panel.widgets;
  return (
    <div className="flex flex-col gap-6">
      {w.indicadores ? <SeccionIndicadores widget={w.indicadores} /> : null}
      {w.riesgo_top || w.repuestos_costo ? (
        // `min-w-0`: sin él, una tabla ancha estira la celda de la rejilla en vez de desplazarse.
        <div className="grid gap-6 xl:grid-cols-2 xl:items-start [&>*]:min-w-0">
          {w.riesgo_top ? <SeccionRiesgo widget={w.riesgo_top} cobertura={w.riesgo_cobertura} /> : null}
          {w.repuestos_costo ? <SeccionRepuestos widget={w.repuestos_costo} /> : null}
        </div>
      ) : null}
      {w.contadores ? <SeccionContadores widget={w.contadores} /> : null}
      {w.alertas_campo ? <SeccionAlertasCampo widget={w.alertas_campo} /> : null}
      {w.alertas_sistema ? <SeccionAlertasSistema widget={w.alertas_sistema} /> : null}
      {w.ordenes_abiertas ? (
        <SeccionOrdenes titulo="Órdenes abiertas" descripcion="Reportadas, en taller o por autorizar; la más antigua arriba." widget={w.ordenes_abiertas} abierta />
      ) : null}
      {w.cola_taller ? (
        <SeccionOrdenes titulo="Cola del taller" descripcion="Primero las fallas, la más antigua arriba; después los cambios planificados." widget={w.cola_taller} />
      ) : null}
      {w.mis_trabajos ? <SeccionMisTrabajos widget={w.mis_trabajos} /> : null}
      {w.mis_lecturas ? <SeccionMisLecturas widget={w.mis_lecturas} /> : null}
      {w.mis_alertas ? <SeccionMisAlertas widget={w.mis_alertas} /> : null}
      {w.salud ? <SeccionSalud widget={w.salud} en={en} /> : null}
    </div>
  );
}

/** Una sección que puede venir degradada: lo dice, sin el error, y el resto del panel sigue. */
function Seccion<T>({
  titulo,
  descripcion,
  widget,
  pie,
  children,
}: {
  readonly titulo: string;
  readonly descripcion?: string;
  readonly widget: Widget<T>;
  readonly pie?: ReactNode;
  readonly children: (datos: T) => ReactNode;
}) {
  if (widget.estado !== "ok" || widget.datos === null) {
    return (
      <Panel nivel={2} titulo={titulo}>
        <p className="flex items-start gap-2 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-1 h-4 w-4 shrink-0 text-estado-aviso" />
          <span>
            Esta información no está disponible en este momento. El resto del panel sigue siendo válido;
            vuelve a cargar la página en unos minutos.
          </span>
        </p>
      </Panel>
    );
  }
  return (
    <Panel nivel={2} titulo={titulo} descripcion={descripcion} pie={pie}>
      {children(widget.datos)}
    </Panel>
  );
}

function Vacio({ children }: { readonly children: ReactNode }) {
  return <p className="text-[0.9375rem] leading-6 text-texto-suave">{children}</p>;
}

const TH = "whitespace-nowrap py-2 pr-4 text-left text-[0.75rem] font-medium uppercase tracking-wide text-texto-tenue";
const TD = "py-2.5 pr-4 align-top";

function Tabla({
  cabeceras,
  children,
  minimo = "min-w-[34rem]",
}: {
  readonly cabeceras: readonly (string | readonly [string, "der"])[];
  readonly children: ReactNode;
  /** Ancho mínimo antes de desplazarse en horizontal (dentro de su propio contenedor). */
  readonly minimo?: string;
}) {
  return (
    <div className="-mx-5 overflow-x-auto px-5 sm:-mx-6 sm:px-6">
      <table className={`w-full ${minimo} border-collapse text-[0.9375rem] [font-variant-numeric:tabular-nums]`}>
        <thead>
          <tr className="border-b border-borde">
            {cabeceras.map((c) =>
              typeof c === "string" ? (
                <th key={c} scope="col" className={TH}>
                  {c}
                </th>
              ) : (
                <th key={c[0]} scope="col" className={`${TH} text-right`}>
                  {c[0]}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Fila({ children }: { readonly children: ReactNode }) {
  return <tr className="border-b border-borde last:border-0">{children}</tr>;
}

function EnlaceEquipo({ codigo, nombre }: { readonly codigo: string; readonly nombre: string }) {
  return (
    <Link href={`/a/${codigo}`} className="font-medium text-accion underline-offset-2 hover:underline [overflow-wrap:anywhere]">
      {nombre}
    </Link>
  );
}

// --- Gerente ------------------------------------------------------------------------------------------

function Medida({ nombre, valor, nota }: { readonly nombre: string; readonly valor: string; readonly nota: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-borde py-4 last:border-0 sm:border-b-0 sm:border-r sm:px-5 sm:first:pl-0 sm:last:border-r-0 sm:last:pr-0">
      <dt className="text-[0.8125rem] font-medium text-texto-suave">{nombre}</dt>
      <dd className="text-[1.375rem] font-semibold leading-7 text-texto [font-variant-numeric:tabular-nums]">{valor}</dd>
      <dd className="text-[0.8125rem] leading-5 text-texto-suave">{nota}</dd>
    </div>
  );
}

function SeccionIndicadores({ widget }: { readonly widget: Widget<Indicadores> }) {
  return (
    <Seccion
      titulo="Indicadores del periodo"
      widget={widget}
      pie="Disponibilidad sobre horas de calendario de 24 h desde que se observa cada equipo; MTBF sobre horas de operación del horómetro. El intervalo del MTBF supone fallas a ritmo constante: con fallas agrupadas, el rango real es más ancho."
    >
      {(d) => {
        const r = d.resumen;
        const mtbf = textoMtbf(r);
        const costo = Number(r.costo_total);
        return (
          <div className="flex flex-col gap-6">
            <dl className="grid sm:grid-cols-2 xl:grid-cols-4 [&>div]:sm:[&:nth-child(2)]:border-r-0 xl:[&>div]:[&:nth-child(2)]:border-r">
              <Medida
                nombre="Disponibilidad"
                valor={porcentajeFino(r.disponibilidad)}
                nota={`Sin contar paradas planificadas: ${porcentajeFino(r.disponibilidad_sin_planificadas)} · Utilización: ${porcentajeFino(r.utilizacion)}`}
              />
              <Medida nombre="Tiempo medio entre fallas (MTBF)" valor={mtbf.valor} nota={mtbf.nota} />
              <Medida
                nombre="Tiempo medio de reparación (MTTR)"
                valor={horasCortas(r.mttr_h)}
                nota={
                  r.fallas_cerradas === 0
                    ? "Ninguna falla cerrada en el periodo"
                    : `${entero(r.fallas_cerradas)} ${r.fallas_cerradas === 1 ? "falla cerrada" : "fallas cerradas"}, de la falla a la salida del taller`
                }
              />
              <Medida
                nombre="Costo de repuestos"
                valor={dinero(costo)}
                nota={
                  r.porcentaje_planificado === null
                    ? "Sin consumos en el periodo"
                    : `${porcentajeFino(r.porcentaje_planificado, 0)} en trabajo planificado · Por falla: ${dinero(r.costo_fallas)}`
                }
              />
            </dl>
            {r.fallas_en_revision > 0 ? (
              <p className="text-[0.8125rem] leading-5 text-texto-suave">
                {r.fallas_en_revision === 1 ? "1 falla tiene" : `${entero(r.fallas_en_revision)} fallas tienen`} el horómetro
                pendiente de confirmar: cuentan como fallas, pero sus horas no entran al cálculo de riesgo.
              </p>
            ) : null}
            <div className="grid gap-8 border-t border-borde pt-6 lg:grid-cols-2">
              <GraficaDisponibilidad meses={d.meses} />
              <GraficaCosto meses={d.meses} />
            </div>
          </div>
        );
      }}
    </Seccion>
  );
}

function SeccionRiesgo({ widget, cobertura }: { readonly widget: Widget<readonly RiesgoTop[]>; readonly cobertura?: Widget<Cobertura> }) {
  const c = cobertura?.estado === "ok" ? cobertura.datos : null;
  return (
    <Seccion
      titulo="Equipos de mayor riesgo"
      widget={widget}
      pie={
        c ? (
          <>
            {entero(c.con_riesgo)} de {entero(c.equipos_activos)} equipos activos tienen riesgo calculado
            {c.sin_edad > 0 ? ` (${entero(c.sin_edad)} sin edad de la pieza declarada)` : ""}. Un equipo sin riesgo calculado no es un
            equipo sin riesgo.
          </>
        ) : (
          "No se pudo saber cuántos equipos tienen riesgo calculado."
        )
      }
    >
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>Ningún equipo activo tiene todavía riesgo calculado.</Vacio>
        ) : (
          <ul className="flex flex-col">
            {filas.map((f) => (
              <li key={f.activo_id} className="flex flex-col gap-1.5 border-b border-borde py-3 first:pt-0 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <EnlaceEquipo codigo={f.codigo} nombre={f.equipo} />
                  <span className="flex items-center gap-2">
                    <span className="text-[1.0625rem] font-semibold text-texto [font-variant-numeric:tabular-nums]">{porcentaje(f.riesgo)}</span>
                    {f.umbral !== null ? <NivelRiesgo valor={nivel(f.riesgo, f.umbral)} /> : null}
                  </span>
                </div>
                <p className="text-[0.8125rem] leading-5 text-texto-suave">
                  {f.componente}
                  {f.planta ? ` · ${f.planta}` : ""}
                  {f.horizonte_horas !== null ? ` · en las próximas ${horas(f.horizonte_horas)} de operación` : ""}
                </p>
                <p className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-texto-suave">
                  <ConfianzaInsignia valor={f.confianza} />
                  <span>
                    {f.fuente === "previo" ? "Estimado con la vida nominal" : "Historial de la empresa"}
                    {f.n_eventos !== null ? ` · ${entero(f.n_eventos)} ${f.n_eventos === 1 ? "falla" : "fallas"}` : ""} · {hace(f.calculado_en)}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        )
      }
    </Seccion>
  );
}

function SeccionRepuestos({ widget }: { readonly widget: Widget<readonly RepuestoCosto[]> }) {
  return (
    <Seccion titulo="Repuestos que más costaron" descripcion="En el periodo, al precio de cada consumo." widget={widget}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>No se consumieron repuestos en el periodo.</Vacio>
        ) : (
          <Tabla cabeceras={["Repuesto", ["Unidades", "der"], ["Costo", "der"]]} minimo="min-w-[18rem]">
            {filas.map((f) => (
              <Fila key={f.codigo}>
                <td className={TD}>
                  <span className="block font-medium text-texto [overflow-wrap:anywhere]">{f.nombre}</span>
                  <span className="font-mono text-[0.8125rem] tracking-[0.04em] text-texto-suave">{f.codigo}</span>
                </td>
                <td className={`${TD} text-right`}>{entero(f.unidades)}</td>
                <td className={`${TD} whitespace-nowrap text-right`}>{dinero(f.costo)}</td>
              </Fila>
            ))}
          </Tabla>
        )
      }
    </Seccion>
  );
}

// --- Supervisor ---------------------------------------------------------------------------------------

function SeccionContadores({ widget }: { readonly widget: Widget<Contadores> }) {
  const enlaces: readonly [keyof Contadores, string, string][] = [
    ["alertas_campo", "Alertas de campo por revisar", "/alertas"],
    ["alertas_sistema", "Alertas del sistema por atender", "/alertas-sistema"],
    ["ordenes_abiertas", "Órdenes abiertas", "/ordenes"],
    ["lecturas_por_confirmar", "Lecturas por confirmar", "/alertas#lecturas-por-revisar"],
  ];
  return (
    <Seccion titulo="Lo que espera tu revisión" widget={widget}>
      {(c) => (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {enlaces.map(([clave, nombre, href]) => (
            <li key={clave}>
              <Link
                href={href}
                className="flex h-full min-h-12 flex-col gap-1 rounded-[var(--radius-control)] border border-borde-fuerte px-4 py-3 transition-colors hover:bg-superficie-alterna"
              >
                <span className="text-[1.375rem] font-semibold leading-7 text-texto [font-variant-numeric:tabular-nums]">{entero(c[clave])}</span>
                <span className="text-[0.875rem] font-medium text-accion">{nombre}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Seccion>
  );
}

function SeccionAlertasCampo({ widget }: { readonly widget: Widget<readonly AlertaCampoPanel[]> }) {
  return (
    <Seccion titulo="Alertas de campo pendientes de revisión" widget={widget} pie={<Link href="/alertas" className="font-medium text-accion underline-offset-2 hover:underline">Ir a la bandeja de alertas</Link>}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>No hay alertas de campo esperando revisión.</Vacio>
        ) : (
          <Tabla cabeceras={["Equipo", "Planta", "Síntoma", "Reportó", "Cuándo"]}>
            {filas.map((f) => (
              <Fila key={f.id}>
                <td className={TD}><EnlaceEquipo codigo={f.codigo} nombre={f.equipo} /></td>
                <td className={`${TD} text-texto-suave`}>{f.planta ?? VACIO}</td>
                <td className={TD}>{ETIQUETA_SINTOMA[f.sintoma] ?? f.sintoma}</td>
                <td className={TD}>{f.reporto}</td>
                <td className={`${TD} text-texto-suave`}>{hace(f.capturado_en)}</td>
              </Fila>
            ))}
          </Tabla>
        )
      }
    </Seccion>
  );
}

function SeccionAlertasSistema({ widget }: { readonly widget: Widget<readonly AlertaSistemaPanel[]> }) {
  return (
    <Seccion titulo="Alertas del sistema por atender" descripcion="Riesgo de mayor a menor; después, repuestos bajo el mínimo." widget={widget} pie={<Link href="/alertas-sistema" className="font-medium text-accion underline-offset-2 hover:underline">Ir a las alertas del sistema</Link>}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>No hay alertas del sistema por atender.</Vacio>
        ) : (
          <Tabla cabeceras={["Tipo", "Detalle", ["Riesgo / stock", "der"], "Estado"]}>
            {filas.map((f) => (
              <Fila key={f.id}>
                <td className={TD}>{f.tipo === "riesgo" ? "Riesgo de falla" : "Reorden"}</td>
                <td className={`${TD} [overflow-wrap:anywhere]`}>
                  {f.tipo === "riesgo" ? `${f.equipo ?? VACIO} · ${f.componente ?? VACIO}` : `${f.repuesto ?? VACIO} (${f.repuesto_codigo ?? VACIO})`}
                </td>
                <td className={`${TD} text-right`}>
                  {f.tipo === "riesgo" ? (f.riesgo === null ? VACIO : porcentaje(f.riesgo)) : `${f.stock ?? 0} / mín. ${f.stock_minimo ?? 0}`}
                </td>
                <td className={TD}>
                  <Insignia tono={f.estado === "activa" ? "aviso" : "neutro"}>{f.estado === "activa" ? "Activa" : "Reconocida"}</Insignia>
                </td>
              </Fila>
            ))}
          </Tabla>
        )
      }
    </Seccion>
  );
}

function SeccionOrdenes({
  titulo,
  descripcion,
  widget,
  abierta = false,
}: {
  readonly titulo: string;
  readonly descripcion: string;
  readonly widget: Widget<readonly OrdenPanel[]>;
  readonly abierta?: boolean;
}) {
  return (
    <Seccion titulo={titulo} descripcion={descripcion} widget={widget}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>{abierta ? "No hay órdenes abiertas." : "No hay órdenes esperando en el taller."}</Vacio>
        ) : (
          <Tabla cabeceras={["Orden", "Equipo", "Componente", "Tipo", "Estado", abierta ? ["Abierta hace", "der"] : "Desde"]}>
            {filas.map((f) => (
              <Fila key={f.id}>
                <td className={TD}>
                  <Link href={`/ordenes/${f.id}`} className="whitespace-nowrap font-mono font-semibold tracking-[0.04em] text-accion underline-offset-2 hover:underline">
                    {numeroOrden(f.numero)}
                  </Link>
                </td>
                <td className={TD}><EnlaceEquipo codigo={f.codigo} nombre={f.equipo} /></td>
                <td className={TD}>{f.componente}</td>
                <td className={`${TD} text-texto-suave`}>{f.es_predictiva ? "Planificada" : "Falla"}</td>
                <td className={TD}><EstadoOrdenInsignia estado={f.estado} /></td>
                <td className={`${TD} ${abierta ? "text-right" : "text-texto-suave"}`}>
                  {abierta && f.horas_abierta !== undefined ? horasCortas(f.horas_abierta) : hace(f.fecha_falla)}
                </td>
              </Fila>
            ))}
          </Tabla>
        )
      }
    </Seccion>
  );
}

// --- Técnico y operario --------------------------------------------------------------------------------

function SeccionMisTrabajos({ widget }: { readonly widget: Widget<readonly OrdenPanel[]> }) {
  return (
    <Seccion titulo="Mis trabajos recientes" widget={widget}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>Todavía no has marcado ninguna orden como reparada.</Vacio>
        ) : (
          <Tabla cabeceras={["Orden", "Equipo", "Componente", "Intervención", "Reparada"]}>
            {filas.map((f) => (
              <Fila key={f.id}>
                <td className={TD}>
                  <Link href={`/ordenes/${f.id}`} className="whitespace-nowrap font-mono font-semibold tracking-[0.04em] text-accion underline-offset-2 hover:underline">
                    {numeroOrden(f.numero)}
                  </Link>
                </td>
                <td className={TD}>{f.equipo}</td>
                <td className={TD}>{f.componente}</td>
                <td className={TD}>{f.tipo_intervencion === "reemplazo" ? "Reemplazo" : f.tipo_intervencion === "ajuste" ? "Ajuste" : "Reparación"}</td>
                <td className={`${TD} text-texto-suave`}>{f.reparada_en ? fechaHora(f.reparada_en) : VACIO}</td>
              </Fila>
            ))}
          </Tabla>
        )
      }
    </Seccion>
  );
}

function SeccionMisLecturas({ widget }: { readonly widget: Widget<readonly MiLectura[]> }) {
  return (
    <Seccion titulo="Mis lecturas recientes" widget={widget}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>Todavía no has registrado lecturas. Escanea la etiqueta de un equipo para empezar.</Vacio>
        ) : (
          <ul className="flex flex-col">
            {filas.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-borde py-2.5 first:pt-0 last:border-0 last:pb-0">
                <span className="min-w-0">
                  <EnlaceEquipo codigo={f.codigo} nombre={f.equipo} />
                  <span className="block text-[0.8125rem] text-texto-suave">
                    {horas(f.valor)} · {hace(f.capturado_en)}
                  </span>
                </span>
                <Insignia tono={f.estado === "en_revision" ? "aviso" : f.estado === "descartada" ? "neutro" : "ok"}>
                  {ETIQUETA_LECTURA[f.estado]}
                </Insignia>
              </li>
            ))}
          </ul>
        )
      }
    </Seccion>
  );
}

function SeccionMisAlertas({ widget }: { readonly widget: Widget<readonly MiAlerta[]> }) {
  return (
    <Seccion titulo="Mis alertas" descripcion="Lo que reportaste y en qué quedó." widget={widget}>
      {(filas) =>
        filas.length === 0 ? (
          <Vacio>No has reportado alertas.</Vacio>
        ) : (
          <ul className="flex flex-col">
            {filas.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-borde py-2.5 first:pt-0 last:border-0 last:pb-0">
                <span className="min-w-0">
                  <EnlaceEquipo codigo={f.codigo} nombre={f.equipo} />
                  <span className="block text-[0.8125rem] text-texto-suave">
                    {ETIQUETA_SINTOMA[f.sintoma] ?? f.sintoma} · {hace(f.capturado_en)}
                  </span>
                </span>
                <EstadoAlertaInsignia estado={f.estado} />
              </li>
            ))}
          </ul>
        )
      }
    </Seccion>
  );
}

// --- Administrador ------------------------------------------------------------------------------------

function SeccionSalud({ widget, en }: { readonly widget: Widget<Salud>; readonly en: string }) {
  return (
    <Seccion titulo="Estado de la plataforma" descripcion="Si el cálculo de riesgo está al día y qué datos le faltan." widget={widget}>
      {(s) => {
        // Contra la hora en que se cargó el panel, no la del render: el resultado no cambia solo.
        const viejo = s.ultimo_calculo === null || new Date(en).getTime() - new Date(s.ultimo_calculo).getTime() > 36 * 3600_000;
        const filas: readonly [string, ReactNode, string?][] = [
          [
            "Último cálculo de riesgo",
            s.ultimo_calculo === null ? "Nunca" : `${fechaHora(s.ultimo_calculo)} (${hace(s.ultimo_calculo)})`,
            viejo ? "Más de un día sin calcular: revisa el job nocturno." : undefined,
          ],
          ["Componentes sin edad de la pieza", entero(s.pares_sin_edad), s.pares_sin_edad > 0 ? "Decláralas en la ficha de cada equipo." : undefined],
          ["Componentes sin modelo", entero(s.pares_sin_modelo), s.pares_sin_modelo > 0 ? "Declara su vida nominal en Componentes." : undefined],
          ["Modelos con confianza baja", entero(s.modelos_confianza_baja)],
          ["Repuestos bajo el mínimo", entero(s.repuestos_bajo_minimo)],
          ["Lecturas por confirmar", entero(s.lecturas_por_confirmar)],
          ["Usuarios activos", entero(s.usuarios_activos)],
        ];
        return (
          <dl className="grid gap-x-8 sm:grid-cols-2">
            {filas.map(([nombre, valor, aviso]) => (
              <div key={nombre} className="flex flex-col gap-0.5 border-b border-borde py-2.5">
                <dt className="text-[0.8125rem] text-texto-suave">{nombre}</dt>
                <dd className="font-semibold text-texto [font-variant-numeric:tabular-nums]">{valor}</dd>
                {aviso ? (
                  <dd className="flex items-start gap-1.5 text-[0.8125rem] text-texto">
                    <IconoAviso className="mt-0.5 h-3.5 w-3.5 shrink-0 text-estado-aviso" />
                    {aviso}
                  </dd>
                ) : null}
              </div>
            ))}
          </dl>
        );
      }}
    </Seccion>
  );
}
