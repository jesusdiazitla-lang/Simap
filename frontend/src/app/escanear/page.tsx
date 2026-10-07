"use client";

/**
 * Escanear un equipo desde dentro de la aplicación, o teclear el código de su etiqueta.
 *
 * La cámara nativa del teléfono es el camino principal —el QR abre la pantalla del equipo directamente,
 * sin pasar por aquí—. Esta pantalla es la alternativa, y el código tecleado es el respaldo para la
 * etiqueta sucia o rayada que ninguna cámara lee (05-fase2-activos-y-campo.md, 6.1).
 */

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { Boton } from "@/components/boton";
import { Campo } from "@/components/campo";
import { EscanerQR } from "@/components/escaner-qr";
import { Panel } from "@/components/marco";
import { Pantalla } from "@/components/pantalla";
import { normalizarCodigo } from "@/lib/qr";

export default function EscanearPage() {
  return (
    <Pantalla cargando="Escanear equipo">
      {() => <Escanear />}
    </Pantalla>
  );
}

function Escanear() {
  const router = useRouter();
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState<string | undefined>();
  const abrir = useCallback((c: string) => router.push(`/a/${c}`), [router]);

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <Panel titulo="Escanear equipo" descripcion="Apunta a la etiqueta QR pegada en la máquina.">
        <EscanerQR alLeer={abrir} />
      </Panel>

      <Panel
        nivel={2}
        titulo="Teclear el código"
        descripcion="Los ocho caracteres impresos bajo el QR, por ejemplo XK7P-2QH9."
      >
        <form
          noValidate
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const c = normalizarCodigo(codigo);
            if (c === null) {
              setError("Son ocho letras y números, sin I, O, 0 ni 1. Revisa la etiqueta.");
              return;
            }
            abrir(c);
          }}
        >
          <Campo
            id="codigo-tecleado"
            etiqueta="Código de la etiqueta"
            nombre="codigo"
            valor={codigo}
            onCambio={(v) => {
              setCodigo(v.toUpperCase());
              setError(undefined);
            }}
            error={error}
            autoComplete="off"
            maxLength={12}
          />
          <Boton variante="secundario" anchoCompleto deshabilitado={codigo.trim() === ""}>
            Abrir equipo
          </Boton>
        </form>
      </Panel>
    </div>
  );
}
