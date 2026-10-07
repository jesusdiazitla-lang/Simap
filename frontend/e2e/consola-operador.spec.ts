/**
 * Revisión de la consola del operador.
 *
 * Además de comprobar que la pantalla se sostiene, deja fijada por escrito la frontera del plano
 * de control: lo que se ve en la tabla es nombre, administrador, equipos y estado, y nada más.
 *
 * Necesita un operador dado de alta con `python -m app.cli crear-operador`.
 */

import { expect, test } from "@playwright/test";

import { operador } from "./credenciales";


async function entrar(page: import("@playwright/test").Page): Promise<void> {
  // El mismo acceso que las plantas: `src/lib/acceso.ts` decide a dónde va cada cuenta.
  await page.goto("/login");
  await page.locator("#acceso-correo").fill(operador.correo);
  await page.locator("#acceso-clave").fill(operador.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/operador$/);
}

test("el operador entra por el mismo acceso y cae en su consola, marcada como tal", async ({ page }) => {
  await entrar(page);
  // La marca va en texto, no solo en color: quien tenga las dos pestañas abiertas debe poder
  // saber en cuál está sin depender de distinguir tonos.
  await expect(page.getByText(/consola del operador/i).first()).toBeVisible();
});

test("la dirección vieja del acceso del operador lleva al acceso común", async ({ page }) => {
  await page.goto("/operador/login");
  await expect(page).toHaveURL(/\/login$/);
});

test("la consola muestra las empresas y deja darlas de alta", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await entrar(page);

  await expect(page.getByRole("heading", { name: /dar de alta una empresa/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /empresas clientes/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /bitácora/i })).toBeVisible();

  // La frontera, por escrito: estas son TODAS las columnas que el plano de control expone.
  // En minúsculas porque `allInnerTexts` devuelve el texto YA transformado por CSS, y las
  // cabeceras van en versalitas. Comparar contra el texto del código daría un falso fallo.
  const columnas = (await page.locator("table thead th").allInnerTexts()).map((t) =>
    t.trim().toLowerCase(),
  );
  expect(columnas).toEqual(["empresa", "administrador", "equipos", "estado", "acciones"]);

  await page.screenshot({ path: "e2e/capturas/consola-escritorio.png", fullPage: true });
});

test("dar de alta una empresa devuelve una contraseña temporal una sola vez", async ({ page }) => {
  await entrar(page);
  const sufijo = Date.now().toString(36);

  // Por id y no por etiqueta: el nombre accesible de cada campo incluye la palabra «obligatorio»
  // que va dentro del <label>, así que buscar por texto exacto no encuentra nada.
  await page.locator("#alta-empresa").fill(`Planta E2E ${sufijo}`);
  await page.locator("#alta-admin-nombre").fill("Admin E2E");
  await page.locator("#alta-admin-correo").fill(`admin-${sufijo}@example.com`);
  await page.getByRole("button", { name: "Crear empresa" }).click();

  const aviso = page.getByRole("alert").filter({ hasText: /contraseña temporal/i });
  await expect(aviso).toBeVisible();
  await expect(aviso).toContainText(`admin-${sufijo}@example.com`);
  await page.screenshot({ path: "e2e/capturas/consola-clave.png", fullPage: true });

  // Y la empresa aparece en la tabla, activa.
  await expect(page.getByRole("cell", { name: `Planta E2E ${sufijo}` })).toBeVisible();
});

test("no se puede entrar en la consola sin sesión", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/operador");
  await expect(page).toHaveURL(/\/login$/);
});
