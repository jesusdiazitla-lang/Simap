# Grafo de dependencias - Frontend (Next.js)

> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.

```mermaid
graph LR
  subgraph app[app]
    src_app_layout_tsx["app/layout.tsx"]
    src_app_globals_css["app/globals.css"]
    src_app_login_page_tsx["app/login/page.tsx"]
    src_app_operador_clave_page_tsx["app/operador/clave/page.tsx"]
    src_app_operador_login_page_tsx["app/operador/login/page.tsx"]
    src_app_operador_page_tsx["app/operador/page.tsx"]
    src_app_page_tsx["app/page.tsx"]
    src_app_panel_clave_page_tsx["app/panel/clave/page.tsx"]
    src_app_panel_page_tsx["app/panel/page.tsx"]
  end
  subgraph components[components]
    src_components_registro_sw_tsx["components/registro-sw.tsx"]
    src_components_boton_tsx["components/boton.tsx"]
    src_components_campo_tsx["components/campo.tsx"]
    src_components_marco_tsx["components/marco.tsx"]
    src_components_formulario_clave_tsx["components/formulario-clave.tsx"]
  end
  subgraph lib[lib]
    src_lib_api_ts["lib/api.ts"]
    src_lib_auth_ts["lib/auth.ts"]
    src_lib_operador_ts["lib/operador.ts"]
  end
  subgraph src[src]
    src_proxy_ts["proxy.ts"]
  end
  src_app_layout_tsx --> src_app_globals_css
  src_app_layout_tsx --> src_components_registro_sw_tsx
  src_app_login_page_tsx --> src_components_boton_tsx
  src_app_login_page_tsx --> src_components_campo_tsx
  src_app_login_page_tsx --> src_components_marco_tsx
  src_app_login_page_tsx --> src_lib_api_ts
  src_app_login_page_tsx --> src_lib_auth_ts
  src_lib_auth_ts --> src_lib_api_ts
  src_app_operador_clave_page_tsx --> src_components_formulario_clave_tsx
  src_app_operador_clave_page_tsx --> src_components_marco_tsx
  src_app_operador_clave_page_tsx --> src_lib_operador_ts
  src_components_formulario_clave_tsx --> src_components_boton_tsx
  src_components_formulario_clave_tsx --> src_components_campo_tsx
  src_components_formulario_clave_tsx --> src_lib_api_ts
  src_lib_operador_ts --> src_lib_api_ts
  src_app_operador_login_page_tsx --> src_components_boton_tsx
  src_app_operador_login_page_tsx --> src_components_campo_tsx
  src_app_operador_login_page_tsx --> src_components_marco_tsx
  src_app_operador_login_page_tsx --> src_lib_api_ts
  src_app_operador_login_page_tsx --> src_lib_operador_ts
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
  src_app_panel_page_tsx --> src_components_boton_tsx
  src_app_panel_page_tsx --> src_components_marco_tsx
  src_app_panel_page_tsx --> src_lib_auth_ts
```
