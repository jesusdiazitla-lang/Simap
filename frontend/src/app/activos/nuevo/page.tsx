"use client";

/** Alta de un equipo (RF-04, RF-05). Al guardar, se va a imprimir su etiqueta: es el paso siguiente. */

import { useRouter } from "next/navigation";

import { FormularioActivo } from "@/components/formulario-activo";
import { Panel } from "@/components/marco";
import { Pantalla } from "@/components/pantalla";
import { crearActivo } from "@/lib/activos";

export default function NuevoActivoPage() {
  const router = useRouter();
  return (
    <Pantalla roles={["administrador"]} cargando="Nuevo equipo">
      {() => (
        <div className="mx-auto max-w-3xl">
          <Panel
            titulo="Dar de alta un equipo"
            descripcion="SIMAP le genera un código QR único. Después podrás imprimir la etiqueta para pegarla en la máquina."
          >
            <FormularioActivo
              inicial={null}
              textoBoton="Dar de alta y crear etiqueta"
              conHorometro
              guardar={async (ficha, horometro) => {
                const activo = await crearActivo({ ...ficha, horometro_inicial: horometro });
                router.replace(`/activos/${activo.id}/etiqueta?nuevo=1`);
              }}
            />
          </Panel>
        </div>
      )}
    </Pantalla>
  );
}
