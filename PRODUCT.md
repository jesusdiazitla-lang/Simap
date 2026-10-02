# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Cinco roles, todos empleados de una empresa industrial cliente. Ninguno es visitante anónimo: se
llega a SIMAP porque alguien de la empresa dio de alta la cuenta.

- **Operario.** Trabaja en la planta, de pie, con guantes, a menudo con una sola mano libre.
  Escanea el QR de un equipo para registrar la lectura del horómetro o levantar una alerta temprana
  (ruido, vibración, calor, olor, fuga). Es quien más veces al día toca el sistema y quien menos
  tiempo tiene.
- **Supervisor.** Lo del operario, más reportar fallas formales, revisar alertas pendientes y ver el
  historial de su planta.
- **Técnico de taller.** Actualiza el estado de una orden de trabajo y registra lo que reparó.
- **Gerente / stakeholder.** Solo lectura: disponibilidad, MTBF, costo de repuestos, activos de
  mayor riesgo.
- **Administrador.** Gestiona usuarios, activos, catálogo de componentes y la configuración de su
  empresa.

El dispositivo se trata **siempre como no confiable**: el mismo teléfono o tableta puede pasar entre
turnos y entre personas. Decisión confirmada por el usuario.

## Users — condiciones físicas

La luz ambiente varía dentro de un mismo turno: sala de máquinas en penumbra, patio a pleno sol,
oficina con fluorescentes. No hay una condición dominante, así que ningún esquema de color único
sirve para todas.

## Product Purpose

Predecir la falla de un equipo industrial **sin sensores**. Los fabricantes restringen el acceso a
la telemetría interna de sus máquinas, e instrumentar con sensores propios no es viable para la
mayoría de las empresas. SIMAP usa las dos únicas señales que cualquier empresa sí tiene: las
**horas de operación del horómetro** y los **reportes del personal de planta**.

Tiene éxito cuando una empresa deja de descubrir sus fallas por avería y empieza a verlas venir: un
activo con fallas frecuentes debe mostrar un riesgo visiblemente mayor antes de detenerse.

## Positioning

El mantenimiento preventivo actúa por calendario, ignorando el estado real del equipo; el correctivo
solo actúa cuando ya se detuvo. SIMAP se sitúa entre los dos y lo hace con datos que la competencia
basada en IoT da por perdidos: ajusta una distribución **Weibull** por componente sobre las horas
entre fallas reales de esa empresa, y corrige el riesgo al alza cuando el personal ha reportado
síntomas recientes. Ningún producto que exija sensores puede atender a este cliente, porque el
cliente no tiene acceso a sus propios sensores.

## Operating Context

- El registro de campo entra por **QR pegado en el equipo**. Escanear abre una vista móvil ligera
  con las acciones permitidas al rol de quien escaneó.
- La planta tiene cobertura irregular: el reporte debe poder crearse sin red y sincronizarse después
  (PWA con cola local).
- El flujo de reporte, desde escanear hasta enviar, **no excede tres pasos** (RNF-03).
- Ciclo de vida de una orden: reportada → en taller → reparada → cerrada. Cada transición queda
  asociada a un responsable distinto (quién reportó, quién reparó, quién autorizó).
- Una tarea diaria recalcula el riesgo y reajusta los parámetros del modelo.

## Capabilities and Constraints

- **Multi-tenant con aislamiento impuesto por la base de datos**, no por el código de la aplicación:
  PostgreSQL Row-Level Security con `FORCE`, políticas por `empresa_id`, y un rol de aplicación que
  no es superusuario ni dueño de las tablas. El `empresa_id` sale siempre del JWT, nunca de un campo
  que el cliente pueda enviar.
- **Portabilidad de motor de base de datos**: requisito del usuario. El motor se cambia modificando
  una sola línea; la estrategia de aislamiento vive detrás de una interfaz (`EstrategiaTenant`) y
  expone si la base la impone de verdad o si es filtrado en la aplicación.
- **Consultas de negocio siempre con el ORM**, no SQL escrito a mano.
- **Modelo de negocio: se cobra por equipo monitoreado.** De ahí se deriva que **el alta de una
  empresa no es autoservicio**: las empresas entran por invitación, y crear un tenant es una
  operación administrativa de quien opera SIMAP, no una ruta pública. Decisión confirmada por el
  usuario.
- La sesión viaja en cookies `httpOnly`, `Secure`, `SameSite`; los tokens nunca llegan al
  JavaScript de la página ni a `localStorage`.
- Contraseñas con Argon2id (64 MiB por hash, deliberadamente caro). Límite de intentos por ventana.
- Vocabulario del dominio, en español y tal como aparece en la base de datos: activo, componente,
  horómetro, alerta, orden de trabajo, repuesto; roles `operario`, `supervisor`, `tecnico_taller`,
  `gerente`, `administrador`.

## Brand Commitments

- El nombre es **SIMAP** (Sistema Inteligente de Mantenimiento Predictivo).
- Toda la interfaz, los mensajes de error y la documentación van en **español**.
- No hay logotipo, tipografía corporativa ni paleta heredada: no existe identidad previa que
  preservar.
- **La interfaz es sobria por decisión del usuario, no expresiva.** SIMAP tiene que poder
  confundirse con un software de mantenimiento industrial (CMMS) al estilo de Fiix, UpKeep o
  Limble: gris neutro, superficies planas, controles con caja visible, densidad alta y un único
  color de acción. Ese es el listón de acabado y el punto de referencia.

  El usuario llegó a esta decisión después de ver construida una primera versión con mundo visual
  propio —la interfaz imitaba una bitácora de mantenimiento en papel, con fondo rayado, margen
  perforado y sello de fecha— y rechazarla: «quiero que se vea más profesional, un layout más
  sobrio, recuerda que esto va para empresas industriales». Aprobar la dirección descrita no fue
  suficiente; lo que rechazó fue el resultado.

  En consecuencia: **nada de fondos con textura, papel, rayado ni metáforas de objetos físicos.**
  Familiaridad por encima de distinción. Cuando una decisión de diseño pueda ir hacia lo expresivo
  o hacia el estándar de la categoría bien ejecutado, va hacia el estándar.

## Evidence on Hand

- Especificación funcional, arquitectura y requerimientos completos en `docs/contexto/01..04*.md`,
  transcritos de los PDF entregados al ITLA. Incluyen RF-01..28, RNF-01..08 y CU-01..06.
- Esquema de base de datos de referencia en `backend/db/schema.sql`; el esquema real lo crean las
  migraciones de Alembic.
- **No hay clientes reales, ni datos de producción, ni casos de éxito, ni precios publicados.** El
  proyecto es académico y no ha operado en ninguna planta. Nada de eso debe inventarse: la carga
  inicial de datos para el modelo está prevista como dataset público o simulado y debe quedar
  marcada como `estimado`.

## Product Principles

1. **El aislamiento se demuestra, no se declara.** Cualquier mecanismo de separación entre empresas
   tiene que fallar una prueba automatizada cuando se rompe. Un aislamiento que solo existe en la
   intención del código no cuenta.
2. **El operario es el usuario más caro de perder.** Es quien alimenta el sistema de datos; si
   reportar le cuesta más que no reportar, el motor de predicción se queda sin insumo y el producto
   entero deja de funcionar.
3. **Sin sensores es una ventaja, no una carencia.** Las decisiones de diseño deben hacer visible
   que el dato humano y el horómetro bastan.
4. **Cada dato del sistema tiene un responsable con nombre.** La trazabilidad de quién reportó,
   reparó y autorizó es parte del producto, no auditoría añadida.
5. **La incertidumbre se muestra, no se esconde.** Un riesgo calculado sobre pocas fallas es un
   riesgo poco fiable, y el usuario tiene que poder notarlo.

## Accessibility & Inclusion

- Uso con guantes y con una sola mano: objetivos táctiles generosos en los caminos de operario.
- La luz ambiente cambia dentro de un mismo turno, así que el esquema claro y el oscuro son ambos de
  primera clase y ambos deben cumplir contraste, no solo uno.
- El color nunca es el único portador de significado: los estados de alerta, riesgo y orden de
  trabajo llevan además texto o icono. Es obligatorio aquí porque el verde operacional y el rojo de
  incidente son justo el par que no distingue un usuario con deuteranopía.
