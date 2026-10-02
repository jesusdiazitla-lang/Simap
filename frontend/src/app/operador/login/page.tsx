"use client";

/**
 * Acceso a la consola del operador de SIMAP.
 *
 * Es una pantalla aparte de `/login` a propósito, aunque se parezcan: son dos planos distintos con
 * dos sesiones distintas, y compartir la pantalla llevaría antes o después a compartir el código
 * que decide a cuál de los dos se está entrando.
 *
 * La barra superior lo dice en texto, no solo con un color: quien llega aquí tiene que saber que
 * está en la consola del proveedor y no en la de su empresa.
 */

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { z } from "zod";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { EtiquetaConsola, Marco, Panel } from "@/components/marco";
import { ErrorApi } from "@/lib/api";
import { entrarComoOperador } from "@/lib/operador";

const ID_FORMULARIO = "consola-form";
const ID_CORREO = "consola-correo";
const ID_CLAVE = "consola-clave";

const esquema = z.object({
  correo: z
    .string()
    .trim()
    .min(1, "Escribe tu correo.")
    .email("Ese correo no tiene un formato válido."),
  password: z.string().min(1, "Escribe tu contraseña."),
});

type Campos = "correo" | "password";

export default function AccesoConsolaPage() {
  const router = useRouter();
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [errores, setErrores] = useState<Partial<Record<Campos, string>>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const avisoRef = useRef<HTMLDivElement>(null);

  function anotar(texto: string): void {
    setAviso(texto);
    requestAnimationFrame(() => avisoRef.current?.focus());
  }

  async function enviar(evento: React.FormEvent<HTMLFormElement>): Promise<void> {
    evento.preventDefault();
    if (enCurso) return;

    const resultado = esquema.safeParse({ correo, password });
    if (!resultado.success) {
      const nuevos: Partial<Record<Campos, string>> = {};
      for (const problema of resultado.error.issues) {
        const campo = problema.path[0] as Campos | undefined;
        if (campo !== undefined) nuevos[campo] ??= problema.message;
      }
      setErrores(nuevos);
      anotar("Faltan datos. Revisa los campos marcados.");
      return;
    }

    setErrores({});
    setAviso(null);
    setEnCurso(true);
    try {
      await entrarComoOperador(resultado.data.correo, resultado.data.password);
      router.replace("/operador");
    } catch (error) {
      setEnCurso(false);
      anotar(
        error instanceof ErrorApi
          ? error.message
          : "Algo falló de forma inesperada. Vuelve a intentarlo.",
      );
    }
  }

  const campoInvalido = errores.correo !== undefined ? ID_CORREO : ID_CLAVE;
  const hayErroresDeCampo = errores.correo !== undefined || errores.password !== undefined;

  return (
    <Marco barra={<EtiquetaConsola />} centrado>
      <div className="mx-auto w-full max-w-[26rem]">
        <Panel
          titulo="Consola del operador"
          descripcion="Acceso para quien opera SIMAP, no para los usuarios de una empresa."
          pie="Si eres usuario de una planta, tu acceso es la pantalla principal de SIMAP, no esta."
        >
          <form id={ID_FORMULARIO} onSubmit={enviar} noValidate className="flex flex-col gap-3">
            <Campo
              id={ID_CORREO}
              etiqueta="Correo"
              nombre="correo"
              tipo="email"
              valor={correo}
              onCambio={setCorreo}
              error={errores.correo}
              autoComplete="username"
              requerido
              autoFocus
              deshabilitado={enCurso}
            />

            <Campo
              id={ID_CLAVE}
              etiqueta="Contraseña"
              nombre="password"
              tipo="password"
              valor={password}
              onCambio={setPassword}
              error={errores.password}
              autoComplete="current-password"
              requerido
              deshabilitado={enCurso}
            />

            <Boton form={ID_FORMULARIO} enCurso={enCurso} textoEnCurso="Comprobando…" anchoCompleto>
              Entrar
            </Boton>

            {/* Debajo del botón y sin hueco reservado: al aparecer no mueve nada que importe. */}
            <div
              ref={avisoRef}
              tabIndex={-1}
              role="alert"
              className="rounded-[var(--radius-control)] outline-none empty:hidden"
            >
              {aviso !== null ? (
                <p className="rounded-[var(--radius-control)] border border-error bg-error-fondo px-3 py-2 text-[0.875rem] leading-5 text-error">
                  {aviso}
                  {hayErroresDeCampo ? (
                    <>
                      {" "}
                      <a
                        href={`#${campoInvalido}`}
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
        </Panel>
      </div>
    </Marco>
  );
}
