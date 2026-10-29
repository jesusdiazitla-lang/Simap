/**
 * Revisión de la interfaz contra sus reglas duras, en los dos temas y los tres anchos.
 *
 * No comprueba que la pantalla sea bonita —eso no se automatiza— sino las cosas que se rompen sin
 * que nadie lo note y que ya se rompieron en este proyecto:
 *
 * - **Desplazamiento horizontal.** Una versión se salía del viewport a 390 px y otra a 768 px.
 *   Entre el móvil y el escritorio hay un tramo que nadie mira.
 * - **El foco invisible.** Hay que comprobar que el campo enfocado se distingue de verdad.
 * - **El error que desplaza el botón.** El fallo clásico de los formularios de acceso: el mensaje
 *   aparece, empuja el contenido, y quien iba a pulsar «Entrar» pulsa otra cosa.
 * - **El tamaño táctil.** Esto se usa de pie y con guantes.
 * - **Que no vuelva un camino de registro.** El alta de empresas es por invitación.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev`. Ver playwright.config.ts.
 */

import { expect, test, type Page } from "@playwright/test";

import { usuario } from "./credenciales";


const ESCRITORIO = { width: 1280, height: 900 };
/** El ancho intermedio, donde una versión anterior desbordó sin que ninguna prueba lo viera. */
const TABLETA = { width: 768, height: 1024 };
const MOVIL = { width: 390, height: 844 };

/** Ningún ancho de pantalla debe provocar barra horizontal. */
async function sinDesplazamientoHorizontal(page: Page): Promise<void> {
  const desborde = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    visible: document.documentElement.clientWidth,
  }));
  expect(
    desborde.scroll,
    `La página mide ${desborde.scroll}px de ancho en un viewport de ${desborde.visible}px`,
  ).toBeLessThanOrEqual(desborde.visible + 1);
}

for (const [nombre, tamano] of [
  ["escritorio", ESCRITORIO],
  ["tableta", TABLETA],
  ["movil", MOVIL],
] as const) {
  for (const tema of ["light", "dark"] as const) {
    test(`el acceso se sostiene en ${nombre} y tema ${tema}`, async ({ page }) => {
      await page.setViewportSize(tamano);
      await page.emulateMedia({ colorScheme: tema });
      await page.goto("/login");

      await expect(page.getByRole("heading", { name: /iniciar sesión/i })).toBeVisible();
      await sinDesplazamientoHorizontal(page);

      // No hay camino de registro: el alta de empresas es por invitacion.
      await expect(page.getByRole("link", { name: /crear cuenta|registrarse/i })).toHaveCount(0);

      await page.screenshot({
        path: `e2e/capturas/acceso-${nombre}-${tema}.png`,
        fullPage: true,
      });
    });
  }
}

test("los controles alcanzan el tamaño táctil mínimo", async ({ page }) => {
  // Se usa de pie y con guantes: 44 px es el minimo de la guia, y el sistema apunta a 48.
  await page.goto("/login");
  for (const id of ["acceso-correo", "acceso-clave"]) {
    const caja = await page.locator(`#${id}`).boundingBox();
    expect(caja!.height, `#${id} mide ${caja!.height}px de alto`).toBeGreaterThanOrEqual(44);
  }
  const boton = await page.getByRole("button", { name: "Entrar" }).boundingBox();
  expect(boton!.height, "el boton primario es mas bajo que el minimo tactil").toBeGreaterThanOrEqual(
    44,
  );
});

test("el campo enfocado se distingue sin depender del anillo del navegador", async ({ page }) => {
  await page.goto("/login");
  // Se prueba sobre la contrasena y no sobre el correo: el correo lleva `autoFocus`, asi que ya
  // esta enfocado al cargar y el estado "antes" seria en realidad el de "despues".
  const clave = page.locator("#acceso-clave");

  const antes = await clave.evaluate((el) => getComputedStyle(el).borderBottomColor);
  await clave.focus();

  // Con `expect.poll` y no con una lectura unica: el borde lleva transicion de color, asi que justo
  // despues de enfocar el valor calculado sigue siendo el viejo durante unos milisegundos. Leerlo
  // una sola vez hacia que la prueba pasara sola y fallara dentro de la tanda completa.
  await expect
    .poll(() => clave.evaluate((el) => getComputedStyle(el).borderBottomColor), {
      message: "el borde debe cambiar al enfocar",
    })
    .not.toBe(antes);

  await expect
    .poll(() => clave.evaluate((el) => getComputedStyle(el).boxShadow), {
      message: "el campo enfocado debe llevar ademas un halo",
    })
    .not.toBe("none");
});

test("un error no mueve el boton de sitio", async ({ page }) => {
  await page.goto("/login");
  const boton = page.getByRole("button", { name: "Entrar" });

  // Se mide `offsetTop`, no `getBoundingClientRect`. El rectangulo dibujado se mueve con el
  // desplazamiento de la pagina, y al fallar el envio el foco salta al aviso y el navegador
  // desplaza unos pixeles para dejarlo a la vista, cosa correcta. `offsetTop` es posicion de
  // maquetacion pura, que es lo unico que esta prueba quiere vigilar.
  const posicion = () =>
    boton.evaluate((el) => {
      let y = 0;
      let nodo: HTMLElement | null = el as HTMLElement;
      while (nodo !== null && nodo.tagName !== "MAIN") {
        y += nodo.offsetTop;
        nodo = nodo.offsetParent as HTMLElement | null;
      }
      return y;
    });

  const antes = await posicion();

  // Envio con los dos campos vacios: falla la validacion del cliente y aparece el aviso.
  await boton.click();
  await expect(page.getByText(/faltan datos/i)).toBeVisible();

  expect(await posicion(), "el boton se ha desplazado al aparecer el error").toBe(antes);
});

test("credenciales validas llevan al panel del rol", async ({ page }) => {
  await page.goto("/login");
  await page.locator("#acceso-correo").fill(usuario.correo);
  await page.locator("#acceso-clave").fill(usuario.password);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page).toHaveURL(/\/panel$/);
  await expect(page.getByRole("heading", { name: /panel del administrador/i })).toBeVisible();
  // En un aparato compartido, cerrar sesion tiene que estar siempre a la vista.
  await expect(page.getByRole("button", { name: /cerrar sesión/i })).toBeVisible();
  await sinDesplazamientoHorizontal(page);

  await page.screenshot({ path: "e2e/capturas/panel-escritorio.png", fullPage: true });

  await page.setViewportSize(MOVIL);
  await sinDesplazamientoHorizontal(page);
  await page.screenshot({ path: "e2e/capturas/panel-movil.png", fullPage: true });
});

test("credenciales invalidas dejan constancia y no revelan si el correo existe", async ({
  page,
}) => {
  await page.goto("/login");
  await page.locator("#acceso-correo").fill("nadie@example.com");
  await page.locator("#acceso-clave").fill("una-clave-cualquiera");
  await page.getByRole("button", { name: "Entrar" }).click();

  // Se acota a `main`: Next monta su propio `role="alert"` para anunciar los cambios de ruta, y sin
  // acotar el selector encuentra dos.
  const aviso = page.getByRole("main").getByRole("alert");
  await expect(aviso).toContainText(/correo o contraseña incorrectos/i);
  // El mensaje no debe decir cual de los dos fallo.
  await expect(aviso).not.toContainText(/no existe|no registrado|contraseña incorrecta$/i);
  await expect(page).toHaveURL(/\/login$/);
});
