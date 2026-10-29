/**
 * Fase 5 de punta a punta (08-fase5-dashboard-y-cierre.md, 10.2 y 12.4; RF-27, RF-28).
 *
 * - Cada rol ve su panel y no las secciones de otro.
 * - La política de contenido lleva un nonce que cambia en cada petición, sin `unsafe-inline` ni
 *   `unsafe-eval`, y un script inyectado sin nonce no se ejecuta (la prueba de control con el nonce
 *   correcto demuestra que la prueba puede detectar ejecución).
 * - El JavaScript de la página no puede leer la cookie de sesión.
 * - Un periodo de más de 24 meses da un aviso claro, no una página rota.
 * - En un teléfono de 390 px no hay desplazamiento horizontal.
 *
 * Cada ejecución da de alta su personal con el administrador de demostración, como las de fase 3 y 4.
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev` (ver playwright.config.ts).
 */

import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { usuario } from "./credenciales";

const API = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

interface Persona {
  readonly correo: string;
  readonly clave: string;
}

async function personal(playwright: { request: { newContext: () => Promise<APIRequestContext> } }): Promise<Record<string, Persona>> {
  const admin = await playwright.request.newContext();
  const login = await admin.post(`${API}/auth/login`, { data: { correo: usuario.correo, password: usuario.password } });
  expect(login.ok(), "el administrador de demostración no puede entrar").toBe(true);
  const sufijo = Date.now().toString(36);
  const resultado: Record<string, Persona> = { administrador: { correo: usuario.correo, clave: usuario.password } };
  for (const rol of ["operario", "supervisor", "tecnico_taller", "gerente"]) {
    const r = await admin.post(`${API}/usuarios`, { data: { nombre: `Panel E2E ${rol}`, correo: `${rol}-e2e-${sufijo}@example.com`, rol } });
    expect(r.status()).toBe(201);
    const datos = await r.json();
    resultado[rol] = { correo: datos.usuario.correo, clave: datos.password_temporal };
  }
  await admin.dispose();
  return resultado;
}

async function entrar(browser: Browser, p: Persona, ancho = 1280, sinServiceWorker = false): Promise<Page> {
  // Sin service worker cuando la prueba intercepta la página: las peticiones que él resuelve no
  // pasan por `page.route`.
  const contexto = await browser.newContext({
    viewport: { width: ancho, height: 900 },
    serviceWorkers: sinServiceWorker ? "block" : "allow",
  });
  const page = await contexto.newPage();
  await page.goto("/login");
  await page.locator("#acceso-correo").fill(p.correo);
  await page.locator("#acceso-clave").fill(p.clave);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(/\/panel/);
  return page;
}

const SECCIONES: Record<string, { ve: string[]; no: string[] }> = {
  operario: { ve: ["Mis lecturas recientes", "Mis alertas"], no: ["Indicadores del periodo", "Cola del taller", "Lo que espera tu revisión"] },
  tecnico_taller: { ve: ["Cola del taller", "Mis trabajos recientes"], no: ["Indicadores del periodo", "Mis lecturas recientes"] },
  supervisor: { ve: ["Lo que espera tu revisión", "Alertas de campo pendientes de revisión", "Órdenes abiertas"], no: ["Indicadores del periodo", "Estado de la plataforma"] },
  gerente: { ve: ["Indicadores del periodo", "Equipos de mayor riesgo", "Repuestos que más costaron"], no: ["Lo que espera tu revisión", "Estado de la plataforma"] },
  administrador: { ve: ["Indicadores del periodo", "Lo que espera tu revisión", "Estado de la plataforma"], no: ["Mis lecturas recientes"] },
};

test("test_rf27_cada_rol_ve_su_panel_y_no_el_de_otro", async ({ browser, playwright }) => {
  test.setTimeout(90_000);
  const gente = await personal(playwright);
  for (const [rol, { ve, no }] of Object.entries(SECCIONES)) {
    const page = await entrar(browser, gente[rol]);
    for (const titulo of ve) await expect(page.getByRole("heading", { name: titulo, exact: true })).toBeVisible();
    for (const titulo of no) await expect(page.getByRole("heading", { name: titulo, exact: true })).toHaveCount(0);
    await page.context().close();
  }
});

test("test_csp_con_nonce_por_peticion_y_script_inyectado_no_se_ejecuta", async ({ browser }) => {
  const page = await entrar(browser, { correo: usuario.correo, clave: usuario.password }, 1280, true);
  const politicas: string[] = [];
  for (let i = 0; i < 2; i++) {
    const r = await page.goto("/panel");
    politicas.push(r?.headers()["content-security-policy"] ?? "");
  }
  const nonce = (csp: string) => /'nonce-([^']+)'/.exec(csp)?.[1];
  expect(nonce(politicas[0])).toBeTruthy();
  expect(nonce(politicas[0])).not.toBe(nonce(politicas[1]));
  for (const csp of politicas) {
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("frame-ancestors 'none'");
  }
  // Un XSS reflejado: un <script> en el propio HTML del servidor. Se intercepta la respuesta de la
  // página y se le insertan dos scripts en línea, uno sin nonce y otro con el nonce de esa misma
  // respuesta (el control: demuestra que la prueba sí detecta una ejecución). Crear el script desde
  // `page.evaluate` no sirve: ese código lo inyecta DevTools y `'strict-dynamic'` lo trata como de
  // confianza.
  const bloqueos: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy/i.test(m.text())) bloqueos.push(m.text());
  });
  let insertado = false;
  await page.route("**/panel", async (ruta) => {
    const respuesta = await ruta.fetch();
    const csp = respuesta.headers()["content-security-policy"] ?? "";
    const n = nonce(csp) ?? "";
    const original = await respuesta.text();
    const html = original.replace(
      /<head[^>]*>/,
      (cabeza) => `${cabeza}<script>window.__sinNonce = true</script><script nonce="${n}">window.__conNonce = true</script>`,
    );
    insertado = html !== original && n !== "";
    await ruta.fulfill({ response: respuesta, body: html });
  });
  await page.goto("/panel");
  const ejecutado = await page.evaluate(() => {
    const w = window as unknown as Record<string, boolean>;
    return { sin: Boolean(w.__sinNonce), con: Boolean(w.__conNonce) };
  });
  expect(insertado, "no se pudo insertar el script en el HTML").toBe(true);
  expect(ejecutado).toEqual({ sin: false, con: true });
  expect(bloqueos.length).toBeGreaterThan(0);
  await page.unroute("**/panel");
  // El JavaScript de la página no ve la cookie de sesión (httpOnly).
  expect(await page.evaluate(() => document.cookie)).not.toContain("simap_access");
  await page.context().close();
});

test("test_rf28_periodo_de_mas_de_24_meses_da_un_aviso_claro", async ({ browser, playwright }) => {
  const gente = await personal(playwright);
  const page = await entrar(browser, gente.gerente);
  await page.goto("/panel?desde=2020-01-01&hasta=2026-01-01");
  await expect(page.getByRole("heading", { name: "Ese periodo no es válido" })).toBeVisible();
  await expect(page.getByText(/sin pasar de 24 meses/)).toBeVisible();
  await page.context().close();
});

test("test_rnf05_panel_del_gerente_en_390_px_sin_desplazamiento_horizontal", async ({ browser, playwright }) => {
  const gente = await personal(playwright);
  const page = await entrar(browser, gente.gerente, 390);
  await expect(page.getByRole("heading", { name: "Indicadores del periodo" })).toBeVisible();
  const desborde = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desborde).toBeLessThanOrEqual(1);
  // Las gráficas se pueden recorrer con el teclado y tienen su tabla.
  await expect(page.getByText("Ver como tabla").first()).toBeVisible();
  await page.context().close();
});
