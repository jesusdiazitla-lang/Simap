# Grafo de dependencias - Frontend (Next.js)

> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.

```mermaid
graph LR
  subgraph app[app]
    src_app_activos__id__editar_page_tsx["app/activos/[id]/editar/page.tsx"]
    src_app_activos__id__etiqueta_page_tsx["app/activos/[id]/etiqueta/page.tsx"]
    src_app_activos_nuevo_page_tsx["app/activos/nuevo/page.tsx"]
    src_app_activos_page_tsx["app/activos/page.tsx"]
    src_app_alertas_page_tsx["app/alertas/page.tsx"]
    src_app_componentes_page_tsx["app/componentes/page.tsx"]
    src_app_equipo_page_tsx["app/equipo/page.tsx"]
    src_app_escanear_page_tsx["app/escanear/page.tsx"]
    src_app_layout_tsx["app/layout.tsx"]
    src_app_globals_css["app/globals.css"]
    src_app_login_page_tsx["app/login/page.tsx"]
    src_app_operador_clave_page_tsx["app/operador/clave/page.tsx"]
    src_app_operador_page_tsx["app/operador/page.tsx"]
    src_app_page_tsx["app/page.tsx"]
    src_app_panel_clave_page_tsx["app/panel/clave/page.tsx"]
    src_app_panel_page_tsx["app/panel/page.tsx"]
    src_app_panel_usuarios_page_tsx["app/panel/usuarios/page.tsx"]
  end
  subgraph components[components]
    src_components_formulario_activo_tsx["components/formulario-activo.tsx"]
    src_components_boton_tsx["components/boton.tsx"]
    src_components_campo_tsx["components/campo.tsx"]
    src_components_marco_tsx["components/marco.tsx"]
    src_components_pantalla_tsx["components/pantalla.tsx"]
    src_components_barra_sesion_tsx["components/barra-sesion.tsx"]
    src_components_indicador_cola_tsx["components/indicador-cola.tsx"]
    src_components_iconos_tsx["components/iconos.tsx"]
    src_components_estado_tsx["components/estado.tsx"]
    src_components_lecturas_por_revisar_tsx["components/lecturas-por-revisar.tsx"]
    src_components_formulario_alerta_tsx["components/formulario-alerta.tsx"]
    src_components_formulario_horometro_tsx["components/formulario-horometro.tsx"]
    src_components_escaner_qr_tsx["components/escaner-qr.tsx"]
    src_components_registro_sw_tsx["components/registro-sw.tsx"]
    src_components_formulario_clave_tsx["components/formulario-clave.tsx"]
  end
  subgraph lib[lib]
    src_lib_activos_ts["lib/activos.ts"]
    src_lib_api_ts["lib/api.ts"]
    src_lib_offline_queue_ts["lib/offline-queue.ts"]
    src_lib_auth_ts["lib/auth.ts"]
    src_lib_campo_ts["lib/campo.ts"]
    src_lib_sesion_ts["lib/sesion.ts"]
    src_lib_formato_ts["lib/formato.ts"]
    src_lib_captura_ts["lib/captura.ts"]
    src_lib_qr_ts["lib/qr.ts"]
    src_lib_acceso_ts["lib/acceso.ts"]
    src_lib_operador_ts["lib/operador.ts"]
    src_lib_usuarios_ts["lib/usuarios.ts"]
  end
  subgraph src[src]
    src_proxy_ts["proxy.ts"]
  end
  src_app_activos__id__editar_page_tsx --> src_components_formulario_activo_tsx
  src_app_activos__id__editar_page_tsx --> src_components_marco_tsx
  src_app_activos__id__editar_page_tsx --> src_components_pantalla_tsx
  src_app_activos__id__editar_page_tsx --> src_lib_activos_ts
  src_app_activos__id__editar_page_tsx --> src_lib_api_ts
  src_components_formulario_activo_tsx --> src_components_boton_tsx
  src_components_formulario_activo_tsx --> src_components_campo_tsx
  src_components_formulario_activo_tsx --> src_lib_activos_ts
  src_components_formulario_activo_tsx --> src_lib_api_ts
  src_lib_activos_ts --> src_lib_api_ts
  src_components_pantalla_tsx --> src_components_barra_sesion_tsx
  src_components_pantalla_tsx --> src_components_boton_tsx
  src_components_pantalla_tsx --> src_components_marco_tsx
  src_components_pantalla_tsx --> src_lib_auth_ts
  src_components_pantalla_tsx --> src_lib_sesion_ts
  src_components_barra_sesion_tsx --> src_components_indicador_cola_tsx
  src_components_barra_sesion_tsx --> src_lib_auth_ts
  src_components_barra_sesion_tsx --> src_lib_sesion_ts
  src_components_indicador_cola_tsx --> src_components_iconos_tsx
  src_components_indicador_cola_tsx --> src_lib_offline_queue_ts
  src_lib_offline_queue_ts --> src_lib_activos_ts
  src_lib_offline_queue_ts --> src_lib_api_ts
  src_lib_offline_queue_ts --> src_lib_auth_ts
  src_lib_offline_queue_ts --> src_lib_campo_ts
  src_lib_auth_ts --> src_lib_api_ts
  src_lib_campo_ts --> src_lib_activos_ts
  src_lib_campo_ts --> src_lib_api_ts
  src_lib_sesion_ts --> src_lib_api_ts
  src_lib_sesion_ts --> src_lib_auth_ts
  src_lib_sesion_ts --> src_lib_offline_queue_ts
  src_app_activos__id__etiqueta_page_tsx --> src_components_boton_tsx
  src_app_activos__id__etiqueta_page_tsx --> src_components_iconos_tsx
  src_app_activos__id__etiqueta_page_tsx --> src_components_marco_tsx
  src_app_activos__id__etiqueta_page_tsx --> src_components_pantalla_tsx
  src_app_activos__id__etiqueta_page_tsx --> src_lib_activos_ts
  src_app_activos_nuevo_page_tsx --> src_components_formulario_activo_tsx
  src_app_activos_nuevo_page_tsx --> src_components_marco_tsx
  src_app_activos_nuevo_page_tsx --> src_components_pantalla_tsx
  src_app_activos_nuevo_page_tsx --> src_lib_activos_ts
  src_app_activos_page_tsx --> src_components_boton_tsx
  src_app_activos_page_tsx --> src_components_campo_tsx
  src_app_activos_page_tsx --> src_components_estado_tsx
  src_app_activos_page_tsx --> src_components_pantalla_tsx
  src_app_activos_page_tsx --> src_lib_activos_ts
  src_app_activos_page_tsx --> src_lib_api_ts
  src_app_activos_page_tsx --> src_lib_auth_ts
  src_app_activos_page_tsx --> src_lib_formato_ts
  src_components_estado_tsx --> src_components_iconos_tsx
  src_app_alertas_page_tsx --> src_components_boton_tsx
  src_app_alertas_page_tsx --> src_components_estado_tsx
  src_app_alertas_page_tsx --> src_components_lecturas_por_revisar_tsx
  src_app_alertas_page_tsx --> src_components_pantalla_tsx
  src_app_alertas_page_tsx --> src_lib_api_ts
  src_app_alertas_page_tsx --> src_lib_auth_ts
  src_app_alertas_page_tsx --> src_lib_campo_ts
  src_app_alertas_page_tsx --> src_lib_formato_ts
  src_components_lecturas_por_revisar_tsx --> src_components_boton_tsx
  src_components_lecturas_por_revisar_tsx --> src_components_estado_tsx
  src_components_lecturas_por_revisar_tsx --> src_components_marco_tsx
  src_components_lecturas_por_revisar_tsx --> src_lib_api_ts
  src_components_lecturas_por_revisar_tsx --> src_lib_campo_ts
  src_components_lecturas_por_revisar_tsx --> src_lib_formato_ts
  src_app_componentes_page_tsx --> src_components_boton_tsx
  src_app_componentes_page_tsx --> src_components_campo_tsx
  src_app_componentes_page_tsx --> src_components_estado_tsx
  src_app_componentes_page_tsx --> src_components_marco_tsx
  src_app_componentes_page_tsx --> src_components_pantalla_tsx
  src_app_componentes_page_tsx --> src_lib_activos_ts
  src_app_componentes_page_tsx --> src_lib_api_ts
  src_app_equipo_page_tsx --> src_components_boton_tsx
  src_app_equipo_page_tsx --> src_components_estado_tsx
  src_app_equipo_page_tsx --> src_components_formulario_alerta_tsx
  src_app_equipo_page_tsx --> src_components_formulario_horometro_tsx
  src_app_equipo_page_tsx --> src_components_iconos_tsx
  src_app_equipo_page_tsx --> src_components_marco_tsx
  src_app_equipo_page_tsx --> src_components_pantalla_tsx
  src_app_equipo_page_tsx --> src_lib_activos_ts
  src_app_equipo_page_tsx --> src_lib_api_ts
  src_app_equipo_page_tsx --> src_lib_auth_ts
  src_app_equipo_page_tsx --> src_lib_campo_ts
  src_app_equipo_page_tsx --> src_lib_formato_ts
  src_app_equipo_page_tsx --> src_lib_offline_queue_ts
  src_app_equipo_page_tsx --> src_lib_qr_ts
  src_components_formulario_alerta_tsx --> src_components_boton_tsx
  src_components_formulario_alerta_tsx --> src_components_formulario_horometro_tsx
  src_components_formulario_alerta_tsx --> src_components_iconos_tsx
  src_components_formulario_alerta_tsx --> src_lib_activos_ts
  src_components_formulario_alerta_tsx --> src_lib_api_ts
  src_components_formulario_alerta_tsx --> src_lib_auth_ts
  src_components_formulario_alerta_tsx --> src_lib_campo_ts
  src_components_formulario_alerta_tsx --> src_lib_captura_ts
  src_components_formulario_alerta_tsx --> src_lib_formato_ts
  src_components_formulario_horometro_tsx --> src_components_boton_tsx
  src_components_formulario_horometro_tsx --> src_components_campo_tsx
  src_components_formulario_horometro_tsx --> src_components_iconos_tsx
  src_components_formulario_horometro_tsx --> src_lib_activos_ts
  src_components_formulario_horometro_tsx --> src_lib_api_ts
  src_components_formulario_horometro_tsx --> src_lib_auth_ts
  src_components_formulario_horometro_tsx --> src_lib_campo_ts
  src_components_formulario_horometro_tsx --> src_lib_captura_ts
  src_components_formulario_horometro_tsx --> src_lib_formato_ts
  src_lib_captura_ts --> src_lib_activos_ts
  src_lib_captura_ts --> src_lib_api_ts
  src_lib_captura_ts --> src_lib_auth_ts
  src_lib_captura_ts --> src_lib_campo_ts
  src_lib_captura_ts --> src_lib_offline_queue_ts
  src_app_escanear_page_tsx --> src_components_boton_tsx
  src_app_escanear_page_tsx --> src_components_campo_tsx
  src_app_escanear_page_tsx --> src_components_escaner_qr_tsx
  src_app_escanear_page_tsx --> src_components_marco_tsx
  src_app_escanear_page_tsx --> src_components_pantalla_tsx
  src_app_escanear_page_tsx --> src_lib_qr_ts
  src_components_escaner_qr_tsx --> src_components_boton_tsx
  src_components_escaner_qr_tsx --> src_components_iconos_tsx
  src_components_escaner_qr_tsx --> src_lib_qr_ts
  src_app_layout_tsx --> src_app_globals_css
  src_app_layout_tsx --> src_components_registro_sw_tsx
  src_app_login_page_tsx --> src_components_boton_tsx
  src_app_login_page_tsx --> src_components_campo_tsx
  src_app_login_page_tsx --> src_components_marco_tsx
  src_app_login_page_tsx --> src_lib_acceso_ts
  src_app_login_page_tsx --> src_lib_api_ts
  src_app_login_page_tsx --> src_lib_auth_ts
  src_app_login_page_tsx --> src_lib_qr_ts
  src_lib_acceso_ts --> src_lib_api_ts
  src_lib_acceso_ts --> src_lib_auth_ts
  src_lib_acceso_ts --> src_lib_operador_ts
  src_lib_operador_ts --> src_lib_api_ts
  src_app_operador_clave_page_tsx --> src_components_formulario_clave_tsx
  src_app_operador_clave_page_tsx --> src_components_marco_tsx
  src_app_operador_clave_page_tsx --> src_lib_operador_ts
  src_components_formulario_clave_tsx --> src_components_boton_tsx
  src_components_formulario_clave_tsx --> src_components_campo_tsx
  src_components_formulario_clave_tsx --> src_lib_api_ts
  src_app_operador_page_tsx --> src_components_boton_tsx
  src_app_operador_page_tsx --> src_components_campo_tsx
  src_app_operador_page_tsx --> src_components_marco_tsx
  src_app_operador_page_tsx --> src_lib_api_ts
  src_app_operador_page_tsx --> src_lib_operador_ts
  src_app_page_tsx --> src_components_marco_tsx
  src_app_page_tsx --> src_lib_auth_ts
  src_app_panel_clave_page_tsx --> src_components_formulario_clave_tsx
  src_app_panel_clave_page_tsx --> src_components_marco_tsx
  src_app_panel_clave_page_tsx --> src_lib_auth_ts
  src_app_panel_page_tsx --> src_components_marco_tsx
  src_app_panel_page_tsx --> src_components_pantalla_tsx
  src_app_panel_page_tsx --> src_lib_auth_ts
  src_app_panel_usuarios_page_tsx --> src_components_boton_tsx
  src_app_panel_usuarios_page_tsx --> src_components_campo_tsx
  src_app_panel_usuarios_page_tsx --> src_components_estado_tsx
  src_app_panel_usuarios_page_tsx --> src_components_marco_tsx
  src_app_panel_usuarios_page_tsx --> src_components_pantalla_tsx
  src_app_panel_usuarios_page_tsx --> src_lib_api_ts
  src_app_panel_usuarios_page_tsx --> src_lib_auth_ts
  src_app_panel_usuarios_page_tsx --> src_lib_formato_ts
  src_app_panel_usuarios_page_tsx --> src_lib_usuarios_ts
  src_lib_usuarios_ts --> src_lib_api_ts
  src_lib_usuarios_ts --> src_lib_auth_ts
```
