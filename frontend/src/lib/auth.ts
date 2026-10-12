/**
 * Sesión y navegación por rol.
 *
 * El rol NO se guarda en el navegador ni se deduce de nada que el cliente pueda tocar: se pregunta
 * al servidor con `GET /auth/yo`, que lo lee del JWT firmado. Guardarlo en `localStorage` habría
 * ahorrado una petición al arrancar y habría permitido a cualquiera abrir las herramientas del
 * navegador, cambiarlo por `administrador` y ver el menú de administración. El menú no es el
 * permiso —cada endpoint comprueba el rol en el backend— pero enseñar opciones que no se pueden
 * usar es una mentira de interfaz, y una que invita a buscar el agujero.
 */

import { ErrorApi, llamar } from "@/lib/api";

/** Roles tal como los guarda la base de datos. El orden es de menor a mayor alcance. */
export const ROLES = [
  "operario",
  "supervisor",
  "tecnico_taller",
  "gerente",
  "administrador",
] as const;

export type Rol = (typeof ROLES)[number];

export interface Usuario {
  readonly id: string;
  readonly empresa_id: string;
  readonly nombre: string;
  readonly correo: string;
  readonly rol: Rol;
  readonly creado_en: string;
}

export interface Sesion {
  readonly usuario: Usuario;
  readonly expira_en_segundos: number;
}

const ETIQUETAS: Readonly<Record<Rol, string>> = {
  operario: "Operario",
  supervisor: "Supervisor",
  tecnico_taller: "Técnico de taller",
  gerente: "Gerencia",
  administrador: "Administración",
};

export function etiquetaDeRol(rol: Rol): string {
  return ETIQUETAS[rol];
}

/**
 * Una cosa que un rol puede hacer.
 *
 * `ruta` solo existe cuando la pantalla está construida. Lo que todavía no existe lleva `fase`, y la
 * interfaz lo muestra desactivado diciendo en qué fase llega. Es preferible a esconderlo: quien usa
 * el sistema ve el alcance completo de su rol, y quien lo evalúa ve el avance real sin tener que
 * abrir el plan.
 */
export interface Accion {
  readonly nombre: string;
  readonly descripcion: string;
  readonly ruta?: string;
  readonly fase?: string;
}

/**
 * Qué ve cada rol al entrar. Sale de la tabla de roles y permisos de
 * `docs/contexto/01-especificacion-funcional.md`, sección 4.
 *
 * Es acumulativo a mano y no por herencia a propósito: un supervisor hace lo del operario «más»
 * cosas, pero escribirlo con herencia haría que añadir una acción de operario se la concediera en
 * silencio a cuatro roles más. Aquí cada concesión está escrita.
 */
export const ACCIONES_POR_ROL: Readonly<Record<Rol, readonly Accion[]>> = {
  operario: [
    {
      nombre: "Escanear equipo",
      descripcion: "Abre la ficha del activo con la cámara y su código QR.",
      ruta: "/escanear",
    },
    {
      nombre: "Registrar horómetro",
      descripcion: "Escanea el equipo y anota las horas de operación de la ronda.",
      ruta: "/escanear",
    },
    {
      nombre: "Levantar alerta",
      descripcion: "Escanea el equipo: ruido, vibración, calor, olor o fuga, con una nota.",
      ruta: "/escanear",
    },
  ],
  supervisor: [
    {
      nombre: "Escanear equipo",
      descripcion: "Abre la ficha del activo con la cámara y su código QR.",
      ruta: "/escanear",
    },
    {
      nombre: "Registrar horómetro",
      descripcion: "Escanea el equipo y anota las horas de operación de la ronda.",
      ruta: "/escanear",
    },
    {
      nombre: "Levantar alerta",
      descripcion: "Escanea el equipo: ruido, vibración, calor, olor o fuga, con una nota.",
      ruta: "/escanear",
    },
    {
      nombre: "Reportar falla",
      descripcion: "Abre una orden de trabajo con horómetro, componente y descripción.",
      fase: "F3",
    },
    {
      nombre: "Revisar alertas",
      descripcion: "Alertas pendientes de la planta: revisar o descartar.",
      ruta: "/alertas",
    },
    {
      nombre: "Historial de la planta",
      descripcion: "Fallas y órdenes de los activos a tu cargo.",
      fase: "F3",
    },
  ],
  tecnico_taller: [
    {
      nombre: "Órdenes en taller",
      descripcion: "Actualiza el estado y registra el trabajo realizado.",
      fase: "F3",
    },
    {
      nombre: "Repuestos usados",
      descripcion: "Anota qué se consumió en cada reparación.",
      fase: "F4",
    },
  ],
  gerente: [
    {
      nombre: "Disponibilidad y MTBF",
      descripcion: "Indicadores de la empresa. Solo lectura.",
      fase: "F5",
    },
    {
      nombre: "Activos de mayor riesgo",
      descripcion: "Qué equipos conviene intervenir antes de que fallen.",
      fase: "F4",
    },
    {
      nombre: "Costo de repuestos",
      descripcion: "Lo que se ha gastado en mantenimiento, por periodo.",
      fase: "F5",
    },
  ],
  administrador: [
    {
      nombre: "Personal de la empresa",
      descripcion: "Dar de alta al personal y asignarle su rol.",
      ruta: "/panel/usuarios",
    },
    {
      nombre: "Equipos",
      descripcion: "Ficha técnica, ubicación, criticidad y código QR de cada equipo.",
      ruta: "/activos",
    },
    {
      nombre: "Catálogo de componentes",
      descripcion: "Los componentes sobre los que se calcula el riesgo.",
      ruta: "/componentes",
    },
  ],
};

/** Una página del menú lateral. */
export interface Destino {
  readonly nombre: string;
  readonly ruta: string;
}

/** Áreas de trabajo del menú. La clave elige el icono; el nombre es lo que se lee. */
export type Area = "campo" | "equipos" | "supervision" | "administracion" | "cuenta";

/** Una rama del árbol: un área de trabajo con las páginas que el rol puede abrir en ella. */
export interface Rama {
  readonly area: Area;
  readonly nombre: string;
  readonly hojas: readonly Destino[];
}

const TODOS: readonly Rol[] = ["operario", "supervisor", "tecnico_taller", "gerente", "administrador"];

/**
 * El menú lateral entero, agrupado por lo que se hace y no por cómo se llama cada pantalla: así las
 * órdenes de trabajo (F3) y el riesgo y el inventario (F4) tienen dónde colgar sin reordenar nada.
 *
 * Cada hoja dice qué roles la ven. Solo pantallas que existen y que ese rol puede usar: la API las
 * rechazaría igual, pero un enlace que lleva a «no tienes permiso» es un callejón. Una rama que se
 * queda sin hojas para un rol no se pinta.
 */
const ARBOL: readonly {
  readonly area: Area;
  readonly nombre: string;
  readonly hojas: readonly (Destino & { readonly roles: readonly Rol[] })[];
}[] = [
  {
    area: "campo",
    nombre: "Campo",
    hojas: [
      { nombre: "Escanear equipo", ruta: "/escanear", roles: ["operario", "supervisor", "tecnico_taller"] },
      { nombre: "Mis alertas", ruta: "/alertas", roles: ["operario"] },
    ],
  },
  {
    area: "equipos",
    nombre: "Equipos",
    hojas: [
      { nombre: "Todos los equipos", ruta: "/activos", roles: ["supervisor", "gerente", "administrador"] },
      { nombre: "Nuevo equipo", ruta: "/activos/nuevo", roles: ["administrador"] },
      { nombre: "Componentes", ruta: "/componentes", roles: ["administrador"] },
    ],
  },
  {
    area: "supervision",
    nombre: "Supervisión",
    hojas: [
      { nombre: "Alertas", ruta: "/alertas", roles: ["supervisor", "gerente", "administrador"] },
      // Vive dentro de la pantalla de alertas; el ancla lleva directo a su panel.
      { nombre: "Lecturas por revisar", ruta: "/alertas#lecturas-por-revisar", roles: ["supervisor", "administrador"] },
    ],
  },
  {
    area: "administracion",
    nombre: "Administración",
    hojas: [{ nombre: "Personal", ruta: "/panel/usuarios", roles: ["administrador"] }],
  },
  {
    area: "cuenta",
    nombre: "Mi cuenta",
    hojas: [{ nombre: "Cambiar contraseña", ruta: "/panel/clave", roles: TODOS }],
  },
];

/** Las ramas del menú que ve un rol, cada una solo con sus hojas. */
export function arbolPara(rol: Rol): readonly Rama[] {
  return ARBOL.map((r) => ({
    area: r.area,
    nombre: r.nombre,
    hojas: r.hojas.filter((h) => h.roles.includes(rol)).map(({ nombre, ruta }) => ({ nombre, ruta })),
  })).filter((r) => r.hojas.length > 0);
}

/**
 * Qué hoja corresponde a la página abierta: la de ruta más larga que la contiene, para que en
 * «/activos/nuevo» se marque «Nuevo equipo» y no también «Todos los equipos». Las hojas con ancla
 * no cuentan: comparten página con otra, y marcar las dos diría que hay dos sitios abiertos.
 */
export function hojaActual(destinos: readonly Destino[], ruta: string): string | null {
  let mejor: string | null = null;
  for (const d of destinos) {
    if (d.ruta.includes("#")) continue;
    const coincide = d.ruta === "/panel" ? ruta === "/panel" : ruta === d.ruta || ruta.startsWith(`${d.ruta}/`);
    if (coincide && (mejor === null || d.ruta.length > mejor.length)) mejor = d.ruta;
  }
  return mejor;
}

/**
 * Dónde aterriza cada rol al iniciar sesión.
 *
 * Hoy todos van al mismo panel, que se adapta al rol. Se escribe igualmente como tabla y no como un
 * `return "/panel"` porque el día que un operario deba caer directo en el escáner de QR, el cambio
 * es una línea de esta tabla y no una condición nueva repartida por las pantallas.
 */
const RUTA_INICIAL: Readonly<Record<Rol, string>> = {
  operario: "/panel",
  supervisor: "/panel",
  tecnico_taller: "/panel",
  gerente: "/panel",
  administrador: "/panel",
};

export function rutaInicialPara(rol: Rol): string {
  return RUTA_INICIAL[rol];
}

/** Abre sesión. Las cookies las pone el servidor; aquí no se guarda ningún token. */
export async function entrar(correo: string, password: string): Promise<Sesion> {
  return llamar<Sesion>("/auth/login", {
    method: "POST",
    cuerpo: { correo, password },
    // Un 401 en el login significa «credenciales incorrectas», no «la sesión caducó»: intentar
    // refrescar aquí escondería el error real detrás de un reintento inútil.
    sinRefrescar: true,
  });
}

export async function salir(): Promise<void> {
  await llamar<void>("/auth/logout", { method: "POST", sinRefrescar: true });
}

/**
 * Quién es el usuario de la sesión actual, o `null` si no hay ninguna.
 *
 * Distingue «no hay sesión» (401, que es una respuesta normal) de «el servidor no está» (que hay que
 * contar al usuario, porque la acción no es volver a entrar sino avisar a quien administra).
 */
export async function usuarioActual(signal?: AbortSignal): Promise<Usuario | null> {
  try {
    return await llamar<Usuario>("/auth/yo", { signal });
  } catch (error) {
    if (error instanceof ErrorApi && error.estado === 401) return null;
    throw error;
  }
}

/**
 * Cambia la contraseña de quien tiene la sesión.
 *
 * El servidor responde con cookies nuevas, así que este aparato sigue dentro; los demás dejan de
 * poder renovar su sesión. `sinRefrescar` porque un fallo de la clave actual llega como 400, y
 * cualquier 401 aquí significa que la sesión ya no existe: renovarla para reintentar un cambio de
 * contraseña no tiene sentido.
 */
export async function cambiarClave(actual: string, nueva: string): Promise<void> {
  await llamar<Sesion>("/auth/cambiar-clave", {
    method: "POST",
    cuerpo: { password_actual: actual, password_nueva: nueva },
    sinRefrescar: true,
  });
}
