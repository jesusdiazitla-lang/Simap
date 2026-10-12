# Grafo de dependencias - Backend (FastAPI)

> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.

```mermaid
graph LR
  subgraph api[api]
    app_api["api"]
    app_api_v1["api.v1"]
    app_api_v1_comun["api.v1.comun"]
    app_api_v1_router["api.v1.router"]
    app_api_v1_routes["api.v1.routes"]
    app_api_v1_routes_activos["api.v1.routes.activos"]
    app_api_v1_routes_alertas["api.v1.routes.alertas"]
    app_api_v1_routes_auth["api.v1.routes.auth"]
    app_api_v1_routes_campo["api.v1.routes.campo"]
    app_api_v1_routes_componentes["api.v1.routes.componentes"]
    app_api_v1_routes_health["api.v1.routes.health"]
    app_api_v1_routes_lecturas["api.v1.routes.lecturas"]
    app_api_v1_routes_operador["api.v1.routes.operador"]
    app_api_v1_routes_usuarios["api.v1.routes.usuarios"]
  end
  subgraph app[app]
    app["app"]
  end
  subgraph cli[cli]
    app_cli["cli"]
  end
  subgraph core[core]
    app_core["core"]
    app_core_almacen["core.almacen"]
    app_core_auth["core.auth"]
    app_core_config["core.config"]
    app_core_cursor["core.cursor"]
    app_core_rbac["core.rbac"]
    app_core_registro["core.registro"]
    app_core_security["core.security"]
  end
  subgraph db[db]
    app_db["db"]
    app_db_deps["db.deps"]
    app_db_session["db.session"]
    app_db_tenant["db.tenant"]
  end
  subgraph jobs[jobs]
    app_jobs["jobs"]
  end
  subgraph main[main]
    app_main["main"]
  end
  subgraph models[models]
    app_models["models"]
    app_models_activo["models.activo"]
    app_models_alerta["models.alerta"]
    app_models_base["models.base"]
    app_models_componente["models.componente"]
    app_models_empresa["models.empresa"]
    app_models_lectura_horometro["models.lectura_horometro"]
    app_models_operador["models.operador"]
    app_models_usuario["models.usuario"]
  end
  subgraph schemas[schemas]
    app_schemas["schemas"]
    app_schemas_activo["schemas.activo"]
    app_schemas_auth["schemas.auth"]
    app_schemas_campo["schemas.campo"]
    app_schemas_health["schemas.health"]
    app_schemas_operador["schemas.operador"]
    app_schemas_usuario["schemas.usuario"]
  end
  subgraph services[services]
    app_services["services"]
    app_services_activos["services.activos"]
    app_services_alertas["services.alertas"]
    app_services_auth["services.auth"]
    app_services_campo["services.campo"]
    app_services_capturas["services.capturas"]
    app_services_componentes["services.componentes"]
    app_services_lecturas["services.lecturas"]
    app_services_limites["services.limites"]
    app_services_operador["services.operador"]
    app_services_qr["services.qr"]
    app_services_usuarios["services.usuarios"]
  end
  app_api_v1_comun --> app_core_almacen
  app_api_v1_comun --> app_core_auth
  app_api_v1_comun --> app_core_config
  app_api_v1_comun --> app_core_cursor
  app_api_v1_comun --> app_core_security
  app_api_v1_comun --> app_services_capturas
  app_api_v1_comun --> app_services_limites
  app_api_v1_router --> app_api_v1_routes_activos
  app_api_v1_router --> app_api_v1_routes_alertas
  app_api_v1_router --> app_api_v1_routes_auth
  app_api_v1_router --> app_api_v1_routes_campo
  app_api_v1_router --> app_api_v1_routes_componentes
  app_api_v1_router --> app_api_v1_routes_health
  app_api_v1_router --> app_api_v1_routes_lecturas
  app_api_v1_router --> app_api_v1_routes_operador
  app_api_v1_router --> app_api_v1_routes_usuarios
  app_api_v1_routes_activos --> app_api_v1_comun
  app_api_v1_routes_activos --> app_core_config
  app_api_v1_routes_activos --> app_core_rbac
  app_api_v1_routes_activos --> app_core_security
  app_api_v1_routes_activos --> app_db_deps
  app_api_v1_routes_activos --> app_models_activo
  app_api_v1_routes_activos --> app_schemas_activo
  app_api_v1_routes_activos --> app_services_activos
  app_api_v1_routes_activos --> app_services_qr
  app_api_v1_routes_alertas --> app_api_v1_comun
  app_api_v1_routes_alertas --> app_core_rbac
  app_api_v1_routes_alertas --> app_core_security
  app_api_v1_routes_alertas --> app_db_deps
  app_api_v1_routes_alertas --> app_schemas_activo
  app_api_v1_routes_alertas --> app_schemas_campo
  app_api_v1_routes_alertas --> app_services_alertas
  app_api_v1_routes_alertas --> app_services_capturas
  app_api_v1_routes_auth --> app_core_almacen
  app_api_v1_routes_auth --> app_core_auth
  app_api_v1_routes_auth --> app_core_config
  app_api_v1_routes_auth --> app_db_deps
  app_api_v1_routes_auth --> app_schemas_auth
  app_api_v1_routes_auth --> app_services_auth
  app_api_v1_routes_auth --> app_services_limites
  app_api_v1_routes_campo --> app_api_v1_comun
  app_api_v1_routes_campo --> app_core_rbac
  app_api_v1_routes_campo --> app_core_security
  app_api_v1_routes_campo --> app_db_deps
  app_api_v1_routes_campo --> app_schemas_campo
  app_api_v1_routes_campo --> app_services_campo
  app_api_v1_routes_componentes --> app_api_v1_comun
  app_api_v1_routes_componentes --> app_core_rbac
  app_api_v1_routes_componentes --> app_core_security
  app_api_v1_routes_componentes --> app_db_deps
  app_api_v1_routes_componentes --> app_schemas_activo
  app_api_v1_routes_componentes --> app_services_componentes
  app_api_v1_routes_health --> app_core_config
  app_api_v1_routes_health --> app_schemas_health
  app_api_v1_routes_lecturas --> app_api_v1_comun
  app_api_v1_routes_lecturas --> app_core_rbac
  app_api_v1_routes_lecturas --> app_core_security
  app_api_v1_routes_lecturas --> app_db_deps
  app_api_v1_routes_lecturas --> app_schemas_activo
  app_api_v1_routes_lecturas --> app_schemas_campo
  app_api_v1_routes_lecturas --> app_services_activos
  app_api_v1_routes_lecturas --> app_services_capturas
  app_api_v1_routes_lecturas --> app_services_lecturas
  app_api_v1_routes_operador --> app_core_almacen
  app_api_v1_routes_operador --> app_core_auth
  app_api_v1_routes_operador --> app_core_config
  app_api_v1_routes_operador --> app_db_deps
  app_api_v1_routes_operador --> app_models_empresa
  app_api_v1_routes_operador --> app_schemas_auth
  app_api_v1_routes_operador --> app_schemas_operador
  app_api_v1_routes_operador --> app_services_limites
  app_api_v1_routes_operador --> app_services_operador
  app_api_v1_routes_usuarios --> app_core_rbac
  app_api_v1_routes_usuarios --> app_core_security
  app_api_v1_routes_usuarios --> app_db_deps
  app_api_v1_routes_usuarios --> app_schemas_usuario
  app_api_v1_routes_usuarios --> app_services_usuarios
  app_cli --> app_core_config
  app_cli --> app_core_security
  app_cli --> app_models_operador
  app_cli --> app_schemas_auth
  app_cli --> app_services_auth
  app_core_almacen --> app_core_config
  app_core_auth --> app_core_registro
  app_core_auth --> app_core_security
  app_core_rbac --> app_core_auth
  app_core_rbac --> app_core_security
  app_core_security --> app_core_config
  app_db_deps --> app_core_auth
  app_db_deps --> app_core_security
  app_db_deps --> app_db_session
  app_db_session --> app_core_config
  app_db_session --> app_db_tenant
  app_main --> app_api_v1_router
  app_main --> app_core_config
  app_main --> app_core_cursor
  app_main --> app_core_registro
  app_models --> app_models_activo
  app_models --> app_models_alerta
  app_models --> app_models_base
  app_models --> app_models_componente
  app_models --> app_models_empresa
  app_models --> app_models_lectura_horometro
  app_models --> app_models_operador
  app_models --> app_models_usuario
  app_models_activo --> app_models_base
  app_models_alerta --> app_models_base
  app_models_componente --> app_models_base
  app_models_empresa --> app_models_base
  app_models_lectura_horometro --> app_models_base
  app_models_operador --> app_models_base
  app_models_usuario --> app_core_security
  app_models_usuario --> app_models_base
  app_schemas_activo --> app_core_config
  app_schemas_auth --> app_core_security
  app_schemas_operador --> app_schemas_auth
  app_schemas_usuario --> app_core_security
  app_services_activos --> app_core_cursor
  app_services_activos --> app_models_activo
  app_services_activos --> app_models_lectura_horometro
  app_services_activos --> app_services_qr
  app_services_alertas --> app_core_config
  app_services_alertas --> app_core_cursor
  app_services_alertas --> app_core_registro
  app_services_alertas --> app_models_activo
  app_services_alertas --> app_models_alerta
  app_services_alertas --> app_services_capturas
  app_services_auth --> app_core_almacen
  app_services_auth --> app_core_config
  app_services_auth --> app_core_security
  app_services_auth --> app_db_deps
  app_services_auth --> app_models_empresa
  app_services_auth --> app_models_usuario
  app_services_auth --> app_services_componentes
  app_services_auth --> app_services_limites
  app_services_campo --> app_core_registro
  app_services_campo --> app_schemas_campo
  app_services_campo --> app_services_alertas
  app_services_campo --> app_services_capturas
  app_services_campo --> app_services_lecturas
  app_services_capturas --> app_core_config
  app_services_capturas --> app_models_activo
  app_services_componentes --> app_models_componente
  app_services_lecturas --> app_core_config
  app_services_lecturas --> app_core_cursor
  app_services_lecturas --> app_core_registro
  app_services_lecturas --> app_models_activo
  app_services_lecturas --> app_models_lectura_horometro
  app_services_lecturas --> app_services_capturas
  app_services_limites --> app_core_almacen
  app_services_limites --> app_core_config
  app_services_operador --> app_core_almacen
  app_services_operador --> app_core_security
  app_services_operador --> app_models_activo
  app_services_operador --> app_models_empresa
  app_services_operador --> app_models_operador
  app_services_operador --> app_models_usuario
  app_services_operador --> app_services_componentes
  app_services_operador --> app_services_limites
  app_services_usuarios --> app_core_security
  app_services_usuarios --> app_models_usuario
```
