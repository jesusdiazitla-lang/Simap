/**
 * Cierre de la fase 1: el desvío por sesión (`src/proxy.ts`), el cambio de la contraseña propia en
 * los dos planos y el service worker mínimo.
 *
 * Las pruebas del proxy piden la página con `maxRedirects: 0` y miran el 307. Si solo comprobaran
 * la URL final no distinguirían el proxy del desvío que cada página ya hace por su cuenta en el
 * navegador, y seguirían pasando aunque el proxy no existiera.
 *
 * Las de cambio de clave usan las cuentas de demostración y DEVUELVEN LA CLAVE ORIGINAL al terminar,
 * pase lo que pase, para no dejar a nadie fuera de su propia demo.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev`. Ver playwright.config.ts.
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { operador, usuario } from "./credenciales";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";

const TEMPORAL = "clave-temporal-de-la-prueba-e2e";

/** Una cookie-pista falsa, tal como la pondría la API. No es una credencial. */
async function ponerPista(page: Page, nombre: string, ruta = "/"): Promise<void> {
  await page.context().addCookies([{ name: nombre, value: "1", url: `${BASE}${ruta}` }]);
}

// --- El proxy --------------------------------------------------------------

test.describe("proxy de sesión", () => {
  test("sin sesión, una pantalla protegida responde con un desvío al acceso", async ({
    request,
  }) => {
    for (const ruta of ["/panel", "/panel/clave"]) {
      const resp = await request.get(ruta, { maxRedirects: 0 });
      expect(resp.status(), ruta).toBe(307);
      expect(resp.headers()["location"], ruta).toMatch(/\/login$/);
    }
  });

  test("la raíz decide en el servidor, sin pantalla intermedia", async ({ request }) => {
    const resp = await request.get("/", { maxRedirects: 0 });
    expect(resp.status()).toBe(307);
    expect(resp.headers()["location"]).toMatch(/\/login$/);
  });

  test("la consola tiene su propio desvío, a su propio acceso", async ({ request }) => {
    const resp = await request.get("/operador", { maxRedirects: 0 });
    expect(resp.status()).toBe(307);
    expect(resp.headers()["location"]).toMatch(/\/operador\/login$/);
  });

  test("la sesión de una planta no deja pasar a la consola", async ({ page }) => {
    await ponerPista(page, "simap_sesion");
    const resp = await page.request.get("/operador", { maxRedirects: 0 });
    expect(resp.status()).toBe(307);
  });

  test("el acceso nunca se desvía, aunque haya pista", async ({ page }) => {
    // Si el proxy mandara a /panel a quien llega a /login con pista, una pista caducada daría un
    // bucle infinito entre las dos pantallas.
    await ponerPista(page, "simap_sesion");
    const resp = await page.request.get("/login", { maxRedirects: 0 });
    expect(resp.status()).toBe(200);
  });

  test("una pista falsa no abre nada: la página pregunta a la API y vuelve al acceso", async ({
    page,
  }) => {
    await ponerPista(page, "simap_sesion");
    await page.goto("/panel");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("los archivos públicos no pasan por el desvío", async ({ request }) => {
    for (const ruta of ["/manifest.webmanifest", "/sw.js", "/offline.html"]) {
      const resp = await request.get(ruta, { maxRedirects: 0 });
      expect(resp.status(), ruta).toBe(200);
    }
  });
});

// --- Cambio de contraseña ----------------------------------------------------

/** Devuelve la clave de demostración a su valor, sea cual sea la que tenga ahora. */
async function restaurar(
  request: APIRequestContext,
  login: string,
  cambio: string,
  correo: string,
  original: string,
): Promise<void> {
  for (const actual of [TEMPORAL, original]) {
    const entrada = await request.post(`${API}${login}`, { data: { correo, password: actual } });
    if (!entrada.ok()) continue;
    if (actual === original) return;
    const vuelta = await request.post(`${API}${cambio}`, {
      data: { password_actual: TEMPORAL, password_nueva: original },
    });
    expect(vuelta.ok(), "no se pudo devolver la clave de demostración a su valor").toBe(true);
    return;
  }
}

async function rellenar(page: Page, prefijo: string, actual: string, nueva: string, repetida = nueva) {
  await page.locator(`#${prefijo}-actual`).fill(actual);
  await page.locator(`#${prefijo}-nueva`).fill(nueva);
  await page.locator(`#${prefijo}-repetida`).fill(repetida);
  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
}

test("un usuario de planta cambia su contraseña desde el panel", async ({ page, playwright }) => {
  const api = await playwright.request.newContext();
  try {
    await page.goto("/login");
    await page.locator("#acceso-correo").fill(usuario.correo);
    await page.locator("#acceso-clave").fill(usuario.password);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/panel$/);

    await page.getByRole("link", { name: "Cambiar contraseña" }).click();
    await expect(page).toHaveURL(/\/panel\/clave$/);

    // Lo que se comprueba en el navegador antes de molestar al servidor.
    await rellenar(page, "clave", usuario.password, TEMPORAL, `${TEMPORAL}-distinta`);
    await expect(page.locator("#clave-repetida-error")).toHaveText(/no coincide/i);

    // Lo que solo sabe el servidor: la actual está mal. El mensaje va junto a ese campo.
    await rellenar(page, "clave", "esta-no-es-la-actual", TEMPORAL);
    await expect(page.locator("#clave-actual-error")).toHaveText(/actual no es correcta/i);

    await rellenar(page, "clave", usuario.password, TEMPORAL);
    await expect(page.getByRole("heading", { name: "Contraseña cambiada" })).toBeVisible();
    await page.screenshot({ path: "e2e/capturas/clave-cambiada.png", fullPage: true });

    // Este aparato sigue dentro.
    await page.getByRole("link", { name: "Volver al panel" }).last().click();
    await expect(page).toHaveURL(/\/panel$/);

    // Y la clave vieja ya no entra.
    const vieja = await api.post(`${API}/auth/login`, { data: { correo: usuario.correo, password: usuario.password } });
    expect(vieja.status()).toBe(401);
  } finally {
    await restaurar(api, "/auth/login", "/auth/cambiar-clave", usuario.correo, usuario.password);
    await api.dispose();
  }
});

test("el operador cambia su contraseña y queda en la bitácora", async ({ page, playwright }) => {
  const api = await playwright.request.newContext();
  try {
    await page.goto("/operador/login");
    await page.locator("#consola-correo").fill(operador.correo);
    await page.locator("#consola-clave").fill(operador.password);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/operador$/);

    await page.getByRole("link", { name: "Cambiar mi contraseña" }).click();
    await expect(page).toHaveURL(/\/operador\/clave$/);
    await rellenar(page, "clave-operador", operador.password, TEMPORAL);
    await expect(page.getByRole("heading", { name: "Contraseña cambiada" })).toBeVisible();

    await page.getByRole("link", { name: "Volver a la consola" }).last().click();
    await expect(page).toHaveURL(/\/operador$/);
    await expect(page.getByText("Cambio de contraseña propia").first()).toBeVisible();
  } finally {
    await restaurar(api, "/operador/login", "/operador/cambiar-clave", operador.correo, operador.password);
    await api.dispose();
  }
});

// --- Service worker ----------------------------------------------------------

test("sin red, una pantalla muestra el aviso de SIMAP y no el error del navegador", async ({
  page,
  context,
}) => {
  await page.goto("/login");
  // Espera a que el worker controle la página; hasta entonces no puede servir nada.
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((listo) =>
        navigator.serviceWorker.addEventListener("controllerchange", () => listo(), { once: true }),
      );
    }
  });

  await context.setOffline(true);
  try {
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sin conexión" })).toBeVisible();
    await page.screenshot({ path: "e2e/capturas/sin-conexion.png", fullPage: true });
  } finally {
    await context.setOffline(false);
  }
});
