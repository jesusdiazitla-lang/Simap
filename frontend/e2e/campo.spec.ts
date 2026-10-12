/**
 * Fase 2 de punta a punta: escanear, registrar y que llegue aunque no haya red.
 *
 * Cada ejecución prepara su propio escenario por la API —un equipo nuevo y un operario nuevo, dados de
 * alta por el administrador de demostración—, así las pruebas no dependen de lo que dejó la anterior.
 *
 * Nombres tomados de `docs/contexto/05-fase2-activos-y-campo.md`, sección 10.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev`: el service worker solo se registra ahí.
 */

import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { usuario } from "./credenciales";

const API = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

interface Escenario {
  readonly activo: { id: string; codigo: string; nombre: string };
  readonly operario: { correo: string; clave: string };
  readonly admin: APIRequestContext;
}

async function preparar(playwright: { request: { newContext: () => Promise<APIRequestContext> } }): Promise<Escenario> {
  const admin = await playwright.request.newContext();
  const login = await admin.post(`${API}/auth/login`, {
    data: { correo: usuario.correo, password: usuario.password },
  });
  expect(login.ok(), "el administrador de demostración no puede entrar").toBe(true);

  const sufijo = Date.now().toString(36);
  const activo = await admin.post(`${API}/activos`, {
    data: { nombre: `Compresor E2E ${sufijo}`, ubicacion: "Nave 2", horometro_inicial: 4800 },
  });
  expect(activo.status()).toBe(201);

  const alta = await admin.post(`${API}/usuarios`, {
    data: { nombre: `Operario E2E ${sufijo}`, correo: `operario-e2e-${sufijo}@example.com`, rol: "operario" },
  });
  expect(alta.status()).toBe(201);
  const datos = await alta.json();
  return {
    activo: await activo.json(),
    operario: { correo: datos.usuario.correo, clave: datos.password_temporal },
    admin,
  };
}

async function entrarDesdeLaEtiqueta(page: Page, codigo: string, correo: string, clave: string): Promise<void> {
  await page.goto(`/a/${codigo}`);
  // Sin sesión: al acceso, recordando el equipo.
  await expect(page).toHaveURL(new RegExp(`/login\\?next=%2Fa%2F${codigo}$`));
  await page.locator("#acceso-correo").fill(correo);
  await page.locator("#acceso-clave").fill(clave);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(new RegExp(`/a/${codigo}$`));
}

async function lecturasDe(admin: APIRequestContext, activoId: string): Promise<number[]> {
  const r = await admin.get(`${API}/activos/${activoId}/lecturas`);
  return ((await r.json()).items as Array<{ valor_horometro: number }>).map((l) => l.valor_horometro);
}

test("test_rnf03_escaneo_a_envio_en_tres_pasos", async ({ page, playwright }) => {
  const e = await preparar(playwright);
  try {
    // Como lo usa un operario: en el teléfono.
    await page.setViewportSize({ width: 390, height: 844 });
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);

    // Lo primero: qué máquina es, para comprobar que la etiqueta es la de la máquina que tiene delante.
    await expect(page.getByRole("heading", { level: 1, name: e.activo.nombre })).toBeVisible();
    await expect(page.getByText("4,800 h").first()).toBeVisible();

    // Paso 1 fue escanear (abrir la URL). Paso 2: rellenar. Paso 3: enviar.
    // Segundos después del alta: un valor creíble. Más de dos horas de salto pediría confirmación.
    await page.locator("#horometro-valor").fill("4801");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText("Lectura registrada: 4,801 h.")).toBeVisible();

    // Y una alerta, también en un formulario y un envío.
    await page.getByText("Vibración", { exact: true }).click();
    await page.getByRole("button", { name: "Reportar vibración" }).click();
    await expect(page.getByText(/Alerta registrada: Vibración/)).toBeVisible();

    expect(await lecturasDe(e.admin, e.activo.id)).toEqual([4801, 4800]);

    await page.screenshot({ path: "e2e/capturas/equipo-operario-movil.png", fullPage: true });
  } finally {
    await e.admin.dispose();
  }
});

test("una lectura que no cuadra pide confirmación antes de enviarse", async ({ page, playwright }) => {
  const e = await preparar(playwright);
  try {
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);
    await page.locator("#horometro-valor").fill("48003");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText(/¿Hay un dígito de más\?/)).toBeVisible();
    await page.getByRole("button", { name: "Corregir" }).click();
    expect(await lecturasDe(e.admin, e.activo.id)).toEqual([4800]);
  } finally {
    await e.admin.dispose();
  }
});

test("un decimal se rechaza en vez de volverse un dígito de más", async ({ page, playwright }) => {
  // Sección 5.1: el horómetro es un entero. Quitar el punto convertía 4801.5 en 48 015.
  const e = await preparar(playwright);
  try {
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);
    await page.locator("#horometro-valor").fill("4801.5");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText(/horas enteras, sin decimales/)).toBeVisible();
    expect(await lecturasDe(e.admin, e.activo.id)).toEqual([4800]);

    // El separador de miles bien puesto sí vale.
    await page.locator("#horometro-valor").fill("4,801");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText("Lectura registrada: 4,801 h.")).toBeVisible();
  } finally {
    await e.admin.dispose();
  }
});

test("test_rf10_envio_sin_conexion_llega_una_sola_vez", async ({ page, context, playwright }) => {
  const e = await preparar(playwright);
  try {
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);
    await expect(page.getByRole("heading", { level: 1, name: e.activo.nombre })).toBeVisible();
    // El service worker tiene que controlar la página para servirla sin red.
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise<void>((listo) =>
          navigator.serviceWorker.addEventListener("controllerchange", () => listo(), { once: true }),
        );
      }
    });

    await context.setOffline(true);
    // La pantalla del equipo abre sin red, con los datos guardados y avisando de que pueden no estar al día.
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: e.activo.nombre })).toBeVisible();
    await expect(page.getByText(/Ves los datos guardados en este teléfono/)).toBeVisible();

    await page.locator("#horometro-valor").fill("4802");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText(/quedó guardada en el teléfono/)).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "1 por enviar" })).toBeVisible();
    await page.screenshot({ path: "e2e/capturas/equipo-sin-conexion.png", fullPage: true });

    // Vuelve la red: se envía sola.
    await context.setOffline(false);
    await expect(page.getByRole("status").filter({ hasText: "Enviado" })).toBeVisible({ timeout: 20_000 });

    // Se corta y vuelve otra vez: el reintento no duplica nada.
    await context.setOffline(true);
    await context.setOffline(false);
    await page.reload();
    expect(await lecturasDe(e.admin, e.activo.id)).toEqual([4802, 4800]);
  } finally {
    await context.setOffline(false);
    await e.admin.dispose();
  }
});

test("una etiqueta de otra empresa o inexistente no abre nada", async ({ page, playwright }) => {
  const e = await preparar(playwright);
  try {
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);
    await page.goto("/a/ZZZZZZZZ");
    await expect(page.getByRole("heading", { name: "No encontramos este equipo" })).toBeVisible();
  } finally {
    await e.admin.dispose();
  }
});

/** Ninguna pantalla nueva debe provocar barra horizontal, en ningún ancho. */
async function sinDesbordar(page: Page, ruta: string): Promise<void> {
  const d = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    visible: document.documentElement.clientWidth,
  }));
  expect(d.scroll, `${ruta} desborda`).toBeLessThanOrEqual(d.visible + 1);
}

test("las pantallas del administrador se sostienen en móvil y escritorio", async ({ browser, playwright }) => {
  const e = await preparar(playwright);
  try {
    for (const [nombre, tamano] of [
      ["movil", { width: 390, height: 844 }],
      ["escritorio", { width: 1280, height: 900 }],
    ] as const) {
      const page = await nuevaPaginaComoAdmin(browser, tamano);
      for (const ruta of [
        "/activos",
        "/alertas",
        "/componentes",
        "/panel/usuarios",
        "/escanear",
        `/a/${e.activo.codigo}`,
        `/activos/${e.activo.id}/etiqueta`,
        "/activos/nuevo",
      ]) {
        await page.goto(ruta);
        await expect(page.getByRole("main")).not.toContainText("Cargando…", { timeout: 15_000 });
        await page.waitForLoadState("networkidle");
        await sinDesbordar(page, `${ruta} (${nombre})`);
        const archivo = ruta.replace(/[/?=]+/g, "-").replace(/^-|-$/g, "") || "raiz";
        await page.screenshot({ path: `e2e/capturas/f2-${archivo}-${nombre}.png`, fullPage: true });
      }
      await page.context().close();
    }
  } finally {
    await e.admin.dispose();
  }
});

async function nuevaPaginaComoAdmin(browser: Browser, tamano: { width: number; height: number }): Promise<Page> {
  const contexto = await browser.newContext({ viewport: tamano });
  const page = await contexto.newPage();
  await page.goto("/login");
  await page.locator("#acceso-correo").fill(usuario.correo);
  await page.locator("#acceso-clave").fill(usuario.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/panel$/);
  return page;
}

test("el supervisor resuelve una lectura que no cuadraba", async ({ browser, playwright }) => {
  const e = await preparar(playwright);
  try {
    // Una lectura con un dígito de más, enviada por la API como lo haría un teléfono sin la pantalla.
    const operario = await playwright.request.newContext();
    await operario.post(`${API}/auth/login`, { data: { correo: e.operario.correo, password: e.operario.clave } });
    const marcada = await operario.post(`${API}/activos/${e.activo.id}/lecturas`, {
      data: { cliente_id: crypto.randomUUID(), capturado_en: new Date().toISOString(), valor: 48000 },
    });
    expect((await marcada.json()).lectura.requiere_revision).toBe(true);
    await operario.dispose();

    const page = await nuevaPaginaComoAdmin(browser, { width: 1280, height: 900 });
    await page.goto("/alertas");
    const fila = page.getByRole("listitem").filter({ hasText: e.activo.nombre }).filter({ hasText: "48,000 h" });
    await expect(fila).toBeVisible();
    await page.screenshot({ path: "e2e/capturas/lecturas-por-revisar.png", fullPage: true });
    await fila.getByRole("button", { name: "Error al teclear" }).click();
    await expect(fila).toHaveCount(0);
    await page.context().close();

    const r = await e.admin.get(`${API}/activos/${e.activo.id}`);
    expect((await r.json()).horometro_actual).toBe(4800);
  } finally {
    await e.admin.dispose();
  }
});

test("lo enviado sin red que el servidor rechaza se le muestra a quien lo capturó", async ({ page, context, playwright }) => {
  const e = await preparar(playwright);
  try {
    await entrarDesdeLaEtiqueta(page, e.activo.codigo, e.operario.correo, e.operario.clave);
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise<void>((listo) =>
          navigator.serviceWorker.addEventListener("controllerchange", () => listo(), { once: true }),
        );
      }
    });

    await context.setOffline(true);
    await page.locator("#horometro-valor").fill("4801");
    await page.getByRole("button", { name: "Registrar lectura" }).click();
    await expect(page.getByText(/quedó guardada en el teléfono/)).toBeVisible();

    // Mientras el operario no tiene red, el administrador da de baja el equipo.
    expect((await e.admin.post(`${API}/activos/${e.activo.id}/baja`)).ok()).toBe(true);

    await context.setOffline(false);
    const aviso = page.getByRole("alert").filter({ hasText: "no se pudo guardar" });
    await expect(aviso).toBeVisible({ timeout: 20_000 });
    await expect(aviso).toContainText("dado de baja");
    await page.screenshot({ path: "e2e/capturas/cola-rechazado.png", fullPage: true });

    await aviso.getByRole("button", { name: "Entendido" }).click();
    await expect(aviso).toHaveCount(0);
  } finally {
    await context.setOffline(false);
    await e.admin.dispose();
  }
});
