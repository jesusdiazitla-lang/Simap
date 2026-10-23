"use client";

/**
 * Configuración de la predicción de la empresa (07-fase4, decisión 5 y 7.1). Solo el administrador.
 *
 * Seis números con sus límites a la vista: los mismos que impone la base, que rechazaría cualquier
 * otro. Cada uno dice qué cambia en la práctica, porque ninguno es obvio: un umbral más bajo evita
 * más fallas pero pide más cambios de pieza (sección 14.5), y ese balance es de cada empresa.
 * Al guardar, el riesgo de todos los equipos se recalcula en segundo plano.
 */

import { useEffect, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { Panel } from "@/components/marco";
import { Esqueleto, Pantalla } from "@/components/pantalla";
import { ErrorApi } from "@/lib/api";
import type { Rol } from "@/lib/auth";
import { guardarConfiguracion, leerConfiguracion, type Configuracion } from "@/lib/prediccion";

const ROLES: readonly Rol[] = ["administrador"];

type Clave = keyof Configuracion;

interface Definicion {
  readonly clave: Clave;
  readonly etiqueta: string;
  readonly ayuda: string;
  readonly minimo: number;
  readonly maximo: number;
  /** El umbral se escribe en porcentaje y se guarda como fracción. */
  readonly porcentaje?: boolean;
  readonly decimales?: boolean;
}

const CAMPOS: readonly Definicion[] = [
  {
    clave: "umbral_riesgo",
    etiqueta: "Umbral de alerta (%)",
    ayuda: "Desde qué riesgo se crea una alerta. Más bajo evita más fallas, pero pide cambiar piezas más a menudo. Entre 5 y 95.",
    minimo: 5,
    maximo: 95,
    porcentaje: true,
  },
  {
    clave: "horizonte_horas",
    etiqueta: "Horizonte (horas de operación)",
    ayuda: "La ventana del riesgo: probabilidad de falla en las próximas N horas de trabajo del equipo. Entre 1 y 2000.",
    minimo: 1,
    maximo: 2000,
  },
  {
    clave: "alertas_minimas",
    etiqueta: "Alertas de campo para subir el riesgo",
    ayuda: "Cuántas alertas del personal (pendientes o revisadas) activan el multiplicador. Entre 1 y 20.",
    minimo: 1,
    maximo: 20,
  },
  {
    clave: "ventana_alertas_dias",
    etiqueta: "Ventana de esas alertas (días)",
    ayuda: "Solo cuentan las alertas de los últimos N días. Entre 1 y 90.",
    minimo: 1,
    maximo: 90,
  },
  {
    clave: "multiplicador_alertas",
    etiqueta: "Multiplicador por alertas de campo",
    ayuda: "Cuánto sube la intensidad de falla con esas alertas: 1,30 es un 30 % más. Entre 1,00 y 2,00.",
    minimo: 1,
    maximo: 2,
    decimales: true,
  },
  {
    clave: "descarte_silencio_dias",
    etiqueta: "Silencio tras descartar (días)",
    ayuda: "Cuánto calla un componente cuya alerta se descartó. Pasado el plazo, si sigue alto, vuelve a avisar. Entre 1 y 90.",
    minimo: 1,
    maximo: 90,
  },
];

function aTexto(def: Definicion, valor: string | number): string {
  if (def.porcentaje) return String(Math.round(Number(valor) * 1000) / 10);
  if (def.decimales) return Number(valor).toFixed(2);
  return String(valor);
}

export default function ConfiguracionPage() {
  return (
    <Pantalla roles={ROLES} cargando="Predicción">
      {() => <Formulario />}
    </Pantalla>
  );
}

function Formulario() {
  const [actual, setActual] = useState<Configuracion | null>(null);
  const [textos, setTextos] = useState<Partial<Record<Clave, string>>>({});
  const [errores, setErrores] = useState<Partial<Record<Clave, string>>>({});
  const [enCurso, setEnCurso] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function cargarEn(c: Configuracion): void {
    setActual(c);
    setTextos(Object.fromEntries(CAMPOS.map((d) => [d.clave, aTexto(d, c[d.clave])])));
  }

  useEffect(() => {
    const control = new AbortController();
    leerConfiguracion(control.signal)
      .then(cargarEn)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError("No se pudo cargar la configuración.");
      });
    return () => control.abort();
  }, []);

  async function guardar(): Promise<void> {
    if (actual === null) return;
    const nuevos: Partial<Record<Clave, string>> = {};
    const cambios: Partial<Record<Clave, string | number>> = {};
    for (const d of CAMPOS) {
      const texto = (textos[d.clave] ?? "").replace(",", ".").trim();
      const n = Number(texto);
      if (texto === "" || Number.isNaN(n) || n < d.minimo || n > d.maximo || (!d.decimales && !d.porcentaje && !Number.isInteger(n))) {
        nuevos[d.clave] = `Entre ${d.minimo} y ${d.maximo}.`;
        continue;
      }
      if (aTexto(d, actual[d.clave]) !== aTexto(d, d.porcentaje ? n / 100 : n)) {
        cambios[d.clave] = d.porcentaje ? (n / 100).toFixed(3) : d.decimales ? n.toFixed(2) : n;
      }
    }
    setErrores(nuevos);
    setMensaje(null);
    if (Object.keys(nuevos).length > 0) return;
    if (Object.keys(cambios).length === 0) {
      setMensaje("No hay cambios que guardar.");
      return;
    }
    setEnCurso(true);
    setError(null);
    try {
      cargarEn(await guardarConfiguracion(cambios));
      setMensaje("Guardado. El riesgo de todos los equipos se está recalculando con estos valores.");
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo guardar.");
    } finally {
      setEnCurso(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-[1.375rem] font-semibold leading-7 text-texto">Predicción</h1>
        <p className="pt-1 text-[0.9375rem] leading-6 text-texto-suave">
          Cómo calcula SIMAP el riesgo de falla y cuándo avisa, para toda la empresa.
        </p>
      </div>
      <Panel
        nivel={2}
        titulo="Parámetros de la empresa"
        pie="Con el umbral del 25 %, las simulaciones del proyecto evitan cerca de la mitad de las fallas a cambio de un cambio planificado por cada falla evitada. Lo que conviene depende de cuánto cuesta aquí una falla frente a un cambio programado."
      >
        {actual === null ? (
          error !== null ? (
            <p role="alert" className="text-[0.9375rem] text-error">{error}</p>
          ) : (
            <Esqueleto />
          )
        ) : (
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void guardar();
            }}
            className="flex flex-col gap-4"
          >
            {CAMPOS.map((d) => (
              <Campo
                key={d.clave}
                etiqueta={d.etiqueta}
                ayuda={d.ayuda}
                nombre={d.clave}
                modoTeclado={d.decimales ? "text" : "numeric"}
                valor={textos[d.clave] ?? ""}
                onCambio={(v) => setTextos((t) => ({ ...t, [d.clave]: v }))}
                error={errores[d.clave]}
                maxLength={6}
                autoComplete="off"
              />
            ))}
            <div>
              <Boton enCurso={enCurso} textoEnCurso="Guardando…">
                Guardar la configuración
              </Boton>
            </div>
            {mensaje !== null ? <p role="status" className="text-[0.9375rem] text-texto-suave">{mensaje}</p> : null}
            {error !== null ? <p role="alert" className="text-[0.9375rem] text-error">{error}</p> : null}
          </form>
        )}
      </Panel>
    </div>
  );
}
