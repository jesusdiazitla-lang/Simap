/**
 * Credenciales de las cuentas con las que entran las pruebas e2e.
 *
 * Salen SOLO de variables de entorno, nunca de un valor por defecto escrito aquí: el repositorio
 * se sube a GitHub y estas son contraseñas de cuentas reales de la base de desarrollo, incluida la
 * del operador de SIMAP, que es la cuenta con más poder del sistema.
 *
 * Si falta alguna, la prueba falla diciendo cuál, en vez de intentar entrar con una clave vacía y
 * fallar con un «Correo o contraseña incorrectos» que haría buscar el problema en otro sitio.
 */

function requerida(nombre: string): string {
  const valor = process.env[nombre];
  if (valor === undefined || valor === "") {
    throw new Error(
      `Falta la variable de entorno ${nombre}. Ver «Revisión de interfaz automatizada» en README.md.`,
    );
  }
  return valor;
}

export const usuario = {
  get correo(): string {
    return requerida("E2E_CORREO");
  },
  get password(): string {
    return requerida("E2E_PASSWORD");
  },
};

export const operador = {
  get correo(): string {
    return requerida("E2E_OPERADOR_CORREO");
  },
  get password(): string {
    return requerida("E2E_OPERADOR_PASSWORD");
  },
};
