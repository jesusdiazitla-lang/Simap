/**
 * La sesión de una pantalla del plano de datos: quién es, si puede estar aquí, y si hay red.
 *
 * Toda pantalla con sesión empieza igual: preguntar a `/auth/yo` quién está, mandar al acceso a
 * quien no tiene sesión (recordando a dónde iba), y arrancar la sincronización de su cola sin
 * conexión. Escrito una vez aquí en lugar de repetido en cada pantalla, donde acabaría divergiendo.
 *
 * SIN RED
 * -------
 * Si el servidor no responde, se usa la identidad guardada la última vez que hubo red. Es lo que
 * permite capturar en una sala de máquinas sin cobertura y que lo capturado quede a nombre de quien
 * lo capturó. No da ningún permiso: el servidor vuelve a comprobarlo todo al recibir la cola.
 */

"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorApi } from "@/lib/api";
import { salir, usuarioActual, type Rol, type Usuario } from "@/lib/auth";
import {
  guardarSesion,
  olvidarDatosDeSesion,
  sesionGuardada,
  vigilarCola,
} from "@/lib/offline-queue";

export type EstadoSesion =
  | { readonly tipo: "cargando" }
  | { readonly tipo: "lista"; readonly usuario: Usuario; readonly sinRed: boolean }
  | { readonly tipo: "sin-permiso"; readonly usuario: Usuario }
  | { readonly tipo: "error"; readonly mensaje: string };

/**
 * La sesión de esta pantalla. Con `roles`, quien tenga otro rol recibe `sin-permiso`: la pantalla
 * lo dice en vez de enseñar un formulario que la API rechazaría.
 */
export function useSesion(roles?: readonly Rol[]): EstadoSesion {
  const router = useRouter();
  const ruta = usePathname();
  const [estado, setEstado] = useState<EstadoSesion>({ tipo: "cargando" });
  const clavesRoles = roles?.join(",") ?? "";

  useEffect(() => {
    const control = new AbortController();
    let dejarDeVigilar: (() => void) | null = null;
    const permitido = (u: Usuario): boolean =>
      clavesRoles === "" || clavesRoles.split(",").includes(u.rol);

    void (async () => {
      try {
        const usuario = await usuarioActual(control.signal);
        if (usuario === null) {
          const destino = `${ruta}${window.location.search}`;
          router.replace(`/login?next=${encodeURIComponent(destino)}`);
          return;
        }
        await guardarSesion(usuario);
        dejarDeVigilar = vigilarCola(usuario.id);
        setEstado(
          permitido(usuario)
            ? { tipo: "lista", usuario, sinRed: false }
            : { tipo: "sin-permiso", usuario },
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ErrorApi && error.esFalloDeRed) {
          const guardado = await sesionGuardada();
          if (guardado !== null) {
            dejarDeVigilar = vigilarCola(guardado.id);
            setEstado(
              permitido(guardado)
                ? { tipo: "lista", usuario: guardado, sinRed: true }
                : { tipo: "sin-permiso", usuario: guardado },
            );
            return;
          }
        }
        setEstado({
          tipo: "error",
          mensaje:
            "No se pudo hablar con el servidor de SIMAP. Comprueba la conexión o avisa a quien lo " +
            "administra.",
        });
      }
    })();

    return () => {
      control.abort();
      dejarDeVigilar?.();
    };
  }, [router, ruta, clavesRoles]);

  return estado;
}

/**
 * Cierra la sesión y olvida lo guardado para consultar sin red, **pero no la cola**: lo capturado y
 * aún no enviado se enviará cuando esa persona vuelva a entrar.
 */
export async function cerrarSesion(): Promise<void> {
  try {
    await salir();
  } finally {
    await olvidarDatosDeSesion();
  }
}
