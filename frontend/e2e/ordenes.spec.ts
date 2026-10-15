/**
 * Fase 3 de punta a punta: una falla recorre su ciclo con tres personas, y una falla reportada sin
 * red llega una sola vez (06-fase3-ordenes-de-trabajo.md, sección 13.2).
 *
 * Cada ejecución prepara su escenario por la API con el administrador de demostración: un equipo
 * nuevo, una supervisora y un técnico nuevos. Así no depende de lo que dejó la anterior.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev`: el service worker solo se registra ahí.
 */

import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { usuario } from "./credenciales";

const API = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

interface Persona {
  readonly correo: string;
  readonly clave: string;
  readonly nombre: string;
}

interface Escenario {
  readonly activo: { id: string; codigo: string; nombre: string };
  readonly supervisora: Persona;
  readonly tecnico: Persona;
  readonly admin: APIRequestContext;
}

async function alta(admin: APIRequestContext, rol: string, nombre: string, sufijo: string): Promise<Persona> {
  const r = await admin.post(`${API}/usuarios`, {
    data: { nombre, correo: `${rol}-e2e-${sufijo}@example.com`, rol },
  });
  expect(r.status()).toBe(201);
  const datos = await r.json();
  return { correo: datos.usuario.correo, clave: datos.password_temporal, nombre };
}

async function preparar(playwright: { request: { newContext: () => Promise<APIRequestContext> } }): Promise<Escenario> {
  const admin = await playwright.request.newContext();
  const login = await admin.post(`${API}/auth/login`, {
    data: { correo: usuario.correo, password: usuario.password },
  });
  expect(login.ok(), "el administrador de demostración no puede entrar").toBe(true);
  // Una empresa dada de alta antes de la plantilla inicial no tiene catálogo: se carga (no duplica).
  expect((await admin.post(`${API}/componentes/plantilla`)).ok()).toBe(true);
  const sufijo = Date.now().toString(36);
  const activo = await admin.post(`${API}/activos`, {
    data: { nombre: `Prensa E2E ${sufijo}`, ubicacion: "Nave 3", horometro_inicial: 4800 },
  });
  expect(activo.status()).toBe(201);
  return {
    activo: await activo.json(),
    supervisora: await alta(admin, "supervisor", `Supervisora E2E ${sufijo}`, sufijo),
    tecnico: await alta(admin, "tecnico_taller", `Técnico E2E ${sufijo}`, sufijo),
    admin,
  };
}

async function entrar(browser: Browser, correo: string, clave: string, destino = "/panel"): Promise<Page> {
  const contexto = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await contexto.newPage();
  await page.goto(destino);
  await page.waitForURL(/\/login/);
  await page.locator("#acceso-correo").fill(correo);
  await page.locator("#acceso-clave").fill(clave);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  return page;
}

async function reportarFalla(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Reportar una falla" }).click();
  await page.getByRole("radio", { name: "Motor", exact: true }).check({ force: true });
  await page.locator("#falla-horometro").fill("4801");
  await page.getByLabel(/Qué pasó/).fill("Se detuvo por sobrecalentamiento al arrancar");
  await page.getByRole("button", { name: /Reportar falla: motor/ }).click();
}

async function ordenesDe(admin: APIRequestContext, activoId: string): Promise<Array<{ id: string; numero: number; estado: string }>> {
  const r = await admin.get(`${API}/activos/${activoId}/ordenes`);
  return (await r.json()).items;
}

test("test_rf11_rf13_ciclo_completo_con_tres_usuarios", async ({ browser, playwright }) => {
  const e = await preparar(playwright);
  try {
    // 1. La supervisora escanea la etiqueta y reporta la falla, en el teléfono.
    const supervisora = await entrar(browser, e.supervisora.correo, e.supervisora.clave, `/a/${e.activo.codigo}`);
    await expect(supervisora.getByRole("heading", { level: 1, name: e.activo.nombre })).toBeVisible();
    await reportarFalla(supervisora);
    await expect(supervisora.getByText(/Falla reportada: se abrió la orden OT-\d{4}/)).toBeVisible();
    await supervisora.screenshot({ path: "e2e/capturas/f3-falla-reportada.png", fullPage: true });
    const [orden] = await ordenesDe(e.admin, e.activo.id);
    expect(orden.estado).toBe("reportada");

    // La pantalla del equipo ya dice que está en falla.
    await supervisora.reload();
    await expect(supervisora.getByRole("region", { name: "Equipo en falla" })).toContainText("Motor");

    // 2. El técnico la toma y registra la reparación.
    const tecnico = await entrar(browser, e.tecnico.correo, e.tecnico.clave, `/ordenes/${orden.id}`);
    await tecnico.getByRole("button", { name: "Llevar al taller" }).click();
    await expect(tecnico.getByText("En taller", { exact: true }).first()).toBeVisible();
    await tecnico.getByLabel("Trabajo realizado").fill("Se cambió el rodamiento del lado acople y se alineó el eje.");
    await tecnico.getByRole("radio", { name: /Reemplazo/ }).check({ force: true });
    await tecnico.getByRole("button", { name: "Marcar como reparada" }).click();
    await expect(tecnico.getByText("Reparada · por autorizar").first()).toBeVisible();
    await tecnico.screenshot({ path: "e2e/capturas/f3-reparada-tecnico.png", fullPage: true });

    // 3. El administrador revisa lo que va a firmar y autoriza la salida.
    const admin = await entrar(browser, usuario.correo, usuario.password, `/ordenes/${orden.id}`);
    await admin.getByRole("button", { name: "Revisar y autorizar" }).click();
    const firma = admin.getByRole("region", { name: "Lo que vas a firmar" });
    await expect(firma).toContainText(e.tecnico.nombre);
    await expect(firma).toContainText("Reemplazo");
    await admin.getByRole("button", { name: "Autorizar y cerrar" }).click();
    await expect(admin.getByText("Cerrada", { exact: true }).first()).toBeVisible();

    // El historial muestra a las tres personas, cada una con su rol.
    const historial = admin.getByRole("list").filter({ hasText: "Falla reportada" });
    await expect(historial).toContainText(e.supervisora.nombre);
    await expect(historial).toContainText(e.tecnico.nombre);
    await expect(historial).toContainText("Cierre autorizado");
    await admin.setViewportSize({ width: 1280, height: 900 });
    await admin.screenshot({ path: "e2e/capturas/f3-orden-cerrada.png", fullPage: true });

    const [cerrada] = await ordenesDe(e.admin, e.activo.id);
    expect(cerrada.estado).toBe("cerrada");
    for (const p of [supervisora, tecnico, admin]) await p.context().close();
  } finally {
    await e.admin.dispose();
  }
});

test("test_rf10_falla_sin_conexion_llega_una_sola_vez", async ({ browser, playwright }) => {
  const e = await preparar(playwright);
  try {
    const page = await entrar(browser, e.supervisora.correo, e.supervisora.clave, `/a/${e.activo.codigo}`);
    // Se espera a que el service worker controle la página: sin él, una recarga sin red no abre.
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise<void>((listo) =>
          navigator.serviceWorker.addEventListener("controllerchange", () => listo(), { once: true }),
        );
      }
    });
    // El catálogo de componentes se carga con red y queda guardado para usarlo sin ella.
    await page.getByRole("button", { name: "Reportar una falla" }).click();
    await expect(page.getByRole("radio", { name: "Motor", exact: true })).toBeAttached();

    await page.context().setOffline(true);
    await page.getByRole("radio", { name: "Motor", exact: true }).check({ force: true });
    await page.locator("#falla-horometro").fill("4801");
    await page.getByLabel(/Qué pasó/).fill("Fuga de aceite en el cilindro principal");
    await page.getByRole("button", { name: /Reportar falla: motor/ }).click();
    await expect(page.getByText(/la falla quedó guardada en este teléfono/)).toBeVisible();
    await expect(page.getByText("Un reporte de falla sin enviar")).toBeVisible();
    // El formulario se retira: un segundo toque no puede encolarla otra vez.
    await expect(page.getByRole("button", { name: /Reportar falla: motor/ })).toHaveCount(0);
    await page.screenshot({ path: "e2e/capturas/f3-falla-sin-conexion.png", fullPage: true });
    expect(await ordenesDe(e.admin, e.activo.id)).toHaveLength(0);

    // Vuelve la red: la cola la envía sola, una vez.
    await page.context().setOffline(false);
    await expect(page.getByText("Un reporte de falla sin enviar")).toHaveCount(0, { timeout: 20_000 });
    await expect.poll(async () => (await ordenesDe(e.admin, e.activo.id)).length).toBe(1);

    // Aunque la red vaya y venga y la cola vuelva a intentarlo, sigue habiendo una sola orden.
    await page.context().setOffline(true);
    await page.context().setOffline(false);
    await page.waitForTimeout(1_500);
    expect(await ordenesDe(e.admin, e.activo.id)).toHaveLength(1);
    await page.context().close();
  } finally {
    await e.admin.dispose();
  }
});
