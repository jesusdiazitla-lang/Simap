/**
 * Fase 4 de punta a punta (07-fase4-prediccion-e-inventario.md, sección 15.2):
 *
 * - Una alerta del sistema se convierte en una orden predictiva, el técnico anota el repuesto y al
 *   autorizar el cierre se descuenta del almacén y la alerta queda resuelta.
 * - Un cierre sin stock suficiente no se hace: la orden sigue en «Reparada» y la pantalla dice qué
 *   falta y cuánto.
 *
 * Cada ejecución prepara su escenario por la API con el administrador de demostración: un componente
 * con vida nominal corta, un equipo con muchas horas, una supervisora, un técnico y un repuesto
 * nuevos. Los nombres siguen los patrones que borra `tools/limpiar_datos_de_prueba.py`.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev` (ver playwright.config.ts).
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
  readonly sufijo: string;
  readonly activo: { id: string; codigo: string; nombre: string };
  readonly componente: { id: string; nombre: string };
  readonly repuesto: { id: string; codigo: string; nombre: string };
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

async function preparar(
  playwright: { request: { newContext: () => Promise<APIRequestContext> } },
  stock: number,
): Promise<Escenario> {
  const admin = await playwright.request.newContext();
  const login = await admin.post(`${API}/auth/login`, {
    data: { correo: usuario.correo, password: usuario.password },
  });
  expect(login.ok(), "el administrador de demostración no puede entrar").toBe(true);
  const sufijo = Date.now().toString(36);

  // Un componente propio con vida nominal corta (60 h). La edad de la pieza se declara en cada prueba.
  const comp = await admin.post(`${API}/componentes`, { data: { nombre: `Rodamiento E2E ${sufijo}` } });
  expect(comp.status()).toBe(201);
  const componente = await comp.json();
  expect((await admin.patch(`${API}/componentes/${componente.id}`, { data: { vida_nominal_horas: 60 } })).ok()).toBe(true);

  const act = await admin.post(`${API}/activos`, {
    data: { nombre: `Bomba E2E ${sufijo}`, ubicacion: "Nave 3", horometro_inicial: 4800 },
  });
  expect(act.status()).toBe(201);
  const activo = await act.json();

  const rep = await admin.post(`${API}/repuestos`, {
    data: { nombre: `Rodamiento de prueba ${sufijo}`, codigo: `E2E-${sufijo}`, stock_inicial: stock, stock_minimo: 0, costo_unitario: "1500.00" },
  });
  expect(rep.status()).toBe(201);
  return {
    sufijo,
    activo,
    componente,
    repuesto: await rep.json(),
    supervisora: await alta(admin, "supervisor", `Supervisora E2E ${sufijo}`, sufijo),
    tecnico: await alta(admin, "tecnico_taller", `Técnico E2E ${sufijo}`, sufijo),
    admin,
  };
}

async function entrar(browser: Browser, correo: string, clave: string, destino: string): Promise<Page> {
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

async function stockDe(admin: APIRequestContext, repuestoId: string): Promise<number> {
  return (await (await admin.get(`${API}/repuestos/${repuestoId}`)).json()).stock_actual;
}

/** El técnico anota un repuesto en la orden: lo busca por código, pone la cantidad y lo añade. */
async function anotarRepuesto(page: Page, codigo: string, cantidad: number): Promise<void> {
  await page.getByPlaceholder(/Nombre o código/).fill(codigo);
  await page.getByRole("button", { name: new RegExp(codigo) }).click();
  await page.getByLabel("Cantidad", { exact: true }).fill(String(cantidad));
  await page.getByRole("button", { name: "Añadir", exact: true }).click();
}

test("test_rf21_alerta_a_orden_predictiva_a_cierre_con_repuesto", async ({ browser, playwright }) => {
  test.setTimeout(90_000);
  const e = await preparar(playwright, 5);
  try {
    // Declarar la edad de la pieza dispara el reajuste y el cálculo en segundo plano. Se instaló a
    // las 4740 h: 60 h de uso sobre una vida nominal de 60 h dan un riesgo de dos tercios a 50 h.
    // (Declararla en 0 h no sirve: una pieza viva a las 4800 h es evidencia de que dura mucho más
    // que 60 h, y el modelo, con razón, baja el riesgo.)
    const edad = await e.admin.put(`${API}/activos/${e.activo.id}/componentes/${e.componente.id}`, {
      data: { horas_instalacion_inicial: 4740 },
    });
    expect(edad.ok()).toBe(true);
    await expect
      .poll(async () => {
        const r = await e.admin.get(`${API}/alertas-sistema?tipo=riesgo&activo_id=${e.activo.id}`);
        return (await r.json()).items.length;
      }, { timeout: 20_000 })
      .toBe(1);

    // 1. La supervisora la ve en la bandeja y la convierte en un cambio planificado.
    const supervisora = await entrar(browser, e.supervisora.correo, e.supervisora.clave, "/alertas-sistema");
    const tarjeta = supervisora.getByRole("listitem").filter({ hasText: e.activo.nombre });
    await expect(tarjeta).toContainText(e.componente.nombre);
    await tarjeta.getByRole("button", { name: "Crear orden predictiva" }).click();
    await supervisora.waitForURL(/\/ordenes\/[0-9a-f-]{36}$/);
    await expect(supervisora.getByText("Cambio planificado", { exact: true })).toBeVisible();
    const ordenId = supervisora.url().split("/").pop()!;

    // 2. El técnico la lleva al taller, anota dos rodamientos y la marca como reparada.
    const tecnico = await entrar(browser, e.tecnico.correo, e.tecnico.clave, `/ordenes/${ordenId}`);
    await tecnico.getByRole("button", { name: "Llevar al taller" }).click();
    await expect(tecnico.getByText("En taller", { exact: true }).first()).toBeVisible();
    await anotarRepuesto(tecnico, e.repuesto.codigo, 2);
    await expect(tecnico.getByText(e.repuesto.nombre).first()).toBeVisible();
    await tecnico.getByLabel("Trabajo realizado").fill("Se cambió el rodamiento antes de que fallara y se engrasó.");
    await tecnico.getByRole("radio", { name: /Reemplazo/ }).check({ force: true });
    await tecnico.getByRole("button", { name: "Marcar como reparada" }).click();
    await expect(tecnico.getByText("Reparada · por autorizar").first()).toBeVisible();
    // Anotar no descuenta: el almacén solo cambia al cerrar.
    expect(await stockDe(e.admin, e.repuesto.id)).toBe(5);

    // 3. La supervisora revisa lo que firma, repuestos incluidos, y autoriza la salida.
    await supervisora.reload();
    await supervisora.getByRole("button", { name: "Revisar y autorizar" }).click();
    const firma = supervisora.getByRole("region", { name: "Lo que vas a firmar" });
    await expect(firma).toContainText(e.repuesto.nombre);
    await supervisora.getByRole("button", { name: "Autorizar y cerrar" }).click();
    await expect(supervisora.getByText("Cerrada", { exact: true }).first()).toBeVisible();
    await supervisora.setViewportSize({ width: 1280, height: 900 });
    await supervisora.screenshot({ path: "e2e/capturas/f4-orden-predictiva-cerrada.png", fullPage: true });

    // El cierre descontó del almacén, dejó el consumo en el libro y resolvió la alerta.
    expect(await stockDe(e.admin, e.repuesto.id)).toBe(3);
    const libro = (await (await e.admin.get(`${API}/repuestos/${e.repuesto.id}/movimientos`)).json()).items;
    expect(libro.some((m: { tipo: string; delta: number }) => m.tipo === "consumo" && m.delta === -2)).toBe(true);
    const resueltas = await e.admin.get(`${API}/alertas-sistema?tipo=riesgo&estado=historial&activo_id=${e.activo.id}`);
    expect((await resueltas.json()).items.map((a: { estado: string }) => a.estado)).toContain("resuelta");
    for (const p of [supervisora, tecnico]) await p.context().close();
  } finally {
    await e.admin.dispose();
  }
});

test("test_rf25_cierre_con_stock_insuficiente_muestra_el_faltante", async ({ browser, playwright }) => {
  test.setTimeout(90_000);
  const e = await preparar(playwright, 1);
  try {
    // La orden llega a «Reparada» por la API con tres unidades anotadas y solo una en el almacén.
    const sup = await playwright.request.newContext();
    expect((await sup.post(`${API}/auth/login`, { data: { correo: e.supervisora.correo, password: e.supervisora.clave } })).ok()).toBe(true);
    const falla = await sup.post(`${API}/activos/${e.activo.id}/fallas`, {
      data: {
        cliente_id: crypto.randomUUID(),
        capturado_en: new Date().toISOString(),
        componente_id: e.componente.id,
        horometro: 4801,
        descripcion: "Ruido metálico en el rodamiento al arrancar",
      },
    });
    expect(falla.ok()).toBe(true);
    const ordenId = (await falla.json()).orden.id;
    const tec = await playwright.request.newContext();
    expect((await tec.post(`${API}/auth/login`, { data: { correo: e.tecnico.correo, password: e.tecnico.clave } })).ok()).toBe(true);
    expect((await tec.post(`${API}/ordenes/${ordenId}/en-taller`, { data: {} })).ok()).toBe(true);
    expect((await tec.put(`${API}/ordenes/${ordenId}/repuestos/${e.repuesto.id}`, { data: { cantidad: 3 } })).ok()).toBe(true);
    expect(
      (await tec.post(`${API}/ordenes/${ordenId}/reparada`, {
        data: { trabajo_realizado: "Se cambió el rodamiento y los dos retenes.", tipo_intervencion: "reemplazo" },
      })).ok(),
    ).toBe(true);

    // La supervisora intenta autorizar: no se cierra y la pantalla dice qué falta.
    const page = await entrar(browser, e.supervisora.correo, e.supervisora.clave, `/ordenes/${ordenId}`);
    await page.getByRole("button", { name: "Revisar y autorizar" }).click();
    await page.getByRole("button", { name: "Autorizar y cerrar" }).click();
    const aviso = page.getByRole("alert").filter({ hasText: "No hay stock para cerrar la orden" });
    await expect(aviso).toBeVisible();
    await expect(aviso).toContainText(e.repuesto.codigo);
    await expect(aviso).toContainText("hay 1, la orden pide 3");
    await page.screenshot({ path: "e2e/capturas/f4-cierre-sin-stock.png", fullPage: true });

    // Nada cambió: la orden sigue en «Reparada» y el almacén conserva su unidad.
    const orden = await (await e.admin.get(`${API}/ordenes/${ordenId}`)).json();
    expect(orden.estado).toBe("reparada");
    expect(await stockDe(e.admin, e.repuesto.id)).toBe(1);
    await page.context().close();
    await sup.dispose();
    await tec.dispose();
  } finally {
    await e.admin.dispose();
  }
});

test("test_10_2_riesgo_sin_conexion_como_ultimo_valor_conocido", async ({ browser, playwright }) => {
  test.setTimeout(90_000);
  const e = await preparar(playwright, 1);
  try {
    expect(
      (await e.admin.put(`${API}/activos/${e.activo.id}/componentes/${e.componente.id}`, {
        data: { horas_instalacion_inicial: 4740 },
      })).ok(),
    ).toBe(true);
    await expect
      .poll(async () => (await (await e.admin.get(`${API}/activos/${e.activo.id}/riesgo`)).json()).componentes?.[0]?.estado_calculo, { timeout: 20_000 })
      .toBe("ok");

    // Con red: la supervisora abre el equipo y ve el riesgo, que queda guardado en el teléfono.
    const page = await entrar(browser, e.supervisora.correo, e.supervisora.clave, `/a/${e.activo.codigo}`);
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller) {
        await new Promise<void>((listo) =>
          navigator.serviceWorker.addEventListener("controllerchange", () => listo(), { once: true }),
        );
      }
    });
    await expect(page.getByText(e.componente.nombre).first()).toBeVisible();
    await page.waitForTimeout(500);

    // Sin red: la ficha guardada y, con ella, el último riesgo conocido, marcado como tal.
    await page.context().setOffline(true);
    await page.reload();
    await expect(page.getByText(/Sin conexión\. Ves los datos guardados/)).toBeVisible();
    await expect(page.getByText(/Último cálculo conocido/)).toBeVisible();
    await expect(page.getByText(e.componente.nombre).first()).toBeVisible();
    await page.screenshot({ path: "e2e/capturas/f4-riesgo-sin-conexion.png", fullPage: true });
    await page.context().setOffline(false);
    await page.context().close();
  } finally {
    await e.admin.dispose();
  }
});
