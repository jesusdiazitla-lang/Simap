/**
 * Página 404 propia (08-fase5, 10.2).
 *
 * La de Next trae `style="…"` y un `<style>` sin nonce: la política de contenido los bloquea y en
 * producción la página salía sin estilos y con errores en la consola. Esta usa el marco de siempre,
 * solo con clases. El enlace va al panel: si no hay sesión, el proxy lo manda al acceso.
 */

import Link from "next/link";

import { Marco, Panel } from "@/components/marco";

export default function NoEncontrada() {
  return (
    <Marco centrado>
      <div className="mx-auto w-full max-w-[26rem]">
        <Panel titulo="Esta página no existe">
          <div className="flex flex-col gap-4">
            <p className="text-[0.9375rem] leading-6 text-texto-suave">
              La dirección no corresponde a ninguna pantalla de SIMAP. Si llegaste desde un enlace,
              puede que esté mal copiado o que la pantalla haya cambiado de sitio.
            </p>
            <Link href="/panel" className="font-semibold text-accion underline underline-offset-2">
              Ir a tu panel
            </Link>
          </div>
        </Panel>
      </div>
    </Marco>
  );
}
