# Grafo de dependencias - Backend (FastAPI)

> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.

```mermaid
graph LR
  subgraph api[api]
    app_api["api"]
    app_api_v1["api.v1"]
    app_api_v1_router["api.v1.router"]
    app_api_v1_routes["api.v1.routes"]
    app_api_v1_routes_auth["api.v1.routes.auth"]
    app_api_v1_routes_health["api.v1.routes.health"]
    app_api_v1_routes_operador["api.v1.routes.operador"]
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
    app_core_rbac["core.rbac"]
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
    app_models_base["models.base"]
    app_models_empresa["models.empresa"]
    app_models_operador["models.operador"]
    app_models_usuario["models.usuario"]
  end
  subgraph schemas[schemas]
    app_schemas["schemas"]
    app_schemas_auth["schemas.auth"]
    app_schemas_health["schemas.health"]
    app_schemas_operador["schemas.operador"]
  end
  subgraph services[services]
    app_services["services"]
    app_services_auth["services.auth"]
    app_services_limites["services.limites"]
    app_services_operador["services.operador"]
  end
  app_api_v1_router --> app_api_v1_routes_auth
  app_api_v1_router --> app_api_v1_routes_health
  app_api_v1_router --> app_api_v1_routes_operador
  app_api_v1_routes_auth --> app_core_almacen
  app_api_v1_routes_auth --> app_core_auth
  app_api_v1_routes_auth --> app_core_config
  app_api_v1_routes_auth --> app_db_deps
  app_api_v1_routes_auth --> app_schemas_auth
  app_api_v1_routes_auth --> app_services_auth
  app_api_v1_routes_auth --> app_services_limites
  app_api_v1_routes_health --> app_core_config
  app_api_v1_routes_health --> app_schemas_health
  app_api_v1_routes_operador --> app_core_almacen
  app_api_v1_routes_operador --> app_core_auth
  app_api_v1_routes_operador --> app_core_config
  app_api_v1_routes_operador --> app_db_deps
  app_api_v1_routes_operador --> app_models_empresa
  app_api_v1_routes_operador --> app_schemas_auth
  app_api_v1_routes_operador --> app_schemas_operador
  app_api_v1_routes_operador --> app_services_limites
  app_api_v1_routes_operador --> app_services_operador
  app_cli --> app_core_config
  app_cli --> app_core_security
  app_cli --> app_models_operador
  app_cli --> app_schemas_auth
  app_cli --> app_services_auth
  app_core_almacen --> app_core_config
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
  app_models --> app_models_base
  app_models --> app_models_empresa
  app_models --> app_models_operador
  app_models --> app_models_usuario
  app_models_empresa --> app_models_base
  app_models_operador --> app_models_base
  app_models_usuario --> app_core_security
  app_models_usuario --> app_models_base
  app_schemas_auth --> app_core_security
  app_schemas_operador --> app_schemas_auth
  app_services_auth --> app_core_almacen
  app_services_auth --> app_core_config
  app_services_auth --> app_core_security
  app_services_auth --> app_db_deps
  app_services_auth --> app_models_empresa
  app_services_auth --> app_models_usuario
  app_services_auth --> app_services_limites
  app_services_limites --> app_core_almacen
  app_services_limites --> app_core_config
  app_services_operador --> app_core_almacen
  app_services_operador --> app_core_security
  app_services_operador --> app_models_empresa
  app_services_operador --> app_models_operador
  app_services_operador --> app_models_usuario
  app_services_operador --> app_services_limites
```
