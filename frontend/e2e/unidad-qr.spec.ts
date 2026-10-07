/**
 * Pruebas unitarias del analizador de QR y del destino `next` (05-fase2-activos-y-campo.md, sección
 * 10: «unit (frontend): parser de QR y destino next»).
 *
 * Se ejecutan con el mismo Playwright que el resto, en Node y sin navegador: son funciones puras y
 * no merece la pena añadir otro ejecutor de pruebas al proyecto para ellas.
 */

import { expect, test } from "@playwright/test";

import { codigoDesdeQr, destinoSeguro, normalizarCodigo } from "../src/lib/qr";

const ORIGEN = "https://simap.example";

test.describe("codigoDesdeQr", () => {
  test("acepta una etiqueta de SIMAP", () => {
    expect(codigoDesdeQr("https://simap.example/a/XK7P2QH9", ORIGEN)).toBe("XK7P2QH9");
  });

  for (const [caso, contenido] of [
    ["otro sitio", "https://simap.example.evil.com/a/XK7P2QH9"],
    ["otro esquema", "http://simap.example/a/XK7P2QH9"],
    ["ruta que no es de equipo", "https://simap.example/login"],
    ["ruta que imita", "https://simap.example/a/XK7P2QH9/../../login"],
    ["con parámetros", "https://simap.example/a/XK7P2QH9?next=//evil.com"],
    ["código con ambiguos", "https://simap.example/a/XK7O2QH1"],
    ["código corto", "https://simap.example/a/XK7P"],
    ["javascript", "javascript:alert(1)"],
    ["texto suelto", "XK7P2QH9"],
  ] as const) {
    test(`rechaza ${caso}`, () => {
      expect(codigoDesdeQr(contenido, ORIGEN)).toBeNull();
    });
  }
});

test.describe("destinoSeguro", () => {
  for (const bueno of ["/a/XK7P2QH9", "/panel", "/activos?estado=baja"]) {
    test(`acepta ${bueno}`, () => {
      expect(destinoSeguro(bueno)).toBe(bueno);
    });
  }

  for (const malo of [
    "https://evil.com",
    "//evil.com",
    "/\\evil.com",
    "\\\\evil.com",
    "javascript:alert(1)",
    "panel",
    "",
    "/login",
    "/login?next=/panel",
    "/operador",
    "/a/X\nSet-Cookie:x",
    null,
  ]) {
    test(`rechaza ${JSON.stringify(malo)}`, () => {
      expect(destinoSeguro(malo)).toBeNull();
    });
  }
});

test("normalizarCodigo acepta lo tecleado a mano y nada más", () => {
  expect(normalizarCodigo(" xk7p-2qh9 ")).toBe("XK7P2QH9");
  expect(normalizarCodigo("XK7O2QH9")).toBeNull();
});
