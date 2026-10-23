/**
 * Cola de capturas sin conexión y su sincronización (RF-10; 05-fase2-activos-y-campo.md, 7.5).
 *
 * Lo que un operario registra sin cobertura se guarda en IndexedDB, en su teléfono, y se envía solo
 * cuando vuelve la red, en lotes a `POST /campo/lotes`. El servidor ignora los repetidos
 * (`cliente_id`), así que reenviar nunca duplica nada.
 *
 * REGLAS QUE VIENEN DEL USO REAL
 * ------------------------------
 * - **La cola es de una persona.** El teléfono pasa entre turnos: solo se envían los ítems de quien
 *   tiene la sesión abierta. Los de otra persona esperan a que vuelva a entrar, y se descartan, con
 *   aviso, pasados 7 días.
 * - **Cerrar sesión no borra la cola.** Borra lo que se guardó para consultar sin red (los equipos y
 *   la identidad), no lo que alguien capturó y todavía no llegó.
 * - **Nada depende de Background Sync**, que no existe en iOS ni en Safari. Se sincroniza al volver
 *   la red, al volver la app a primer plano, al arrancar y con un temporizador que espera cada vez
 *   más mientras quede algo.
 * - **Un ítem rechazado no se reintenta para siempre.** El servidor dice por qué no entrará nunca
 *   (equipo dado de baja, captura demasiado antigua); se aparta y se le muestra a quien lo capturó.
 * - **Si la sesión caducó del todo**, la cola se conserva intacta y se envía tras volver a entrar.
 */

import { openDB, type DBSchema, type IDBPDatabase } from "idb";

import { ErrorApi, llamar } from "@/lib/api";
import type { Activo } from "@/lib/activos";
import type { Usuario } from "@/lib/auth";
import type { Sintoma } from "@/lib/campo";

/** Lo que lleva un reporte de falla encolado (F3, 9.5). */
export interface DatosFalla {
  readonly componente_id: string;
  readonly componente_nombre: string;
  readonly horometro: number;
  readonly temperatura: number | null;
  readonly codigo_error: string | null;
  readonly descripcion: string;
  readonly alerta_id: string | null;
}

export interface ItemCola {
  readonly cliente_id: string;
  readonly tipo: "lectura" | "alerta" | "falla";
  readonly activo_id: string;
  /** Nombre del equipo, para que la lista de pendientes se entienda sin red. */
  readonly equipo: string;
  readonly capturado_en: string;
  readonly valor?: number;
  readonly sintoma?: Sintoma;
  readonly nota?: string | null;
  readonly falla?: DatosFalla;
  readonly usuario_id: string;
  readonly empresa_id: string;
  readonly encolado_en: number;
  intentos: number;
  estado: "pendiente" | "rechazado";
  motivo: string | null;
  /** Rechazo con código estable: `orden_abierta_existente` trae la orden que ya existía. */
  codigo?: string | null;
  orden_id?: string | null;
  numero?: number | null;
}

interface EquipoGuardado {
  readonly clave: string;
  readonly usuario_id: string;
  readonly activo: Activo;
  readonly guardado_en: number;
  /**
   * Último riesgo conocido del equipo (07-fase4, 10.2): sin red se muestra como tal, con la hora de
   * su cálculo. Opcional: los equipos guardados antes de la fase 4 no lo tienen. Es opaco aquí
   * (`RiesgoEquipo` de `@/lib/prediccion`): importarlo crearía un ciclo a través de `@/lib/ordenes`.
   */
  readonly riesgo?: unknown;
}

interface Esquema extends DBSchema {
  cola: { key: string; value: ItemCola; indexes: { usuario: string } };
  equipos: { key: string; value: EquipoGuardado };
  sesion: { key: string; value: Usuario };
}

const MAX_LOTE = 50;
const DIAS_RETENCION_AJENOS = 7;
const ESPERA_MIN_MS = 5_000;
const ESPERA_MAX_MS = 5 * 60_000;

let promesaBase: Promise<IDBPDatabase<Esquema>> | null = null;

function base(): Promise<IDBPDatabase<Esquema>> {
  promesaBase ??= openDB<Esquema>("simap-campo", 1, {
    upgrade(db) {
      const cola = db.createObjectStore("cola", { keyPath: "cliente_id" });
      cola.createIndex("usuario", "usuario_id");
      db.createObjectStore("equipos", { keyPath: "clave" });
      db.createObjectStore("sesion");
    },
  });
  return promesaBase;
}

function disponible(): boolean {
  return typeof indexedDB !== "undefined";
}

// --- Estado observable por la interfaz ------------------------------------------

export interface EstadoCola {
  readonly enLinea: boolean;
  readonly pendientes: number;
  /** Reportes de falla sin enviar. Se avisan aparte, más visibles: perder uno es lo más grave. */
  readonly fallasPendientes: readonly ItemCola[];
  readonly rechazados: readonly ItemCola[];
  readonly sincronizando: boolean;
  /** Cuándo llegó al servidor lo último que se envió desde la cola, para decir «Enviado». */
  readonly ultimoEnvio: number | null;
  /** Ítems de otras personas descartados por antiguos en la última limpieza. */
  readonly descartadosAjenos: number;
}

const ESTADO_SERVIDOR: EstadoCola = {
  enLinea: true,
  pendientes: 0,
  fallasPendientes: [],
  rechazados: [],
  sincronizando: false,
  ultimoEnvio: null,
  descartadosAjenos: 0,
};

let estado: EstadoCola = ESTADO_SERVIDOR;
const oyentes = new Set<() => void>();

function publicar(cambios: Partial<EstadoCola>): void {
  estado = { ...estado, ...cambios };
  for (const oyente of oyentes) oyente();
}

export function suscribirCola(oyente: () => void): () => void {
  oyentes.add(oyente);
  return () => oyentes.delete(oyente);
}

export function estadoCola(): EstadoCola {
  return estado;
}

export function estadoColaServidor(): EstadoCola {
  return ESTADO_SERVIDOR;
}

// --- Cola ------------------------------------------------------------------------

export async function encolar(
  item: Omit<ItemCola, "encolado_en" | "intentos" | "estado" | "motivo">,
): Promise<void> {
  const db = await base();
  await db.put("cola", { ...item, encolado_en: Date.now(), intentos: 0, estado: "pendiente", motivo: null });
  // iOS puede purgar el almacenamiento de un sitio poco usado. Pedir que sea persistente protege la
  // cola; si el navegador dice que no, se sigue igual.
  void navigator.storage?.persist?.().catch(() => false);
  await refrescar(item.usuario_id);
  programar(ESPERA_MIN_MS);
}

async function itemsDe(usuarioId: string): Promise<ItemCola[]> {
  const db = await base();
  return db.getAllFromIndex("cola", "usuario", usuarioId);
}

async function refrescar(usuarioId: string): Promise<void> {
  const items = await itemsDe(usuarioId);
  publicar({
    pendientes: items.filter((i) => i.estado === "pendiente").length,
    fallasPendientes: items.filter((i) => i.estado === "pendiente" && i.tipo === "falla"),
    rechazados: items.filter((i) => i.estado === "rechazado"),
  });
}

/** Quien capturó un ítem rechazado ya lo vio: se quita de la cola. */
export async function descartarRechazados(usuarioId: string): Promise<void> {
  const db = await base();
  const tx = db.transaction("cola", "readwrite");
  for (const item of await tx.store.index("usuario").getAll(usuarioId)) {
    if (item.estado === "rechazado") await tx.store.delete(item.cliente_id);
  }
  await tx.done;
  await refrescar(usuarioId);
}

/** Quien tiene la sesión ya leyó el aviso de capturas ajenas descartadas. */
export function olvidarAvisoDescartados(): void {
  publicar({ descartadosAjenos: 0 });
}

async function purgarAjenosAntiguos(usuarioId: string): Promise<number> {
  const limite = Date.now() - DIAS_RETENCION_AJENOS * 86_400_000;
  const db = await base();
  const tx = db.transaction("cola", "readwrite");
  let descartados = 0;
  for (const item of await tx.store.getAll()) {
    if (item.usuario_id !== usuarioId && item.encolado_en < limite) {
      await tx.store.delete(item.cliente_id);
      descartados += 1;
    }
  }
  await tx.done;
  return descartados;
}

interface ResultadoItem {
  readonly indice: number;
  readonly cliente_id: string | null;
  readonly estado: "creado" | "duplicado" | "rechazado";
  readonly motivo: string | null;
  readonly codigo?: string | null;
  readonly orden_id?: string | null;
  readonly numero?: number | null;
}

/** Lo que se envía al servidor por cada ítem: solo lo que su tipo admite. */
function paraEnviar(item: ItemCola): Record<string, unknown> {
  const comun = { cliente_id: item.cliente_id, activo_id: item.activo_id, capturado_en: item.capturado_en };
  if (item.tipo === "lectura") return { tipo: "lectura", ...comun, valor: item.valor };
  if (item.tipo === "alerta") return { tipo: "alerta", ...comun, sintoma: item.sintoma, nota: item.nota ?? null };
  const f = item.falla;
  return {
    tipo: "falla",
    ...comun,
    componente_id: f?.componente_id,
    horometro: f?.horometro,
    temperatura: f?.temperatura ?? null,
    codigo_error: f?.codigo_error ?? null,
    descripcion: f?.descripcion,
    alerta_id: f?.alerta_id ?? null,
  };
}

/**
 * Envía la cola de una persona. Devuelve cuántos ítems llegaron.
 *
 * Lote a lote, de hasta 50. Si la red falla a mitad, lo que no se confirmó sigue en la cola: nada
 * se borra hasta que el servidor dice «creado» o «duplicado».
 */
export async function sincronizar(usuarioId: string): Promise<number> {
  if (!disponible() || estado.sincronizando) return 0;
  publicar({ sincronizando: true });
  let enviados = 0;
  try {
    const descartados = await purgarAjenosAntiguos(usuarioId);
    if (descartados > 0) publicar({ descartadosAjenos: descartados });

    const pendientes = (await itemsDe(usuarioId))
      .filter((i) => i.estado === "pendiente")
      .sort((a, b) => a.capturado_en.localeCompare(b.capturado_en));

    for (let i = 0; i < pendientes.length; i += MAX_LOTE) {
      const lote = pendientes.slice(i, i + MAX_LOTE);
      const cuerpo = { items: lote.map(paraEnviar) };
      const respuesta = await llamar<{ resultados: ResultadoItem[] }>("/campo/lotes", {
        method: "POST",
        cuerpo,
      });

      const db = await base();
      const tx = db.transaction("cola", "readwrite");
      for (const r of respuesta.resultados) {
        const item = lote[r.indice];
        if (item === undefined) continue;
        if (r.estado === "rechazado") {
          // No se reintenta: daría el mismo resultado. Una falla de un componente que ya tiene orden
          // abierta vuelve con esa orden, para que quien la capturó pueda abrirla.
          await tx.store.put({
            ...item,
            estado: "rechazado",
            motivo: r.motivo,
            codigo: r.codigo ?? null,
            orden_id: r.orden_id ?? null,
            numero: r.numero ?? null,
            intentos: item.intentos + 1,
          });
        } else {
          await tx.store.delete(item.cliente_id);
          enviados += 1;
        }
      }
      await tx.done;
    }
    if (enviados > 0) publicar({ ultimoEnvio: Date.now() });
    publicar({ enLinea: true });
    return enviados;
  } catch (error) {
    // Sin red, o la sesión caducó del todo (401 tras intentar renovarla): la cola queda intacta
    // y se reintentará. Cualquier otro error también la conserva; perder capturas es lo único que
    // esta función no puede hacer.
    if (error instanceof ErrorApi && error.esFalloDeRed) publicar({ enLinea: false });
    return enviados;
  } finally {
    publicar({ sincronizando: false });
    await refrescar(usuarioId);
  }
}

// --- Disparadores -------------------------------------------------------------------

let usuarioActivo: string | null = null;
let temporizador: ReturnType<typeof setTimeout> | null = null;
let espera = ESPERA_MIN_MS;

function programar(ms: number): void {
  if (temporizador !== null) clearTimeout(temporizador);
  temporizador = setTimeout(() => void ciclo(), ms);
}

async function ciclo(): Promise<void> {
  temporizador = null;
  if (usuarioActivo === null) return;
  await sincronizar(usuarioActivo);
  if (estado.pendientes > 0) {
    // Retroceso exponencial mientras quede algo: no martillear un servidor caído ni gastar la
    // batería de un teléfono que pasa la tarde sin cobertura.
    espera = Math.min(espera * 2, ESPERA_MAX_MS);
    programar(espera);
  } else {
    espera = ESPERA_MIN_MS;
  }
}

function alVolverLaRed(): void {
  publicar({ enLinea: true });
  espera = ESPERA_MIN_MS;
  void ciclo();
}

function alPerderLaRed(): void {
  publicar({ enLinea: false });
}

function alVolverAPrimerPlano(): void {
  if (document.visibilityState === "visible") void ciclo();
}

/**
 * Empieza a vigilar la cola de esta persona. Se llama al cargar cualquier pantalla con sesión; es
 * idempotente. Devuelve la función que deja de vigilar.
 */
export function vigilarCola(usuarioId: string): () => void {
  if (!disponible()) return () => undefined;
  usuarioActivo = usuarioId;
  publicar({ enLinea: navigator.onLine });
  window.addEventListener("online", alVolverLaRed);
  window.addEventListener("offline", alPerderLaRed);
  document.addEventListener("visibilitychange", alVolverAPrimerPlano);
  void ciclo();
  return () => {
    window.removeEventListener("online", alVolverLaRed);
    window.removeEventListener("offline", alPerderLaRed);
    document.removeEventListener("visibilitychange", alVolverAPrimerPlano);
    if (temporizador !== null) clearTimeout(temporizador);
    temporizador = null;
  };
}

// --- Lo que se guarda para consultar sin red ---------------------------------------

/**
 * Guarda la ficha de un equipo escaneado, para poder mostrarla sin red (marcada como no
 * actualizada). Es de la persona que la vio: en un teléfono compartido nadie ve lo que guardó otro.
 */
export async function guardarEquipo(usuarioId: string, activo: Activo): Promise<void> {
  if (!disponible()) return;
  const db = await base();
  const clave = `${usuarioId}:${activo.codigo}`;
  // Se conserva el riesgo ya guardado: la ficha y el riesgo llegan por separado.
  const previo = await db.get("equipos", clave);
  await db.put("equipos", { clave, usuario_id: usuarioId, activo, guardado_en: Date.now(), riesgo: previo?.riesgo });
}

/** Guarda el último riesgo calculado de un equipo ya guardado, para mostrarlo sin red. */
export async function guardarRiesgo(usuarioId: string, codigo: string, riesgo: unknown): Promise<void> {
  if (!disponible()) return;
  const db = await base();
  const fila = await db.get("equipos", `${usuarioId}:${codigo}`);
  if (fila === undefined) return;
  await db.put("equipos", { ...fila, riesgo });
}

export async function equipoGuardado(
  usuarioId: string,
  codigo: string,
): Promise<{ activo: Activo; guardado_en: number; riesgo: unknown } | null> {
  if (!disponible()) return null;
  const db = await base();
  const fila = await db.get("equipos", `${usuarioId}:${codigo}`);
  return fila === undefined ? null : { activo: fila.activo, guardado_en: fila.guardado_en, riesgo: fila.riesgo ?? null };
}

/** Quién tiene la sesión, guardado para poder capturar sin red y saber a quién pertenece lo capturado. */
export async function guardarSesion(usuario: Usuario): Promise<void> {
  if (!disponible()) return;
  const db = await base();
  await db.put("sesion", usuario, "actual");
}

export async function sesionGuardada(): Promise<Usuario | null> {
  if (!disponible()) return null;
  const db = await base();
  return (await db.get("sesion", "actual")) ?? null;
}

/**
 * Al cerrar sesión: se olvidan los equipos guardados y la identidad, **no la cola**. Lo capturado
 * y aún no enviado es de quien lo capturó y se enviará cuando vuelva a entrar.
 */
export async function olvidarDatosDeSesion(): Promise<void> {
  usuarioActivo = null;
  if (!disponible()) return;
  const db = await base();
  const tx = db.transaction(["equipos", "sesion"], "readwrite");
  await tx.objectStore("equipos").clear();
  await tx.objectStore("sesion").clear();
  await tx.done;
  publicar({ pendientes: 0, fallasPendientes: [], rechazados: [] });
}
