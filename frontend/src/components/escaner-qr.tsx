"use client";

/**
 * Escáner de QR dentro de la aplicación (05-fase2-activos-y-campo.md, sección 7.4).
 *
 * Es la alternativa a la cámara nativa del teléfono, que abre la URL del QR directamente y no
 * necesita nada de esto. Sirve cuando la cámara nativa no ofrece abrir enlaces, o para no salir de
 * la aplicación entre equipo y equipo durante una ronda.
 *
 * QUÉ LEE Y QUÉ NO
 * ----------------
 * El contenido leído pasa por `codigoDesdeQr`, que solo acepta `{este origen}/a/{código válido}`.
 * Un QR ajeno pegado encima de una etiqueta no lleva a ninguna parte: se dice que no es de SIMAP y se
 * sigue escaneando.
 *
 * CÓMO LEE
 * --------
 * Con `BarcodeDetector` del navegador donde existe (Chrome en Android), que usa el lector del
 * sistema. Donde no existe (Safari en iOS), con jsQR sobre fotogramas del vídeo. Se descartó
 * `html5-qrcode`, que proponía el documento: no publica versiones desde 2023.
 *
 * La cámara no se abre sola: se abre al pulsar. Un permiso de cámara pedido nada más cargar, sin que
 * la persona sepa por qué, se deniega por reflejo, y luego no hay forma fácil de deshacerlo.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Boton } from "@/components/boton";
import { IconoAviso, IconoEscanear } from "@/components/iconos";
import { codigoDesdeQr } from "@/lib/qr";

type Detector = { detect(fuente: CanvasImageSource): Promise<Array<{ rawValue: string }>> };
type ConstructorDetector = new (opciones: { formats: string[] }) => Detector;

const INTERVALO_MS = 200;

export function EscanerQR({ alLeer }: { readonly alLeer: (codigo: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const flujo = useRef<MediaStream | null>(null);
  const [activo, setActivo] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const detener = useCallback(() => {
    flujo.current?.getTracks().forEach((pista) => pista.stop());
    flujo.current = null;
    setActivo(false);
  }, []);

  useEffect(() => detener, [detener]);

  useEffect(() => {
    if (!activo || video.current === null) return;
    const el = video.current;
    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout> | null = null;
    const lienzo = document.createElement("canvas");
    const contexto = lienzo.getContext("2d", { willReadFrequently: true });

    const Nativo = (globalThis as { BarcodeDetector?: ConstructorDetector }).BarcodeDetector;
    const detector = Nativo !== undefined ? new Nativo({ formats: ["qr_code"] }) : null;

    async function leerFotograma(): Promise<string | null> {
      if (el.readyState < 2) return null;
      if (detector !== null) {
        const encontrados = await detector.detect(el);
        return encontrados[0]?.rawValue ?? null;
      }
      if (contexto === null) return null;
      lienzo.width = el.videoWidth;
      lienzo.height = el.videoHeight;
      contexto.drawImage(el, 0, 0);
      const imagen = contexto.getImageData(0, 0, lienzo.width, lienzo.height);
      const jsQR = (await import("jsqr")).default;
      return jsQR(imagen.data, imagen.width, imagen.height)?.data ?? null;
    }

    async function vuelta(): Promise<void> {
      if (cancelado) return;
      try {
        const leido = await leerFotograma();
        if (leido !== null) {
          const codigo = codigoDesdeQr(leido, window.location.origin);
          if (codigo !== null) {
            detener();
            alLeer(codigo);
            return;
          }
          setAviso("Ese QR no es una etiqueta de SIMAP. Apunta a la etiqueta del equipo.");
        }
      } catch {
        // Un fotograma ilegible no es un error: se prueba con el siguiente.
      }
      temporizador = setTimeout(() => void vuelta(), INTERVALO_MS);
    }

    void vuelta();
    return () => {
      cancelado = true;
      if (temporizador !== null) clearTimeout(temporizador);
    };
  }, [activo, alLeer, detener]);

  async function abrir(): Promise<void> {
    setAviso(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setAviso(
        "Este navegador no da acceso a la cámara aquí. La cámara necesita una conexión segura (HTTPS). Usa la cámara del teléfono o teclea el código.",
      );
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      flujo.current = s;
      setActivo(true);
      requestAnimationFrame(() => {
        if (video.current !== null) {
          video.current.srcObject = s;
          void video.current.play();
        }
      });
    } catch (error) {
      setAviso(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "Sin permiso para usar la cámara. Actívalo en los ajustes del navegador, o teclea el código."
          : "No se pudo abrir la cámara. Teclea el código de la etiqueta.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {activo ? (
        <>
          <div className="relative overflow-hidden rounded-[var(--radius-control)] border border-borde-fuerte bg-black">
            <video ref={video} muted playsInline className="aspect-square w-full object-cover sm:aspect-video" />
            {/* Marco de encuadre: dice dónde poner la etiqueta. No es decoración. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-[18%] rounded-[var(--radius-control)] border-2 border-white/90"
            />
          </div>
          <p role="status" className="text-[0.875rem] text-texto-suave">
            Apunta a la etiqueta del equipo. Se abre sola al leerla.
          </p>
          <Boton tipo="button" variante="secundario" onClick={detener} anchoCompleto>
            Cerrar cámara
          </Boton>
        </>
      ) : (
        <Boton tipo="button" onClick={() => void abrir()} anchoCompleto>
          <span className="inline-flex items-center gap-2">
            <IconoEscanear />
            Abrir cámara
          </span>
        </Boton>
      )}
      {aviso !== null ? (
        <p role="alert" className="flex gap-2 rounded-[var(--radius-control)] border border-estado-aviso bg-superficie px-3 py-2.5 text-[0.9375rem] leading-6 text-texto">
          <IconoAviso className="mt-0.5 text-estado-aviso" />
          <span>{aviso}</span>
        </p>
      ) : null}
    </div>
  );
}
