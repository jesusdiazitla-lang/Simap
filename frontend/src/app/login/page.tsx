"use client";

/**
 * Pantalla de acceso (RF-02, CU-06), la misma para todos: usuarios de las empresas y operador de
 * SIMAP. Quién es quién lo decide `src/lib/acceso.ts`; por debajo los dos planos siguen separados.
 *
 * Sin texto de presentación del producto: quien llega ya sabe qué es SIMAP. Y sin camino de
 * registro, porque el alta de una empresa es por invitación y la crea quien opera SIMAP con
 * `python -m app.cli crear-empresa`.
 *
 * SOBRE LA VALIDACIÓN
 * -------------------
 * Se valida con Zod en el cliente para no gastar una petición (ni un hash Argon2id de 64 MiB en el
 * servidor) en un correo al que le falta la arroba. Pero la validación del cliente **no es la
 * seguridad**: el backend vuelve a validar lo mismo con Pydantic, y si los dos discrepan gana el
 * backend. Aquí solo se evita el viaje.
 *
 * Se usa Zod suelto y `useState` en lugar de react-hook-form porque son dos campos. La librería
 * entra en F2, donde los formularios de horómetro y alerta tienen ramas y pasos de verdad.
 */

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { z } from "zod";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { FechaHora, Marco, Panel } from "@/components/marco";
import { ErrorApi } from "@/lib/api";
import { acceder } from "@/lib/acceso";
import { rutaInicialPara } from "@/lib/auth";
import { destinoSeguro } from "@/lib/qr";

const ID_FORMULARIO = "acceso-form";
const ID_CORREO = "acceso-correo";
const ID_CLAVE = "acceso-clave";

const esquema = z.object({
  correo: z
    .string()
    .trim()
    .min(1, "Escribe tu correo.")
    .email("Ese correo no tiene un formato válido."),
  password: z.string().min(1, "Escribe tu contraseña."),
});

type Campos = "correo" | "password";

export default function AccesoPage() {
  const router = useRouter();
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [errores, setErrores] = useState<Partial<Record<Campos, string>>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const avisoRef = useRef<HTMLDivElement>(null);

  function anotar(texto: string): void {
    setAviso(texto);
    // El foco va al aviso tras un envío fallido: es lo que hace que quien navega con teclado o con
    // lector de pantalla se entere de que pasó algo, sin mover el foco mientras se escribe.
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
      const acceso = await acceder(resultado.data.correo, resultado.data.password);
      if (acceso.plano === "operador") {
        // El operador va siempre a su consola, aunque viniera de otra dirección: `next` es para las
        // pantallas de las plantas, a las que su sesión no da acceso.
        router.replace("/operador");
        return;
      }
      // No se guarda nada del usuario en el navegador: el rol se vuelve a pedir al servidor en el
      // panel. Aquí solo se usa para saber a dónde llevarlo.
      // Si se llegó aquí desde una dirección protegida (una etiqueta escaneada sin sesión), se vuelve
      // a ella; si no, al panel del rol. El destino se valida: nunca otro sitio.
      const siguiente = destinoSeguro(new URLSearchParams(window.location.search).get("next"));
      router.replace(siguiente ?? rutaInicialPara(acceso.sesion.usuario.rol));
    } catch (error) {
      setEnCurso(false);
      if (!(error instanceof ErrorApi)) {
        anotar("Algo falló de forma inesperada. Vuelve a intentarlo.");
        return;
      }
      if (error.estado === 422) {
        setErrores({ correo: error.campos.correo, password: error.campos.password });
        anotar(error.message);
        return;
      }
      if (error.estado === 429) {
        const espera = error.esperaSegundos;
        anotar(
          espera !== undefined
            ? `Demasiados intentos. Vuelve a probar en ${espera} segundos.`
            : error.message,
        );
        return;
      }
      anotar(error.message);
    }
  }

  const campoInvalido = errores.correo !== undefined ? ID_CORREO : ID_CLAVE;
  const hayErroresDeCampo = errores.correo !== undefined || errores.password !== undefined;

  return (
    <Marco barra={<FechaHora />} centrado>
      <div className="mx-auto w-full max-w-[26rem]">
        <Panel
          titulo="Iniciar sesión"
          descripcion="Entra con tu correo y tu contraseña."
          pie="El acceso a SIMAP es por invitación. Si tu empresa todavía no tiene cuenta, o no recuerdas tu contraseña, habla con quien administra SIMAP en tu planta."
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

            {/* El aviso va DEBAJO del botón, y ahí no hace falta reservarle hueco.
                Puesto encima del formulario tenía que llevar altura fija, porque al aparecer
                empujaba el botón hacia abajo justo cuando el usuario iba a volver a pulsarlo —el
                fallo clásico de los formularios de acceso—; y reservar el hueco dejaba un vacío
                permanente en la parte alta del panel que parece un error de maquetación. Debajo,
                crecer no mueve nada que importe.
                Sigue siendo alcanzable: recibe el foco al fallar el envío y va con `role="alert"`,
                así que un lector de pantalla lo anuncia sin que haya que ir a buscarlo. */}
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
