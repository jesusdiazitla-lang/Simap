"use client";

/**
 * Cambio de la contraseña propia. Lo usan los dos planos: el panel de una empresa y la consola del
 * operador.
 *
 * No sabe a cuál de los dos sirve: recibe la función que habla con la API. Así el componente no
 * importa ni `lib/auth` ni `lib/operador`, y no hay forma de que una pantalla de cliente acabe
 * llamando al endpoint del operador porque el formulario «ya lo tenía importado».
 *
 * Pide la clave nueva dos veces. En un login sobra —si te equivocas, vuelves a probar—, pero aquí
 * un error de tecleo que nadie ve deja a la persona fuera de su cuenta, y en una planta no hay a
 * quién pedirle ayuda a las tres de la madrugada.
 */

import { useRef, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { ErrorApi } from "@/lib/api";

/** Igual que `MIN_PASSWORD` en `backend/app/schemas/auth.py`. El servidor lo vuelve a comprobar. */
const MIN_CLAVE = 12;

type Campos = "actual" | "nueva" | "repetida";

interface FormularioClaveProps {
  /** Prefijo de los `id`, para que dos formularios en el mismo documento no choquen. */
  readonly prefijo: string;
  /** Llama a la API. Debe lanzar `ErrorApi` si falla. */
  readonly cambiar: (actual: string, nueva: string) => Promise<void>;
  /** Qué hacer cuando la clave ya cambió. */
  readonly alTerminar: () => void;
}

export function FormularioClave({ prefijo, cambiar, alTerminar }: FormularioClaveProps) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const [errores, setErrores] = useState<Partial<Record<Campos, string>>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const avisoRef = useRef<HTMLDivElement>(null);

  const idFormulario = `${prefijo}-form`;
  const ids: Record<Campos, string> = {
    actual: `${prefijo}-actual`,
    nueva: `${prefijo}-nueva`,
    repetida: `${prefijo}-repetida`,
  };

  function anotar(texto: string): void {
    setAviso(texto);
    requestAnimationFrame(() => avisoRef.current?.focus());
  }

  function validar(): Partial<Record<Campos, string>> {
    const fallos: Partial<Record<Campos, string>> = {};
    if (actual.trim() === "") fallos.actual = "Escribe tu contraseña actual.";
    // Se mide recortada porque así la guarda el servidor (ver `CambioClaveRequest`).
    if (nueva.trim().length < MIN_CLAVE) {
      fallos.nueva = `Tiene que tener al menos ${MIN_CLAVE} caracteres.`;
    } else if (nueva.trim() === actual.trim()) {
      fallos.nueva = "Tiene que ser distinta de la actual.";
    }
    if (repetida !== nueva) fallos.repetida = "No coincide con la contraseña nueva.";
    return fallos;
  }

  async function enviar(evento: React.FormEvent<HTMLFormElement>): Promise<void> {
    evento.preventDefault();
    if (enCurso) return;

    const fallos = validar();
    if (Object.keys(fallos).length > 0) {
      setErrores(fallos);
      anotar("Revisa los campos marcados.");
      return;
    }

    setErrores({});
    setAviso(null);
    setEnCurso(true);
    try {
      await cambiar(actual, nueva);
      alTerminar();
    } catch (error) {
      setEnCurso(false);
      if (error instanceof ErrorApi && error.estado === 400) {
        // La actual estaba mal: el mensaje va junto a ese campo, que es donde hay que corregir.
        setErrores({ actual: error.message });
        anotar(error.message);
        return;
      }
      if (error instanceof ErrorApi && error.estado === 401) {
        anotar("Tu sesión ha caducado. Vuelve a entrar para cambiar la contraseña.");
        return;
      }
      anotar(
        error instanceof ErrorApi
          ? error.message
          : "Algo falló de forma inesperada. Vuelve a intentarlo.",
      );
    }
  }

  const primerInvalido = (["actual", "nueva", "repetida"] as const).find(
    (campo) => errores[campo] !== undefined,
  );

  return (
    <form id={idFormulario} onSubmit={enviar} noValidate className="flex flex-col gap-3">
      <Campo
        id={ids.actual}
        etiqueta="Contraseña actual"
        nombre="password_actual"
        tipo="password"
        valor={actual}
        onCambio={setActual}
        error={errores.actual}
        autoComplete="current-password"
        requerido
        autoFocus
        deshabilitado={enCurso}
      />
      <Campo
        id={ids.nueva}
        etiqueta={`Contraseña nueva · mínimo ${MIN_CLAVE} caracteres`}
        nombre="password_nueva"
        tipo="password"
        valor={nueva}
        onCambio={setNueva}
        error={errores.nueva}
        // Le dice al gestor de contraseñas que proponga una y la guarde en lugar de la anterior.
        autoComplete="new-password"
        requerido
        deshabilitado={enCurso}
      />
      <Campo
        id={ids.repetida}
        etiqueta="Repite la contraseña nueva"
        nombre="password_repetida"
        tipo="password"
        valor={repetida}
        onCambio={setRepetida}
        error={errores.repetida}
        autoComplete="new-password"
        requerido
        deshabilitado={enCurso}
      />

      <Boton form={idFormulario} enCurso={enCurso} textoEnCurso="Cambiando…" anchoCompleto>
        Cambiar contraseña
      </Boton>

      {/* Debajo del botón, como en el acceso: al aparecer no mueve nada que haya que pulsar. */}
      <div
        ref={avisoRef}
        tabIndex={-1}
        role="alert"
        className="rounded-[var(--radius-control)] outline-none empty:hidden"
      >
        {aviso !== null ? (
          <p className="rounded-[var(--radius-control)] border border-error bg-error-fondo px-3 py-2 text-[0.875rem] leading-5 text-error">
            {aviso}
            {primerInvalido !== undefined ? (
              <>
                {" "}
                <a
                  href={`#${ids[primerInvalido]}`}
                  className="font-semibold underline underline-offset-2"
                >
                  Ir al campo
                </a>
              </>
            ) : null}
          </p>
        ) : null}
      </div>
    </form>
  );
}
