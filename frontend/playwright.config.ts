import { defineConfig, devices } from "@playwright/test";

// Credenciales de las cuentas de prueba (ver e2e/credenciales.ts). Viven en `.env.e2e`, que el
// `.gitignore` excluye por el patrón `.env*`: son contraseñas reales de la base de desarrollo y no
// deben llegar al repositorio. Si el archivo no existe se usan las variables de entorno sin más.
try {
  process.loadEnvFile(".env.e2e");
} catch {
  // Sin archivo: CI o quien prefiera exportar las variables a mano.
}

/**
 * Pruebas de extremo a extremo de SIMAP.
 *
 * No arrancan los servidores: se ejecutan contra un entorno ya levantado. Arrancarlos desde aquí
 * escondería que estas pruebas necesitan **la API y la base de datos reales**, que es justo lo que
 * las hace valer: comprueban la sesión de verdad, no una simulación.
 *
 * SE EJECUTAN CONTRA LA COMPILACIÓN, NO CONTRA `next dev`
 * -------------------------------------------------------
 *     npm run build && npx next start --port 3000
 *
 * Contra el servidor de desarrollo fallaban dos o tres pruebas distintas en cada ejecución, y no
 * por el código: `next dev` compila cada ruta la primera vez que se pide —en esta máquina además
 * con el compilador WASM, porque el binario nativo de SWC está corrupto— y llegó a devolver 500 con
 * un manifiesto JSON truncado. Una prueba que unas veces pasa y otras no es peor que no tenerla,
 * porque enseña a ignorar los fallos. Contra la compilación, las nueve pasan en catorce segundos.
 *
 * Por eso tampoco están todavía en el pipeline de CI. Entran en F5, junto al resto de pruebas de
 * flujo, cuando el `docker compose` completo corra allí. Mientras tanto se usan a mano para revisar
 * la interfaz, que es de donde salieron.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  // Un solo trabajador: todas las pruebas comparten el mismo backend y las mismas cuentas de
  // demostración, y algunas cambian su contraseña y la devuelven. En paralelo, otro archivo
  // intentaba entrar con la clave de Ana justo mientras estaba cambiada, y fallaba por azar.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    locale: "es-DO",
    timezoneId: "America/Santo_Domingo",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
